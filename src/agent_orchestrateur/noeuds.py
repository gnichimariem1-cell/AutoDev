"""Noeuds du graphe LangGraph : un noeud par agent du Modele, plus un noeud de
correction par boucle et un noeud d'echec final.

Chaque noeud appelle l'agent existant (aucun agent n'est modifie) et renvoie
uniquement les cles de l'etat qu'il met a jour. Les decisions (continuer,
corriger, abandonner) ne sont PAS prises ici mais dans routage.py.

Chaque noeud d'agent est protege par @_proteger : si l'agent leve une exception
(Ollama injoignable, credit Claude epuise, timeout...), le pipeline ne plante
pas ; l'erreur est placee dans l'etat et le routage envoie vers le noeud echec,
pour que la Vue affiche quand meme le rapport detaille.
"""
import functools
import os
import subprocess
import time

import requests

from src.common.logging_config import configurer_logging
from src.agent_po.product_owner import generer_user_stories
from src.agent_architect.architect import generer_architecture
from src.agent_dev.developer import generer_code, appliquer_corrections
from src.agent_test.testeur import generer_plan_et_tests, reviser_tests, lire_tests, restaurer_tests
from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend
from src.agent_dockerization.dockerization import generer_dockerisation, appliquer_corrections_dockerisation
from src.agent_validation_docker.validation_docker import valider_dockerisation
from src.agent_e2e.e2e import (
    generer_tests_e2e, executer_tests_e2e, dossier_e2e, lire_tests_e2e, restaurer_tests_e2e,
    cause_de_l_echec, consignes_de_correction, corriger_scenarios_e2e,
)
from src.common.schemas import SortieAgentE2E, RapportE2E, EchecE2E
from src.agent_orchestrateur.etat import EtatPipeline, MAX_TENTATIVES

logger = configurer_logging()


# Relance automatique d'un agent en cas d'erreur PASSAGERE (timeout, coupure
# reseau, Claude surcharge) : ESSAIS_AGENT essais au total, attente croissante.
# Une erreur DURABLE (credit epuise, cle invalide...) n'est pas relancee :
# le run part vers echec et peut etre repris avec le bouton "Reprendre".
ESSAIS_AGENT = max(1, int(os.environ.get("ESSAIS_AGENT", 2)))
ATTENTE_RELANCE = float(os.environ.get("ATTENTE_RELANCE", 10))

ERREURS_PASSAGERES = (
    TimeoutError,
    ConnectionError,
    subprocess.TimeoutExpired,
    requests.ConnectionError,
    requests.Timeout,
)
MOTS_ERREUR_PASSAGERE = ("overloaded", "rate limit", "rate_limit", "529", "503", "temporarily unavailable")


def est_erreur_passagere(e: Exception) -> bool:
    if isinstance(e, ERREURS_PASSAGERES):
        return True
    message = str(e).lower()
    return any(mot in message for mot in MOTS_ERREUR_PASSAGERE)


def _proteger(nom_noeud: str):
    def decorateur(noeud):
        @functools.wraps(noeud)
        def noeud_protege(etat: EtatPipeline) -> dict:
            for essai in range(1, ESSAIS_AGENT + 1):
                try:
                    return noeud(etat)
                except Exception as e:
                    if est_erreur_passagere(e) and essai < ESSAIS_AGENT:
                        attente = ATTENTE_RELANCE * essai
                        logger.warning("Noeud %s : erreur passagere (%s : %s), relance automatique %d/%d dans %.0f s",
                                       nom_noeud, type(e).__name__, e, essai + 1, ESSAIS_AGENT, attente)
                        time.sleep(attente)
                        continue
                    logger.exception("Plantage du noeud %s (essai %d/%d)", nom_noeud, essai, ESSAIS_AGENT)
                    return {"etape": nom_noeud, "erreur": f"{type(e).__name__} : {e}"}
        return noeud_protege
    return decorateur


