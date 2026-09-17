"""Agent Orchestrateur — role de Controleur dans l'organisation MVC du projet.

Ce module ne produit aucun livrable lui-meme : il coordonne les agents du
Modele (Product Owner, Architect, Developer, QA backend, Frontend, QA frontend,
Dockerization) dans le bon ordre, gere les deux boucles de correction (backend
puis frontend), et renvoie le resultat final a la Vue (src/agent_form/app.py).
"""
import os

from src.common.schemas import BesoinUtilisateur
from src.agent_po.product_owner import generer_user_stories
from src.agent_architect.architect import generer_architecture
from src.agent_dev.developer import generer_code, appliquer_corrections
from src.agent_frontend.frontend import generer_frontend, appliquer_corrections_frontend
from src.agent_qa.qa import lancer_tests, lancer_tests_frontend
from src.agent_dockerization.dockerization import generer_dockerisation

MAX_TENTATIVES = int(os.environ.get("MAX_TENTATIVES", 3))

def executer_pipeline(besoin: BesoinUtilisateur, dossier_backend="output/backend", dossier_frontend="output/frontend"):
    user_stories = generer_user_stories(besoin)
    architecture = generer_architecture(user_stories)
    generer_code(user_stories, dossier_backend, architecture=architecture)

    rapport_backend = None
    for tentative_backend in range(1, MAX_TENTATIVES + 1):
        rapport_backend = lancer_tests(dossier_backend)
        if rapport_backend.succes:
            break
        if tentative_backend == MAX_TENTATIVES:
            return {
                "succes": False,
                "etape": "backend",
                "user_stories": user_stories,
                "architecture": architecture,
                "rapport_backend": rapport_backend,
                "tentative_backend": tentative_backend,
            }
        appliquer_corrections(rapport_backend.erreurs, dossier_backend)

    generer_frontend(user_stories, dossier_backend, dossier_frontend)

    rapport_frontend = None
    for tentative_frontend in range(1, MAX_TENTATIVES + 1):
        rapport_frontend = lancer_tests_frontend(dossier_frontend)
        if rapport_frontend.succes:
            rapport_dockerisation = generer_dockerisation(dossier_backend, dossier_frontend)
            return {
                "succes": True,
                "user_stories": user_stories,
                "architecture": architecture,
                "rapport_backend": rapport_backend,
                "rapport_frontend": rapport_frontend,
                "rapport_dockerisation": rapport_dockerisation,
                "tentative_backend": tentative_backend,
                "tentative_frontend": tentative_frontend,
            }
        if tentative_frontend == MAX_TENTATIVES:
            return {
                "succes": False,
                "etape": "frontend",
                "user_stories": user_stories,
                "architecture": architecture,
                "rapport_backend": rapport_backend,
                "rapport_frontend": rapport_frontend,
                "tentative_backend": tentative_backend,
                "tentative_frontend": tentative_frontend,
            }
        appliquer_corrections_frontend(rapport_frontend.erreurs, dossier_frontend)

    return {"succes": False}
