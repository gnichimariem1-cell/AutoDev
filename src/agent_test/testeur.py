"""Test Agent : ecrit le plan de test et les tests pytest du backend AVANT le code.

Le Developer Agent ecrit ensuite le code pour faire passer ces tests, sans avoir
le droit de les modifier (l'orchestrateur en garde une empreinte et restaure les
originaux s'ils ont ete touches). Seul le Test Agent peut corriger les tests
(reviser_tests), si le QA echoue encore apres toutes les tentatives du Developer.

Le plan et les tests suivent le CONTRAT_TECHNIQUE, que le Developer suit aussi.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from src.common.schemas import SortiePO, SortieArchitecte, SortieTestAgent

CLAUDE_BIN = shutil.which("claude") or "claude"

# Organisation du backend imposee au Test Agent ET au Developer : c'est ce qui
# permet d'ecrire les tests avant le code.
CONTRAT_TECHNIQUE = """Contrat technique du backend (obligatoire) :
- l'application FastAPI est l'objet `app` du module `app/main.py` (import : `from app.main import app`)
- la base de donnees est geree dans `app/database.py`, qui expose `Base` (declarative SQLAlchemy)
  et `get_db` (dependance FastAPI qui fournit une session SQLAlchemy)
- les routes, methodes HTTP, champs JSON et codes de reponse sont ceux du plan de test
- les tests se lancent avec `pytest <dossier backend>`, le dossier backend etant dans le PYTHONPATH"""


def _extraire_json(texte: str) -> str:
    """Isole le JSON de la reponse : Claude Code ajoute parfois du texte ou des
    balises markdown autour."""
    bloc = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texte, re.DOTALL)
    if bloc:
        return bloc.group(1)
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        raise ValueError("Test Agent : aucun plan de test JSON dans la reponse")
    return texte[debut:fin + 1]


def _appeler_claude(prompt: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [CLAUDE_BIN, "-p", "--allowedTools", "Write,Edit"],
        input=prompt,
        capture_output=True, text=True, timeout=int(os.environ.get("CLAUDE_TIMEOUT", 1200)),
        encoding="utf-8", errors="replace",
    )


def lister_tests(dossier_backend: str) -> list[str]:
    dossier = Path(dossier_backend) / "tests"
    return sorted(str(f) for f in dossier.rglob("*.py")) if dossier.exists() else []


def lire_tests(dossier_backend: str) -> dict[str, str]:
    """Contenu de chaque fichier de tests : sert d'empreinte pour detecter (et
    annuler) toute modification par un autre agent."""
    return {f: Path(f).read_text(encoding="utf-8", errors="replace") for f in lister_tests(dossier_backend)}


def restaurer_tests(dossier_backend: str, originaux: dict[str, str]) -> list[str]:
    """Remet les tests dans leur etat d'origine. Renvoie la liste des fichiers
    qui avaient ete modifies, supprimes ou ajoutes."""
    touches = []
    actuels = lire_tests(dossier_backend)
    for chemin in set(actuels) - set(originaux):
        Path(chemin).unlink()
        touches.append(chemin)
    for chemin, contenu in originaux.items():
        if actuels.get(chemin) != contenu:
            Path(chemin).parent.mkdir(parents=True, exist_ok=True)
            Path(chemin).write_text(contenu, encoding="utf-8")
            touches.append(chemin)
    return sorted(touches)


def plan_en_markdown(plan: SortieTestAgent, titre_projet: str = "") -> str:
    lignes = [
        f"# Plan de test{' — ' + titre_projet if titre_projet else ''}",
        "",
        "Plan ecrit par le Test Agent d'AutoDev avant le code. Chaque cas correspond a un test pytest.",
        "",
        "| ID | User story | Scenario | Requete | Code attendu | Resultat attendu | Priorite |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in plan.cas:
        lignes.append(f"| {c.id} | {c.user_story} | {c.scenario} | {c.methode} {c.route} | "
                      f"{c.code_attendu} | {c.resultat_attendu} | {c.priorite} |")
    lignes += ["", "Fichiers de tests :", ""] + [f"- `{f}`" for f in plan.fichiers_tests]
    return "\n".join(lignes) + "\n"


def generer_plan_et_tests(user_stories: SortiePO, dossier_backend: str = "output/backend",
                          architecture: SortieArchitecte | None = None,
                          fichier_plan: str | None = None) -> SortieTestAgent:
    """Ecrit le plan de test et les tests pytest dans <dossier_backend>/tests/,
    avant que le Developer n'ecrive le code."""
    Path(dossier_backend, "tests").mkdir(parents=True, exist_ok=True)
    bloc_architecture = ""
    if architecture:
        bloc_architecture = (
            "Architecture prevue par l'Architect Agent :\n"
            f"- Stack : {', '.join(architecture.stack_technique)}\n"
            + "\n".join(f"- {m}" for m in architecture.structure_modules) + "\n\n"
        )

    prompt = f"""Tu es un ingenieur de test. Le code du backend N'EXISTE PAS ENCORE : tu ecris les tests
AVANT le code (TDD). Un autre agent ecrira ensuite le code pour faire passer tes tests.

User Stories :
{user_stories.model_dump_json(indent=2)}

{bloc_architecture}{CONTRAT_TECHNIQUE}

Travail demande :
1. Concois un plan de test : pour chaque user story, au moins un cas nominal et un cas d'erreur
   (ex : donnees invalides -> 422, ressource inexistante -> 404, acces sans authentification -> 401).
2. Ecris les tests pytest dans {dossier_backend}/tests/ :
   - un fichier conftest.py qui cree une base SQLite en memoire (StaticPool), cree les tables avec
     `Base.metadata.create_all`, surcharge `get_db` via `app.dependency_overrides` et fournit un
     `fastapi.testclient.TestClient`
   - un test par cas du plan, dont le nom commence par l'ID du cas (ex : `def test_T01_...`)
   - aucun service externe (pas de PostgreSQL, pas de reseau)
3. N'ecris AUCUN fichier en dehors de {dossier_backend}/tests/ : pas de code applicatif.

Quand les fichiers sont ecrits, reponds UNIQUEMENT avec le plan en JSON, sans texte autour :
{{"cas": [{{"id": "T01", "user_story": "US1", "scenario": "...", "methode": "POST",
"route": "/auth/register", "code_attendu": 201, "resultat_attendu": "...", "priorite": "haute"}}]}}"""

    resultat = _appeler_claude(prompt)
    if resultat.returncode != 0:
        raise RuntimeError(f"Test Agent a échoué : {resultat.stdout}\n{resultat.stderr}")

    plan = SortieTestAgent.model_validate(json.loads(_extraire_json(resultat.stdout)))
    plan.fichiers_tests = lister_tests(dossier_backend)
    if not plan.fichiers_tests:
        raise RuntimeError("Test Agent : aucun fichier de tests n'a ete ecrit")
    fichier_plan = fichier_plan or str(Path(dossier_backend) / "PLAN_DE_TEST.md")
    Path(fichier_plan).write_text(plan_en_markdown(plan), encoding="utf-8")
    return plan


