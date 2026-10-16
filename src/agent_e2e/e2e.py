"""Agent E2E (etape 2 : API + navigateur, rapport seulement) : teste l'application
generee de bout en bout, comme un vrai utilisateur.

Deux parties, comme le Test Agent et le QA :

1. generer_tests_e2e() — l'IA (Claude Code) lit le code genere et ecrit des
   scenarios dans <output>/e2e/ :
   - test_api_e2e.py : parcours complets sur la vraie API (httpx), vraie base PostgreSQL ;
   - test_interface_e2e.py : parcours dans un vrai navigateur Chromium (Playwright).
   Le fichier conftest.py (fixtures) est ecrit par AutoDev, pas par l'IA.

2. executer_tests_e2e() — sans IA : AutoDev demarre l'application avec Docker
   Compose, lance les scenarios avec pytest, puis arrete et nettoie tout
   (`down -v`).

Quand AutoDev tourne lui-meme dans un conteneur, l'application est joignable sur
host.docker.internal, mais le frontend genere appelle l'API sur localhost : un
relais TCP rend les ports de l'application joignables sur localhost dans le
conteneur AutoDev, pour que le navigateur se comporte comme celui d'un utilisateur.

Le resultat est un rapport : il ne bloque pas le run et ne declenche pas de
correction (ce sera l'etape 3).
"""
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

from src.agent_validation_docker import validation_docker as vd
from src.common.schemas import SortiePO, SortieAgentE2E, ScenarioE2E, RapportE2E, EchecE2E

CLAUDE_BIN = shutil.which("claude") or "claude"
NOM_PROJET = "autodev-e2e"
E2E_TIMEOUT = int(os.environ.get("E2E_TIMEOUT", 900))
FICHIER_RAPPORT = "rapport_e2e.json"


def dossier_e2e(dossier_docker: str) -> str:
    return str(Path(dossier_docker) / "e2e")


# --- Fichiers ecrits par AutoDev (pas par l'IA) ---

CONFTEST = '''"""Fixtures des tests E2E, ecrites par AutoDev (ne pas modifier)."""
import os
import uuid
from pathlib import Path

import pytest

API_URL = os.environ.get("E2E_API_URL", "http://localhost:8000").rstrip("/")
FRONT_URL = os.environ.get("E2E_FRONT_URL", "http://localhost:8080").rstrip("/")


@pytest.fixture(scope="session")
def api_url():
    """URL de l'API de l'application demarree (ex : http://localhost:8000)."""
    return API_URL


@pytest.fixture(scope="session")
def front_url():
    """URL de l'interface web de l'application demarree (ex : http://localhost:8080)."""
    return FRONT_URL


@pytest.fixture
def nouvel_email():
    """Fabrique une adresse e-mail unique : chaque test cree ses propres comptes."""
    def fabrique(prefixe="e2e"):
        return f"{prefixe}-{uuid.uuid4().hex[:10]}@e2e-autodev.fr"
    return fabrique


@pytest.fixture(scope="session")
def variables_app():
    """Variables du fichier .env de l'application (ex : mot de passe administrateur)."""
    variables = {}
    fichier = Path(os.environ.get("E2E_FICHIER_ENV", ""))
    if fichier.is_file():
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                nom, valeur = ligne.split("=", 1)
                variables[nom.strip()] = valeur.strip().strip('"').strip("'")
    return variables


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Navigateur Playwright : adresse de l'interface par defaut, langue francaise."""
    return {**browser_context_args, "base_url": FRONT_URL, "locale": "fr-FR"}
'''

PYTEST_INI = "[pytest]\naddopts = -p no:cacheprovider\n"


def ecrire_fichiers_autodev(dossier: str) -> None:
    Path(dossier, "conftest.py").write_text(CONFTEST, encoding="utf-8")
    Path(dossier, "pytest.ini").write_text(PYTEST_INI, encoding="utf-8")


def lister_tests_e2e(dossier: str) -> list[str]:
    return sorted(str(f) for f in Path(dossier).glob("test_*.py"))


# --- 1. Ecriture des scenarios par l'IA ---

def _extraire_json(texte: str) -> str:
    bloc = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texte, re.DOTALL)
    if bloc:
        return bloc.group(1)
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        raise ValueError("Agent E2E : aucune liste de scenarios JSON dans la reponse")
    return texte[debut:fin + 1]


