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

    if resultat["succes"]:
        rapport = resultat["rapport"]
        message = f"""✅ SUCCES — Backend genere en {resultat['tentative']} tentative(s)

Tests passes : {rapport.tests_passes}
Tests echoues : {rapport.tests_echoues}
Couverture de code : {rapport.couverture_pct:.1f}%

Le code source complet a ete genere dans le dossier : output/backend/
"""
    else:
        rapport = resultat.get("rapport")
        erreurs = "\n".join(rapport.erreurs) if rapport else "Erreur inconnue"
        message = f"""ECHEC apres {resultat.get('tentative', '?')} tentative(s)

Erreurs rencontrees :
{erreurs}
"""
    return message

demo = gr.Interface(
    fn=lancer_pipeline_complet,
    inputs=[
        gr.Textbox(label="Titre du projet", placeholder="Ex: Todo App"),
        gr.Textbox(label="Description", lines=3, placeholder="Decris ton projet en quelques phrases"),
        gr.Textbox(label="Utilisateurs cibles", placeholder="Ex: Etudiants, particuliers..."),
        gr.Textbox(label="Fonctionnalites cles (separees par virgules)", placeholder="login, creer tache, marquer terminee"),
        gr.Textbox(label="Structure du projet", lines=2, placeholder="Ex: pages/sections souhaitees, organisation generale (optionnel)"),
    ],
    outputs=gr.Textbox(label="Resultat du pipeline", lines=12),
    title="AutoDev — Generateur de backend automatique",
    description="Remplis le formulaire ci-dessous. Le pipeline va automatiquement generer un backend FastAPI complet, teste et pret a l'emploi (compte 3 a 10 minutes).",
)

if __name__ == "__main__":
    demo.launch()