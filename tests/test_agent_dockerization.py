from unittest.mock import patch, MagicMock

import pytest

from src.agent_dockerization.dockerization import generer_dockerisation, nommer_projet_compose
from src.common.schemas import SortieDockerization


@pytest.fixture(autouse=True)
def dossier_temporaire(tmp_path, monkeypatch):
    """generer_dockerisation cree son dossier de sortie : pas dans output/ du projet."""
    monkeypatch.chdir(tmp_path)


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


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_generer_dockerisation_lit_le_readme_du_backend(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_dockerisation("output/backend", "output/frontend")
    prompt = mock_run.call_args.kwargs["input"]
    assert "output/backend/README.md" in prompt
    assert "output/backend/.env.example" in prompt


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_generer_dockerisation_aligne_le_pilote_postgres_sur_requirements(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_dockerisation("output/backend", "output/frontend")
    prompt = mock_run.call_args.kwargs["input"]
    assert "output/backend/requirements.txt" in prompt
    assert "postgresql+psycopg2://" in prompt
    assert "postgresql+psycopg://" in prompt


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_generer_dockerisation_sans_bash_ni_lancement_docker(mock_run):
    """Issue #2 : avec le socket Docker, l'agent lancait docker compose up lui-meme."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_dockerisation("output/backend", "output/frontend")
    commande = mock_run.call_args.args[0]
    assert "Bash" not in commande[commande.index("--allowedTools") + 1]
    assert "Ne lance PAS docker" in mock_run.call_args.kwargs["input"]


def test_nommer_projet_compose_ajoute_le_nom_en_tete(tmp_path):
    """Issue #1 : sans nom, tous les projets generes partageaient le volume output_db_data."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  db:\n    image: postgres:16\n", encoding="utf-8")
    nommer_projet_compose(str(tmp_path), "todo-app-20261012-164425-0910")
    assert compose.read_text(encoding="utf-8") == (
        "name: todo-app-20261012-164425-0910\nservices:\n  db:\n    image: postgres:16\n")


def test_nommer_projet_compose_remplace_un_nom_existant(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("name: output\nservices:\n  app:\n    container_name: x\n", encoding="utf-8")
    nommer_projet_compose(str(tmp_path), "run-2")
    contenu = compose.read_text(encoding="utf-8")
    assert contenu.startswith("name: run-2\n")
    assert "name: output" not in contenu
    assert "container_name: x" in contenu


def test_nommer_projet_compose_sans_fichier(tmp_path):
    nommer_projet_compose(str(tmp_path), "run-3")
    assert not (tmp_path / "docker-compose.yml").exists()