def consigne_e2e(user_stories: SortiePO, demande: str, dossier_backend: str, dossier: str,
                 dossier_frontend: str = "output/frontend") -> str:
    return f"""Tu es un testeur de bout en bout (E2E). L'application ci-dessous est deja ecrite. AutoDev va la
demarrer avec Docker (vraie base PostgreSQL) : l'API repond sur l'URL de la fixture `api_url`, l'interface
web sur celle de la fixture `front_url`. Ton travail : ecrire des scenarios qui utilisent l'application
COMME UN VRAI UTILISATEUR, sans aucun mock, pour verifier que chaque user story fonctionne vraiment.

Demande d'origine du client (les regles metier a verifier) :
{demande}

User stories :
{user_stories.model_dump_json(indent=2)}

Code de l'application, a LIRE d'abord :
- backend dans {dossier_backend}/ : routes, schemas, regles metier et README.md (URL exactes, champs JSON,
  codes de reponse, comptes crees au demarrage) ;
- frontend dans {dossier_frontend}/ : pages HTML et JavaScript (champs, boutons, textes affiches, pages).
Le fichier {dossier}/conftest.py est deja ecrit : lis-le. Il fournit les fixtures `api_url`, `front_url`,
`nouvel_email()` (adresse unique), `variables_app` (variables du .env de l'application, par exemple un
mot de passe administrateur) et `page` (navigateur Chromium, fourni par pytest-playwright).

Ecris EXACTEMENT deux fichiers, dans {dossier}/ uniquement :
1. test_api_e2e.py : parcours complets sur l'API avec httpx (`httpx.Client(base_url=api_url)` garde les
   cookies de connexion). Au moins un scenario par user story, et un scenario pour chaque regle metier de
   la demande (l'action interdite doit etre refusee, avec le code de reponse attendu).
2. test_interface_e2e.py : 3 a 6 parcours principaux dans le navigateur avec Playwright
   (`from playwright.sync_api import Page, expect`, fixture `page`) : ouvrir `front_url`, remplir les
   formulaires, cliquer, puis verifier avec `expect(...)` ce qui s'affiche (inscription et connexion,
   l'action principale de l'application, un message d'erreur montre a l'utilisateur). Utilise les
   libelles, roles et textes reellement presents dans les pages (`get_by_label`, `get_by_role`,
   `get_by_text`) plutot que des selecteurs CSS fragiles.

Regles :
- entre 8 et 25 scenarios en tout ;
- chaque test cree ses propres donnees (comptes avec `nouvel_email()`), ne depend d'aucun autre test et
  marche dans n'importe quel ordre ;
- nom de chaque test : `test_E01_...`, `test_E02_...` (numerotation unique sur les deux fichiers) ;
- pas de `time.sleep` de plus d'une seconde : `expect(...)` attend tout seul ;
- chaque assertion a un message clair en francais : ce qui etait attendu et ce qui a ete obtenu
  (par exemple le code HTTP et le debut de la reponse) ;
- ne modifie ni conftest.py ni pytest.ini, n'ecris dans aucun autre dossier, ne modifie pas l'application ;
- n'affiche jamais un mot de passe dans un message ;
- n'execute aucune commande : AutoDev lance les tests lui-meme.

Quand les fichiers sont ecrits, reponds UNIQUEMENT avec ce JSON, sans texte autour :
{{"scenarios": [{{"id": "E01", "type": "api", "user_story": "US1", "description": "..."}}]}}
(type : "api" ou "interface")"""


def generer_tests_e2e(user_stories: SortiePO, demande: str, dossier_backend: str = "output/backend",
                      dossier: str = "output/e2e", dossier_frontend: str = "output/frontend") -> SortieAgentE2E:
    """L'Agent E2E ecrit les scenarios dans dossier (vide au depart)."""
    if Path(dossier).exists():
        shutil.rmtree(dossier)
    Path(dossier).mkdir(parents=True)
    ecrire_fichiers_autodev(dossier)
    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit,Glob,Grep"],
        input=consigne_e2e(user_stories, demande, dossier_backend, dossier, dossier_frontend),
        capture_output=True, text=True, timeout=int(os.environ.get("CLAUDE_TIMEOUT", 1200)),
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Agent E2E a échoué : {resultat.stdout}\n{resultat.stderr}")
    ecrire_fichiers_autodev(dossier)  # au cas ou l'IA les aurait modifies
    fichiers = lister_tests_e2e(dossier)
    if not fichiers:
        raise RuntimeError(f"Agent E2E : aucun fichier test_*.py ecrit dans {dossier}/")
    donnees = json.loads(_extraire_json(resultat.stdout))
    return SortieAgentE2E(scenarios=[ScenarioE2E.model_validate(s) for s in donnees.get("scenarios", [])],
                          fichiers=fichiers)


