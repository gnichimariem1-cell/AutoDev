from pydantic import BaseModel, Field
from typing import Literal

class BesoinUtilisateur(BaseModel):
    """Sortie de l'Agent 1 (Formulaire)"""
    titre_projet: str
    description: str
    utilisateurs_cibles: str
    fonctionnalites_cles: list[str]
    contraintes_techniques: str = ""
    delai_souhaite: str = ""

class UserStory(BaseModel):
    id: str
    titre: str
    description: str
    criteres_acceptation: list[str]
    priorite: Literal["haute", "moyenne", "basse"]

class SortiePO(BaseModel):
    """Sortie de l'Agent 2 (Product Owner)"""
    user_stories: list[UserStory]

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