"""File d'attente des runs : plusieurs projets lances l'un apres l'autre, sans surveillance.

AutoDev ne fait qu'un run a la fois (un seul dossier output/, les memes ports
pour la Validation Docker et les Tests E2E). La file les enchaine :

- un run reussit, ou echoue a cause du PROJET (tests en echec apres 3 essais,
  agent qui plante sur ce projet) : la file passe au suivant. Le run se relance
  plus tard depuis « Runs existants » ;
- un run s'arrete a cause de la MACHINE (connexion Claude expiree, Docker
  arrete, port occupe, disque plein) : la file se met en PAUSE. Continuer ne
  servirait a rien, tous les runs suivants s'arreteraient de la meme facon.
  Une fois le probleme regle, « Reprendre la file » reprend ce run la ou il
  s'est arrete (sans refaire les etapes reussies), puis les suivants.

La file est gardee dans un fichier JSON (FILE_ATTENTE_JSON) : elle survit a un
redemarrage d'AutoDev. Un run qui tournait pendant le redemarrage est repris,
et la file attend « Reprendre la file ».

Ce module ne connait pas Gradio : la Vue (src/agent_form/app.py) lui donne les
deux fonctions qui demarrent un run (nouveau, ou reprise d'un run arrete).
"""
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.common.logging_config import configurer_logging
from src.common.schemas import BesoinUtilisateur

logger = configurer_logging()

FICHIER_PAR_DEFAUT = "checkpoints/file_attente.json"

EN_ATTENTE = "en attente"
EN_COURS = "en cours"
TERMINE = "termine"
ECHEC = "echec"
ARRETE_MACHINE = "arrete (machine)"
REMIS = "remis dans la file"

# Erreurs qui viennent de la machine ou du compte, pas du projet
MOTS_MACHINE = (
    "authenticate", "auth login", "setup-token", "not logged in", "please run /login",
    "credit balance", "usage limit", "limit reached", "quota",
    # Limite d'utilisation du compte Claude (ex : « You've hit your 5-hour limit · resets 6:40pm (UTC) »)
    "hit your", "-hour limit", "weekly limit", "rate limit", "resets ",
    "docker n'est pas joignable", "cannot connect to the docker daemon", "docker daemon",
    "no space left", "port(s) deja occupe",
)


def cause_de_l_arret(etat: dict, exception: Exception | None = None) -> str:
    """"succes", "projet" ou "machine" pour un run termine (etat final du graphe)."""
    if exception is not None:
        return "machine"  # le run n'a meme pas pu aller au bout du graphe
    if etat.get("succes"):
        return "succes"
    if etat.get("demande_a_preciser"):
        return "projet"  # la demande est a reformuler, rien a regler sur la machine
    for cle in ("rapport_validation_docker", "rapport_e2e"):
        rapport = etat.get(cle)
        if rapport is not None and getattr(rapport, "erreur_environnement", False):
            return "machine"
    erreur = str(etat.get("erreur", "")).lower()
    if any(mot in erreur for mot in MOTS_MACHINE):
        return "machine"
    return "projet"


def message_d_arret(etat: dict, exception: Exception | None = None) -> str:
    """Ce qui s'est passe, en une phrase courte."""
    if exception is not None:
        return f"{type(exception).__name__} : {exception}"[:300]
    if etat.get("erreur"):
        return f"plantage a l'etape {etat.get('etape', '?')} : {etat['erreur']}"[:300]
    for cle in ("rapport_validation_docker", "rapport_e2e"):
        rapport = etat.get(cle)
        if rapport is not None and getattr(rapport, "erreur_environnement", False):
            return " ".join(getattr(rapport, "erreurs", []) or [])[:300] or "probleme sur la machine"
    return f"echec a l'etape {etat.get('etape', '?')}" if etat.get("etape") else "echec"


def conseil(message: str) -> str:
    """Ce qu'il faut faire pour regler un arret de la machine."""
    texte = message.lower()
    if any(mot in texte for mot in ("authenticate", "auth login", "setup-token", "login")):
        return "Reconnecte Claude : docker compose exec -it autodev claude auth login"
    if "port" in texte:
        return ("Trouve qui occupe le port : docker ps --filter \"publish=8000\" --format \"{{.Names}}\", "
                "puis arrete cette application")
    if "docker" in texte:
        return "Demarre Docker Desktop et attends qu'il soit pret"
    if "space" in texte:
        return "Libere de la place sur le disque (ex : docker system prune)"
    if "limit" in texte or "credit" in texte or "quota" in texte:
        reprise = re.search(r"resets?\s+([^.;\n]+?)(?:\s*[.;]|$)", message, re.IGNORECASE)
        quand = f" (le compte indique : resets {reprise.group(1).strip()})" if reprise else ""
        return f"Limite d'utilisation du compte Claude atteinte : attends qu'elle soit levee{quand}"
    return "Regle le probleme indique"