# --- 2. Execution des scenarios (sans IA) ---

class _Relais(socketserver.ThreadingTCPServer):
    """Relais TCP : 127.0.0.1:port local -> hote:port distant."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port_local: int, hote: str, port_distant: int):
        self.cible = (hote, port_distant)
        super().__init__(("127.0.0.1", port_local), _GestionnaireRelais)


class _GestionnaireRelais(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            distant = socket.create_connection(self.server.cible, timeout=10)
        except OSError:
            return
        distant.settimeout(None)

        def copier(source, destination):
            try:
                while donnees := source.recv(65536):
                    destination.sendall(donnees)
            except OSError:
                pass
            finally:
                for s in (source, destination):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        retour = threading.Thread(target=copier, args=(distant, self.request), daemon=True)
        retour.start()
        copier(self.request, distant)
        retour.join(timeout=5)
        distant.close()


def demarrer_relais(hote: str, ports: list[int]) -> list[_Relais]:
    """Rend hote:port joignable sur localhost:port (inutile si hote est deja localhost)."""
    if hote in ("localhost", "127.0.0.1"):
        return []
    relais = []
    for port in ports:
        serveur = _Relais(port, hote, port)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        relais.append(serveur)
    return relais


def arreter_relais(relais: list[_Relais]) -> None:
    for serveur in relais:
        serveur.shutdown()
        serveur.server_close()


def navigateur_disponible() -> bool:
    """Playwright et son navigateur Chromium sont installes (image AutoDev a jour)."""
    try:
        import pytest_playwright  # noqa: F401
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def _type_du_test(nodeid: str) -> str:
    return "interface" if "test_interface" in nodeid.split("::")[0] else "api"


def _id_du_test(nodeid: str) -> str:
    m = re.search(r"test_(E\d+)", nodeid)
    return m.group(1) if m else nodeid.split("::")[-1]


def lancer_scenarios(fichiers: list[str], dossier: str, api_url: str, fichier_env: str = "",
                     front_url: str = "") -> RapportE2E:
    """Lance les scenarios avec pytest sur l'application deja demarree."""
    if not fichiers:  # sans fichier, pytest lancerait les tests du dossier courant
        raise ValueError("lancer_scenarios : aucun fichier de scenarios")
    rapport_json = Path(dossier) / FICHIER_RAPPORT
    rapport_json.unlink(missing_ok=True)
    env = dict(os.environ, E2E_API_URL=api_url, E2E_FICHIER_ENV=fichier_env, E2E_FRONT_URL=front_url or api_url)
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", *fichiers, "-q", "--rootdir", dossier,
         "-c", str(Path(dossier) / "pytest.ini"), "--json-report", f"--json-report-file={rapport_json}"],
        capture_output=True, text=True, timeout=E2E_TIMEOUT, env=env, encoding="utf-8", errors="replace",
    )
    if not rapport_json.exists():
        return RapportE2E(docker_disponible=True, succes=False, erreurs=[
            "Les scenarios E2E n'ont pas pu etre lances (pas de rapport pytest).\n"
            f"{resultat.stdout[-1500:]}\n{resultat.stderr[-1500:]}"])
    rapport = json.loads(rapport_json.read_text(encoding="utf-8"))
    echecs = []
    for test in rapport.get("tests", []):
        if test["outcome"] in ("failed", "error"):
            etape = next((test.get(p) for p in ("call", "setup", "teardown")
                          if test.get(p, {}).get("outcome") in ("failed", "error")), {}) or {}
            echecs.append(EchecE2E(id=_id_du_test(test["nodeid"]), type=_type_du_test(test["nodeid"]),
                                   test=test["nodeid"], message=str(etape.get("longrepr", ""))[-1500:]))
    for collecte in rapport.get("collectors", []):
        if collecte["outcome"] == "failed":
            echecs.append(EchecE2E(id="collecte", type=_type_du_test(collecte["nodeid"]), test=collecte["nodeid"],
                                   message=str(collecte.get("longrepr", ""))[-1500:]))
    total = rapport["summary"].get("total", 0)
    reussis = rapport["summary"].get("passed", 0)
    erreurs = [f"[E2E {e.type}] {e.id} ({e.test}) : {e.message}" for e in echecs]
    if total == 0 and not echecs:
        erreurs.append("Aucun scenario E2E n'a ete trouve.")
    return RapportE2E(docker_disponible=True, succes=not erreurs, total=total, reussis=reussis,
                      echecs=echecs, erreurs=erreurs)


