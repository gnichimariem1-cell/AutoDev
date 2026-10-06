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

executer_pipeline_en_direct() renvoie l'etat apres chaque noeud (progression
en direct dans la Vue) ; executer_pipeline() renvoie seulement l'etat final.

Le dictionnaire retourne (l'etat final du graphe) contient la sortie de CHAQUE
agent atteint (pas seulement les rapports QA), pour que la Vue affiche le
detail agent par agent, meme en cas d'echec en cours de route.
"""
from src.common.schemas import BesoinUtilisateur
from src.common.logging_config import configurer_logging
from src.agent_orchestrateur.graphe import construire_graphe, LIMITE_RECURSION

logger = configurer_logging()

GRAPHE = construire_graphe()


def executer_pipeline_en_direct(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend", dossier_docker="output"):
    """Execute le pipeline et renvoie (nom du noeud termine, etat courant) apres
    CHAQUE noeud, pour que la Vue affiche la progression en direct. Le dernier
    etat produit est l'etat final."""
    logger.info("=== Nouveau run pour le projet '%s' ===", besoin.titre_projet)

    etat = {
        "besoin": besoin,
        "dossier_backend": dossier_backend,
        "dossier_frontend": dossier_frontend,
        "dossier_docker": dossier_docker,
        "succes": True,
    }
    # stream_mode="updates" : chaque evenement contient les cles modifiees par
    # le noeud ; l'etat n'ayant pas de reducer, les fusionner suffit a obtenir
    # l'etat complet (identique a celui renvoye par GRAPHE.invoke).
    for evenement in GRAPHE.stream(dict(etat), config={"recursion_limit": LIMITE_RECURSION}, stream_mode="updates"):
        for noeud, mise_a_jour in evenement.items():
            etat.update(mise_a_jour or {})
            yield noeud, etat

    if etat["succes"]:
        logger.info("=== Run termine avec SUCCES pour '%s' ===", besoin.titre_projet)


def executer_pipeline(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend", dossier_docker="output"):
    """Execute le pipeline jusqu'au bout et renvoie l'etat final."""
    etat = None
    for _, etat in executer_pipeline_en_direct(besoin, dossier_backend, dossier_frontend, dossier_docker):
        pass
    return etat
