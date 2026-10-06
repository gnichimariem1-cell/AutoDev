"""Decisions du graphe (aretes conditionnelles) : apres chaque QA, continuer
("ok"), demander une correction ("corriger") ou abandonner ("abandon").

Fonctions pures (aucun appel d'agent, aucun effet de bord) : testables seules.
"""
from src.agent_orchestrateur.etat import EtatPipeline, MAX_TENTATIVES


def router_qa_backend(etat: EtatPipeline) -> str:
    if etat["rapport_backend"].succes:
        return "ok"
    if etat["tentative_backend"] >= MAX_TENTATIVES:
        return "abandon"
    return "corriger"


def router_qa_frontend(etat: EtatPipeline) -> str:
    if etat["rapport_frontend"].succes:
        return "ok"
    if etat["tentative_frontend"] >= MAX_TENTATIVES:
        return "abandon"
    return "corriger"


def router_validation_docker(etat: EtatPipeline) -> str:
    rapport = etat["rapport_validation_docker"]
    # Docker non joignable : validation ignoree, le pipeline reste en succes
    if not rapport.docker_disponible or rapport.succes:
        return "ok"
    # Erreur de la machine (ex : port occupe) : inutile de demander une correction
    if rapport.erreur_environnement or etat["tentative_docker"] >= MAX_TENTATIVES:
        return "abandon"
    return "corriger"
