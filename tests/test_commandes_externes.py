"""Commandes externes du backend genere et securite de l'appel a claude."""
from unittest.mock import patch

from src.common.commandes_externes import commandes_utilisees, problemes_securite_claude
from tests.test_agent_qa import _faux_pytest
from src.agent_qa.qa import lancer_tests


def _backend(tmp_path, code):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "ia.py").write_text(code)
    return tmp_path / "backend"


def test_commandes_utilisees(tmp_path):
    backend = _backend(tmp_path, 'cmd = ["claude", "-p"]\nsubprocess.run(("git", "status"))\nx = ["bonjour", 1]\n')
    assert commandes_utilisees(backend) == {"claude", "git"}
    assert commandes_utilisees(tmp_path / "absent") == set()


def test_appel_claude_sur(tmp_path):
    """Le code reel du chatbot, apres correction."""
    backend = _backend(tmp_path, 'cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--output-format", "text"]\n')
    assert problemes_securite_claude(backend) == []


def test_appel_claude_avec_les_connecteurs_du_compte(tmp_path):
    """Le code du chatbot genere : --tools "" seul laissait Claude Docs accessible."""
    backend = _backend(tmp_path, 'cmd = ["claude", "-p", "--tools", "", "--output-format", "text"]\n')
    probleme = problemes_securite_claude(backend)
    assert len(probleme) == 1 and "manque : --strict-mcp-config" in probleme[0]


def test_appel_claude_avec_outils_autorises(tmp_path):
    backend = _backend(tmp_path, 'cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--allowedTools", "Read"]\n')
    assert "interdit : --allowedTools" in problemes_securite_claude(backend)[0]


@patch("src.agent_qa.qa.subprocess.run")
def test_qa_backend_renvoie_le_probleme_au_developer(mock_run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _backend(tmp_path, 'cmd = ["claude", "-p", "--tools", ""]\n')
    mock_run.side_effect = _faux_pytest(tmp_path, {
        "summary": {"passed": 3, "total": 3}, "tests": [], "collectors": []})
    rapport = lancer_tests("backend")
    assert rapport.tests_passes == 3 and rapport.succes is False
    assert "--strict-mcp-config" in rapport.erreurs[0]
