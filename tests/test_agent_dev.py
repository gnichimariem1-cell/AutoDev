from unittest.mock import patch, MagicMock
from src.agent_dev.developer import generer_code
from src.common.schemas import SortiePO, UserStory

@patch("src.agent_dev.developer.subprocess.run")
def test_generer_code_appelle_claude_et_liste_fichiers(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    (tmp_path / "main.py").write_text("print('hello')")

    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Login", description="d",
        criteres_acceptation=["c"], priorite="haute")])

    resultat = generer_code(stories, dossier_sortie=str(tmp_path))
    assert mock_run.called
    assert any("main.py" in f for f in resultat.fichiers_generes)