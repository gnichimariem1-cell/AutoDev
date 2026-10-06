"""Sauvegarde de l'etat du pipeline (checkpointing LangGraph) apres chaque noeud,
dans une base SQLite. Permet de reprendre un run apres un plantage (credit
Claude epuise, Ollama arrete, application fermee...) sans refaire les etapes
deja reussies — et donc sans repayer les appels Claude correspondants.

Emplacement de la base : variable d'environnement CHECKPOINT_DB
(defaut : checkpoints/pipeline.sqlite ; ":memory:" pour les tests).
"""
import os
import sqlite3
from pathlib import Path

from pydantic import BaseModel
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

import src.common.schemas as schemas

CHEMIN_PAR_DEFAUT = "checkpoints/pipeline.sqlite"

# Types que la base a le droit de recreer a la lecture. LangGraph bloquera
# bientot les types non declares (avertissement "Deserializing unregistered
# type") : on autorise explicitement tous les schemas Pydantic du projet.
TYPES_AUTORISES = [
    (schemas.__name__, nom) for nom, classe in vars(schemas).items()
    if isinstance(classe, type) and issubclass(classe, BaseModel) and classe is not BaseModel
]


def creer_checkpointer() -> SqliteSaver:
    chemin = os.environ.get("CHECKPOINT_DB", CHEMIN_PAR_DEFAUT)
    if chemin != ":memory:":
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False : Gradio execute chaque requete dans un thread
    # different ; SqliteSaver protege lui-meme ses acces par un verrou.
    connexion = sqlite3.connect(chemin, check_same_thread=False)
    return SqliteSaver(connexion, serde=JsonPlusSerializer(allowed_msgpack_modules=TYPES_AUTORISES))
