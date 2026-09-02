import json
import unicodedata
import requests
from src.common.schemas import BesoinUtilisateur, SortiePO

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3"

PROMPT_TEMPLATE = """Tu es un Product Owner. À partir du besoin ci-dessous, génère des User Stories
au format JSON STRICT (rien d'autre que le JSON), avec ce schéma EXACT (respecte precisement
les noms de champs, SANS accents) :
{{"user_stories": [{{"id": "US1", "titre": "...", "description": "...",
"criteres_acceptation": ["..."], "priorite": "haute|moyenne|basse"}}]}}

IMPORTANT : le champ se nomme "priorite" (sans accent), pas "priorité".

Besoin :
{besoin_json}
"""

def _retirer_accents(texte: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(c)
    )

def _normaliser_cles(obj):
    """Corrige récursivement les clés de dictionnaire avec accents (ex: 'priorité' -> 'priorite')."""
    if isinstance(obj, dict):
        return {_retirer_accents(k): _normaliser_cles(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normaliser_cles(item) for item in obj]
    return obj

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
    donnees_brutes = json.loads(contenu)
    donnees_normalisees = _normaliser_cles(donnees_brutes)
    return SortiePO.model_validate(donnees_normalisees)