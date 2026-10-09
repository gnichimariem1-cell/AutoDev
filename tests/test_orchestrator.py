from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.common.schemas import RapportValidationDocker
from tests.sorties import BESOIN, QA_KO, FE_KO, DOCKER_KO


def test_pipeline_reussit_du_premier_coup(agents):
    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is True
    assert resultat["tentative_backend"] == 1
    assert resultat["tentative_frontend"] == 1
    agents.appliquer_corrections.assert_not_called()
    agents.appliquer_corrections_frontend.assert_not_called()


def test_pipeline_echoue_apres_3_tentatives_backend(agents):
    agents.lancer_tests.return_value = QA_KO

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "backend"
    assert resultat["tentative_backend"] == 3
    # 3 tentatives, revision des tests par le Test Agent, puis 3 nouvelles tentatives
    agents.reviser_tests.assert_called_once()
    assert resultat["tests_revises"] is True
    assert agents.lancer_tests.call_count == 6
    assert agents.appliquer_corrections.call_count == 4
    agents.generer_frontend.assert_not_called()


def test_pipeline_echoue_apres_3_tentatives_frontend(agents):
    agents.lancer_tests_frontend.return_value = FE_KO

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "frontend"
    assert resultat["tentative_frontend"] == 3
    assert agents.appliquer_corrections_frontend.call_count == 2
    agents.generer_frontend.assert_called_once()


def test_pipeline_echoue_apres_3_tentatives_docker(agents):
    agents.valider_dockerisation.return_value = DOCKER_KO

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "docker"
    assert resultat["tentative_docker"] == 3
    assert agents.appliquer_corrections_dockerisation.call_count == 2


def test_pipeline_reussit_si_docker_non_joignable(agents):
    agents.valider_dockerisation.return_value = RapportValidationDocker(docker_disponible=False, succes=False)

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is True
    assert resultat["rapport_validation_docker"].docker_disponible is False
    agents.valider_dockerisation.assert_called_once()
    agents.appliquer_corrections_dockerisation.assert_not_called()


def test_pipeline_ne_corrige_pas_une_erreur_environnement_docker(agents):
    agents.valider_dockerisation.return_value = RapportValidationDocker(
        docker_disponible=True, succes=False, erreurs=["ports : 8000 occupe"], erreur_environnement=True
    )

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "docker"
    assert resultat["tentative_docker"] == 1
    agents.appliquer_corrections_dockerisation.assert_not_called()
