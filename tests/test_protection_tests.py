"""Protection des tests generes : une correction ne doit pas faire passer le QA
en supprimant ou en modifiant les tests du backend."""
from unittest.mock import patch, MagicMock

from src.agent_dev.developer import appliquer_corrections
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.common.schemas import RapportQA
from tests.sorties import BESOIN, QA_KO

# 3 tests au lieu de 5 : des tests ont disparu, meme si tout "passe"
QA_OK_MOINS_DE_TESTS = RapportQA(tests_passes=3, tests_echoues=0, couverture_pct=90, succes=True)
QA_OK_TOUS_LES_TESTS = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)


@patch("src.agent_dev.developer.subprocess.run")
def test_prompt_de_correction_interdit_de_toucher_aux_tests(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    appliquer_corrections(["test_login echoue"], dossier_sortie=str(tmp_path))
    prompt = mock_run.call_args.kwargs["input"]
    assert "Ne modifie PAS et ne supprime PAS les fichiers de tests" in prompt


def test_tests_supprimes_refuses_puis_vraie_correction(agents):
    agents.lancer_tests.side_effect = [QA_KO, QA_OK_MOINS_DE_TESTS, QA_OK_TOUS_LES_TESTS]

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is True
    assert agents.lancer_tests.call_count == 3
    assert agents.appliquer_corrections.call_count == 2
    erreurs_envoyees = agents.appliquer_corrections.call_args_list[1].args[0]
    assert any("nombre de tests a diminue (5 -> 3)" in e for e in erreurs_envoyees)


def test_tests_supprimes_a_chaque_fois_echec(agents):
    agents.lancer_tests.side_effect = [QA_KO, QA_OK_MOINS_DE_TESTS, QA_OK_MOINS_DE_TESTS]

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "backend"
    agents.generer_frontend.assert_not_called()


def test_meme_nombre_de_tests_accepte(agents):
    agents.lancer_tests.side_effect = [QA_KO, QA_OK_TOUS_LES_TESTS]

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is True
    assert agents.lancer_tests.call_count == 2