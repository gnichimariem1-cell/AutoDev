"""Etat partage du graphe LangGraph : remplace les variables locales de l'ancien
executer_pipeline(). Chaque noeud lit cet etat et renvoie uniquement les cles
qu'il modifie ; LangGraph les fusionne dans l'etat.

Les cles de sortie sont EXACTEMENT celles que la Vue (src/agent_form/app.py)
lit dans le resultat : l'etat final est renvoye tel quel a la Vue.
"""
import os
from typing import TypedDict

from src.common.schemas import (
    BesoinUtilisateur, SortiePO, SortieArchitecte, SortieDev, RapportQA,
    SortieFrontend, RapportQAFrontend, SortieDockerization, RapportValidationDocker,
    SortieTestAgent,
)

MAX_TENTATIVES = int(os.environ.get("MAX_TENTATIVES", 3))


class EtatPipeline(TypedDict, total=False):
    # Entrees (fournies par executer_pipeline)
    id_run: str  # identifiant du run, sert a le reprendre apres un plantage
    besoin: BesoinUtilisateur
    dossier_backend: str
    dossier_frontend: str
    dossier_docker: str

    # Sorties des agents
    user_stories: SortiePO
    architecture: SortieArchitecte
    plan_tests: SortieTestAgent
    # Contenu des tests ecrits par le Test Agent : tout changement par un autre agent est annule
    tests_originaux: dict[str, str]
    # Le Test Agent a deja revise ses tests une fois (apres l'echec de toutes les corrections)
    tests_revises: bool
    sortie_dev: SortieDev
    rapport_backend: RapportQA
    sortie_frontend: SortieFrontend
    rapport_frontend: RapportQAFrontend
    rapport_dockerisation: SortieDockerization
    rapport_validation_docker: RapportValidationDocker

    # Compteurs des boucles de correction
    tentative_backend: int
    tentative_frontend: int
    tentative_docker: int

    # Resultat : succes, et en cas d'echec l'etape ou le pipeline s'est arrete :
    # - echec de QA apres MAX_TENTATIVES : "backend", "frontend" ou "docker"
    # - plantage d'un agent (exception) : le nom du noeud, ex "developer",
    #   et le message dans "erreur"
    succes: bool
    etape: str
    erreur: str