def reviser_tests(rapport_erreurs: list[str], dossier_backend: str, plan: SortieTestAgent) -> SortieTestAgent:
    """Appele seulement si le QA echoue encore apres toutes les tentatives du
    Developer : le Test Agent verifie si ce sont ses tests qui sont faux."""
    prompt = f"""Tu es l'ingenieur de test qui a ecrit les tests de {dossier_backend}/tests/.
Le code a ete corrige plusieurs fois mais ces tests echouent toujours :
{json.dumps(rapport_erreurs, ensure_ascii=False, indent=2)}

Plan de test d'origine :
{plan.model_dump_json(indent=2)}

{CONTRAT_TECHNIQUE}

Verifie chaque test qui echoue :
- si le TEST est faux (erreur dans le test, attente contraire au plan ou au contrat), corrige le test ;
- si le test est correct et que c'est le code qui ne respecte pas le plan, NE CHANGE PAS le test.
Ne supprime aucun cas du plan et ne rends aucun test moins exigeant.
Ne modifie que les fichiers de {dossier_backend}/tests/."""

    resultat = _appeler_claude(prompt)
    if resultat.returncode != 0:
        raise RuntimeError(f"Revision des tests échouée : {resultat.stdout}\n{resultat.stderr}")
    return plan.model_copy(update={"fichiers_tests": lister_tests(dossier_backend)})