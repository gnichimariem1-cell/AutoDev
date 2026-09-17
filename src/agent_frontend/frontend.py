import json
import subprocess
import shutil
from pathlib import Path
from src.common.schemas import SortiePO, SortieFrontend

CLAUDE_BIN = shutil.which("claude") or "claude"

PROMPT_TEMPLATE = """Génère un frontend web statique (HTML/CSS/JavaScript vanilla, sans framework
ni étape de build) dans {dossier_sortie}, qui consomme l'API backend déjà générée dans {dossier_backend}.

Commence par lire les routes de {dossier_backend}/app/routers/ pour connaître les endpoints exacts
(chemins, méthodes HTTP, corps de requête/réponse) et respecte-les précisément.

User Stories à couvrir :
{user_stories_json}

Contraintes :
- Un fichier index.html comme point d'entrée, un app.js pour la logique, un style.css pour le style.
- Utilise fetch() pour appeler l'API (URL de base configurable en haut de app.js, ex: http://localhost:8000).
- Écris les fichiers directement sur disque.
"""


def _lister_fichiers(dossier_sortie: str) -> list[str]:
    return [str(p) for p in Path(dossier_sortie).rglob("*") if p.is_file()]


def generer_frontend(
    user_stories: SortiePO,
    dossier_backend: str = "output/backend",
    dossier_sortie: str = "output/frontend",
) -> SortieFrontend:
    Path(dossier_sortie).mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_TEMPLATE.format(
        dossier_sortie=dossier_sortie,
        dossier_backend=dossier_backend,
        user_stories_json=user_stories.model_dump_json(indent=2),
    )

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"Claude Code a échoué (frontend) : {resultat.stdout}\n{resultat.stderr}"
        )

    return SortieFrontend(
        fichiers_generes=_lister_fichiers(dossier_sortie),
        resume_technique=resultat.stdout[:500],
    )


def appliquer_corrections_frontend(
    rapport_erreurs: list[str], dossier_sortie: str = "output/frontend"
) -> SortieFrontend:
    prompt = f"""Corrige le frontend dans {dossier_sortie}. Voici les erreurs QA à résoudre :
{json.dumps(rapport_erreurs, ensure_ascii=False, indent=2)}"""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Read,Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"Correction échouée (frontend) : {resultat.stdout}\n{resultat.stderr}"
        )

    return SortieFrontend(
        fichiers_generes=_lister_fichiers(dossier_sortie),
        resume_technique=resultat.stdout[:500],
    )
