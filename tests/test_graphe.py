from src.agent_orchestrateur.etat import MAX_TENTATIVES
from src.agent_orchestrateur.graphe import construire_graphe, schema_markdown, FICHIER_SCHEMA, LIMITE_RECURSION
from src.agent_orchestrateur.orchestrateur import executer_pipeline, executer_pipeline_en_direct
from src.agent_orchestrateur.routage import continuer_ou_abandonner, router_qa_backend, router_qa_frontend, router_validation_docker
from src.common.schemas import RapportValidationDocker
from tests.sorties import BESOIN, QA_OK, QA_KO, FE_OK, FE_KO, DOCKER_KO, PLAN_TESTS


# --- Routeurs : fonctions pures, aucun mock necessaire ---

def test_continuer_ou_abandonner():
    assert continuer_ou_abandonner({}) == "continuer"
    assert continuer_ou_abandonner({"erreur": "RuntimeError : boom"}) == "abandon"


def test_routeurs_qa_abandonnent_si_plantage():
    plantage = {"erreur": "RuntimeError : boom"}
    assert router_qa_backend(plantage) == "abandon"
    assert router_qa_frontend(plantage) == "abandon"
    assert router_validation_docker(plantage) == "abandon"


def test_router_qa_backend():
    assert router_qa_backend({"rapport_backend": QA_OK, "tentative_backend": 1}) == "ok"
    assert router_qa_backend({"rapport_backend": QA_KO, "tentative_backend": 1}) == "corriger"
    # derniere tentative : une revision des tests par le Test Agent, puis abandon
    assert router_qa_backend({"rapport_backend": QA_KO, "tentative_backend": MAX_TENTATIVES,
                              "plan_tests": PLAN_TESTS}) == "reviser_tests"
    assert router_qa_backend({"rapport_backend": QA_KO, "tentative_backend": MAX_TENTATIVES,
                              "plan_tests": PLAN_TESTS, "tests_revises": True}) == "abandon"


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

    # Chaque noeud d'agent peut aller vers echec en cas de plantage
    plantages = {
        (n, "echec") for n in [
            "po", "architect", "test_agent", "developer", "correction_backend", "revision_tests", "frontend",
            "correction_frontend", "dockerization", "correction_docker",
        ]
    }
    assert {
        ("__start__", "po"), ("po", "architect"), ("architect", "test_agent"),
        ("test_agent", "developer"), ("developer", "qa_backend"),
        ("qa_backend", "frontend"), ("qa_backend", "correction_backend"), ("qa_backend", "echec"),
        ("qa_backend", "revision_tests"), ("revision_tests", "qa_backend"),
        ("correction_backend", "qa_backend"),
        ("frontend", "qa_frontend"),
        ("qa_frontend", "dockerization"), ("qa_frontend", "correction_frontend"), ("qa_frontend", "echec"),
        ("correction_frontend", "qa_frontend"),
        ("dockerization", "validation_docker"),
        ("validation_docker", "__end__"), ("validation_docker", "correction_docker"), ("validation_docker", "echec"),
        ("correction_docker", "validation_docker"),
        ("echec", "__end__"),
    } | plantages == aretes


def test_schema_docs_a_jour():
    """docs/pipeline.md doit correspondre au graphe : sinon lancer `make graphe`."""
    assert FICHIER_SCHEMA.read_text(encoding="utf-8") == schema_markdown()


# --- Pire cas : toutes les boucles vont jusqu'a la derniere tentative ---

def test_pire_cas_reste_sous_la_limite_de_recursion(agents):
    # backend et frontend ne reussissent qu'a la derniere tentative, docker echoue jusqu'au bout
    agents.lancer_tests.side_effect = [QA_KO] * (MAX_TENTATIVES - 1) + [QA_OK]
    agents.lancer_tests_frontend.side_effect = [FE_KO] * (MAX_TENTATIVES - 1) + [FE_OK]
    agents.valider_dockerisation.return_value = DOCKER_KO

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "docker"
    assert resultat["tentative_backend"] == MAX_TENTATIVES
    assert resultat["tentative_frontend"] == MAX_TENTATIVES
    assert resultat["tentative_docker"] == MAX_TENTATIVES
    noeuds_executes = 7 + 3 * (2 * MAX_TENTATIVES - 1) + 2 * MAX_TENTATIVES
    assert noeuds_executes < LIMITE_RECURSION


# --- Plantage d'un agent : le pipeline s'arrete proprement avec un rapport ---

def test_plantage_agent_renvoie_un_rapport(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "developer"
    assert resultat["erreur"] == "RuntimeError : credit Claude epuise"
    assert "architecture" in resultat
    agents.generer_frontend.assert_not_called()


def test_plantage_pendant_une_correction(agents):
    agents.lancer_tests.return_value = QA_KO
    agents.appliquer_corrections.side_effect = TimeoutError("trop long")

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "correction_backend"
    assert "trop long" in resultat["erreur"]
    assert agents.lancer_tests.call_count == 1
    agents.generer_frontend.assert_not_called()


# --- Execution en direct : un evenement par noeud termine ---

def test_execution_en_direct_suit_les_noeuds(agents):
    agents.lancer_tests.side_effect = [QA_KO, QA_OK]

    evenements = [(noeud, dict(etat)) for noeud, etat in executer_pipeline_en_direct(BESOIN)]

    assert [noeud for noeud, _ in evenements] == [
        "po", "architect", "test_agent", "developer", "qa_backend", "correction_backend", "qa_backend",
        "frontend", "qa_frontend", "dockerization", "validation_docker",
    ]
    # l'etat s'enrichit au fil des noeuds
    assert "architecture" not in evenements[0][1]
    assert "architecture" in evenements[1][1]
    assert evenements[-1][1]["succes"] is True
