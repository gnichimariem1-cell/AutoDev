import json
import requests
from src.common.schemas import BesoinUtilisateur, SortiePO

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3"

PROMPT_TEMPLATE = """Tu es un Product Owner. À partir du besoin ci-dessous, génère des User Stories
au format JSON STRICT (rien d'autre que le JSON), avec ce schéma :
{{"user_stories": [{{"id": "US1", "titre": "...", "description": "...",
"criteres_acceptation": ["..."], "priorite": "haute|moyenne|basse"}}]}}

Besoin :
{besoin_json}
"""

def generer_user_stories(besoin: BesoinUtilisateur) -> SortiePO:
    prompt = PROMPT_TEMPLATE.format(besoin_json=besoin.model_dump_json(indent=2))
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }, timeout=300)
    response.raise_for_status()
    contenu = response.json()["response"]
    return SortiePO.model_validate(json.loads(contenu))