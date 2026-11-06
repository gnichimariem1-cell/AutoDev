"""Regles des agents (dossier regles/) : chaque agent a son fichier et le recoit dans sa consigne."""
from unittest.mock import MagicMock, patch

import pytest

from src.common.regles import AGENTS, DOSSIER_REGLES, bloc_regles, regles_de
from tests.sorties import USER_STORIES, ARCHITECTURE, PLAN_TESTS

OK = MagicMock(returncode=0, stdout='{"cas": [], "stack_technique": ["FastAPI"], "structure_modules": [], '
                                    '"justification": "x"}', stderr="")


def test_chaque_agent_a_son_fichier_de_regles():
    assert (DOSSIER_REGLES / "README.md").exists()
    for agent in AGENTS:
        texte = regles_de(agent)
        assert texte.startswith("# Regles") or texte.startswith("# Règles"), agent
        assert "Pourquoi" in texte, f"{agent} : chaque fichier explique ses regles"


def test_valeurs_remplacees_et_agent_inconnu():
    assert "output/frontend/.dockerignore" in regles_de("dockerization", dossier_frontend="output/frontend")
    assert "{dossier_frontend}" in regles_de("dockerization")
    assert bloc_regles("developer").startswith("\n\nRegles a respecter (fichier regles/developer.md)")
    with pytest.raises(FileNotFoundError):
        regles_de("agent_inconnu")


def _consigne(mock_run):
    return mock_run.call_args.kwargs["input"]


@patch("src.agent_architect.architect.subprocess.run", return_value=OK)
def test_architect_recoit_ses_regles(mock_run):
    from src.agent_architect.architect import generer_architecture
    generer_architecture(USER_STORIES)
    assert "regles/architect.md" in _consigne(mock_run) and "frontend/" in _consigne(mock_run)


@patch("src.agent_dev.developer.subprocess.run", return_value=MagicMock(returncode=0, stdout="ok", stderr=""))
def test_developer_recoit_ses_regles_aussi_en_correction(mock_run, tmp_path):
    from src.agent_dev.developer import generer_code, appliquer_corrections
    generer_code(USER_STORIES, str(tmp_path / "backend"), architecture=ARCHITECTURE)
    assert "regles/developer.md" in _consigne(mock_run)
    appliquer_corrections(["E01 : 500"], str(tmp_path / "backend"))
    assert "jamais .local" in _consigne(mock_run) and "--strict-mcp-config" in _consigne(mock_run)


@patch("src.agent_frontend.frontend.subprocess.run", return_value=MagicMock(returncode=0, stdout="ok", stderr=""))
def test_frontend_recoit_ses_regles_aussi_en_correction(mock_run, tmp_path):
    from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
    generer_frontend(USER_STORIES, "b", str(tmp_path / "front"))
    assert "regles/frontend.md" in _consigne(mock_run) and "textContent" in _consigne(mock_run)
    appliquer_corrections_frontend(["E02 : bouton absent"], str(tmp_path / "front"))
    assert "regles/frontend.md" in _consigne(mock_run)


@patch("src.agent_dockerization.dockerization.subprocess.run",
       return_value=MagicMock(returncode=0, stdout="ok", stderr=""))
def test_dockerization_recoit_ses_regles_aussi_en_correction(mock_run, tmp_path, monkeypatch):
    from src.agent_dockerization.dockerization import appliquer_corrections_dockerisation
    monkeypatch.chdir(tmp_path)
    appliquer_corrections_dockerisation(["build : erreur"], "sortie")
    consigne = _consigne(mock_run)
    assert "Aucun volume qui monte un dossier du projet" in consigne
    assert "sortie/frontend/.dockerignore" in consigne


@patch("src.agent_test.testeur.subprocess.run", return_value=OK)
def test_test_agent_recoit_ses_regles_en_revision(mock_run, tmp_path):
    from src.agent_test.testeur import reviser_tests
    reviser_tests(["T01"], str(tmp_path), PLAN_TESTS)
    assert "regles/test_agent.md" in _consigne(mock_run)
    assert "ne rends aucun test moins exigeant" in _consigne(mock_run)


def test_product_owner_et_agent_e2e_recoivent_leurs_regles():
    from src.agent_e2e.e2e import consigne_e2e
    from src.agent_po import product_owner
    assert "regles/agent_e2e.md" in consigne_e2e(USER_STORIES, "demande", "b", "e2e", "f")
    with patch.object(product_owner, "_demander", return_value=USER_STORIES) as demander:
        from tests.sorties import BESOIN
        product_owner.generer_user_stories(BESOIN)
    assert "regles/product_owner.md" in demander.call_args.args[0]
