from unittest.mock import patch, MagicMock
from src.orchestrator import executer_pipeline
from src.common.schemas import BesoinUtilisateur, RapportQA

@patch("src.orchestrator.lancer_tests")
@patch("src.orchestrator.appliquer_corrections")
@patch("src.orchestrator.generer_code")
@patch("src.orchestrator.generer_user_stories")
def test_pipeline_reussit_du_premier_coup(mock_po, mock_dev, mock_corr, mock_qa):
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is True
    assert resultat["tentative"] == 1
    mock_corr.assert_not_called()

@patch("src.orchestrator.lancer_tests")
@patch("src.orchestrator.appliquer_corrections")
@patch("src.orchestrator.generer_code")
@patch("src.orchestrator.generer_user_stories")
def test_pipeline_echoue_apres_3_tentatives(mock_po, mock_dev, mock_corr, mock_qa):
    mock_po.return_value = MagicMock()
    mock_qa.return_value = RapportQA(tests_passes=2, tests_echoues=3, couverture_pct=40, succes=False, erreurs=["e1"])

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is False
    assert resultat["tentative"] == 3
    assert mock_corr.call_count == 2