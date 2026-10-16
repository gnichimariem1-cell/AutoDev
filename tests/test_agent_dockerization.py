from unittest.mock import patch, MagicMock

import pytest

from src.agent_dockerization.dockerization import generer_dockerisation
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


def test_nom_de_projet_compose_unique(tmp_path):
    """GEN-09 : chaque application generee a son propre nom de projet (et donc ses volumes)."""
    from src.agent_dockerization.dockerization import nommer_projet_compose
    (tmp_path / ".id_run").write_text("biblioth-que-du-coll-ge-20261012-204150-bc65")
    (tmp_path / "docker-compose.yml").write_text("name: output\nservices:\n  db:\n    image: postgres:16\n")
    assert nommer_projet_compose(str(tmp_path)) == "biblioth-que-du-coll-ge-20261012-204150-bc65"
    lignes = (tmp_path / "docker-compose.yml").read_text().splitlines()
    assert lignes[0] == "name: biblioth-que-du-coll-ge-20261012-204150-bc65"
    assert sum(ligne.startswith("name:") for ligne in lignes) == 1  # l'ancien nom est remplace
    assert "services:" in lignes


def test_nom_de_projet_sans_id_de_run(tmp_path):
    from src.agent_dockerization.dockerization import nommer_projet_compose
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    assert nommer_projet_compose(str(tmp_path)) is None


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_dockerization_sans_bash_ni_secret_en_clair(mock_run):
    """SYS-13 : l'agent ne peut plus lancer docker compose up lui-meme."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_dockerisation("output/backend", "output/frontend")
    commande = mock_run.call_args.args[0]
    assert "Bash" not in commande[commande.index("--allowedTools") + 1]
    prompt = mock_run.call_args.kwargs["input"]
    assert "Aucun mot de passe ni secret en clair" in prompt
    assert "N'execute aucune commande" in prompt
    assert "jamais .local" in prompt  # ADMIN_EMAIL en .local : connexion en 500 (trouve par l'Agent E2E)


def test_dockerfile_autodev_sans_tampon():
    """SEC-09 : l'avertissement de demarrage doit apparaitre dans docker compose logs."""
    from pathlib import Path
    racine = Path(__file__).resolve().parent.parent
    assert "PYTHONUNBUFFERED=1" in (racine / "Dockerfile").read_text(encoding="utf-8-sig")
