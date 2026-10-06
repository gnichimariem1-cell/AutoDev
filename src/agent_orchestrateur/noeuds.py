"""Noeuds du graphe LangGraph : un noeud par agent du Modele, plus un noeud de
correction par boucle et un noeud d'echec final.

Chaque noeud appelle l'agent existant (aucun agent n'est modifie) et renvoie
uniquement les cles de l'etat qu'il met a jour. Les decisions (continuer,
corriger, abandonner) ne sont PAS prises ici mais dans routage.py.
"""
from src.common.logging_config import configurer_logging
from src.agent_po.product_owner import generer_user_stories
from src.agent_architect.architect import generer_architecture
from src.agent_dev.developer import generer_code, appliquer_corrections
from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend
from src.agent_dockerization.dockerization import generer_dockerisation, appliquer_corrections_dockerisation
from src.agent_validation_docker.validation_docker import valider_dockerisation
from src.agent_orchestrateur.etat import EtatPipeline, MAX_TENTATIVES

logger = configurer_logging()


def noeud_po(etat: EtatPipeline) -> dict:
    logger.info("[1/8] Product Owner Agent : demarrage")
    user_stories = generer_user_stories(etat["besoin"])
    logger.info("[1/8] Product Owner Agent : OK (%d User Stories)", len(user_stories.user_stories))
    return {"user_stories": user_stories}


def noeud_architect(etat: EtatPipeline) -> dict:
    logger.info("[2/8] Architect Agent : demarrage")
    architecture = generer_architecture(etat["user_stories"])
    logger.info("[2/8] Architect Agent : OK (stack : %s)", ", ".join(architecture.stack_technique))
    return {"architecture": architecture}


def noeud_developer(etat: EtatPipeline) -> dict:
    logger.info("[3/8] Developer Agent : demarrage")
    sortie_dev = generer_code(etat["user_stories"], etat["dossier_backend"], architecture=etat["architecture"])
    logger.info("[3/8] Developer Agent : OK (%d fichiers generes)", len(sortie_dev.fichiers_generes))
    return {"sortie_dev": sortie_dev}


def noeud_qa_backend(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_backend", 0) + 1
    logger.info("[4/8] QA Agent backend : tentative %d/%d", tentative, MAX_TENTATIVES)
    rapport = lancer_tests(etat["dossier_backend"])
    if rapport.succes:
        logger.info("[4/8] QA Agent backend : OK (%d tests passes, couverture %.1f%%)",
                    rapport.tests_passes, rapport.couverture_pct)
    return {"rapport_backend": rapport, "tentative_backend": tentative, "etape": "backend"}


def noeud_correction_backend(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_backend"]
    logger.warning("[4/8] QA Agent backend : echec tentative %d — correction en cours — %s",
                   etat["tentative_backend"], rapport.erreurs)
    return {"sortie_dev": appliquer_corrections(rapport.erreurs, etat["dossier_backend"])}


def noeud_frontend(etat: EtatPipeline) -> dict:
    logger.info("[5/8] Frontend Agent : demarrage")
    sortie_frontend = generer_frontend(etat["user_stories"], etat["dossier_backend"], etat["dossier_frontend"])
    logger.info("[5/8] Frontend Agent : OK (%d fichiers generes)", len(sortie_frontend.fichiers_generes))
    return {"sortie_frontend": sortie_frontend}


def noeud_qa_frontend(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_frontend", 0) + 1
    logger.info("[6/8] QA Agent frontend : tentative %d/%d", tentative, MAX_TENTATIVES)
    rapport = lancer_tests_frontend(etat["dossier_frontend"])
    if rapport.succes:
        logger.info("[6/8] QA Agent frontend : OK (%d fichiers verifies)", len(rapport.fichiers_verifies))
    return {"rapport_frontend": rapport, "tentative_frontend": tentative, "etape": "frontend"}


def noeud_correction_frontend(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_frontend"]
    logger.warning("[6/8] QA Agent frontend : echec tentative %d — correction en cours — %s",
                   etat["tentative_frontend"], rapport.erreurs)
    return {"sortie_frontend": appliquer_corrections_frontend(rapport.erreurs, etat["dossier_frontend"])}


def noeud_dockerization(etat: EtatPipeline) -> dict:
    logger.info("[7/8] Dockerization Agent : demarrage")
    rapport = generer_dockerisation(etat["dossier_backend"], etat["dossier_frontend"], etat["dossier_docker"])
    logger.info("[7/8] Dockerization Agent : OK (%d fichiers generes)", len(rapport.fichiers_generes))
    return {"rapport_dockerisation": rapport}


def noeud_validation_docker(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_docker", 0) + 1
    logger.info("[8/8] Docker Validation Agent : tentative %d/%d", tentative, MAX_TENTATIVES)
    rapport = valider_dockerisation(etat["dossier_docker"])
    if not rapport.docker_disponible:
        logger.warning("[8/8] Docker Validation Agent : Docker non joignable, validation ignoree")
    elif rapport.succes:
        logger.info("[8/8] Docker Validation Agent : OK (build, demarrage et services verifies)")
    return {"rapport_validation_docker": rapport, "tentative_docker": tentative, "etape": "docker"}


def noeud_correction_docker(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_validation_docker"]
    logger.warning("[8/8] Docker Validation Agent : echec tentative %d — correction en cours — %s",
                   etat["tentative_docker"], rapport.erreurs)
    return {"rapport_dockerisation": appliquer_corrections_dockerisation(rapport.erreurs, etat["dossier_docker"])}


# Pour chaque etape pouvant echouer : (cle du rapport, cle du compteur)
_RAPPORTS_PAR_ETAPE = {
    "backend": ("rapport_backend", "tentative_backend"),
    "frontend": ("rapport_frontend", "tentative_frontend"),
    "docker": ("rapport_validation_docker", "tentative_docker"),
}


def noeud_echec(etat: EtatPipeline) -> dict:
    etape = etat["etape"]
    cle_rapport, cle_tentative = _RAPPORTS_PAR_ETAPE[etape]
    logger.error("ECHEC definitif a l'etape %s (tentative %d/%d) — %s",
                 etape, etat[cle_tentative], MAX_TENTATIVES, etat[cle_rapport].erreurs)
    logger.info("=== Run termine en ECHEC (etape %s) pour '%s' ===", etape, etat["besoin"].titre_projet)
    return {"succes": False}
