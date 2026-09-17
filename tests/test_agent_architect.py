import json
from unittest.mock import patch, MagicMock

from src.agent_architect.architect import generer_architecture
from src.common.schemas import SortiePO, UserStory, SortieArchitecte


def _user_stories_exemple():
    return SortiePO(user_stories=[
        UserStory(id="US1", titre="Connexion", description="En tant qu'utilisateur je veux me connecter",
                   criteres_acceptation=["Login valide accepte"], priorite="haute"),
    ])


@patch("src.agent_architect.architect.subprocess.run")
def test_generer_architecture_retourne_une_sortie_architecte(mock_run):
    reponse_json = json.dumps({
        "stack_technique": ["FastAPI", "PostgreSQL", "SQLAlchemy"],
        "structure_modules": ["app/main.py - point d'entree", "app/models.py - modeles"],
        "justification": "Stack simple et eprouvee pour une API CRUD.",
    })
    mock_run.return_value = MagicMock(returncode=0, stdout=reponse_json, stderr="")

    resultat = generer_architecture(_user_stories_exemple())

    assert isinstance(resultat, SortieArchitecte)
    assert "FastAPI" in resultat.stack_technique
    assert len(resultat.structure_modules) == 2


@patch("src.agent_architect.architect.subprocess.run")
def test_generer_architecture_leve_une_erreur_si_claude_code_echoue(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

    try:
        generer_architecture(_user_stories_exemple())
        assert False, "une RuntimeError etait attendue"
    except RuntimeError as e:
        assert "Architect Agent" in str(e)
