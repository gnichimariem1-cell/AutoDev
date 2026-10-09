import subprocess
import os
import json
import shutil
from pathlib import Path
from src.common.schemas import SortiePO, SortieDev, SortieArchitecte
from src.agent_test.testeur import CONTRAT_TECHNIQUE

CLAUDE_BIN = shutil.which("claude") or "claude"

def generer_code(user_stories: SortiePO, dossier_sortie: str = "output/backend", architecture: SortieArchitecte | None = None) -> SortieDev:
    Path(dossier_sortie).mkdir(parents=True, exist_ok=True)

    if architecture:
        bloc_architecture = f"""Respecte cette architecture, definie par l'Architect Agent :
- Stack technique : {", ".join(architecture.stack_technique)}
- Structure des modules :
{chr(10).join("  - " + m for m in architecture.structure_modules)}
- Justification : {architecture.justification}

"""
    else:
        bloc_architecture = ""

    prompt = f"""Génère une API FastAPI + PostgreSQL dans {dossier_sortie} pour ces User Stories :
{user_stories.model_dump_json(indent=2)}

{bloc_architecture}Génère UNIQUEMENT le backend (l'API) : aucun fichier HTML/CSS/JavaScript, pas de dossier
frontend/ ni static/, et l'API ne sert pas de fichiers statiques (pas de StaticFiles). Le frontend
est généré séparément par un autre agent et servi par son propre conteneur : ignore les modules
frontend de l'architecture ci-dessus. Active CORS (CORSMiddleware) pour que ce frontend, servi sur
un autre port (ex : http://localhost:8080), puisse appeler l'API.

Inclus également :
- un fichier .env.example listant les variables necessaires (DATABASE_URL, SECRET_KEY, etc.)
- un README.md qui documente comment lancer l'API : variables d'environnement, creation
  ou migration du schema de la base, initialisation eventuelle (ex : compte admin) et
  commande de demarrage (uvicorn sur le port 8000)

Ne génère PAS de Dockerfile ni de docker-compose.yml : la configuration Docker de
l'ensemble (backend, frontend, base PostgreSQL) est produite ensuite par un autre agent,
a partir de ce README.md.

Les tests existent DEJA dans {dossier_sortie}/tests/ : ils ont ete ecrits avant le code par le
Test Agent, d'apres le plan {dossier_sortie}/PLAN_DE_TEST.md. Lis-les d'abord : ils fixent les routes,
les champs JSON et les codes de reponse attendus. Ecris le code pour qu'ils passent tous.
- Ne modifie PAS, ne supprime PAS et n'ajoute PAS de fichiers dans {dossier_sortie}/tests/
  (toute modification sera annulee automatiquement)
- respecte ce contrat technique, que les tests utilisent :
{CONTRAT_TECHNIQUE}
- ajoute pytest et httpx dans requirements.txt

Écris les fichiers directement sur disque."""

    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=int(os.environ.get("CLAUDE_TIMEOUT", 1200)),
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"Claude Code a échoué : {resultat.stdout}\n{resultat.stderr}"
        )

    fichiers = [str(p) for p in Path(dossier_sortie).rglob("*.py")]
    return SortieDev(fichiers_generes=fichiers, resume_technique=resultat.stdout[:500])


def appliquer_corrections(rapport_erreurs: list[str], dossier_sortie: str = "output/backend") -> SortieDev:
    prompt = f"""Corrige le code dans {dossier_sortie}. Voici les erreurs QA à résoudre :
{json.dumps(rapport_erreurs, ensure_ascii=False, indent=2)}

Ne modifie PAS et ne supprime PAS les fichiers de tests ({dossier_sortie}/tests/) :
corrige uniquement le code de l'application pour que les tests existants passent."""
    resultat = subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit,Bash"],
        input=prompt,
        capture_output=True, text=True, timeout=int(os.environ.get("CLAUDE_TIMEOUT", 1200)),
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(
            f"Correction échouée : {resultat.stdout}\n{resultat.stderr}"
        )
    fichiers = [str(p) for p in Path(dossier_sortie).rglob("*.py")]
    return SortieDev(fichiers_generes=fichiers, resume_technique=resultat.stdout[:500])
