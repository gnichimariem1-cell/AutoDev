from unittest.mock import patch, MagicMock

from src.agent_orchestrateur.etat import MAX_TENTATIVES
from src.agent_orchestrateur.graphe import construire_graphe, LIMITE_RECURSION
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.agent_orchestrateur.routage import router_qa_backend, router_qa_frontend, router_validation_docker
from src.common.schemas import BesoinUtilisateur, RapportQA, RapportQAFrontend, RapportValidationDocker

QA_OK = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)
QA_KO = RapportQA(tests_passes=2, tests_echoues=3, couverture_pct=40, succes=False, erreurs=["e1"])
FE_OK = RapportQAFrontend(fichiers_verifies=["index.html"], succes=True)
FE_KO = RapportQAFrontend(fichiers_verifies=["index.html"], succes=False, erreurs=["erreur JS"])
DOCKER_KO = RapportValidationDocker(docker_disponible=True, succes=False, erreurs=["build : erreur"])


# --- Routeurs : fonctions pures, aucun mock necessaire ---

def test_router_qa_backend():
    assert router_qa_backend({"rapport_backend": QA_OK, "tentative_backend": 1}) == "ok"
    assert router_qa_backend({"rapport_backend": QA_KO, "tentative_backend": 1}) == "corriger"
    assert router_qa_backend({"rapport_backend": QA_KO, "tentative_backend": MAX_TENTATIVES}) == "abandon"


def test_router_qa_frontend():
    assert router_qa_frontend({"rapport_frontend": FE_OK, "tentative_frontend": 1}) == "ok"
    assert router_qa_frontend({"rapport_frontend": FE_KO, "tentative_frontend": 1}) == "corriger"
    assert router_qa_frontend({"rapport_frontend": FE_KO, "tentative_frontend": MAX_TENTATIVES}) == "abandon"


def test_router_validation_docker():
    non_joignable = RapportValidationDocker(docker_disponible=False, succes=False)
    ok = RapportValidationDocker(docker_disponible=True, succes=True)
    port_occupe = RapportValidationDocker(docker_disponible=True, succes=False, erreur_environnement=True)

    assert router_validation_docker({"rapport_validation_docker": ok, "tentative_docker": 1}) == "ok"
    assert router_validation_docker({"rapport_validation_docker": non_joignable, "tentative_docker": 1}) == "ok"
    assert router_validation_docker({"rapport_validation_docker": port_occupe, "tentative_docker": 1}) == "abandon"
    assert router_validation_docker({"rapport_validation_docker": DOCKER_KO, "tentative_docker": 1}) == "corriger"
    assert router_validation_docker({"rapport_validation_docker": DOCKER_KO, "tentative_docker": MAX_TENTATIVES}) == "abandon"


# --- Structure du graphe ---

def test_structure_du_graphe():
    graphe = construire_graphe().get_graph()
    aretes = {(a.source, a.target) for a in graphe.edges}

    assert {
        ("__start__", "po"), ("po", "architect"), ("architect", "developer"),
        ("developer", "qa_backend"),
        ("qa_backend", "frontend"), ("qa_backend", "correction_backend"), ("qa_backend", "echec"),
        ("correction_backend", "qa_backend"),
        ("frontend", "qa_frontend"),
        ("qa_frontend", "dockerization"), ("qa_frontend", "correction_frontend"), ("qa_frontend", "echec"),
        ("correction_frontend", "qa_frontend"),
        ("dockerization", "validation_docker"),
        ("validation_docker", "__end__"), ("validation_docker", "correction_docker"), ("validation_docker", "echec"),
        ("correction_docker", "validation_docker"),
        ("echec", "__end__"),
    } == aretes


# --- Pire cas : toutes les boucles vont jusqu'a la derniere tentative ---

@patch("src.agent_orchestrateur.noeuds.valider_dockerisation", return_value=DOCKER_KO)
@patch("src.agent_orchestrateur.noeuds.appliquer_corrections_dockerisation")
@patch("src.agent_orchestrateur.noeuds.generer_dockerisation")
@patch("src.agent_orchestrateur.noeuds.lancer_tests_frontend")
@patch("src.agent_orchestrateur.noeuds.appliquer_corrections_frontend")
@patch("src.agent_orchestrateur.noeuds.generer_frontend")
@patch("src.agent_orchestrateur.noeuds.lancer_tests")
@patch("src.agent_orchestrateur.noeuds.appliquer_corrections")
@patch("src.agent_orchestrateur.noeuds.generer_code")
@patch("src.agent_orchestrateur.noeuds.generer_architecture")
@patch("src.agent_orchestrateur.noeuds.generer_user_stories")
def test_pire_cas_reste_sous_la_limite_de_recursion(mock_po, mock_arch, mock_dev, mock_corr, mock_qa, mock_fe, mock_corr_fe, mock_qa_fe, mock_dock, mock_corr_dock, mock_valid_dock):
    mock_po.return_value = MagicMock()
    mock_arch.return_value = MagicMock()
    mock_dock.return_value = MagicMock()
    # backend et frontend ne reussissent qu'a la derniere tentative, docker echoue jusqu'au bout
    mock_qa.side_effect = [QA_KO] * (MAX_TENTATIVES - 1) + [QA_OK]
    mock_qa_fe.side_effect = [FE_KO] * (MAX_TENTATIVES - 1) + [FE_OK]

    besoin = BesoinUtilisateur(titre_projet="x", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])
    resultat = executer_pipeline(besoin)

    assert resultat["succes"] is False
    assert resultat["etape"] == "docker"
    assert resultat["tentative_backend"] == MAX_TENTATIVES
    assert resultat["tentative_frontend"] == MAX_TENTATIVES
    assert resultat["tentative_docker"] == MAX_TENTATIVES
    noeuds_executes = 6 + 3 * (2 * MAX_TENTATIVES - 1)
    assert noeuds_executes < LIMITE_RECURSION
