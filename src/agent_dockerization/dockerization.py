import subprocess
import shutil
from pathlib import Path
from src.common.schemas import SortieDockerization

CLAUDE_BIN = shutil.which("claude") or "claude"


def generer_dockerisation(dossier_backend: str = "output/backend", dossier_frontend: str = "output/frontend") -> SortieDockerization:
    """Dockerization Agent : se declenche une fois le backend ET le frontend
    valides par leurs QA Agents respectifs (voir agent_orchestrateur/orchestrateur.py).
    Produit une configuration Docker unifiee (Dockerfile + docker-compose.yml)
    pour l'ensemble du projet, sur le code reellement teste. Pas de boucle de
    correction ici : contrairement a QA, il n'y a pas de test automatique a
    faire echouer/reussir sur cet agent.
    """
    prompt = f"""Genere une configuration Docker unifiee pour ce projet, compose de deux parties deja
generees et validees :
- backend FastAPI dans {dossier_backend}
- frontend statique (HTML/CSS/JS) dans {dossier_frontend}

Ecris a la racine du projet :
- un Dockerfile pour le backend (image python slim, installe les dependances de
  {dossier_backend}/requirements.txt, expose le port 8000)
- un docker-compose.yml avec 3 services : "app" (le backend, build depuis le
  Dockerfile ci-dessus), "frontend" (sert les fichiers statiques de
  {dossier_frontend}, par exemple via nginx:alpine ou un serveur simple), et "db"
  (postgres:16, volume nomme pour persister les donnees)
- un fichier .dockerignore adapte

Ecris les fichiers directement sur disque, a la racine du projet (pas dans
{dossier_backend} ni {dossier_frontend})."""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Dockerization Agent a échoué : {resultat.stderr}")

    fichiers = [
        str(p) for p in Path(".").glob("Dockerfile*")
    ] + [
        str(p) for p in Path(".").glob("docker-compose*.yml")
    ] + [
        str(p) for p in Path(".").glob(".dockerignore")
    ]
    return SortieDockerization(fichiers_generes=fichiers, resume_technique=resultat.stdout[:500])
