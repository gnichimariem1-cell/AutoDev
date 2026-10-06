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

Chaque nouveau run part d'un dossier de sortie vide : les fichiers du run
precedent sont deplaces dans archives/<id du run precedent>/ (archiver_sorties).
Une reprise, elle, garde le dossier tel quel.

L'etat est sauvegarde apres chaque noeud (sauvegarde.py). Un run qui a plante
peut etre repris avec reprendre_pipeline_en_direct(id_run) : il repart du noeud
qui a plante, sans refaire les etapes deja reussies.

Le dictionnaire retourne (l'etat final du graphe) contient la sortie de CHAQUE
agent atteint (pas seulement les rapports QA), pour que la Vue affiche le
detail agent par agent, meme en cas d'echec en cours de route.
"""
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.common.schemas import BesoinUtilisateur
from src.common.logging_config import configurer_logging
from src.agent_orchestrateur.graphe import construire_graphe, LIMITE_RECURSION
from src.agent_orchestrateur.sauvegarde import creer_checkpointer

logger = configurer_logging()

GRAPHE = construire_graphe(checkpointer=creer_checkpointer())


class RepriseImpossible(Exception):
    """Le run demande n'existe pas ou n'a pas plante (termine normalement)."""


def nouvel_id_run(besoin: BesoinUtilisateur) -> str:
    """Ex : "todo-app-20261005-142530-3f9a" — lisible et unique."""
    slug = re.sub(r"[^a-z0-9]+", "-", besoin.titre_projet.lower()).strip("-")[:30] or "projet"
    return f"{slug}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"


DOSSIER_ARCHIVES = "archives"
# Fichier ecrit dans le dossier de sortie pour savoir a quel run il appartient
FICHIER_ID_RUN = ".id_run"


def archiver_sorties(dossier: str, id_run: str) -> Path | None:
    """Deplace le contenu de dossier (sorties du run precedent) dans
    archives/<id du run precedent>/, puis recree dossier vide, marque avec id_run.
    Sans cela, chaque run ecrit par-dessus les fichiers des precedents (ex : deux
    migrations Alembic "0001" en conflit, anciens tests relances par le QA).
    Retourne le dossier d'archive, ou None si dossier etait absent ou vide."""
    sortie = Path(dossier)
    archive = None
    if sortie.is_dir() and any(sortie.iterdir()):
        marqueur = sortie / FICHIER_ID_RUN
        nom = (marqueur.read_text().strip() if marqueur.exists() else
               f"{sortie.name}-{datetime.fromtimestamp(sortie.stat().st_mtime):%Y%m%d-%H%M%S}")
        archive = Path(DOSSIER_ARCHIVES) / nom
        if archive.exists():
            archive = archive.with_name(f"{nom}-{uuid.uuid4().hex[:4]}")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sortie), str(archive))
        logger.info("Sorties du run precedent archivees dans %s", archive)
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / FICHIER_ID_RUN).write_text(id_run)
    return archive


def _config(id_run: str) -> dict:
    return {"configurable": {"thread_id": id_run}, "recursion_limit": LIMITE_RECURSION}


def _suivre(entree, config: dict, etat: dict):
    """Execute le graphe et renvoie (noeud termine, etat courant) apres chaque noeud.
    stream_mode="updates" : chaque evenement contient les cles modifiees par le
    noeud ; l'etat n'ayant pas de reducer, les fusionner suffit a obtenir l'etat
    complet (identique a celui renvoye par GRAPHE.invoke)."""
    for evenement in GRAPHE.stream(entree, config=config, stream_mode="updates"):
        for noeud, mise_a_jour in evenement.items():
            etat.update(mise_a_jour or {})
            yield noeud, etat

    if etat["succes"]:
        logger.info("=== Run termine avec SUCCES pour '%s' ===", etat["besoin"].titre_projet)


def executer_pipeline_en_direct(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend", dossier_docker="output"):
    """Execute le pipeline et renvoie (nom du noeud termine, etat courant) apres
    CHAQUE noeud, pour que la Vue affiche la progression en direct. Le dernier
    etat produit est l'etat final."""
    id_run = nouvel_id_run(besoin)
    logger.info("=== Nouveau run '%s' pour le projet '%s' ===", id_run, besoin.titre_projet)
    # dossier_docker contient dossier_backend et dossier_frontend (par defaut)
    archiver_sorties(dossier_docker, id_run)

    etat = {
        "id_run": id_run,
        "besoin": besoin,
        "dossier_backend": dossier_backend,
        "dossier_frontend": dossier_frontend,
        "dossier_docker": dossier_docker,
        "succes": True,
    }
    yield from _suivre(dict(etat), _config(id_run), etat)


def executer_pipeline(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend", dossier_docker="output"):
    """Execute le pipeline jusqu'au bout et renvoie l'etat final."""
    etat = None
    for _, etat in executer_pipeline_en_direct(besoin, dossier_backend, dossier_frontend, dossier_docker):
        pass
    return etat


def point_de_reprise(id_run: str):
    """Renvoie la sauvegarde a partir de laquelle reprendre le run id_run :
    - application arretee en plein noeud : la derniere sauvegarde (son noeud
      suivant n'a jamais termine) ;
    - agent qui a plante : la derniere sauvegarde AVANT le plantage (sans
      "erreur"), dont le noeud suivant est celui qui a plante.
    Leve RepriseImpossible si le run est inconnu ou s'est termine sans plantage
    (succes, ou echec de QA apres MAX_TENTATIVES : le relancer ne changerait rien)."""
    config = {"configurable": {"thread_id": id_run}}
    derniere = GRAPHE.get_state(config)
    if not derniere.values:
        raise RepriseImpossible(f"Aucun run '{id_run}' dans les sauvegardes.")
    if derniere.next:
        return derniere
    if not derniere.values.get("erreur"):
        raise RepriseImpossible(f"Le run '{id_run}' s'est termine sans plantage : rien a reprendre.")
    for sauvegarde in GRAPHE.get_state_history(config):
        if sauvegarde.next and not sauvegarde.values.get("erreur"):
            return sauvegarde
    raise RepriseImpossible(f"Aucun point de reprise trouve pour le run '{id_run}'.")


def reprendre_pipeline_en_direct(id_run: str):
    """Reprend le run id_run a partir de point_de_reprise() ; meme format de
    sortie que executer_pipeline_en_direct()."""
    sauvegarde = point_de_reprise(id_run)
    logger.info("=== Reprise du run '%s' a l'etape %s ===", id_run, ", ".join(sauvegarde.next))
    marqueur = Path(sauvegarde.values["dossier_docker"]) / FICHIER_ID_RUN
    if marqueur.exists() and marqueur.read_text().strip() != id_run:
        logger.warning(
            "Le dossier %s contient les sorties du run '%s', pas de '%s' : celles de '%s' "
            "sont dans %s/%s/.", sauvegarde.values["dossier_docker"], marqueur.read_text().strip(),
            id_run, id_run, DOSSIER_ARCHIVES, id_run,
        )
    config = dict(sauvegarde.config, recursion_limit=LIMITE_RECURSION)
    yield from _suivre(None, config, dict(sauvegarde.values))
