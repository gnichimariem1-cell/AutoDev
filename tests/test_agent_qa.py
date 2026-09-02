import json
from unittest.mock import patch, MagicMock
from src.agent_qa.qa import lancer_tests

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