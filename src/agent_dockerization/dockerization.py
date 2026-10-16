import json
import re
import subprocess
import shutil
from pathlib import Path
from src.common.schemas import SortieDockerization

CLAUDE_BIN = shutil.which("claude") or "claude"
# Fichier ecrit par l'orchestrateur dans output/ : l'ID du run.
FICHIER_ID_RUN = ".id_run"


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
  Dockerfile ci-dessus), "frontend" (sert les fichiers statiques de
  {dossier_frontend}, par exemple via nginx:alpine ou un serveur simple), et "db"
  (postgres:16, volume nomme pour persister les donnees)
- un fichier .dockerignore adapte

Le DATABASE_URL du service "app" doit utiliser le pilote PostgreSQL installe par
{dossier_backend}/requirements.txt (ne pas en ajouter un autre) :
- psycopg2 ou psycopg2-binary -> postgresql+psycopg2://...
- psycopg (version 3, ex : psycopg[binary]) -> postgresql+psycopg://...
- asyncpg -> postgresql+asyncpg://...

Les services "app" et "frontend" doivent publier leur port sur l'hote (ex : 8000 et
8080) : la configuration sera testee automatiquement (build, demarrage, requetes HTTP).

Aucun mot de passe ni secret en clair dans docker-compose.yml (utilisateur et mot de
passe PostgreSQL, compte administrateur, cle JWT...) : utilise des variables ${{NOM_VARIABLE}}.
Ecris leurs valeurs dans {dossier_sortie}/.env (valeurs aleatoires, au moins 16 caracteres
pour les mots de passe), et les memes noms sans valeur dans {dossier_sortie}/.env.example.
Docker Compose lit {dossier_sortie}/.env automatiquement.
Adresses e-mail par defaut (compte administrateur, comptes de demonstration) : un domaine normal
(ex : cabinet-medical.fr), jamais .local, .localhost, .test, .invalid ni .example : la validation
des e-mails (EmailStr) les refuse et l'application planterait.

N'execute aucune commande (pas de docker compose up, pas de docker build) : AutoDev
construit et teste la configuration lui-meme juste apres.

Ecris les fichiers directement sur disque, dans {dossier_sortie}/ uniquement."""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit"],
        input=prompt,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Dockerization Agent a échoué : {resultat.stderr}")

    nommer_projet_compose(dossier_sortie)
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

    nommer_projet_compose(dossier_sortie)
    return SortieDockerization(fichiers_generes=_lister_fichiers(dossier_sortie), resume_technique=resultat.stdout[:500])


def nommer_projet_compose(dossier_sortie: str = "output") -> str | None:
    """Donne a l'application generee son propre nom de projet Docker Compose.

    Sans nom, Docker Compose prend le nom du dossier (« output ») : toutes les
    applications generees partageaient alors le meme volume de base de donnees
    (output_db_data), et un ancien volume gardait les identifiants d'un ancien
    projet (defaut GEN-09). On ecrit « name: <id du run> » en premiere ligne
    du docker-compose.yml. Renvoie le nom, ou None si rien n'a ete fait."""
    compose = Path(dossier_sortie) / "docker-compose.yml"
    fichier_id = Path(dossier_sortie) / FICHIER_ID_RUN
    if not compose.exists() or not fichier_id.exists():
        return None
    # Nom de projet Compose : minuscules, chiffres, « - » et « _ », commence par une lettre ou un chiffre.
    nom = re.sub(r"[^a-z0-9_-]+", "-", fichier_id.read_text(encoding="utf-8").strip().lower()).strip("-_")
    if not nom:
        return None
    lignes = [ligne for ligne in compose.read_text(encoding="utf-8").splitlines()
              if not re.match(r"name\s*:", ligne)]
    compose.write_text(f"name: {nom}\n" + "\n".join(lignes) + "\n", encoding="utf-8")
    return nom
