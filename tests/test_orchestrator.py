from unittest.mock import patch, MagicMock
from src.orchestrator import executer_pipeline
from src.common.schemas import BesoinUtilisateur, RapportQA, RapportQAFrontend


@patch("src.orchestrator.lancer_tests_frontend")
@patch("src.orchestrator.appliquer_corrections_frontend")
@patch("src.orchestrator.generer_frontend")
@patch("src.orchestrator.lancer_tests")
@patch("src.orchestrator.appliquer_corrections")
@patch("src.orchestrator.generer_code")
@patch("src.orchestrator.generer_user_stories")
def test_pipeline_reussit_du_premier_coup(mock_po, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe):
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)
    mock_qa_fe.return_value = RapportQAFrontend(fichiers_verifies=["index.html"], succes=True)

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is True
    assert resultat["tentative_backend"] == 1
    assert resultat["tentative_frontend"] == 1
    mock_corr.assert_not_called()
    mock_corr_fe.assert_not_called()


@patch("src.orchestrator.lancer_tests_frontend")
@patch("src.orchestrator.appliquer_corrections_frontend")
@patch("src.orchestrator.generer_frontend")
@patch("src.orchestrator.lancer_tests")
@patch("src.orchestrator.appliquer_corrections")
@patch("src.orchestrator.generer_code")
@patch("src.orchestrator.generer_user_stories")
def test_pipeline_echoue_apres_3_tentatives_backend(mock_po, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe):
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=2, tests_echoues=3, couverture_pct=40, succes=False, erreurs=["e1"])

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is False
    assert resultat["etape"] == "backend"
    assert resultat["tentative_backend"] == 3
    assert mock_corr.call_count == 2
    mock_fe.assert_not_called()


@patch("src.orchestrator.lancer_tests_frontend")
@patch("src.orchestrator.appliquer_corrections_frontend")
@patch("src.orchestrator.generer_frontend")
@patch("src.orchestrator.lancer_tests")
@patch("src.orchestrator.appliquer_corrections")
@patch("src.orchestrator.generer_code")
@patch("src.orchestrator.generer_user_stories")
def test_pipeline_echoue_apres_3_tentatives_frontend(mock_po, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe):
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)
    mock_qa_fe.return_value = RapportQAFrontend(
        fichiers_verifies=["index.html"], succes=False, erreurs=["erreur JS"]
    )

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is False
    assert resultat["etape"] == "frontend"
    assert resultat["tentative_frontend"] == 3
    assert mock_corr_fe.call_count == 2
    mock_fe.assert_called_once()
