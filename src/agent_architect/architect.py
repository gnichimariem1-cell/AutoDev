import subprocess
import shutil
from src.common.schemas import SortiePO, SortieArchitecte

CLAUDE_BIN = shutil.which("claude") or "claude"

PROMPT_SYSTEME = """Tu es un architecte logiciel. A partir des User Stories fournies, propose une
architecture applicative pour une API FastAPI + PostgreSQL (backend) consommee par un frontend
HTML/CSS/JS. Ne genere AUCUN code : uniquement une proposition d'architecture.

Reponds UNIQUEMENT avec un JSON valide, sans texte autour, au format exact :
{
  "stack_technique": ["FastAPI", "PostgreSQL", "SQLAlchemy", "..."],
  "structure_modules": ["app/main.py - point d'entree FastAPI", "app/models.py - modeles SQLAlchemy", "..."],
  "justification": "explication concise des choix ci-dessus, 3-5 phrases"
}"""


def generer_architecture(user_stories: SortiePO) -> SortieArchitecte:
    """Architect Agent : propose la stack technique et la structure du projet
    a partir des User Stories, sans generer de code. Le resultat est ensuite
    transmis au Developer Agent (voir agent_orchestrateur/orchestrateur.py)
    qui le suit comme contrainte de generation.
    """
    prompt = f"{PROMPT_SYSTEME}\n\nUser Stories :\n{user_stories.model_dump_json(indent=2)}"

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p"],
        input=prompt,
        capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Architect Agent a échoué : {resultat.stderr}")

    return SortieArchitecte.model_validate_json(resultat.stdout.strip())
