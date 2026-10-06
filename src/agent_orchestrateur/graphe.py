"""Assemblage du graphe LangGraph du pipeline :

START -> po -> architect -> developer -> qa_backend -> frontend -> qa_frontend
      -> dockerization -> validation_docker -> END

Chaque QA a trois sorties (voir routage.py) : "ok" vers l'etape suivante,
"corriger" vers son noeud de correction (qui reboucle sur le QA), "abandon"
vers le noeud echec.
"""
from langgraph.graph import StateGraph, START, END

from src.agent_orchestrateur.etat import EtatPipeline, MAX_TENTATIVES
from src.agent_orchestrateur import noeuds
from src.agent_orchestrateur.routage import router_qa_backend, router_qa_frontend, router_validation_docker

# Nombre de noeuds executes dans le pire cas : po, architect, developer,
# frontend, dockerization, echec (6) + pour chacune des 3 boucles, MAX_TENTATIVES
# QA et MAX_TENTATIVES - 1 corrections. LangGraph s'arrete par defaut a 25 pas,
# ce qui serait depasse des MAX_TENTATIVES=4 : on calcule donc la limite.
LIMITE_RECURSION = 6 + 3 * (2 * MAX_TENTATIVES - 1) + 5


def construire_graphe():
    graphe = StateGraph(EtatPipeline)

    graphe.add_node("po", noeuds.noeud_po)
    graphe.add_node("architect", noeuds.noeud_architect)
    graphe.add_node("developer", noeuds.noeud_developer)
    graphe.add_node("qa_backend", noeuds.noeud_qa_backend)
    graphe.add_node("correction_backend", noeuds.noeud_correction_backend)
    graphe.add_node("frontend", noeuds.noeud_frontend)
    graphe.add_node("qa_frontend", noeuds.noeud_qa_frontend)
    graphe.add_node("correction_frontend", noeuds.noeud_correction_frontend)
    graphe.add_node("dockerization", noeuds.noeud_dockerization)
    graphe.add_node("validation_docker", noeuds.noeud_validation_docker)
    graphe.add_node("correction_docker", noeuds.noeud_correction_docker)
    graphe.add_node("echec", noeuds.noeud_echec)

    graphe.add_edge(START, "po")
    graphe.add_edge("po", "architect")
    graphe.add_edge("architect", "developer")
    graphe.add_edge("developer", "qa_backend")

    graphe.add_conditional_edges("qa_backend", router_qa_backend, {
        "ok": "frontend", "corriger": "correction_backend", "abandon": "echec",
    })
    graphe.add_edge("correction_backend", "qa_backend")

    graphe.add_edge("frontend", "qa_frontend")
    graphe.add_conditional_edges("qa_frontend", router_qa_frontend, {
        "ok": "dockerization", "corriger": "correction_frontend", "abandon": "echec",
    })
    graphe.add_edge("correction_frontend", "qa_frontend")

    graphe.add_edge("dockerization", "validation_docker")
    graphe.add_conditional_edges("validation_docker", router_validation_docker, {
        "ok": END, "corriger": "correction_docker", "abandon": "echec",
    })
    graphe.add_edge("correction_docker", "validation_docker")

    graphe.add_edge("echec", END)

    return graphe.compile()
