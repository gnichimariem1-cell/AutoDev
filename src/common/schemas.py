from pydantic import BaseModel, Field
from typing import Literal

class BesoinUtilisateur(BaseModel):
    """Sortie du Formulaire utilisateur"""
    titre_projet: str
    description: str
    utilisateurs_cibles: str
    fonctionnalites_cles: list[str]
    structure_projet: str = ""

class UserStory(BaseModel):
    id: str
    titre: str
    description: str
    criteres_acceptation: list[str]
    priorite: Literal["haute", "moyenne", "basse"]

class SortiePO(BaseModel):
    """Sortie de l'Agent 2 (Product Owner)"""
    user_stories: list[UserStory]

class SortieArchitecte(BaseModel):
    """Sortie de l'Architect Agent"""
    stack_technique: list[str]
    structure_modules: list[str]
    justification: str

class CasDeTest(BaseModel):
    """Un cas du plan de test ecrit par le Test Agent"""
    id: str
    user_story: str
    scenario: str
    methode: str
    route: str
    code_attendu: int
    resultat_attendu: str
    priorite: str = "haute"

class SortieTestAgent(BaseModel):
    """Sortie du Test Agent : le plan de test et les fichiers de tests ecrits"""
    cas: list[CasDeTest]
    fichiers_tests: list[str] = []

class SortieDev(BaseModel):
    """Sortie de l'Agent 3 (Developer)"""
    fichiers_generes: list[str]
    resume_technique: str

class RapportQA(BaseModel):
    """Sortie de l'Agent 4 (QA)"""
    tests_passes: int
    tests_echoues: int
    couverture_pct: float
    succes: bool
    erreurs: list[str] = []

class SortieFrontend(BaseModel):
    """Sortie de l'Agent Frontend"""
    fichiers_generes: list[str]
    resume_technique: str

class RapportQAFrontend(BaseModel):
    """Sortie de la verification QA du frontend"""
    fichiers_verifies: list[str]
    succes: bool
    erreurs: list[str] = []

class SortieDockerization(BaseModel):
    """Sortie du Dockerization Agent"""
    fichiers_generes: list[str]
    resume_technique: str

class EtapeValidationDocker(BaseModel):
    """Une etape de la validation Docker (config, build, demarrage, services)"""
    nom: str
    succes: bool
    details: str = ""

class RapportValidationDocker(BaseModel):
    """Sortie du Docker Validation Agent"""
    docker_disponible: bool
    etapes: list[EtapeValidationDocker] = []
    succes: bool
    erreurs: list[str] = []
    # True si l'echec vient de la machine (ex : port deja occupe) et non de la
    # configuration generee : inutile alors de demander une correction a Claude.
    erreur_environnement: bool = False


class ScenarioE2E(BaseModel):
    """Un scenario ecrit par l'Agent E2E"""
    id: str
    type: str = "api"
    user_story: str = ""
    description: str = ""

class SortieAgentE2E(BaseModel):
    """Sortie de l'Agent E2E : les scenarios ecrits dans <output>/e2e/"""
    scenarios: list[ScenarioE2E] = []
    fichiers: list[str] = []
    active: bool = True  # False : E2E desactive ou Docker non joignable

class EchecE2E(BaseModel):
    """Un scenario E2E en echec"""
    id: str
    type: str = "api"
    test: str = ""
    message: str = ""

class RapportE2E(BaseModel):
    """Resultat des scenarios E2E joues sur l'application demarree"""
    docker_disponible: bool
    succes: bool
    total: int = 0
    reussis: int = 0
    echecs: list[EchecE2E] = []
    erreurs: list[str] = []
    erreur_environnement: bool = False
    navigateur: bool = True  # False : Chromium absent, seuls les scenarios API ont ete lances
    remarque: str = ""