def executer_tests_e2e(dossier_docker: str = "output", dossier: str | None = None) -> RapportE2E:
    """Demarre l'application, lance les scenarios E2E, puis arrete tout."""
    dossier = dossier or dossier_e2e(dossier_docker)
    compose = vd._commande_compose()
    if compose is None:
        return RapportE2E(docker_disponible=False, succes=False,
                          erreurs=["Docker n'est pas joignable : tests E2E non effectues."])
    navigateur = navigateur_disponible()
    fichiers = [f for f in lister_tests_e2e(dossier) if navigateur or "test_interface" not in Path(f).name]
    remarque = "" if navigateur else ("Navigateur non installe dans l'image AutoDev : seuls les scenarios API "
                                      "sont lances (reconstruire l'image pour les scenarios d'interface).")
    if not fichiers:
        return RapportE2E(docker_disponible=False, succes=False, navigateur=navigateur, remarque=remarque,
                          erreurs=["Aucun scenario E2E a lancer (pas de fichier test_*.py)."])

    def executer(args, timeout):
        return subprocess.run(compose + ["-p", NOM_PROJET] + args, cwd=dossier_docker, capture_output=True,
                              text=True, timeout=timeout, encoding="utf-8", errors="replace")

    def echec(message, environnement=False):
        return RapportE2E(docker_disponible=True, succes=False, erreurs=[message],
                          erreur_environnement=environnement, navigateur=navigateur, remarque=remarque)

    resultat = executer(["config", "--format", "json"], 60)
    if resultat.returncode != 0:
        return echec(f"docker compose config : {resultat.stderr[-1500:]}")
    config = json.loads(resultat.stdout)
    port_api = (vd._ports_publies(config, "app") or [8000])[0]
    port_front = (vd._ports_publies(config, "frontend") or [8080])[0]
    occupes = [p for s in config.get("services", {}) for p in vd._ports_publies(config, s) if vd._port_occupe(p)]
    if occupes:
        return echec(f"port(s) deja occupe(s) sur la machine : {', '.join(map(str, occupes))}. Arreter "
                     "l'application qui les utilise (ex : `docker compose down` dans output/) puis relancer.",
                     environnement=True)
    relais = []
    try:
        resultat = executer(["up", "-d", "--build"], vd.BUILD_TIMEOUT)
        if resultat.returncode != 0:
            return echec(f"demarrage de l'application : {(resultat.stdout + resultat.stderr)[-1500:]}")
        for port in (port_api, port_front):
            probleme = vd._attendre_reponse_http(f"http://{vd.HOTE_VALIDATION}:{port}/", vd.DEMARRAGE_TIMEOUT)
            if probleme:
                return echec(f"l'application ne repond pas sur le port {port} ({probleme}).")
        # Le navigateur et les scenarios utilisent localhost, comme un vrai utilisateur
        relais = demarrer_relais(vd.HOTE_VALIDATION, [port_api, port_front])
        rapport = lancer_scenarios(fichiers, dossier, f"http://localhost:{port_api}",
                                   str(Path(dossier_docker, ".env").resolve()), f"http://localhost:{port_front}")
        if not rapport.succes:
            logs = executer(["logs", "--tail", "40", "app"], 60).stdout
            rapport = rapport.model_copy(update={"erreurs": rapport.erreurs + [f"Logs du backend :\n{logs[-2500:]}"]})
        return rapport.model_copy(update={"navigateur": navigateur, "remarque": remarque})
    except subprocess.TimeoutExpired as e:
        return echec(f"commande trop longue : {' '.join(map(str, e.cmd))}")
    finally:
        arreter_relais(relais)
        executer(["down", "-v", "--remove-orphans"], 120)
