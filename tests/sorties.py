"""Sorties d'agents realistes (vrais objets Pydantic) pour les tests de
l'orchestrateur : l'etat du graphe est sauvegarde apres chaque noeud, il doit
donc contenir des objets serialisables (pas de MagicMock)."""
from src.common.schemas import (
    BesoinUtilisateur, SortiePO, UserStory, SortieArchitecte, SortieDev, RapportQA,
    SortieFrontend, RapportQAFrontend, SortieDockerization, RapportValidationDocker,
    SortieTestAgent, CasDeTest, SortieAgentE2E, ScenarioE2E, RapportE2E, EchecE2E,
)

BESOIN = BesoinUtilisateur(titre_projet="Todo App", description="y", utilisateurs_cibles="z", fonctionnalites_cles=["a"])

USER_STORIES = SortiePO(user_stories=[UserStory(
    id="US1", titre="Creer une tache", description="...", criteres_acceptation=["ok"], priorite="haute",
)])
ARCHITECTURE = SortieArchitecte(stack_technique=["FastAPI"], structure_modules=["app/main.py"], justification="...")
PLAN_TESTS = SortieTestAgent(cas=[CasDeTest(
    id="T01", user_story="US1", scenario="Creer une tache valide", methode="POST", route="/tasks",
    code_attendu=201, resultat_attendu="tache creee",
)], fichiers_tests=["output/backend/tests/test_taches.py"])
SORTIE_DEV = SortieDev(fichiers_generes=["app/main.py"], resume_technique="backend genere")
SORTIE_FRONTEND = SortieFrontend(fichiers_generes=["index.html"], resume_technique="frontend genere")
SORTIE_DOCKER = SortieDockerization(fichiers_generes=["Dockerfile"], resume_technique="docker genere")

QA_OK = RapportQA(tests_passes=5, tests_echoues=0, couverture_pct=90, succes=True)
QA_KO = RapportQA(tests_passes=2, tests_echoues=3, couverture_pct=40, succes=False, erreurs=["e1"])
FE_OK = RapportQAFrontend(fichiers_verifies=["index.html"], succes=True)
FE_KO = RapportQAFrontend(fichiers_verifies=["index.html"], succes=False, erreurs=["erreur JS"])
DOCKER_OK = RapportValidationDocker(docker_disponible=True, succes=True)
DOCKER_KO = RapportValidationDocker(docker_disponible=True, succes=False, erreurs=["build : erreur"])
PLAN_E2E = SortieAgentE2E(scenarios=[
    ScenarioE2E(id="E01", user_story="US1", description="Creer une tache par l'API"),
    ScenarioE2E(id="E02", user_story="US1", description="Titre vide refuse"),
], fichiers=["output/e2e/test_api_e2e.py"])
E2E_OK = RapportE2E(docker_disponible=True, succes=True, total=2, reussis=2)
E2E_KO = RapportE2E(docker_disponible=True, succes=False, total=2, reussis=1, echecs=[
    EchecE2E(id="E02", test="test_api_e2e.py::test_E02", message="attendu 422, obtenu 201")],
    erreurs=["E02 : attendu 422, obtenu 201"])
