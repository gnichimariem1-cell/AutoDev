import gradio as gr
import json
from src.common.schemas import BesoinUtilisateur

def collecter_besoin(titre, description, utilisateurs, fonctionnalites, contraintes, delai):
    besoin = BesoinUtilisateur(
        titre_projet=titre,
        description=description,
        utilisateurs_cibles=utilisateurs,
        fonctionnalites_cles=[f.strip() for f in fonctionnalites.split(",") if f.strip()],
        contraintes_techniques=contraintes,
        delai_souhaite=delai,
    )
    return besoin.model_dump_json(indent=2)

demo = gr.Interface(
    fn=collecter_besoin,
    inputs=[
        gr.Textbox(label="Titre du projet"),
        gr.Textbox(label="Description", lines=3),
        gr.Textbox(label="Utilisateurs cibles"),
        gr.Textbox(label="Fonctionnalités clés (séparées par virgules)"),
        gr.Textbox(label="Contraintes techniques"),
        gr.Textbox(label="Délai souhaité"),
    ],
    outputs=gr.Textbox(label="JSON structuré du besoin"),
    title="Agent 1 — Formulaire utilisateur",
)

if __name__ == "__main__":
    demo.launch()