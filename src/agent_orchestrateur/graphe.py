"""Assemblage du graphe LangGraph du pipeline :

START -> po -> architect -> test_agent -> developer -> qa_backend -> frontend -> qa_frontend
      -> dockerization -> validation_docker -> END

Chaque QA a trois sorties (voir routage.py) : "ok" vers l'etape suivante,
"corriger" vers son noeud de correction (qui reboucle sur le QA), "abandon"
vers le noeud echec. Les autres noeuds continuent vers le suivant, ou vont
vers echec si leur agent a plante.

Le schema du graphe est exporte dans docs/pipeline.md :
    python -m src.agent_orchestrateur.graphe   (ou : make graphe)
"""
from pathlib import Path

from langgraph.graph import StateGraph, START, END

from src.agent_orchestrateur.etat import EtatPipeline, MAX_TENTATIVES
from src.agent_orchestrateur import noeuds
from src.agent_orchestrateur.routage import (
    continuer_ou_abandonner, router_qa_backend, router_qa_frontend, router_validation_docker,
)

# Nombre de noeuds executes dans le pire cas : po, architect, test_agent,
# developer, frontend, dockerization, echec (7) + pour chacune des 3 boucles, MAX_TENTATIVES
# QA et MAX_TENTATIVES - 1 corrections. LangGraph s'arrete par defaut a 25 pas,
# ce qui serait depasse des MAX_TENTATIVES=4 : on calcule donc la limite.
LIMITE_RECURSION = 7 + 3 * (2 * MAX_TENTATIVES - 1) + 5

FICHIER_SCHEMA = Path("docs/pipeline.md")


def construire_graphe(checkpointer=None):
    graphe = StateGraph(EtatPipeline)

    graphe.add_node("po", noeuds.noeud_po)
    graphe.add_node("architect", noeuds.noeud_architect)
    graphe.add_node("test_agent", noeuds.noeud_test_agent)
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

    def enchainer(source: str, suivant: str):
        graphe.add_conditional_edges(source, continuer_ou_abandonner, {
            "continuer": suivant, "abandon": "echec",
        })

    graphe.add_edge(START, "po")
    enchainer("po", "architect")
    enchainer("architect", "test_agent")
    enchainer("test_agent", "developer")
    enchainer("developer", "qa_backend")

    graphe.add_conditional_edges("qa_backend", router_qa_backend, {
        "ok": "frontend", "corriger": "correction_backend", "abandon": "echec",
    })
    enchainer("correction_backend", "qa_backend")

    enchainer("frontend", "qa_frontend")
    graphe.add_conditional_edges("qa_frontend", router_qa_frontend, {
        "ok": "dockerization", "corriger": "correction_frontend", "abandon": "echec",
    })
    enchainer("correction_frontend", "qa_frontend")

    enchainer("dockerization", "validation_docker")
    graphe.add_conditional_edges("validation_docker", router_validation_docker, {
        "ok": END, "corriger": "correction_docker", "abandon": "echec",
    })
    enchainer("correction_docker", "validation_docker")

    graphe.add_edge("echec", END)

    return graphe.compile(checkpointer=checkpointer)


def schema_markdown() -> str:
    mermaid = construire_graphe().get_graph().draw_mermaid()
    return (
        "# Graphe du pipeline AutoDev\n\n"
        "Genere automatiquement depuis `src/agent_orchestrateur/graphe.py` : ne pas modifier a la main,\n"
        "relancer `make graphe` apres toute modification du graphe.\n\n"
        "- trait plein : enchainement inconditionnel\n"
        "- pointilles : decision du routage (`ok` / `corriger` / `abandon` / `continuer`)\n\n"
        f"```mermaid\n{mermaid}```\n"
    )


if __name__ == "__main__":
    FICHIER_SCHEMA.parent.mkdir(exist_ok=True)
    FICHIER_SCHEMA.write_text(schema_markdown(), encoding="utf-8")
    print(f"Schema ecrit dans {FICHIER_SCHEMA}")
