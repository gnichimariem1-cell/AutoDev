import difflib
import json
import os
import re
import unicodedata
import requests
from src.common.schemas import BesoinUtilisateur, SortiePO, UserStory

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen3")

PROMPT_TEMPLATE = """Tu es un Product Owner. À partir du besoin ci-dessous, génère des User Stories
au format JSON STRICT (rien d'autre que le JSON), avec ce schéma EXACT (respecte precisement
les noms de champs, SANS accents ni caracteres speciaux) :
{{"user_stories": [{{"id": "US1", "titre": "...", "description": "...",
"criteres_acceptation": ["..."], "priorite": "haute|moyenne|basse"}}]}}

Regles de priorite (methode MoSCoW) :
- "haute" : indispensable, sans elle l'application ne sert a rien (ex : se connecter, la fonction principale)
- "moyenne" : importante, mais l'application fonctionne sans elle (ex : historique, profil)
- "basse" : confort, peut attendre une version suivante (ex : supprimer, trier, exporter)
S'il y a plus de 3 user stories, elles ne peuvent pas toutes etre "haute" : fais de vrais choix.

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
            if cle_simple in CHAMPS_SIMPLIFIES:
                cle_corrigee = CHAMPS_SIMPLIFIES[cle_simple]
            else:
                proches = difflib.get_close_matches(
                    cle_simple, CHAMPS_SIMPLIFIES.keys(), n=1, cutoff=0.6
                )
                cle_corrigee = CHAMPS_SIMPLIFIES[proches[0]] if proches else k
            nouveau[cle_corrigee] = _normaliser_cles(v)
        return nouveau
    if isinstance(obj, list):
        return [_normaliser_cles(item) for item in obj]
    return obj


def _demander(prompt: str) -> SortiePO:
    """Envoie la consigne a Ollama et renvoie les user stories validees."""
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        # Sortie structuree : Ollama contraint la generation au schema de SortiePO
        # (champs obligatoires, valeurs de priorite), et non plus seulement a un JSON valide.
        "format": SortiePO.model_json_schema(),
        # Desactive le raisonnement de qwen3 : reponse plus courte et plus rapide.
        "think": False,
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


# --- Verification : chaque fonctionnalite du formulaire a sa user story ---

MOTS_VIDES = {"le", "la", "les", "un", "une", "des", "de", "du", "se", "son", "sa", "ses",
              "mon", "ma", "mes", "et", "ou", "au", "aux", "en", "pour", "par", "sur",
              "avec", "dans", "the", "and", "to", "of"}

CONSIGNE_COMPLEMENT = """

ATTENTION : ta reponse precedente a oublie ces fonctionnalites demandees : {oubliees}.
Reponds a nouveau avec TOUTES les user stories : celles de ta reponse precedente
ET une user story pour chaque fonctionnalite oubliee (avec ses criteres d'acceptation).
Ta reponse precedente :
{precedente}
"""


def _racines(texte: str) -> set[str]:
    """Debuts de mots significatifs (4 lettres) : « deconnecter » et « deconnexion » -> « deco »."""
    mots = _cle_simplifiee_mots(texte)
    return {m[:4] for m in mots if len(m) >= 3 and m not in MOTS_VIDES}


def _cle_simplifiee_mots(texte: str) -> list[str]:
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c)
    )
    return re.findall(r"[a-z]+", sans_accents.lower())


def fonctionnalites_manquantes(fonctionnalites: list[str], sortie: SortiePO) -> list[str]:
    """Fonctionnalites du formulaire qui n'apparaissent dans aucune user story."""
    textes = [_racines(" ".join([us.titre, us.description, *us.criteres_acceptation]))
              for us in sortie.user_stories]
    manquantes = []
    for fonctionnalite in fonctionnalites:
        racines = _racines(fonctionnalite)
        if racines and not any(racines <= texte for texte in textes):
            manquantes.append(fonctionnalite)
    return manquantes


def _completer(sortie: SortiePO, manquantes: list[str]) -> SortiePO:
    """Dernier recours : une user story simple pour chaque fonctionnalite encore oubliee."""
    stories = list(sortie.user_stories)
    for fonctionnalite in manquantes:
        stories.append(UserStory(
            id=f"US{len(stories) + 1}",
            titre=fonctionnalite[:1].upper() + fonctionnalite[1:],
            description=f"L'utilisateur doit pouvoir : {fonctionnalite}.",
            criteres_acceptation=[f"La fonctionnalite « {fonctionnalite} » est disponible et fonctionne"],
            priorite="moyenne",
        ))
    return SortiePO(user_stories=stories)


def generer_user_stories(besoin: BesoinUtilisateur) -> SortiePO:
    prompt = PROMPT_TEMPLATE.format(besoin_json=besoin.model_dump_json(indent=2))
    sortie = _demander(prompt)

    manquantes = fonctionnalites_manquantes(besoin.fonctionnalites_cles, sortie)
    if manquantes:
        sortie = _demander(prompt + CONSIGNE_COMPLEMENT.format(
            oubliees=", ".join(manquantes), precedente=sortie.model_dump_json(indent=2)))
        manquantes = fonctionnalites_manquantes(besoin.fonctionnalites_cles, sortie)
        if manquantes:
            sortie = _completer(sortie, manquantes)
    return sortie
