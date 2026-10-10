"""Docker Validation Agent : verifie que la configuration Docker produite par le
Dockerization Agent fonctionne reellement, sans IA (verifications deterministes) :

1. fichiers presents (Dockerfile, docker-compose.yml)
   + le Dockerfile n'execute pas l'application en root (instruction USER)
2. `docker compose config` : le YAML est valide
   + ports publies libres sur la machine (sinon erreur d'environnement,
   non transmise a Claude : la configuration n'est pas en cause)
3. `docker compose build` : les images se construisent
4. `docker compose up -d` : les conteneurs demarrent
5. les services "app" (backend) et "frontend" repondent en HTTP
6. `docker compose down -v` : nettoyage systematique, meme en cas d'echec

Les erreurs (avec les logs des conteneurs) sont renvoyees a l'orchestrateur,
qui les transmet au Dockerization Agent pour correction (boucle de correction).

Si Docker n'est pas joignable (ex : pipeline lance dans un conteneur sans le
socket Docker monte), la validation n'est pas effectuee : docker_disponible=False.
"""
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import requests

from src.common.schemas import RapportValidationDocker, EtapeValidationDocker

NOM_PROJET = "autodev-validation"
SERVICES_HTTP = ["app", "frontend"]

BUILD_TIMEOUT = int(os.environ.get("DOCKER_BUILD_TIMEOUT", 900))
DEMARRAGE_TIMEOUT = int(os.environ.get("DOCKER_DEMARRAGE_TIMEOUT", 120))
# Hote ou joindre les ports publies : "localhost" en local, "host.docker.internal"
# si le pipeline tourne lui-meme dans un conteneur.
HOTE_VALIDATION = os.environ.get("DOCKER_VALIDATION_HOST", "localhost")


def _commande_compose() -> list[str] | None:
    """Retourne la commande Compose disponible (`docker compose` ou `docker-compose`),
    ou None si Docker n'est pas joignable."""
    docker_bin = shutil.which("docker")
    if docker_bin:
        if subprocess.run([docker_bin, "info"], capture_output=True).returncode != 0:
            return None
        if subprocess.run([docker_bin, "compose", "version"], capture_output=True).returncode == 0:
            return [docker_bin, "compose"]
    compose_bin = shutil.which("docker-compose")
    return [compose_bin] if compose_bin else None


def _executer(compose: list[str], args: list[str], dossier: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        compose + ["-p", NOM_PROJET] + args,
        cwd=dossier, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )


def _ports_publies(config: dict, service: str) -> list[int]:
    ports = config.get("services", {}).get(service, {}).get("ports", [])
    return [int(p["published"]) for p in ports if isinstance(p, dict) and p.get("published")]


def _port_occupe(port: int) -> bool:
    try:
        with socket.create_connection((HOTE_VALIDATION, port), timeout=1):
            return True
    except OSError:
        return False


def _attendre_reponse_http(url: str, timeout: int) -> str | None:
    """Interroge url jusqu'a obtenir une reponse HTTP < 500. Retourne None si OK,
    sinon le dernier probleme rencontre."""
    limite = time.monotonic() + timeout
    probleme = "aucune reponse"
    while time.monotonic() < limite:
        try:
            reponse = requests.get(url, timeout=5)
            if reponse.status_code < 500:
                return None
            probleme = f"code HTTP {reponse.status_code}"
        except requests.RequestException as e:
            probleme = str(e)
        time.sleep(3)
    return probleme


UTILISATEURS_ROOT = {"root", "0", "0:0", "root:root"}


def utilisateur_final(dockerfile: str) -> str | None:
    """Utilisateur qui execute l'application : derniere instruction USER apres le
    dernier FROM du Dockerfile. None s'il n'y en a pas (donc root par defaut)."""
    utilisateur = None
    for ligne in dockerfile.splitlines():
        mots = ligne.strip().split()
        if not mots:
            continue
        instruction = mots[0].upper()
        if instruction == "FROM":
            utilisateur = None
        elif instruction == "USER" and len(mots) > 1:
            utilisateur = mots[1]
    return utilisateur


