from pydantic import BaseModel, Field
from typing import Literal

class BesoinUtilisateur(BaseModel):
    """Sortie du Formulaire utilisateur"""
    titre_projet: str
    description: str
    utilisateurs_cibles: str
    fonctionnalites_cles: list[str]
    structure_projet: str = ""
    # True : le Product Owner a juge la demande claire avant le lancement (ou l'utilisateur
    # a choisi un de ses scenarios) ; le pipeline ne la reverifie pas
    demande_verifiee: bool = False
    # Trace pour le rapport : demande d'origine et scenario choisi, vide sinon
    origine: str = ""

# Champs de BesoinUtilisateur propres a AutoDev, jamais envoyes aux agents
CHAMPS_SUIVI_BESOIN = {"demande_verifiee", "origine"}


class ScenarioDemande(BaseModel):
    """Une interpretation precise d'une demande ambigue, proposee par le Product Owner"""
    titre_projet: str
    description: str
    utilisateurs_cibles: str
    fonctionnalites_cles: list[str]
    difference: str = ""  # en une phrase : ce qui distingue ce scenario des autres
    nom_court: str = ""   # 2 a 4 mots qui le distinguent des autres (boutons du formulaire)

class AnalyseDemande(BaseModel):
    """Analyse de la demande par le Product Owner, avant le lancement du run"""
    clarte: Literal["claire", "ambigue", "vague"]
    manques: list[str] = []
    questions: list[str] = []
    scenarios: list[ScenarioDemande] = []

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
    # Un code HTTP (201), plusieurs codes possibles ("201/409"), ou rien ("-")
    code_attendu: int | str | None = None
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
    # "application" ou "scenario" ; vide : deduite du message (voir agent_e2e.cause_de_l_echec)
    cause: str = ""

class CaptureE2E(BaseModel):
    """Preuves d'un scenario d'interface : capture de fin et video (chemins depuis la racine d'AutoDev)"""
    id: str
    image: str = ""
    video: str = ""
    etapes: list[str] = []  # captures aux etapes cles (fixture etape("nom")), dans l'ordre

class EssaiE2E(BaseModel):
    """Un essai des Tests E2E : resultat et scenarios en echec (message court, qui corrige)"""
    numero: int
    reussis: int = 0
    total: int = 0
    echecs: list[EchecE2E] = []  # message raccourci ; cause = "Agent E2E", "Developer" ou "Frontend"


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
    # Scenarios ignores (pytest.skip) : ils n'ont rien verifie, le message donne la raison
    ignores: list[EchecE2E] = []
    # Captures et videos des scenarios d'interface (navigateur Chromium)
    captures: list[CaptureE2E] = []
    remarque: str = ""
    # Tous les essais de ce run, dans l'ordre (le dernier est ce rapport)
    essais: list[EssaiE2E] = []