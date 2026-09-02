import subprocess
import json
import shutil
from pathlib import Path
from src.common.schemas import SortiePO, SortieDev

CLAUDE_BIN = shutil.which("claude") or "claude"

def generer_code(user_stories: SortiePO, dossier_sortie: str = "output/backend") -> SortieDev:
    Path(dossier_sortie).mkdir(parents=True, exist_ok=True)
    prompt = f"""Génère une API FastAPI + PostgreSQL dans {dossier_sortie} pour ces User Stories :
{user_stories.model_dump_json(indent=2)}
Écris les fichiers directement sur disque."""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Claude Code a échoué : {resultat.stderr}")

    fichiers = [str(p) for p in Path(dossier_sortie).rglob("*.py")]
    return SortieDev(fichiers_generes=fichiers, resume_technique=resultat.stdout[:500])


def appliquer_corrections(rapport_erreurs: list[str], dossier_sortie: str = "output/backend") -> SortieDev:
    prompt = f"""Corrige le code dans {dossier_sortie}. Voici les erreurs QA à résoudre :
{json.dumps(rapport_erreurs, ensure_ascii=False, indent=2)}"""
    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Correction échouée : {resultat.stderr}")
    fichiers = [str(p) for p in Path(dossier_sortie).rglob("*.py")]
    return SortieDev(fichiers_generes=fichiers, resume_technique=resultat.stdout[:500])