import json
import re
import subprocess
import shutil
from pathlib import Path
from src.common.schemas import SortieDockerization
from src.common.regles import bloc_regles

CLAUDE_BIN = shutil.which("claude") or "claude"


def generer_dockerisation(dossier_backend: str = "output/backend", dossier_frontend: str = "output/frontend", dossier_sortie: str = "output") -> SortieDockerization:
    """Dockerization Agent : se declenche une fois le backend ET le frontend
    valides par leurs QA Agents respectifs (voir agent_orchestrateur/orchestrateur.py).
    Produit une configuration Docker unifiee (Dockerfile + docker-compose.yml)
    dans dossier_sortie ("output/" par defaut) — JAMAIS a la racine du projet
    AutoDev, pour ne pas ecraser son propre docker-compose.yml (celui qui fait
    tourner le pipeline lui-meme).

    La configuration produite est ensuite verifiee par le Docker Validation Agent
    (src/agent_validation_docker), qui renvoie ses erreurs a
    appliquer_corrections_dockerisation() en cas d'echec.
    """
    Path(dossier_sortie).mkdir(parents=True, exist_ok=True)

    prompt = f"""Genere une configuration Docker unifiee pour ce projet, compose de deux parties deja
generees et validees :
- backend FastAPI dans {dossier_backend}
- frontend statique (HTML/CSS/JS) dans {dossier_frontend}

Commence par lire {dossier_backend}/README.md et {dossier_backend}/.env.example : ils
indiquent comment demarrer le backend (migrations ou creation du schema, initialisation,
commande uvicorn) et les variables d'environnement necessaires.

Ecris DANS LE DOSSIER {dossier_sortie}/ (pas ailleurs, surtout pas a la racine du
projet AutoDev qui a deja son propre docker-compose.yml) :
- un Dockerfile pour le backend (image python slim, installe les dependances de
  {dossier_backend}/requirements.txt, expose le port 8000, utilisateur non-root
  pour executer l'application)
- un docker-compose.yml avec 3 services : "app" (le backend, build depuis le
  Dockerfile ci-dessus), "frontend" (image construite depuis {dossier_frontend}/Dockerfile,
  que tu ecris : FROM nginx:alpine puis COPY des fichiers statiques dans /usr/share/nginx/html ;
  dans docker-compose.yml : build avec context ./frontend), et "db"
  (postgres:16, volume nomme pour persister les donnees)
- un fichier .dockerignore adapte

Le DATABASE_URL du service "app" doit utiliser le pilote PostgreSQL installe par
{dossier_backend}/requirements.txt (ne pas en ajouter un autre) :
- psycopg2 ou psycopg2-binary -> postgresql+psycopg2://...
- psycopg (version 3, ex : psycopg[binary]) -> postgresql+psycopg://...
- asyncpg -> postgresql+asyncpg://...

Les services "app" et "frontend" doivent publier leur port sur l'hote (ex : 8000 et
8080) : l'etape suivante (Docker Validation) testera la configuration (build, demarrage,
requetes HTTP).

Aucun mot de passe ni secret en clair dans docker-compose.yml (utilisateur et mot de
passe PostgreSQL, compte administrateur, cle JWT...) : utilise des variables ${{NOM_VARIABLE}}.
Ecris leurs valeurs dans {dossier_sortie}/.env (valeurs aleatoires, au moins 16 caracteres
pour les mots de passe), et les memes noms sans valeur dans {dossier_sortie}/.env.example.
Docker Compose lit {dossier_sortie}/.env automatiquement.
{bloc_regles('dockerization', dossier_frontend=dossier_frontend)}

N'execute aucune commande (pas de docker compose up, pas de docker build) : AutoDev
construit et teste la configuration lui-meme juste apres.

Ecris les fichiers directement sur disque, dans {dossier_sortie}/ uniquement."""

    # Pas de Bash : avec le socket Docker monte, l'agent lancait lui-meme
    # docker compose up, depassait le timeout et laissait des conteneurs (issue #2).
    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit"],
        input=prompt,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Dockerization Agent a échoué : {resultat.stderr}")

    return SortieDockerization(fichiers_generes=_lister_fichiers(dossier_sortie), resume_technique=resultat.stdout[:500])


def _lister_fichiers(dossier_sortie: str) -> list[str]:
    return [
        str(p) for p in Path(dossier_sortie).glob("Dockerfile*")
    ] + [
        str(p) for p in Path(dossier_sortie).glob("docker-compose*.yml")
    ] + [
        str(p) for p in Path(dossier_sortie).glob(".dockerignore")
    ]


def appliquer_corrections_dockerisation(rapport_erreurs: list[str], dossier_sortie: str = "output") -> SortieDockerization:
    prompt = f"""Corrige la configuration Docker dans {dossier_sortie}/ (Dockerfile, docker-compose.yml,
.dockerignore). Elle a echoue a la validation (docker compose config/build/up puis verification
HTTP des services "app" et "frontend"). Garde les noms de services "app", "frontend" et "db".
Ne modifie que les fichiers Docker de {dossier_sortie}/, pas le code du backend ni du frontend.
Garde la premiere ligne « name: ... » du docker-compose.yml, ne mets aucun secret en clair
(variables ${{...}} lues dans {dossier_sortie}/.env) et n'execute aucune commande.
{bloc_regles('dockerization', dossier_frontend=dossier_sortie + '/frontend')}

Erreurs de validation :
{json.dumps(rapport_erreurs, ensure_ascii=False, indent=2)}"""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit"],
        input=prompt,
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Correction Docker échouée : {resultat.stdout}\n{resultat.stderr}")

    return SortieDockerization(fichiers_generes=_lister_fichiers(dossier_sortie), resume_technique=resultat.stdout[:500])


def nommer_projet_compose(dossier_sortie: str, nom: str) -> None:
    """Ecrit "name: <nom>" en tete de docker-compose.yml (issue #1).

    Sans nom, docker compose prend celui du dossier ("output") pour tous les
    projets generes : ils partagent alors le volume de la base, initialise une
    seule fois avec le mot de passe du premier projet. Fait par le code et non
    par le prompt, pour qu'une correction de l'agent ne puisse pas le retirer.
    """
    compose = Path(dossier_sortie) / "docker-compose.yml"
    # Nom de projet Compose : minuscules, chiffres, « - » et « _ », commence par une lettre ou un chiffre.
    nom = re.sub(r"[^a-z0-9_-]+", "-", nom.strip().lower()).strip("-_")
    if not compose.exists() or not nom:
        return
    contenu = re.sub(r"^name\s*:.*\n?", "", compose.read_text(encoding="utf-8"), flags=re.MULTILINE)
    compose.write_text(f"name: {nom}\n{contenu}", encoding="utf-8")
