"""Agent Orchestrateur — role de Controleur dans l'organisation MVC du projet.

Ce module ne produit aucun livrable lui-meme : il coordonne les agents du
Modele (Product Owner, Architect, Developer, QA backend, Frontend, QA frontend,
Dockerization, Docker Validation) dans le bon ordre, gere les boucles de
correction (backend, frontend puis Docker), et renvoie le resultat final a la
Vue (src/agent_form/app.py).

La coordination est un graphe LangGraph, decoupe en :
- etat.py    : l'etat partage entre les noeuds (EtatPipeline)
- noeuds.py  : un noeud par agent + noeuds de correction + noeud d'echec
- routage.py : les decisions apres chaque QA (ok / corriger / abandon)
- graphe.py  : l'assemblage des noeuds et des aretes

Chaque etape est journalisee (src/common/logging_config.py) en console ET
dans logs/pipeline.log, pour retrouver precisement ou un run s'est arrete
meme en cas de crash ou de fermeture du terminal.

Le dictionnaire retourne (l'etat final du graphe) contient la sortie de CHAQUE
agent atteint (pas seulement les rapports QA), pour que la Vue affiche le
detail agent par agent, meme en cas d'echec en cours de route.
"""
from src.common.schemas import BesoinUtilisateur
from src.common.logging_config import configurer_logging
from src.agent_orchestrateur.graphe import construire_graphe, LIMITE_RECURSION

logger = configurer_logging()

GRAPHE = construire_graphe()


def executer_pipeline(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend", dossier_docker="output"):
    logger.info("=== Nouveau run pour le projet '%s' ===", besoin.titre_projet)

    etat_final = GRAPHE.invoke(
        {
            "besoin": besoin,
            "dossier_backend": dossier_backend,
            "dossier_frontend": dossier_frontend,
            "dossier_docker": dossier_docker,
            "succes": True,
        },
        config={"recursion_limit": LIMITE_RECURSION},
    )

    if etat_final["succes"]:
        logger.info("=== Run termine avec SUCCES pour '%s' ===", besoin.titre_projet)
    return etat_final
