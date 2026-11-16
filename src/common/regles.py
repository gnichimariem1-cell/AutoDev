"""Regles des agents : un fichier Markdown par agent dans le dossier regles/ du projet.

Chaque agent lit son fichier et l'ajoute a sa consigne : les regles se lisent et se modifient
sur GitHub sans toucher au code Python. Voir regles/README.md.
"""
from pathlib import Path

DOSSIER_REGLES = Path(__file__).resolve().parents[2] / "regles"
AGENTS = ("product_owner", "architect", "test_agent", "developer", "frontend", "dockerization", "agent_e2e")


def regles_de(agent: str, **valeurs) -> str:
    """Texte de regles/<agent>.md ; {nom} est remplace par la valeur donnee (ex : dossier_frontend)."""
    texte = (DOSSIER_REGLES / f"{agent}.md").read_text(encoding="utf-8")
    for nom, valeur in valeurs.items():
        texte = texte.replace("{" + nom + "}", str(valeur))
    return texte


def bloc_regles(agent: str, **valeurs) -> str:
    """Bloc a ajouter a la consigne de l'agent."""
    return f"\n\nRegles a respecter (fichier regles/{agent}.md) :\n{regles_de(agent, **valeurs)}\n"
