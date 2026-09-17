"""Agent Orchestrateur — role de Controleur dans l'organisation MVC du projet.

Ce module ne produit aucun livrable lui-meme : il coordonne les agents du
Modele (Product Owner, Architect, Developer, QA backend, Frontend, QA frontend,
Dockerization) dans le bon ordre, gere les deux boucles de correction (backend
puis frontend), et renvoie le resultat final a la Vue (src/agent_form/app.py).

Chaque etape est journalisee (src/common/logging_config.py) en console ET
dans logs/pipeline.log, pour retrouver precisement ou un run s'est arrete
meme en cas de crash ou de fermeture du terminal.

Le dictionnaire retourne contient aussi la sortie de CHAQUE agent (pas
seulement les rapports QA), pour que la Vue affiche le detail agent par
agent, meme en cas d'echec en cours de route.
"""
import os

from src.common.schemas import BesoinUtilisateur
from src.common.logging_config import configurer_logging
from src.agent_po.product_owner import generer_user_stories
from src.agent_architect.architect import generer_architecture
from src.agent_dev.developer import generer_code, appliquer_corrections
from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend
from src.agent_dockerization.dockerization import generer_dockerisation

MAX_TENTATIVES = int(os.environ.get("MAX_TENTATIVES", 3))

logger = configurer_logging()


def executer_pipeline(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend"):
    logger.info("=== Nouveau run pour le projet '%s' ===", besoin.titre_projet)

    logger.info("[1/7] Product Owner Agent : demarrage")
    user_stories = generer_user_stories(besoin)
    logger.info("[1/7] Product Owner Agent : OK (%d User Stories)", len(user_stories.user_stories))

    logger.info("[2/7] Architect Agent : demarrage")
    architecture = generer_architecture(user_stories)
    logger.info("[2/7] Architect Agent : OK (stack : %s)", ", ".join(architecture.stack_technique))

    logger.info("[3/7] Developer Agent : demarrage")
    sortie_dev = generer_code(user_stories, dossier_backend, architecture=architecture)
    logger.info("[3/7] Developer Agent : OK (%d fichiers generes)", len(sortie_dev.fichiers_generes))

    rapport_backend = None
    for tentative_backend in range(1, MAX_TENTATIVES + 1):
        logger.info("[4/7] QA Agent backend : tentative %d/%d", tentative_backend, MAX_TENTATIVES)
        rapport_backend = lancer_tests(dossier_backend)
        if rapport_backend.succes:
            logger.info("[4/7] QA Agent backend : OK (%d tests passes, couverture %.1f%%)",
                        rapport_backend.tests_passes, rapport_backend.couverture_pct)
            break
        if tentative_backend == MAX_TENTATIVES:
            logger.error("[4/7] QA Agent backend : ECHEC definitif apres %d tentatives — %s",
                         MAX_TENTATIVES, rapport_backend.erreurs)
            return {
                "succes": False,
                "etape": "backend",
                "user_stories": user_stories,
                "architecture": architecture,
                "sortie_dev": sortie_dev,
                "rapport_backend": rapport_backend,
                "tentative_backend": tentative_backend,
            }
        logger.warning("[4/7] QA Agent backend : echec tentative %d — correction en cours — %s",
                       tentative_backend, rapport_backend.erreurs)
        sortie_dev = appliquer_corrections(rapport_backend.erreurs, dossier_backend)

    logger.info("[5/7] Frontend Agent : demarrage")
    sortie_frontend = generer_frontend(user_stories, dossier_backend, dossier_frontend)
    logger.info("[5/7] Frontend Agent : OK (%d fichiers generes)", len(sortie_frontend.fichiers_generes))

    rapport_frontend = None
    for tentative_frontend in range(1, MAX_TENTATIVES + 1):
        logger.info("[6/7] QA Agent frontend : tentative %d/%d", tentative_frontend, MAX_TENTATIVES)
        rapport_frontend = lancer_tests_frontend(dossier_frontend)
        if rapport_frontend.succes:
            logger.info("[6/7] QA Agent frontend : OK (%d fichiers verifies)", len(rapport_frontend.fichiers_verifies))
            logger.info("[7/7] Dockerization Agent : demarrage")
            rapport_dockerisation = generer_dockerisation(dossier_backend, dossier_frontend)
            logger.info("[7/7] Dockerization Agent : OK (%d fichiers generes)", len(rapport_dockerisation.fichiers_generes))
            logger.info("=== Run termine avec SUCCES pour '%s' ===", besoin.titre_projet)
            return {
                "succes": True,
                "user_stories": user_stories,
                "architecture": architecture,
                "sortie_dev": sortie_dev,
                "rapport_backend": rapport_backend,
                "sortie_frontend": sortie_frontend,
                "rapport_frontend": rapport_frontend,
                "rapport_dockerisation": rapport_dockerisation,
                "tentative_backend": tentative_backend,
                "tentative_frontend": tentative_frontend,
            }
        if tentative_frontend == MAX_TENTATIVES:
            logger.error("[6/7] QA Agent frontend : ECHEC definitif apres %d tentatives — %s",
                         MAX_TENTATIVES, rapport_frontend.erreurs)
            logger.info("=== Run termine en ECHEC (etape frontend) pour '%s' ===", besoin.titre_projet)
            return {
                "succes": False,
                "etape": "frontend",
                "user_stories": user_stories,
                "architecture": architecture,
                "sortie_dev": sortie_dev,
                "rapport_backend": rapport_backend,
                "sortie_frontend": sortie_frontend,
                "rapport_frontend": rapport_frontend,
                "tentative_backend": tentative_backend,
                "tentative_frontend": tentative_frontend,
            }
        logger.warning("[6/7] QA Agent frontend : echec tentative %d — correction en cours — %s",
                       tentative_frontend, rapport_frontend.erreurs)
        sortie_frontend = appliquer_corrections_frontend(rapport_frontend.erreurs, dossier_frontend)

    return {"succes": False}
