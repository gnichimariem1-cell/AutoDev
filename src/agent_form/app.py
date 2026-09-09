import gradio as gr
from src.common.schemas import BesoinUtilisateur
from src.orchestrator import executer_pipeline

def collecter_besoin(titre, description, utilisateurs, fonctionnalites, structure):
    besoin = BesoinUtilisateur(
        titre_projet=titre,
        description=description,
        utilisateurs_cibles=utilisateurs,
        fonctionnalites_cles=[f.strip() for f in fonctionnalites.split(",") if f.strip()],
        structure_projet=structure,
    )
    return besoin

def lancer_pipeline_complet(titre, description, utilisateurs, fonctionnalites, structure):
    besoin = collecter_besoin(titre, description, utilisateurs, fonctionnalites, structure)

    resultat = executer_pipeline(besoin)

    user_stories = resultat.get("user_stories")
    user_stories_json = user_stories.model_dump_json(indent=2) if user_stories else "{}"

    if resultat["succes"]:
        rapport_be = resultat["rapport_backend"]
        rapport_fe = resultat["rapport_frontend"]
        message = f"""✅ SUCCES — Backend + Frontend generes

Backend (tentative {resultat['tentative_backend']}) :
  Tests passes : {rapport_be.tests_passes}
  Tests echoues : {rapport_be.tests_echoues}
  Couverture de code : {rapport_be.couverture_pct:.1f}%

Frontend (tentative {resultat['tentative_frontend']}) :
  Fichiers verifies : {len(rapport_fe.fichiers_verifies)}
  Statut : OK

Code source genere dans : output/backend/ et output/frontend/
"""
    else:
        etape = resultat.get("etape", "?")
        rapport = resultat.get("rapport_frontend") if etape == "frontend" else resultat.get("rapport_backend")
        erreurs = "\n".join(rapport.erreurs) if rapport else "Erreur inconnue"
        message = f"""ECHEC a l'etape "{etape}"

Erreurs rencontrees :
{erreurs}
"""
    return message, user_stories_json

demo = gr.Interface(
    fn=lancer_pipeline_complet,
    inputs=[
        gr.Textbox(label="Titre du projet", placeholder="Ex: Todo App 1"),
        gr.Textbox(label="Description", lines=3, placeholder="Decris ton projet en quelques phrases"),
        gr.Textbox(label="Utilisateurs cibles", placeholder="Ex: Etudiants, particuliers..."),
        gr.Textbox(label="Fonctionnalites cles (separees par virgules)", placeholder="login, creer tache, marquer terminee"),
        gr.Textbox(label="Structure du projet", lines=2, placeholder="Ex: pages/sections souhaitees, organisation generale (optionnel)"),
    ],
    outputs=[
        gr.Textbox(label="Resultat du pipeline", lines=12),
        gr.Code(label="User Stories (JSON)", language="json", lines=20),
    ],
    title="AutoDev — Generateur de backend et frontend automatique",
    description="Remplis le formulaire ci-dessous. Le pipeline va automatiquement generer un backend FastAPI et un frontend web, testes et prets a l'emploi (compte 3 a 10 minutes).",
)

if __name__ == "__main__":
    demo.launch()