import json
import os

import pytest
from unittest.mock import patch, MagicMock
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend

@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_calcule_le_rapport(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_run.side_effect = _faux_pytest(tmp_path, {
        "summary": {"passed": 8, "failed": 1},
        "tests": [{"nodeid": "test_x.py::test_echoue", "outcome": "failed"}],
    }, couverture=87.5)

    rapport = lancer_tests("src")
    assert rapport.tests_passes == 8
    assert rapport.succes is False
    assert rapport.couverture_pct == 87.5



def _faux_pytest(tmp_path, rapport, couverture=50.0):
    """Simule pytest : ecrit les rapports au moment de l'appel (comme le vrai pytest)."""
    def executer(commande, **kwargs):
        if commande[0] == "pytest":
            (tmp_path / "rapport_pytest.json").write_text(json.dumps(rapport))
            (tmp_path / "coverage.json").write_text(
                json.dumps({"totals": {"percent_covered": couverture}}))
        return MagicMock(returncode=0)
    return executer


@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_succes_si_tous_les_tests_passent(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_run.side_effect = _faux_pytest(tmp_path, {
        "summary": {"passed": 5, "total": 5, "collected": 5},
        "tests": [{"nodeid": f"tests/test_api.py::test_{i}", "outcome": "passed"} for i in range(5)],
        "collectors": [],
    })

    rapport = lancer_tests("backend")
    assert rapport.succes is True
    assert rapport.erreurs == []
    env = mock_run.call_args.kwargs["env"]
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path / "backend")


@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_echoue_si_aucun_test(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_run.side_effect = _faux_pytest(tmp_path, {
        "summary": {"total": 0, "collected": 0}, "tests": [], "collectors": [],
    }, couverture=0.0)

    rapport = lancer_tests("backend")
    assert rapport.succes is False
    assert any("Aucun test" in e for e in rapport.erreurs)


@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_echoue_si_erreur_de_collecte(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_run.side_effect = _faux_pytest(tmp_path, {
        "summary": {"passed": 2, "error": 1, "total": 2, "collected": 2},
        "tests": [{"nodeid": "tests/test_a.py::test_ok", "outcome": "passed"}],
        "collectors": [{
            "nodeid": "tests/test_b.py", "outcome": "failed",
            "longrepr": "ModuleNotFoundError: No module named 'app'",
        }],
    })

    rapport = lancer_tests("backend")
    assert rapport.succes is False
    assert any("No module named 'app'" in e for e in rapport.erreurs)


@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_ne_relit_pas_un_ancien_rapport(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rapport_pytest.json").write_text(json.dumps({"summary": {"passed": 9}}))
    mock_run.return_value = MagicMock(returncode=4, stdout="", stderr="crash")

    with pytest.raises(RuntimeError, match="rapport_pytest.json manquant"):
        lancer_tests("backend")

def test_lancer_tests_frontend_detecte_index_manquant(tmp_path):
    rapport = lancer_tests_frontend(str(tmp_path))
    assert rapport.succes is False
    assert any("index.html" in e for e in rapport.erreurs)


def test_lancer_tests_frontend_ok_si_index_present(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    rapport = lancer_tests_frontend(str(tmp_path))
    assert rapport.succes is True
    assert rapport.erreurs == []


@patch("src.agent_qa.qa.shutil.which", return_value="/usr/bin/node")
@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_frontend_detecte_erreur_syntaxe_js(mock_run, mock_which, tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "app.js").write_text("const x = ;")
    mock_run.return_value = MagicMock(returncode=1, stderr="SyntaxError: Unexpected token")

    rapport = lancer_tests_frontend(str(tmp_path))
    assert rapport.succes is False
    assert any("SyntaxError" in e for e in rapport.erreurs)