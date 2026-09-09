import json
from unittest.mock import patch, MagicMock
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend

@patch("src.agent_qa.qa.subprocess.run")
def test_lancer_tests_calcule_le_rapport(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_run.return_value = MagicMock(returncode=0)

    (tmp_path / "rapport_pytest.json").write_text(json.dumps({
        "summary": {"passed": 8, "failed": 1},
        "tests": [{"nodeid": "test_x.py::test_echoue", "outcome": "failed"}],
    }))
    (tmp_path / "coverage.json").write_text(json.dumps({"totals": {"percent_covered": 87.5}}))

    rapport = lancer_tests("src")
    assert rapport.tests_passes == 8
    assert rapport.succes is False
    assert rapport.couverture_pct == 87.5


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