def valider_dockerisation(dossier: str = "output") -> RapportValidationDocker:
    compose = _commande_compose()
    if compose is None:
        return RapportValidationDocker(
            docker_disponible=False, succes=False,
            erreurs=["Docker n'est pas joignable : validation non effectuee."],
        )

    etapes: list[EtapeValidationDocker] = []
    erreurs: list[str] = []

    def echec(nom: str, details: str, environnement: bool = False) -> RapportValidationDocker:
        etapes.append(EtapeValidationDocker(nom=nom, succes=False, details=details[-2000:]))
        erreurs.append(f"{nom} : {details[-2000:]}")
        return RapportValidationDocker(
            docker_disponible=True, etapes=etapes, succes=False, erreurs=erreurs,
            erreur_environnement=environnement,
        )

    manquants = [f for f in ("Dockerfile", "docker-compose.yml") if not (Path(dossier) / f).exists()]
    if manquants:
        return echec("fichiers", f"fichiers manquants dans {dossier}/ : {', '.join(manquants)}")
    etapes.append(EtapeValidationDocker(nom="fichiers", succes=True))

    utilisateur = utilisateur_final(
        (Path(dossier) / "Dockerfile").read_text(encoding="utf-8", errors="replace"))
    if utilisateur is None or utilisateur in UTILISATEURS_ROOT:
        return echec(
            "non-root",
            "le Dockerfile execute l'application en root. Creer un utilisateur non privilegie "
            "(ex : RUN useradd -m app) et ajouter `USER app` apres le dernier FROM.",
        )
    etapes.append(EtapeValidationDocker(nom="non-root", succes=True, details=f"USER {utilisateur}"))

    resultat = _executer(compose, ["config", "--format", "json"], dossier, 60)
    if resultat.returncode != 0:
        return echec("config", resultat.stderr)
    config = json.loads(resultat.stdout)
    services_absents = [s for s in SERVICES_HTTP if s not in config.get("services", {})]
    if services_absents:
        return echec("config", f"services absents de docker-compose.yml : {', '.join(services_absents)}")
    etapes.append(EtapeValidationDocker(nom="config", succes=True))

    ports_occupes = [
        port for service in config.get("services", {})
        for port in _ports_publies(config, service) if _port_occupe(port)
    ]
    if ports_occupes:
        return echec(
            "ports",
            f"port(s) deja occupe(s) sur la machine : {', '.join(map(str, ports_occupes))}. "
            "Arreter l'application qui les utilise (ex : `docker compose down` dans output/) "
            "puis relancer.",
            environnement=True,
        )
    etapes.append(EtapeValidationDocker(nom="ports", succes=True))

    try:
        resultat = _executer(compose, ["build"], dossier, BUILD_TIMEOUT)
        if resultat.returncode != 0:
            return echec("build", resultat.stdout + resultat.stderr)
        etapes.append(EtapeValidationDocker(nom="build", succes=True))

        resultat = _executer(compose, ["up", "-d"], dossier, DEMARRAGE_TIMEOUT)
        if resultat.returncode != 0:
            return echec("demarrage", resultat.stdout + resultat.stderr)
        etapes.append(EtapeValidationDocker(nom="demarrage", succes=True))

        for service in SERVICES_HTTP:
            ports = _ports_publies(config, service)
            if not ports:
                return echec(f"service {service}", "aucun port publie dans docker-compose.yml")
            url = f"http://{HOTE_VALIDATION}:{ports[0]}/"
            probleme = _attendre_reponse_http(url, DEMARRAGE_TIMEOUT)
            if probleme:
                logs = _executer(compose, ["logs", "--tail", "50", service], dossier, 60).stdout
                return echec(f"service {service}", f"{url} ne repond pas ({probleme}).\nLogs :\n{logs}")
            etapes.append(EtapeValidationDocker(nom=f"service {service}", succes=True, details=url))
    except subprocess.TimeoutExpired as e:
        return echec("timeout", f"commande trop longue : {' '.join(e.cmd)}")
    finally:
        _executer(compose, ["down", "-v", "--remove-orphans"], dossier, 120)

    return RapportValidationDocker(docker_disponible=True, etapes=etapes, succes=True)