@dataclass
class ElementFile:
    numero: int
    titre: str
    besoin: dict
    statut: str = EN_ATTENTE
    id_run: str = ""
    message: str = ""
    reprise: bool = False  # True : reprendre le run id_run la ou il s'est arrete


class FileAttente:
    """demarrer_nouveau(besoin) et demarrer_reprise(id_run) renvoient un run en
    arriere-plan (attributs termine, evenements, exception, id_run, methode
    attendre), ou None si un autre run tourne deja (la file attend alors)."""

    def __init__(self, demarrer_nouveau, demarrer_reprise, chemin: str | None = FICHIER_PAR_DEFAUT,
                 attente_si_occupe: float = 10.0):
        self._demarrer_nouveau = demarrer_nouveau
        self._demarrer_reprise = demarrer_reprise
        self._chemin = Path(chemin) if chemin else None
        self._attente = attente_si_occupe
        self._verrou = threading.RLock()
        self._travailleur: threading.Thread | None = None
        self.elements: list[ElementFile] = []
        self.en_pause = False
        self.raison_pause = ""
        self._charger()

    # --- Actions de la Vue ---

    def ajouter(self, besoin: BesoinUtilisateur) -> ElementFile:
        with self._verrou:
            numero = max((e.numero for e in self.elements), default=0) + 1
            element = ElementFile(numero=numero, titre=besoin.titre_projet, besoin=besoin.model_dump())
            self.elements.append(element)
            self._sauver()
        logger.info("[File] %s ajoute a la file (n° %d)", element.titre, numero)
        self._demarrer_travailleur()
        return element

    def mettre_en_pause(self, raison: str = "mise en pause a la main") -> None:
        """Le run en cours va jusqu'au bout ; les suivants attendent."""
        with self._verrou:
            self.en_pause, self.raison_pause = True, raison
            self._sauver()

    def reprendre(self) -> None:
        """Apres un arret de la machine : le run arrete est repris la ou il
        s'est arrete, puis la file continue."""
        with self._verrou:
            for element in self.elements:
                if element.statut == ARRETE_MACHINE:
                    element.statut, element.reprise = EN_ATTENTE, bool(element.id_run)
            self.en_pause, self.raison_pause = False, ""
            self._sauver()
        self._demarrer_travailleur()

    def vider(self) -> int:
        """Retire les projets qui n'ont pas encore commence ; renvoie leur nombre."""
        with self._verrou:
            restants = [e for e in self.elements if e.statut != EN_ATTENTE]
            retires = len(self.elements) - len(restants)
            self.elements = restants
            self._sauver()
        return retires

    def remettre(self, numero: int) -> ElementFile | None:
        """Projet en echec : il repart du debut comme un nouveau projet (nouveau
        run, dossier propre), avec le meme formulaire. L'ancien reste dans la
        liste, marque « remis dans la file », pour garder la trace de l'echec."""
        with self._verrou:
            ancien = next((e for e in self.elements if e.numero == numero and e.statut == ECHEC), None)
            if ancien is None:
                return None
            nouveau = ElementFile(numero=max(e.numero for e in self.elements) + 1, titre=ancien.titre,
                                  besoin=dict(ancien.besoin))
            ancien.statut = REMIS
            ancien.message = f"{ancien.message} → remis dans la file (n° {nouveau.numero})".strip(" →")
            self.elements.append(nouveau)
            self._sauver()
        logger.info("[File] %s remis dans la file (n° %d -> n° %d)", ancien.titre, numero, nouveau.numero)
        self._demarrer_travailleur()
        return nouveau

    def echecs(self) -> list[ElementFile]:
        with self._verrou:
            return [ElementFile(**asdict(e)) for e in self.elements if e.statut == ECHEC]

    def retirer_les_termines(self) -> None:
        with self._verrou:
            self.elements = [e for e in self.elements if e.statut not in (TERMINE, ECHEC, REMIS)]
            self._sauver()

    def copie(self) -> list[ElementFile]:
        with self._verrou:
            return [ElementFile(**asdict(e)) for e in self.elements]

    def travaille(self) -> bool:
        return self._travailleur is not None and self._travailleur.is_alive()

    def attendre_fin(self, timeout: float = 10) -> None:
        """Pour les tests : attend que le travailleur n'ait plus rien a faire."""
        if self._travailleur is not None:
            self._travailleur.join(timeout)

    # --- Travailleur : un thread qui enchaine les runs ---

    def _demarrer_travailleur(self) -> None:
        with self._verrou:
            if self.travaille() or self.en_pause:
                return
            self._travailleur = threading.Thread(target=self._boucle, daemon=True, name="file-attente")
            self._travailleur.start()

    def _suivant(self) -> ElementFile | None:
        with self._verrou:
            if self.en_pause:
                return None
            return next((e for e in self.elements if e.statut == EN_ATTENTE), None)

    def _boucle(self) -> None:
        while True:
            element = self._suivant()
            if element is None:
                return
            try:
                if element.reprise:
                    run = self._demarrer_reprise(element.id_run)
                else:
                    run = self._demarrer_nouveau(BesoinUtilisateur(**element.besoin))
            except Exception as e:  # ex : reprise impossible (run archive, termine...)
                self._finir(element, ECHEC, f"{type(e).__name__} : {e}"[:300])
                continue
            if run is None:  # un run lance a la main tourne encore : on attend
                time.sleep(self._attente)
                continue
            with self._verrou:
                element.statut = EN_COURS
                self._sauver()
            logger.info("[File] demarrage de %s (n° %d)", element.titre, element.numero)
            while not run.termine:
                run.attendre(len(run.evenements), 5)
                if run.id_run and element.id_run != run.id_run:
                    with self._verrou:
                        element.id_run = run.id_run
                        self._sauver()
            etat = run.evenements[-1][1] if run.evenements else {}
            element.id_run = etat.get("id_run") or run.id_run or element.id_run
            cause = cause_de_l_arret(etat, run.exception)
            message = "" if cause == "succes" else message_d_arret(etat, run.exception)
            if cause == "succes":
                self._finir(element, TERMINE, "")
            elif cause == "projet":
                self._finir(element, ECHEC, message)
            else:
                self._finir(element, ARRETE_MACHINE, message)
                self.mettre_en_pause(f"{element.titre} : {message}")
                logger.warning("[File] en pause : probleme sur la machine (%s)", message)
                return

    def _finir(self, element: ElementFile, statut: str, message: str) -> None:
        with self._verrou:
            element.statut, element.message, element.reprise = statut, message, False
            self._sauver()
        logger.info("[File] %s (n° %d) : %s %s", element.titre, element.numero, statut, message)

    # --- Fichier JSON ---

    def _sauver(self) -> None:
        if self._chemin is None:
            return
        self._chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {"en_pause": self.en_pause, "raison_pause": self.raison_pause,
                   "elements": [asdict(e) for e in self.elements]}
        temporaire = self._chemin.with_suffix(".tmp")
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        temporaire.replace(self._chemin)

    def _charger(self) -> None:
        if self._chemin is None or not self._chemin.exists():
            return
        try:
            donnees = json.loads(self._chemin.read_text(encoding="utf-8"))
            self.elements = [ElementFile(**e) for e in donnees.get("elements", [])]
        except (ValueError, TypeError) as e:
            logger.warning("[File] fichier %s illisible, file videe : %s", self._chemin, e)
            self.elements = []
            return
        self.en_pause = donnees.get("en_pause", False)
        self.raison_pause = donnees.get("raison_pause", "")
        interrompus = [e for e in self.elements if e.statut == EN_COURS]
        for element in interrompus:  # AutoDev a redemarre pendant ce run
            element.statut, element.reprise = EN_ATTENTE, bool(element.id_run)
            element.message = "AutoDev a redemarre pendant ce run : il sera repris la ou il s'est arrete"
        if interrompus:
            self.en_pause = True
            self.raison_pause = "AutoDev a redemarre pendant un run de la file"


def chemin_par_defaut() -> str | None:
    """FILE_ATTENTE_JSON vide : file en memoire seulement (tests)."""
    valeur = os.environ.get("FILE_ATTENTE_JSON", FICHIER_PAR_DEFAUT)
    return valeur or None
