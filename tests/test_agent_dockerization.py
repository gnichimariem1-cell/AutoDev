from unittest.mock import patch, MagicMock

from src.agent_dockerization.dockerization import generer_dockerisation
from src.common.schemas import SortieDockerization


@patch("src.agent_dockerization.dockerization.Path.glob")
@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_generer_dockerisation_retourne_une_sortie_dockerization(mock_run, mock_glob):
    mock_run.return_value = MagicMock(returncode=0, stdout="Dockerfile et docker-compose.yml generes", stderr="")
    mock_glob.return_value = []

    resultat = generer_dockerisation("output/backend", "output/frontend")

    assert isinstance(resultat, SortieDockerization)
    assert "generes" in resultat.resume_technique


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_generer_dockerisation_leve_une_erreur_si_claude_code_echoue(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

    try:
        generer_dockerisation("output/backend", "output/frontend")
        assert False, "une RuntimeError etait attendue"
    except RuntimeError as e:
        assert "Dockerization Agent" in str(e)
