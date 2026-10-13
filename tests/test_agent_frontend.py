from unittest.mock import patch, MagicMock
from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
from src.common.schemas import BesoinUtilisateur, SortiePO, UserStory, SortieArchitecte


@patch("src.agent_frontend.frontend.subprocess.run")
def test_generer_frontend_appelle_claude_et_liste_fichiers(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    (tmp_path / "index.html").write_text("<html></html>")

    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Login", description="d",
        criteres_acceptation=["c"], priorite="haute")])

    resultat = generer_frontend(stories, dossier_backend="output/backend", dossier_sortie=str(tmp_path))
    assert mock_run.called
    assert any("index.html" in f for f in resultat.fichiers_generes)


@patch("src.agent_frontend.frontend.subprocess.run")
def test_appliquer_corrections_frontend_relance_claude(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    (tmp_path / "app.js").write_text("console.log('ok');")

    resultat = appliquer_corrections_frontend(["erreur X"], dossier_sortie=str(tmp_path))
    assert mock_run.called
    assert any("app.js" in f for f in resultat.fichiers_generes)


@patch("src.agent_frontend.frontend.subprocess.run")
def test_generer_frontend_transmet_organisation_et_pages_prevues(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Login", description="d",
        criteres_acceptation=["c"], priorite="haute")])
    architecture = SortieArchitecte(
        stack_technique=["FastAPI"],
        structure_modules=[
            "app/main.py - point d'entree FastAPI",
            "frontend/catalogue.html - liste paginee des livres",
            "frontend/js/api.js - client fetch centralise",
        ],
        justification="j",
    )

    generer_frontend(stories, dossier_backend="output/backend", dossier_sortie=str(tmp_path),
                     architecture=architecture, organisation_interface="Une page catalogue et un tableau de bord")

    prompt = mock_run.call_args.kwargs["input"]
    assert "Une page catalogue et un tableau de bord" in prompt
    assert "- catalogue.html - liste paginee des livres" in prompt
    assert "- js/api.js - client fetch centralise" in prompt
    assert "app/main.py" not in prompt


@patch("src.agent_frontend.frontend.subprocess.run")
def test_generer_frontend_prevoit_l_ecran_des_ressources_prealables(mock_run, tmp_path):
    """Issue #3 : l'interface FR-02 renvoyait a la base de donnees pour creer un membre."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Emprunter un livre", description="d",
        criteres_acceptation=["c"], priorite="haute")])
    generer_frontend(stories, dossier_backend="output/backend", dossier_sortie=str(tmp_path))
    assert "jamais avoir a passer" in mock_run.call_args.kwargs["input"]


@patch("src.agent_frontend.frontend.subprocess.run")
def test_generer_frontend_recoit_la_description_du_besoin(mock_run, tmp_path):
    """Issue #4 : le Frontend ne voyait que les User Stories."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    stories = SortiePO(user_stories=[UserStory(
        id="US1", titre="Poser une question", description="d", criteres_acceptation=["c"], priorite="haute")])
    besoin = BesoinUtilisateur(titre_projet="FAQ", description="le membre voit ensuite la reponse",
                               utilisateurs_cibles="membres", fonctionnalites_cles=["poser une question"])
    generer_frontend(stories, dossier_backend="output/backend", dossier_sortie=str(tmp_path), besoin=besoin)
    prompt = mock_run.call_args.kwargs["input"]
    assert "le membre voit ensuite la reponse" in prompt
    assert "accessible depuis l'interface" in prompt
