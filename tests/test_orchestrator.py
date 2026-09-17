from unittest.mock import patch, MagicMock
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.common.schemas import BesoinUtilisateur, RapportQA, RapportQAFrontend


@patch("src.agent_orchestrateur.orchestrateur.generer_dockerisation")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests_frontend")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections_frontend")
@patch("src.agent_orchestrateur.orchestrateur.generer_frontend")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections")
@patch("src.agent_orchestrateur.orchestrateur.generer_code")
@patch("src.agent_orchestrateur.orchestrateur.generer_architecture")
@patch("src.agent_orchestrateur.orchestrateur.generer_user_stories")
def test_pipeline_reussit_du_premier_coup(mock_po, mock_arch, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe, mock_dock):
    mock_dock.return_value = MagicMock()
    mock_arch.return_value = MagicMock()
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


@patch("src.agent_orchestrateur.orchestrateur.generer_dockerisation")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests_frontend")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections_frontend")
@patch("src.agent_orchestrateur.orchestrateur.generer_frontend")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections")
@patch("src.agent_orchestrateur.orchestrateur.generer_code")
@patch("src.agent_orchestrateur.orchestrateur.generer_architecture")
@patch("src.agent_orchestrateur.orchestrateur.generer_user_stories")
def test_pipeline_echoue_apres_3_tentatives_backend(mock_po, mock_arch, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe, mock_dock):
    mock_dock.return_value = MagicMock()
    mock_arch.return_value = MagicMock()
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=2, tests_echoues=3, couverture_pct=40, succes=False, erreurs=["e1"])

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is False
    assert resultat["etape"] == "backend"
    assert resultat["tentative_backend"] == 3
    assert mock_corr.call_count == 2
    mock_fe.assert_not_called()


@patch("src.agent_orchestrateur.orchestrateur.generer_dockerisation")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests_frontend")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections_frontend")
@patch("src.agent_orchestrateur.orchestrateur.generer_frontend")
@patch("src.agent_orchestrateur.orchestrateur.lancer_tests")
@patch("src.agent_orchestrateur.orchestrateur.appliquer_corrections")
@patch("src.agent_orchestrateur.orchestrateur.generer_code")
@patch("src.agent_orchestrateur.orchestrateur.generer_architecture")
@patch("src.agent_orchestrateur.orchestrateur.generer_user_stories")
def test_pipeline_echoue_apres_3_tentatives_frontend(mock_po, mock_arch, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe, mock_dock):
    mock_dock.return_value = MagicMock()
    mock_arch.return_value = MagicMock()
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
