from unittest.mock import patch, MagicMock
from src.agent_dev.developer import generer_code
from src.common.schemas import BesoinUtilisateur, SortiePO, UserStory

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
    prompt = mock_run.call_args.kwargs["input"]
    assert "UNIQUEMENT le backend" in prompt
    assert "CORSMiddleware" in prompt
    assert "Ne génère PAS de Dockerfile ni de docker-compose.yml" in prompt
    assert "README.md" in prompt


@patch("src.agent_dev.developer.subprocess.run")
def test_generer_code_demande_les_ressources_prealables(mock_run, tmp_path):
    """Issue #3 : FR-02 sans creation de membre, emprunter etait impossible."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Emprunter un livre", description="d",
        criteres_acceptation=["c"], priorite="haute")])
    generer_code(stories, dossier_sortie=str(tmp_path))
    prompt = mock_run.call_args.kwargs["input"]
    assert "permettre de creer cette autre ressource" in prompt
    assert "n'est pas une ressource" in prompt


@patch("src.agent_dev.developer.subprocess.run")
def test_generer_code_recoit_la_description_du_besoin(mock_run, tmp_path):
    """Issue #4 : le Developer ne voyait que les User Stories."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Poser une question", description="d", criteres_acceptation=["c"], priorite="haute")])
    besoin = BesoinUtilisateur(titre_projet="FAQ", description="le membre voit ensuite la reponse",
                               utilisateurs_cibles="membres", fonctionnalites_cles=["poser une question"])
    generer_code(stories, dossier_sortie=str(tmp_path), besoin=besoin)
    prompt = mock_run.call_args.kwargs["input"]
    assert "le membre voit ensuite la reponse" in prompt
    assert "realise par l'API" in prompt