@_proteger("po")
def noeud_po(etat: EtatPipeline) -> dict:
    logger.info("[1/9] Product Owner Agent : demarrage")
    user_stories = generer_user_stories(etat["besoin"])
    logger.info("[1/9] Product Owner Agent : OK (%d User Stories)", len(user_stories.user_stories))
    return {"user_stories": user_stories}


@_proteger("architect")
def noeud_architect(etat: EtatPipeline) -> dict:
    logger.info("[2/9] Architect Agent : demarrage")
    architecture = generer_architecture(etat["user_stories"])
    logger.info("[2/9] Architect Agent : OK (stack : %s)", ", ".join(architecture.stack_technique))
    return {"architecture": architecture}


@_proteger("test_agent")
def noeud_test_agent(etat: EtatPipeline) -> dict:
    logger.info("[3/9] Test Agent : demarrage (plan de test et tests ecrits avant le code)")
    plan = generer_plan_et_tests(etat["user_stories"], etat["dossier_backend"], architecture=etat.get("architecture"))
    logger.info("[3/9] Test Agent : OK (%d cas de test, %d fichiers)", len(plan.cas), len(plan.fichiers_tests))
    return {"plan_tests": plan, "tests_originaux": lire_tests(etat["dossier_backend"])}


@_proteger("developer")
def noeud_developer(etat: EtatPipeline) -> dict:
    logger.info("[4/9] Developer Agent : demarrage")
    sortie_dev = generer_code(etat["user_stories"], etat["dossier_backend"], architecture=etat["architecture"])
    logger.info("[4/9] Developer Agent : OK (%d fichiers generes)", len(sortie_dev.fichiers_generes))
    return {"sortie_dev": sortie_dev}


