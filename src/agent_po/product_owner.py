import difflib
import json
import os
import re
import unicodedata
import shutil
import subprocess
import requests
from pydantic import ValidationError
from src.common.schemas import BesoinUtilisateur, SortiePO, UserStory, CHAMPS_SUIVI_BESOIN
from src.common.regles import bloc_regles
from src.common.logging_config import configurer_logging

logger = configurer_logging()

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen3")
# Moteur du Product Owner : "ollama" (local, par defaut) ou "claude" (Claude Code).
CLAUDE_BIN = shutil.which("claude") or "claude"

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
# Autres noms que le modele donne parfois a la priorite (ex : Stock du labo, « moscow »)
CHAMPS_SIMPLIFIES.update({cle: "priorite" for cle in (
    "priority", "importance", "moscow", "prio", "niveau", "niveaudepriorite", "prioritemoscow", "methodemoscow")})

# Valeurs de priorite acceptees, ramenees a haute / moyenne / basse (MoSCoW compris)
VALEURS_PRIORITE = {
    "haute": "haute", "high": "haute", "must": "haute", "musthave": "haute", "indispensable": "haute",
    "critique": "haute", "elevee": "haute", "forte": "haute", "essentielle": "haute",
    "moyenne": "moyenne", "medium": "moyenne", "should": "moyenne", "shouldhave": "moyenne",
    "normale": "moyenne", "importante": "moyenne",
    "basse": "basse", "low": "basse", "could": "basse", "couldhave": "basse", "wont": "basse",
    "wonthave": "basse", "faible": "basse", "confort": "basse", "optionnelle": "basse",
}


class ReponseInvalide(RuntimeError):
    """Reponse du modele inutilisable (JSON invalide ou champs manquants) : on peut la redemander."""


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


def _normaliser_priorites(donnees):
    """« Must », « High », « Haute » -> « haute » (idem moyenne, basse)."""
    if isinstance(donnees, dict):
        for story in donnees.get("user_stories", []) or []:
            if isinstance(story, dict) and isinstance(story.get("priorite"), str):
                story["priorite"] = VALEURS_PRIORITE.get(_cle_simplifiee(story["priorite"]), story["priorite"])
    return donnees


def _resume_erreur(erreur: ValidationError) -> str:
    """Les premieres erreurs, lisibles : « user_stories.0.priorite : Field required »."""
    lignes = [f"{'.'.join(str(x) for x in e['loc'])} : {e['msg']}" for e in erreur.errors()[:5]]
    reste = len(erreur.errors()) - len(lignes)
    return "; ".join(lignes) + (f" (et {reste} autres)" if reste > 0 else "")


def _valider(donnees_brutes) -> SortiePO:
    try:
        return SortiePO.model_validate(_normaliser_priorites(_normaliser_cles(donnees_brutes)))
    except ValidationError as e:
        raise ReponseInvalide(f"reponse incomplete : {_resume_erreur(e)}") from e


def _demander_ollama(prompt: str) -> SortiePO:
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
        raise ReponseInvalide(
            f"Ollama n'a pas retourné un JSON valide.\n"
            f"Contenu reçu (200 premiers caracteres) : {contenu[:200]!r}\n"
            f"Erreur : {e}"
        )
    return _valider(donnees_brutes)


def _extraire_json(texte: str) -> str:
    """Claude encadre parfois sa reponse de balises ```json ... ``` : on les retire."""
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", texte.strip(), re.DOTALL)
    return match.group(1).strip() if match else texte.strip()


def _demander_claude(prompt: str) -> SortiePO:
    """Envoie la meme consigne a Claude Code et renvoie les user stories validees."""
    resultat = subprocess.run(
        [CLAUDE_BIN, "-p"],
        input=prompt + "\nReponds UNIQUEMENT avec le JSON, sans texte autour.",
        capture_output=True, text=True, timeout=int(os.environ.get("CLAUDE_TIMEOUT", 1200)),
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        raise RuntimeError(f"Product Owner (Claude) a échoué : {resultat.stdout}\n{resultat.stderr}")
    contenu = _extraire_json(resultat.stdout)
    try:
        donnees_brutes = json.loads(contenu)
    except json.JSONDecodeError as e:
        raise ReponseInvalide(
            f"Claude n'a pas retourné un JSON valide.\n"
            f"Contenu reçu (200 premiers caracteres) : {contenu[:200]!r}\n"
            f"Erreur : {e}"
        )
    return _valider(donnees_brutes)


def moteur_po() -> str:
    """Moteur choisi dans .env (PO_MOTEUR) ; Ollama si absent ou inconnu."""
    moteur = os.environ.get("PO_MOTEUR", "ollama").strip().lower()
    return moteur if moteur in ("ollama", "claude") else "ollama"


def _demander_une_fois(prompt: str) -> SortiePO:
    if moteur_po() == "claude":
        return _demander_claude(prompt)
    return _demander_ollama(prompt)


CONSIGNE_CORRECTION = """

ATTENTION : ta reponse precedente etait inutilisable ({erreur}).
Reponds a nouveau avec le JSON complet. CHAQUE user story doit avoir exactement les 5 champs
"id", "titre", "description", "criteres_acceptation" et "priorite", et "priorite" vaut
"haute", "moyenne" ou "basse" (pas d'autre nom de champ, pas d'autre valeur).
"""


def _demander(prompt: str) -> SortiePO:
    """Envoie la consigne au moteur choisi (Ollama ou Claude). Une reponse inutilisable
    (JSON invalide, champ manquant) est redemandee UNE fois en disant ce qui n'allait pas.
    Une erreur du moteur lui-meme (connexion, limite du compte) n'est pas redemandee."""
    try:
        return _demander_une_fois(prompt)
    except ReponseInvalide as e:
        logger.warning("[PO] reponse inutilisable, nouvel essai : %s", str(e)[:300])
        return _demander_une_fois(prompt + CONSIGNE_CORRECTION.format(erreur=str(e)[:600]))


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
    prompt = PROMPT_TEMPLATE.format(besoin_json=besoin.model_dump_json(indent=2, exclude=CHAMPS_SUIVI_BESOIN)) + bloc_regles("product_owner")
    sortie = _demander(prompt)

    manquantes = fonctionnalites_manquantes(besoin.fonctionnalites_cles, sortie)
    if manquantes:
        sortie = _demander(prompt + CONSIGNE_COMPLEMENT.format(
            oubliees=", ".join(manquantes), precedente=sortie.model_dump_json(indent=2)))
        manquantes = fonctionnalites_manquantes(besoin.fonctionnalites_cles, sortie)
        if manquantes:
            sortie = _completer(sortie, manquantes)
    return sortie
