import json
import re
import unicodedata
import requests
from src.common.schemas import BesoinUtilisateur, SortiePO

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3"

PROMPT_TEMPLATE = """Tu es un Product Owner. À partir du besoin ci-dessous, génère des User Stories
au format JSON STRICT (rien d'autre que le JSON), avec ce schéma EXACT (respecte precisement
les noms de champs, SANS accents ni caracteres speciaux) :
{{"user_stories": [{{"id": "US1", "titre": "...", "description": "...",
"criteres_acceptation": ["..."], "priorite": "haute|moyenne|basse"}}]}}

IMPORTANT : les noms de champs doivent etre exactement "id", "titre", "description",
"criteres_acceptation", "priorite" (AUCUN accent, AUCUNE apostrophe dans les noms de champs).

Besoin :
{besoin_json}
"""

CHAMPS_ATTENDUS = ["id", "titre", "description", "criteres_acceptation", "priorite", "user_stories"]


def _cle_simplifiee(texte: str) -> str:
    """Réduit une clé à ses seules lettres minuscules (sans accents, apostrophes, espaces, etc.)."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte)
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z]", "", sans_accents.lower())


CHAMPS_SIMPLIFIES = {_cle_simplifiee(c): c for c in CHAMPS_ATTENDUS}


def _normaliser_cles(obj):
    """Corrige récursivement les clés de dictionnaire déformées par le modèle IA
    (accents, apostrophes, fautes de frappe) en les faisant correspondre au champ attendu le plus proche."""
    if isinstance(obj, dict):
        nouveau = {}
        for k, v in obj.items():
            cle_simple = _cle_simplifiee(k)
            cle_corrigee = CHAMPS_SIMPLIFIES.get(cle_simple, k)
            nouveau[cle_corrigee] = _normaliser_cles(v)
        return nouveau
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
    }, timeout=600)
    response.raise_for_status()

    contenu = response.json().get("response", "").strip()

    if not contenu:
        raise RuntimeError(
            "Ollama a retourné une réponse vide. "
            "Le modèle a peut-être été interrompu ou surchargé. Réessaie."
        )

    try:
        donnees_brutes = json.loads(contenu)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama n'a pas retourné un JSON valide.\n"
            f"Contenu reçu (200 premiers caracteres) : {contenu[:200]!r}\n"
            f"Erreur : {e}"
        )

    donnees_normalisees = _normaliser_cles(donnees_brutes)
    return SortiePO.model_validate(donnees_normalisees)