@_proteger("qa_backend")
def noeud_qa_backend(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_backend", 0) + 1
    logger.info("[5/9] QA Agent backend : tentative %d/%d", tentative, MAX_TENTATIVES)
    # Les tests appartiennent au Test Agent : si un autre agent les a modifies,
    # supprimes ou en a ajoute, on remet les originaux avant de les lancer.
    touches = restaurer_tests(etat["dossier_backend"], etat["tests_originaux"]) if etat.get("tests_originaux") else []
    rapport = lancer_tests(etat["dossier_backend"])
    if touches:
        logger.warning("[5/9] QA Agent backend : tests modifies par la correction, originaux restaures : %s", touches)
        rapport = rapport.model_copy(update={"succes": False, "erreurs": rapport.erreurs + [
            f"Les fichiers de tests ont ete modifies ({', '.join(touches)}) : ils ont ete restaures. "
            "Ne touche pas aux tests, corrige uniquement le code de l'application."]})
    if rapport.succes:
        logger.info("[5/9] QA Agent backend : OK (%d tests passes, couverture %.1f%%)",
                    rapport.tests_passes, rapport.couverture_pct)
    return {"rapport_backend": rapport, "tentative_backend": tentative, "etape": "backend"}


@_proteger("correction_backend")
def noeud_correction_backend(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_backend"]
    logger.warning("[5/9] QA Agent backend : echec tentative %d — correction en cours — %s",
                   etat["tentative_backend"], rapport.erreurs)
    return {"sortie_dev": appliquer_corrections(rapport.erreurs, etat["dossier_backend"])}


@_proteger("revision_tests")
def noeud_revision_tests(etat: EtatPipeline) -> dict:
    """Le code a ete corrige MAX_TENTATIVES fois sans succes : le Test Agent
    verifie si ce sont ses tests qui sont faux. Une seule revision par run ;
    le Developer a ensuite de nouveau MAX_TENTATIVES essais."""
    rapport = etat["rapport_backend"]
    logger.warning("[5/9] QA Agent backend : echec apres %d tentatives — revision des tests par le Test Agent — %s",
                   etat["tentative_backend"], rapport.erreurs)
    plan = reviser_tests(rapport.erreurs, etat["dossier_backend"], etat["plan_tests"])
    return {"plan_tests": plan, "tests_originaux": lire_tests(etat["dossier_backend"]),
            "tests_revises": True, "tentative_backend": 0}


@_proteger("frontend")
def noeud_frontend(etat: EtatPipeline) -> dict:
    logger.info("[6/9] Frontend Agent : demarrage")
    sortie_frontend = generer_frontend(
        etat["user_stories"], etat["dossier_backend"], etat["dossier_frontend"],
        architecture=etat.get("architecture"), organisation_interface=etat["besoin"].structure_projet,
    )
    logger.info("[6/9] Frontend Agent : OK (%d fichiers generes)", len(sortie_frontend.fichiers_generes))
    return {"sortie_frontend": sortie_frontend}


@_proteger("qa_frontend")
def noeud_qa_frontend(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_frontend", 0) + 1
    logger.info("[7/9] QA Agent frontend : tentative %d/%d", tentative, MAX_TENTATIVES)
    rapport = lancer_tests_frontend(etat["dossier_frontend"])
    if rapport.succes:
        logger.info("[7/9] QA Agent frontend : OK (%d fichiers verifies)", len(rapport.fichiers_verifies))
    return {"rapport_frontend": rapport, "tentative_frontend": tentative, "etape": "frontend"}


@_proteger("correction_frontend")
def noeud_correction_frontend(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_frontend"]
    logger.warning("[7/9] QA Agent frontend : echec tentative %d — correction en cours — %s",
                   etat["tentative_frontend"], rapport.erreurs)
    return {"sortie_frontend": appliquer_corrections_frontend(rapport.erreurs, etat["dossier_frontend"])}


@_proteger("dockerization")
def noeud_dockerization(etat: EtatPipeline) -> dict:
    logger.info("[8/9] Dockerization Agent : demarrage")
    rapport = generer_dockerisation(etat["dossier_backend"], etat["dossier_frontend"], etat["dossier_docker"])
    logger.info("[8/9] Dockerization Agent : OK (%d fichiers generes)", len(rapport.fichiers_generes))
    return {"rapport_dockerisation": rapport}


@_proteger("validation_docker")
def noeud_validation_docker(etat: EtatPipeline) -> dict:
    tentative = etat.get("tentative_docker", 0) + 1
    logger.info("[9/9] Docker Validation Agent : tentative %d/%d", tentative, MAX_TENTATIVES)
    rapport = valider_dockerisation(etat["dossier_docker"])
    if not rapport.docker_disponible:
        logger.warning("[9/9] Docker Validation Agent : Docker non joignable, validation ignoree")
    elif rapport.succes:
        logger.info("[9/9] Docker Validation Agent : OK (build, demarrage et services verifies)")
    return {"rapport_validation_docker": rapport, "tentative_docker": tentative, "etape": "docker"}


@_proteger("correction_docker")
def noeud_correction_docker(etat: EtatPipeline) -> dict:
    rapport = etat["rapport_validation_docker"]
    logger.warning("[9/9] Docker Validation Agent : echec tentative %d — correction en cours — %s",
                   etat["tentative_docker"], rapport.erreurs)
    return {"rapport_dockerisation": appliquer_corrections_dockerisation(rapport.erreurs, etat["dossier_docker"])}


def e2e_actif() -> bool:
    """Tests E2E actives (par defaut). E2E_ACTIF=0 dans .env pour les desactiver."""
    return os.environ.get("E2E_ACTIF", "1").strip().lower() not in ("0", "non", "false", "no")


def _demande_complete(besoin) -> str:
    return (f"Titre : {besoin.titre_projet}\nDescription : {besoin.description}\n"
            f"Utilisateurs : {besoin.utilisateurs_cibles}\n"
            f"Fonctionnalites : {', '.join(besoin.fonctionnalites_cles)}\nInterface : {besoin.structure_projet}")


@_proteger("generation_e2e")
def noeud_generation_e2e(etat: EtatPipeline) -> dict:
    """L'Agent E2E ecrit des scenarios qui utilisent l'application comme un vrai utilisateur (API et navigateur)."""
    validation = etat.get("rapport_validation_docker")
    if not e2e_actif():
        logger.info("[E2E] Agent E2E : desactive (E2E_ACTIF=0 dans .env)")
        return {"plan_e2e": SortieAgentE2E(active=False)}
    if validation is not None and not validation.docker_disponible:
        logger.warning("[E2E] Agent E2E : Docker non joignable, scenarios non ecrits")
        return {"plan_e2e": SortieAgentE2E(active=False)}
    logger.info("[E2E] Agent E2E : demarrage (scenarios API et navigateur)")
    dossier = dossier_e2e(etat["dossier_docker"])
    plan = generer_tests_e2e(etat["user_stories"], _demande_complete(etat["besoin"]),
                             etat["dossier_backend"], dossier, dossier_frontend=etat["dossier_frontend"])
    logger.info("[E2E] Agent E2E : OK (%d scenarios)", len(plan.scenarios))
    # Version de reference des scenarios : un autre agent ne pourra pas les modifier
    return {"plan_e2e": plan, "e2e_originaux": lire_tests_e2e(dossier)}


# Erreurs du lancement de l'application : envoyees au Developer comme un scenario en echec
DEBUTS_ERREUR_DEMARRAGE = ("demarrage de l'application", "l'application ne repond pas")


def _controles_apres_correction(etat: EtatPipeline, maj: dict) -> list[EchecE2E]:
    """Apres une correction, les controles d'avant (tests unitaires du Test Agent, QA
    frontend) doivent toujours passer. Renvoie les echecs a corriger."""
    echecs = []
    if etat.get("tests_originaux"):
        restaurer_tests(etat["dossier_backend"], etat["tests_originaux"])
    qa = lancer_tests(etat["dossier_backend"])
    maj["rapport_backend"] = qa
    if not qa.succes:
        echecs.append(EchecE2E(id="tests unitaires", type="api", test="backend/tests/", cause="application",
                               message="Les tests unitaires du backend ne passent plus apres la correction :\n"
                                       + "\n".join(qa.erreurs)[-1500:]))
    qa_front = lancer_tests_frontend(etat["dossier_frontend"])
    maj["rapport_frontend"] = qa_front
    if not qa_front.succes:
        echecs.append(EchecE2E(id="QA frontend", type="interface", test="frontend/", cause="application",
                               message="Le controle du frontend echoue apres la correction :\n"
                                       + "\n".join(qa_front.erreurs)[-1500:]))
    return echecs


@_proteger("e2e")
def noeud_e2e(etat: EtatPipeline) -> dict:
    """AutoDev demarre l'application et joue les scenarios E2E (sans IA)."""
    tentative = etat.get("tentative_e2e", 0) + 1
    plan = etat.get("plan_e2e")
    if plan is None or not plan.active:
        raison = "desactives (E2E_ACTIF=0)" if not e2e_actif() else "non effectues : Docker n'est pas joignable"
        return {"rapport_e2e": RapportE2E(docker_disponible=False, succes=False, erreurs=[f"Tests E2E {raison}."]),
                "tentative_e2e": tentative}
    dossier = dossier_e2e(etat["dossier_docker"])
    maj = {"tentative_e2e": tentative}
    # Les scenarios appartiennent a l'Agent E2E : si un autre agent les a modifies, on remet la reference
    touches = restaurer_tests_e2e(dossier, etat["e2e_originaux"]) if etat.get("e2e_originaux") else []
    if touches:
        logger.warning("[E2E] scenarios modifies par une correction, version de reference restauree : %s", touches)
    if tentative > 1:
        echecs = _controles_apres_correction(etat, maj)
        if echecs:
            precedent = etat["rapport_e2e"]
            logger.warning("[E2E] controles en echec apres la correction : %s", [e.id for e in echecs])
            maj["rapport_e2e"] = RapportE2E(
                docker_disponible=True, succes=False, total=precedent.total, reussis=precedent.reussis,
                echecs=echecs, erreurs=[f"{e.id} : {e.message}" for e in echecs],
                navigateur=precedent.navigateur, remarque=precedent.remarque)
            return maj
    logger.info("[E2E] Tests E2E : tentative %d/%d (demarrage de l'application et des scenarios)",
                tentative, MAX_TENTATIVES)
    rapport = executer_tests_e2e(etat["dossier_docker"], dossier)
    if (rapport.docker_disponible and not rapport.succes and not rapport.echecs
            and not rapport.erreur_environnement and rapport.erreurs
            and rapport.erreurs[0].startswith(DEBUTS_ERREUR_DEMARRAGE)):
        rapport = rapport.model_copy(update={"echecs": [EchecE2E(
            id="demarrage", type="api", test="docker compose up", cause="application",
            message="\n".join(rapport.erreurs)[-1500:])]})
    if not rapport.docker_disponible:
        logger.warning("[E2E] Tests E2E : non effectues (%s)", " ".join(rapport.erreurs))
    elif rapport.succes:
        logger.info("[E2E] Tests E2E : OK (%d/%d scenarios)", rapport.reussis, rapport.total)
    else:
        logger.warning("[E2E] Tests E2E : %d/%d scenarios reussis — %s",
                       rapport.reussis, rapport.total, [e.id for e in rapport.echecs])
    if rapport.erreur_environnement:
        logger.warning("[E2E] Tests E2E : probleme sur la machine — %s", " ".join(rapport.erreurs))
        maj["etape"] = "e2e"
    maj["rapport_e2e"] = rapport
    return maj


@_proteger("correction_e2e")
def noeud_correction_e2e(etat: EtatPipeline) -> dict:
    """Chaque scenario en echec part vers celui qui peut le corriger :
    - le code du scenario plante -> l'Agent E2E corrige son scenario ;
    - l'application ne fait pas ce qui est attendu -> Developer (API) ou Frontend Agent (interface)."""
    rapport = etat["rapport_e2e"]
    groupes = {"scenario": [], "api": [], "interface": []}
    for echec in rapport.echecs:
        groupes["scenario" if cause_de_l_echec(echec) == "scenario" else echec.type].append(echec)
    logger.warning("[E2E] Tests E2E : echec tentative %d/%d — correction en cours — scenarios : %s, API : %s, "
                   "interface : %s", etat["tentative_e2e"], MAX_TENTATIVES,
                   *([e.id for e in groupes[g]] for g in ("scenario", "api", "interface")))
    maj = {}
    if groupes["scenario"]:
        dossier = dossier_e2e(etat["dossier_docker"])
        corriger_scenarios_e2e(groupes["scenario"], dossier, etat["dossier_backend"], etat["dossier_frontend"])
        maj["e2e_originaux"] = lire_tests_e2e(dossier)  # nouvelle version de reference, ecrite par l'Agent E2E
    if groupes["api"]:
        maj["sortie_dev"] = appliquer_corrections(consignes_de_correction(groupes["api"], "api"),
                                                  etat["dossier_backend"])
    if groupes["interface"]:
        maj["sortie_frontend"] = appliquer_corrections_frontend(
            consignes_de_correction(groupes["interface"], "interface"), etat["dossier_frontend"])
    return maj


# Pour chaque etape pouvant echouer : (cle du rapport, cle du compteur)
_RAPPORTS_PAR_ETAPE = {
    "backend": ("rapport_backend", "tentative_backend"),
    "frontend": ("rapport_frontend", "tentative_frontend"),
    "docker": ("rapport_validation_docker", "tentative_docker"),
    "e2e": ("rapport_e2e", "tentative_e2e"),
}


def noeud_echec(etat: EtatPipeline) -> dict:
    etape = etat["etape"]
    if etat.get("erreur"):
        logger.error("PLANTAGE de l'etape %s — %s", etape, etat["erreur"])
    else:
        cle_rapport, cle_tentative = _RAPPORTS_PAR_ETAPE[etape]
        logger.error("ECHEC definitif a l'etape %s (tentative %d/%d) — %s",
                     etape, etat[cle_tentative], MAX_TENTATIVES, etat[cle_rapport].erreurs)
    logger.info("=== Run termine en ECHEC (etape %s) pour '%s' ===", etape, etat["besoin"].titre_projet)
    return {"succes": False}
