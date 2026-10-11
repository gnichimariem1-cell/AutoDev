import html
import os
import re
import threading
import time

from dotenv import load_dotenv

# Charge .env avant tout import qui lit l'environnement : les sous-processus `claude`
# heritent ainsi de ANTHROPIC_API_KEY / CLAUDE_CONFIG_DIR (compte Claude du projet).
# Les variables deja definies (ex. par docker compose) restent prioritaires.
load_dotenv()

from pathlib import Path

import gradio as gr
from src.common.schemas import BesoinUtilisateur
from src.agent_orchestrateur.etat import MAX_TENTATIVES
from src.agent_orchestrateur.orchestrateur import (
    executer_pipeline_en_direct, reprendre_pipeline_en_direct, point_de_reprise, RepriseImpossible,
    rejouer_pipeline_en_direct, point_de_rejeu, ETAPES_REJOUABLES,
    historique_runs, etat_du_run, FICHIER_ID_RUN,
)

LONGUEUR_MAX_DESCRIPTION = 1000
LONGUEUR_MAX_CHAMP_COURT = 200
MOTIFS_SUSPECTS = [
    r"ignor[ez]?\s+(les\s+)?(instructions|consignes)",
    r"ignore\s+(previous|all)\s+instructions",
    r"system\s*prompt",
    r"\bact\s+as\b",
]


def valider_besoin(titre, description, utilisateurs, fonctionnalites, structure):
    """Validation basique cote AutoDev, en complement des garde-fous propres
    a Claude Code. Renvoie un message d'erreur (str) si invalide, ou None si OK.
    """
    champs_courts = {"Titre du projet": titre, "Utilisateurs cibles": utilisateurs}
    for nom, valeur in champs_courts.items():
        if valeur and len(valeur) > LONGUEUR_MAX_CHAMP_COURT:
            return f"{nom} trop long (max {LONGUEUR_MAX_CHAMP_COURT} caracteres)."

    if description and len(description) > LONGUEUR_MAX_DESCRIPTION:
        return f"Description trop longue (max {LONGUEUR_MAX_DESCRIPTION} caracteres)."

    texte_complet = " ".join(filter(None, [titre, description, utilisateurs, fonctionnalites, structure]))
    for motif in MOTIFS_SUSPECTS:
        if re.search(motif, texte_complet, re.IGNORECASE):
            return (
                "Le texte saisi contient un motif qui ressemble a une tentative "
                "d'instruction destinee a l'IA plutot qu'a une description de projet. "
                "Reformule ta demande."
            )
    return None


def collecter_besoin(titre, description, utilisateurs, fonctionnalites, structure):
    besoin = BesoinUtilisateur(
        titre_projet=titre,
        description=description,
        utilisateurs_cibles=utilisateurs,
        fonctionnalites_cles=[f.strip() for f in fonctionnalites.split(",") if f.strip()],
        structure_projet=structure,
    )
    return besoin


def _section_product_owner(resultat) -> str:
    user_stories = resultat.get("user_stories")
    if not user_stories:
        return "1. Product Owner Agent\n   (non atteint)\n"
    titres = [f"   - {us.titre} [{us.priorite}]" for us in user_stories.user_stories]
    return (
        "1. Product Owner Agent — OK\n"
        f"   {len(user_stories.user_stories)} User Stories generees :\n"
        + "\n".join(titres) + "\n"
    )


def _section_architect(resultat) -> str:
    architecture = resultat.get("architecture")
    if not architecture:
        return "2. Architect Agent\n   (non atteint)\n"
    modules = [f"   - {m}" for m in architecture.structure_modules]
    return (
        "2. Architect Agent — OK\n"
        f"   Stack technique : {', '.join(architecture.stack_technique)}\n"
        "   Structure des modules :\n" + "\n".join(modules) + "\n"
        f"   Justification : {architecture.justification}\n"
    )


def _section_test_agent(resultat) -> str:
    plan = resultat.get("plan_tests")
    if not plan:
        return "2b. Test Agent\n   (non atteint)\n"
    cas = [f"   - {c.id} {c.methode} {c.route} -> {c.code_attendu} : {c.scenario}" for c in plan.cas]
    revision = "   Tests revises une fois apres l'echec des corrections\n" if resultat.get("tests_revises") else ""
    return (
        "2b. Test Agent — OK (tests ecrits avant le code)\n"
        f"   {len(plan.cas)} cas de test, {len(plan.fichiers_tests)} fichiers de tests\n"
        + "\n".join(cas) + "\n" + revision
    )


def _section_developer(resultat) -> str:
    sortie_dev = resultat.get("sortie_dev")
    if not sortie_dev:
        return "3. Developer Agent\n   (non atteint)\n"
    return (
        "3. Developer Agent — OK\n"
        f"   Fichiers generes : {len(sortie_dev.fichiers_generes)}\n"
        f"   Resume : {sortie_dev.resume_technique[:300]}\n"
    )


def _section_qa_backend(resultat) -> str:
    rapport_be = resultat.get("rapport_backend")
    if not rapport_be:
        return "4. QA Agent (backend)\n   (non atteint)\n"
    statut = "OK" if rapport_be.succes else "ECHEC"
    texte = (
        f"4. QA Agent (backend) — {statut} (tentative {resultat.get('tentative_backend', '?')})\n"
        f"   Tests passes : {rapport_be.tests_passes}\n"
        f"   Tests echoues : {rapport_be.tests_echoues}\n"
        f"   Couverture de code : {rapport_be.couverture_pct:.1f}%\n"
    )
    if not rapport_be.succes:
        texte += "   Erreurs :\n" + "\n".join(f"     - {e}" for e in rapport_be.erreurs) + "\n"
    return texte


def _section_frontend(resultat) -> str:
    sortie_fe = resultat.get("sortie_frontend")
    if not sortie_fe:
        return "5. Frontend Agent\n   (non atteint)\n"
    return (
        "5. Frontend Agent — OK\n"
        f"   Fichiers generes : {len(sortie_fe.fichiers_generes)}\n"
        f"   Resume : {sortie_fe.resume_technique[:300]}\n"
    )


def _section_qa_frontend(resultat) -> str:
    rapport_fe = resultat.get("rapport_frontend")
    if not rapport_fe:
        return "6. QA Agent (frontend)\n   (non atteint)\n"
    statut = "OK" if rapport_fe.succes else "ECHEC"
    texte = (
        f"6. QA Agent (frontend) — {statut} (tentative {resultat.get('tentative_frontend', '?')})\n"
        f"   Fichiers verifies : {len(rapport_fe.fichiers_verifies)}\n"
    )
    if not rapport_fe.succes:
        texte += "   Erreurs :\n" + "\n".join(f"     - {e}" for e in rapport_fe.erreurs) + "\n"
    return texte


def _section_dockerization(resultat) -> str:
    rapport_dock = resultat.get("rapport_dockerisation")
    if not rapport_dock:
        return "7. Dockerization Agent\n   (non atteint)\n"
    return (
        "7. Dockerization Agent — OK\n"
        f"   Fichiers generes : {len(rapport_dock.fichiers_generes)} (dans output/)\n"
        f"   Resume : {rapport_dock.resume_technique[:300]}\n"
    )


def _section_validation_docker(resultat) -> str:
    rapport = resultat.get("rapport_validation_docker")
    if not rapport:
        return "8. Docker Validation Agent\n   (non atteint)\n"
    if not rapport.docker_disponible:
        return "8. Docker Validation Agent — NON EFFECTUEE\n   Docker n'est pas joignable depuis le pipeline.\n"
    statut = "OK" if rapport.succes else "ECHEC"
    lignes = [f"   - {e.nom} : {'OK' if e.succes else 'ECHEC'}" for e in rapport.etapes]
    texte = (
        f"8. Docker Validation Agent — {statut} (tentative {resultat.get('tentative_docker', '?')})\n"
        + "\n".join(lignes) + "\n"
    )
    if not rapport.succes:
        if rapport.erreur_environnement:
            texte += "   Probleme sur la machine (pas dans la configuration generee) :\n"
        texte += "   Erreurs :\n" + "\n".join(f"     - {e}" for e in rapport.erreurs) + "\n"
    return texte


SECTIONS = {
    "Product Owner": _section_product_owner,
    "Architect": _section_architect,
    "Test Agent": _section_test_agent,
    "Developer": _section_developer,
    "QA Backend": _section_qa_backend,
    "Frontend": _section_frontend,
    "QA Frontend": _section_qa_frontend,
    "Dockerization": _section_dockerization,
    "Validation Docker": _section_validation_docker,
}
TOUTES_LES_SECTIONS = list(SECTIONS.keys())

# Libelles des noeuds du graphe (src/agent_orchestrateur/graphe.py), pour
# afficher la progression en direct et les plantages.
LIBELLES_NOEUDS = {
    "po": "Product Owner Agent",
    "architect": "Architect Agent",
    "test_agent": "Test Agent",
    "developer": "Developer Agent",
    "qa_backend": "QA Agent (backend)",
    "correction_backend": "Correction du backend",
    "revision_tests": "Revision des tests (Test Agent)",
    "frontend": "Frontend Agent",
    "qa_frontend": "QA Agent (frontend)",
    "correction_frontend": "Correction du frontend",
    "dockerization": "Dockerization Agent",
    "validation_docker": "Docker Validation Agent",
    "correction_docker": "Correction de la config Docker",
    "echec": "Arret du pipeline",
}


def _ligne_titre(resultat) -> str:
    noeud_en_cours = resultat.get("_en_cours")
    if noeud_en_cours and resultat.get("erreur"):
        return f"⏳ ARRET EN COURS — plantage de : {LIBELLES_NOEUDS.get(noeud_en_cours, noeud_en_cours)}"
    if noeud_en_cours:
        return f"⏳ EN COURS — derniere etape terminee : {LIBELLES_NOEUDS.get(noeud_en_cours, noeud_en_cours)}"
    if resultat["succes"]:
        return "✅ SUCCES — pipeline complet"
    etape = resultat.get("etape", "?")
    if resultat.get("erreur"):
        return (
            f"❌ PLANTAGE a l'etape \"{LIBELLES_NOEUDS.get(etape, etape)}\"\n"
            f"Erreur : {resultat['erreur']}"
        )
    return f"❌ ECHEC a l'etape \"{etape}\""


def construire_rapport_detaille(resultat, sections_choisies=None) -> str:
    """Construit un rapport texte agent par agent. sections_choisies filtre
    quelles sections apparaissent. None = tout afficher (valeur par defaut,
    utilisee au tout premier appel) ; une liste (meme vide) = respecter
    exactement ce qui est coche, y compris si l'utilisateur a tout decoche.
    Les etapes non atteintes (pipeline arrete avant) sont marquees comme
    telles plutot que simplement omises ; pendant un run (cle "_en_cours"),
    elles sont marquees "(en attente)".
    """
    if sections_choisies is None:
        sections_choisies = TOUTES_LES_SECTIONS

    en_cours = bool(resultat.get("_en_cours"))
    corps = [_ligne_titre(resultat), "=" * 50]
    for nom in TOUTES_LES_SECTIONS:
        if nom in sections_choisies:
            section = SECTIONS[nom](resultat)
            corps.append(section.replace("(non atteint)", "(en attente)") if en_cours else section)

    if not sections_choisies:
        corps.append("(Aucune section cochee — coche au moins une case ci-dessus pour voir le detail.)")

    if resultat["succes"] and not en_cours and "Dockerization" in sections_choisies:
        corps.append("Code source genere dans : output/backend/ et output/frontend/\nConfig Docker generee dans : output/\n")
    return "\n".join(corps)


def _user_stories_json(resultat) -> str:
    user_stories = resultat.get("user_stories")
    return user_stories.model_dump_json(indent=2) if user_stories else "{}"


def _boutons(actifs: bool):
    """Mise a jour des boutons "Lancer" et "Reprendre" : desactives pendant un
    run, pour eviter deux pipelines en parallele sur le meme dossier output/."""
    return gr.update(interactive=actifs), gr.update(interactive=actifs)


# Pendant une etape longue (ex : Developer Agent, ~10 min), la page est
# rafraichie a cet intervalle (en secondes) avec le temps ecoule.
INTERVALLE_RAFRAICHISSEMENT = 5


class RunEnArrierePlan:
    """Execute un run du pipeline dans un thread, independamment de la page.

    Avant, le pipeline avancait seulement quand Gradio demandait la suite a la
    page : si la page perdait sa connexion pendant une etape longue, le run
    restait fige apres cette etape. Ici le thread va jusqu'au bout quoi qu'il
    arrive cote navigateur ; la page ne fait que suivre les evenements, et peut
    s'y rattacher apres un rechargement (suivre_run_actif)."""

    def __init__(self, evenements, id_run=""):
        self.id_run = id_run
        self.evenements = []  # (noeud termine, etat) dans l'ordre
        self.termine = False
        self.exception = None
        self.debut = time.time()
        self.debut_etape = self.debut
        self._condition = threading.Condition()
        threading.Thread(target=self._executer, args=(evenements,), daemon=True).start()

    def _executer(self, evenements):
        try:
            for noeud, etat in evenements:
                with self._condition:
                    self.id_run = etat.get("id_run", self.id_run)
                    self.evenements.append((noeud, dict(etat)))
                    self.debut_etape = time.time()
                    self._condition.notify_all()
        except Exception as e:
            self.exception = e
        finally:
            with self._condition:
                self.termine = True
                self._condition.notify_all()

    def attendre(self, deja_vus: int, timeout: float):
        """Attend (au plus timeout s) un evenement au-dela des deja_vus premiers,
        ou la fin du run. Renvoie (nouveaux evenements, run termine)."""
        with self._condition:
            self._condition.wait_for(lambda: len(self.evenements) > deja_vus or self.termine, timeout)
            return self.evenements[deja_vus:], self.termine


# Dernier run lance depuis cette application (en cours ou termine)
_run_actif: RunEnArrierePlan | None = None
_verrou_run = threading.Lock()


def _demarrer_run(evenements, id_run="") -> RunEnArrierePlan | None:
    """Demarre un run en arriere-plan, sauf si un autre est encore en cours
    (deux runs en parallele ecriraient dans le meme dossier output/)."""
    global _run_actif
    with _verrou_run:
        if _run_actif and not _run_actif.termine:
            return None
        _run_actif = RunEnArrierePlan(evenements, id_run)
        return _run_actif


def _message_run_deja_en_cours():
    id_run = _run_actif.id_run or "(en cours de demarrage)"
    return (f"⚠️ Un run est deja en cours (ID : {id_run}). Attends sa fin ou recharge la page "
            "pour suivre sa progression (detail aussi dans logs/pipeline.log).",
            gr.update(), gr.update(), *_boutons(False), id_run)


def _duree(secondes: float) -> str:
    minutes, secondes = divmod(int(secondes), 60)
    return f"{minutes} min {secondes:02d} s" if minutes else f"{secondes} s"


def _suivre_dans_la_vue(run: RunEnArrierePlan, sections_choisies, sortie_initiale):
    """Generateur : Gradio met a jour l'affichage a chaque `yield`, donc apres
    chaque etape du pipeline, et toutes les INTERVALLE_RAFRAICHISSEMENT s
    pendant une etape longue. Sorties : rapport, User Stories JSON, etat,
    bouton Lancer, bouton Reprendre, ID du run.
    Si la page se deconnecte, seul ce suivi s'arrete : le run continue."""
    derniere_sortie = sortie_initiale
    yield derniere_sortie
    resultat = None
    vus = 0
    debut_etape = time.monotonic()
    while True:
        nouveaux, termine = run.attendre(vus, INTERVALLE_RAFRAICHISSEMENT)
        vus += len(nouveaux)
        for noeud, etat in nouveaux:
            resultat = dict(etat, _en_cours=noeud)
            debut_etape = time.monotonic()
            if noeud == "echec":
                continue  # le yield final ci-dessous affiche directement l'echec
            derniere_sortie = (construire_rapport_detaille(resultat, sections_choisies),
                               _user_stories_json(resultat), resultat, *_boutons(False), resultat["id_run"])
            yield derniere_sortie
        if termine:
            break
        if not nouveaux:
            texte = f"{derniere_sortie[0]}\n\n⏱ Etape suivante en cours depuis {_duree(time.monotonic() - debut_etape)}"
            yield (texte, *derniere_sortie[1:])

    if run.exception:
        raise run.exception
    if resultat is None:
        yield ("❌ Le run s'est arrete sans produire de resultat (voir logs/pipeline.log).",
               gr.update(), gr.update(), *_boutons(True), run.id_run)
        return
    resultat.pop("_en_cours")
    yield (construire_rapport_detaille(resultat, sections_choisies), _user_stories_json(resultat),
           resultat, *_boutons(True), resultat["id_run"])


def lancer_pipeline_complet(titre, description, utilisateurs, fonctionnalites, structure, sections_choisies):
    erreur_validation = valider_besoin(titre, description, utilisateurs, fonctionnalites, structure)
    if erreur_validation:
        yield f"❌ Entree refusee : {erreur_validation}", "{}", None, *_boutons(True), ""
        return

    besoin = collecter_besoin(titre, description, utilisateurs, fonctionnalites, structure)
    run = _demarrer_run(executer_pipeline_en_direct(besoin))
    if run is None:
        yield _message_run_deja_en_cours()
        return
    yield from _suivre_dans_la_vue(
        run, sections_choisies,
        ("⏳ Pipeline lance — Product Owner Agent en cours...", "{}", None, *_boutons(False), ""),
    )


def reprendre_pipeline(id_run, sections_choisies):
    """Reprend un run qui a plante, a partir de l'etape qui a plante. L'ID est
    rempli automatiquement apres chaque run ; il peut aussi etre colle a la main
    (ex : apres un redemarrage de l'application, il figure dans logs/pipeline.log)."""
    id_run = (id_run or "").strip()
    try:
        etape = ", ".join(point_de_reprise(id_run).next)
    except RepriseImpossible as e:
        yield f"⚠️ Reprise impossible : {e}", gr.update(), gr.update(), *_boutons(True), id_run
        return
    run = _demarrer_run(reprendre_pipeline_en_direct(id_run), id_run)
    if run is None:
        yield _message_run_deja_en_cours()
        return
    yield from _suivre_dans_la_vue(
        run, sections_choisies,
        (f"⏳ Reprise du run {id_run} a l'etape {etape}...", gr.update(), gr.update(), *_boutons(False), id_run),
    )


def rejouer_pipeline(id_run, etape, sections_choisies):
    """Rejoue un run deja termine a partir de l'etape choisie, apres une
    modification d'un agent : les etapes precedentes sont reprises des
    sauvegardes (pas refaites, pas repayees)."""
    id_run = (id_run or "").strip()
    noeud = ETAPES_REJOUABLES.get(etape)
    if not noeud:
        yield "⚠️ Choisis l'etape a partir de laquelle rejouer.", gr.update(), gr.update(), *_boutons(True), id_run
        return
    try:
        point_de_rejeu(id_run, noeud)
    except RepriseImpossible as e:
        yield f"⚠️ Rejeu impossible : {e}", gr.update(), gr.update(), *_boutons(True), id_run
        return
    run = _demarrer_run(rejouer_pipeline_en_direct(id_run, noeud), id_run)
    if run is None:
        yield _message_run_deja_en_cours()
        return
    yield from _suivre_dans_la_vue(
        run, sections_choisies,
        (f"⏳ Rejeu du run {id_run} a partir de l'etape {etape}...", gr.update(), gr.update(), *_boutons(False), id_run),
    )


def suivre_run_actif(sections_choisies):
    """A l'ouverture (ou au rechargement) de la page : se rattache au run en
    cours, ou affiche le resultat du dernier run, avec son ID pre-rempli."""
    run = _run_actif
    if run is None or run.termine:
        # « Run en cours » montre seulement un run qui tourne : un run termine
        # se retrouve dans « Runs existants ». Relancer reste grise tant
        # qu'aucun run n'est choisi.
        yield gr.update(), gr.update(), gr.update(), gr.update(interactive=True), gr.update(), gr.update()
        return
    yield from _suivre_dans_la_vue(
        run, sections_choisies,
        (f"⏳ Reconnexion au run {run.id_run or '(en cours de demarrage)'}...",
         gr.update(), gr.update(), *_boutons(run.termine), run.id_run),
    )


def rafraichir_affichage(sections_choisies, resultat):
    if not resultat:
        return "Lance d'abord le pipeline (bouton \"Lancer le pipeline\") — rien a afficher pour l'instant."
    return construire_rapport_detaille(resultat, sections_choisies)


# --- Barre d'etapes (au-dessus du formulaire) ---
# (cle du noeud, libelle affiche, cle de l'etat remplie quand l'etape est terminee)
ETAPES_BARRE = [
    ("po", "Product Owner", "user_stories"),
    ("architect", "Architect", "architecture"),
    ("test_agent", "Test Agent", "plan_tests"),
    ("developer", "Developer", "sortie_dev"),
    ("qa_backend", "QA Backend", "rapport_backend"),
    ("frontend", "Frontend", "sortie_frontend"),
    ("qa_frontend", "QA Frontend", "rapport_frontend"),
    ("dockerization", "Dockerization", "rapport_dockerisation"),
    ("validation_docker", "Validation Docker", "rapport_validation_docker"),
]
# Etape d'echec final (cle "etape" de l'etat) -> noeud du controle concerne
ETAPE_ECHEC_VERS_NOEUD = {"backend": "qa_backend", "frontend": "qa_frontend", "docker": "validation_docker"}
STYLES_ETAT = {
    "ok": ("#ECFDF5", "#10B981", "#047857", "✓ "),
    "en_cours": ("#FFF7ED", "#F97316", "#C2410C", "⏳ "),
    "ko": ("#FEF2F2", "#EF4444", "#B91C1C", "✗ "),
    "attention": ("#FEFCE8", "#EAB308", "#854D0E", "! "),
    "attente": ("#F9FAFB", "#D1D5DB", "#9CA3AF", ""),
}


def etats_des_etapes(resultat) -> list[tuple[str, str, str]]:
    """Pour chaque etape : (libelle, etat, detail). etat parmi ok, en_cours, ko,
    attention, attente. Calcule uniquement a partir du resultat du pipeline."""
    if not resultat:
        return [(libelle, "attente", "") for _, libelle, _ in ETAPES_BARRE]
    en_cours = bool(resultat.get("_en_cours"))
    plantage = resultat.get("etape") if resultat.get("erreur") else None
    echec_final = None
    if not en_cours and not resultat.get("succes") and not plantage:
        echec_final = ETAPE_ECHEC_VERS_NOEUD.get(resultat.get("etape"))

    etapes, actif_trouve = [], False
    for noeud, libelle, cle in ETAPES_BARRE:
        valeur = resultat.get(cle)
        etat, detail = "attente", ""
        if noeud == plantage:
            etat, detail = "ko", "plantage"
        elif valeur is not None:
            etat = "ok"
            if noeud == "test_agent":
                detail = f"{len(valeur.cas)} cas" + (" · revises" if resultat.get("tests_revises") else "")
            elif noeud == "qa_backend":
                detail = f"{valeur.tests_passes}/{valeur.tests_passes + valeur.tests_echoues}"
            if noeud in ("qa_backend", "qa_frontend", "validation_docker") and not valeur.succes:
                tentative = resultat.get(
                    {"qa_backend": "tentative_backend", "qa_frontend": "tentative_frontend",
                     "validation_docker": "tentative_docker"}[noeud], 1)
                if noeud == "validation_docker" and not valeur.docker_disponible:
                    etat, detail = "attention", "non effectuee"
                elif noeud == echec_final or not en_cours:
                    etat = "ko"
                    detail = "machine" if getattr(valeur, "erreur_environnement", False) else f"echec {tentative}/{MAX_TENTATIVES}"
                else:
                    etat, detail = "en_cours", f"correction · tentative {tentative}/{MAX_TENTATIVES}"
                    actif_trouve = True
        elif en_cours and not plantage and not actif_trouve:
            etat, actif_trouve = "en_cours", True
        etapes.append((libelle, etat, detail))
    return etapes


def barre_etapes(resultat) -> str:
    """HTML de la barre d'etapes affichee au-dessus du formulaire."""
    if not resultat:
        return ""
    puces = []
    for libelle, etat, detail in etats_des_etapes(resultat):
        fond, bord, texte, icone = STYLES_ETAT[etat]
        suffixe = f" · {detail}" if detail else ""
        puces.append(
            f'<span style="display:inline-block;margin:3px 0;padding:6px 10px;border-radius:8px;'
            f'border:1.5px solid {bord};background:{fond};color:{texte};font-weight:600;font-size:13px">'
            f"{icone}{libelle}{suffixe}</span>")
    if resultat.get("_en_cours"):
        statut = "en cours"
    elif resultat.get("succes"):
        statut = "termine avec succes"
    else:
        statut = "arrete"
    titre = f"Run <b>{resultat.get('id_run', '')}</b> — {statut}"
    fleche = '<span style="color:#9CA3AF;margin:0 4px">→</span>'
    return (f'<div style="border:1px solid #E5E7EB;border-radius:10px;padding:10px 12px">'
            f'<div style="font-size:13px;color:#4B5563;margin-bottom:4px">{titre}</div>'
            f"{fleche.join(puces)}</div>")


# --- Interface : onglets « Run en cours » et « Runs existants » ---
COLONNES_HISTORIQUE = ["Projet", "Date", "Resultat", "Arret a"]
ETAPES_ECHEC_LISIBLES = {"backend": "QA Backend", "frontend": "QA Frontend", "docker": "Validation Docker",
                         "docker (machine)": "Validation Docker (machine)"}
COULEURS_STATUT = {"SUCCES": ("#ECFDF5", "#047857"), "ECHEC": ("#FEF2F2", "#B91C1C"),
                   "PLANTAGE": ("#FEF2F2", "#B91C1C"), "INTERROMPU": ("#FFF7ED", "#C2410C"),
                   "EN COURS": ("#FFF7ED", "#C2410C")}
MESSAGES_ETAPE = {
    "Product Owner": "Le Product Owner transforme la demande en user stories.",
    "Architect": "L'Architect choisit les technologies et l'organisation du code.",
    "Test Agent": "Le Test Agent ecrit le plan de test et les tests, avant le code.",
    "Developer": "Le Developer ecrit le backend pour faire passer les tests.",
    "QA Backend": "Le QA lance les tests du backend.",
    "Frontend": "Le Frontend Agent ecrit l'interface (HTML, CSS, JavaScript).",
    "QA Frontend": "Le QA verifie le frontend.",
    "Dockerization": "Le Dockerization Agent ecrit le Dockerfile et le docker-compose.",
    "Validation Docker": "Le Docker Validation Agent construit et demarre l'application pour verifier qu'elle marche.",
}
CORRECTEURS = {"QA Backend": "le Developer corrige le code",
               "QA Frontend": "le Frontend Agent corrige l'interface",
               "Validation Docker": "le Dockerization Agent corrige la configuration"}
# Style de la page (passe a demo.launch : Gradio 6)
CSS_AUTODEV = """
.carte { background: #FFFFFF !important; border: 1px solid #E5E7EB !important;
         border-radius: 12px !important; padding: 14px !important; gap: 10px !important; }
.carte .prose, .carte .prose * { color: #374151 !important; }
.table-runs, .table-runs * { font-family: var(--font) !important; }
.table-runs td { font-size: 14px !important; }
.table-runs th { background: #F9FAFB !important; color: #6B7280 !important; font-size: 13px !important; }
"""
COULEURS_PRIORITE = {"haute": ("#FEF2F2", "#B91C1C"), "moyenne": ("#FFF7ED", "#C2410C"), "basse": ("#F1F5F9", "#475569")}


def _e(texte) -> str:
    """Texte echappe pour le HTML (les sorties des agents viennent d'une IA)."""
    return html.escape(str(texte))


# ---------- Historique ----------

def runs_pour_tableau() -> tuple[list[list[str]], list[str]]:
    """Lignes du tableau (Projet, Date, Resultat, Arret a) et ID de chaque ligne,
    du run le plus recent au plus ancien."""
    lignes, ids = [], []
    actif = _run_actif.id_run if run_en_cours() else None
    for run in historique_runs():
        etape = run["etape"]
        arret = ETAPES_ECHEC_LISIBLES.get(etape) or LIBELLES_NOEUDS.get(etape, etape) or "—"
        statut = run["statut"] + (" · archive" if run["archive"] else "")
        if run["id_run"] == actif:
            statut, arret = "EN COURS", "—"
        lignes.append([run["titre"], run["date"], statut, arret])
        ids.append(run["id_run"])
    return lignes, ids


def _pastille_statut(statut) -> str:
    fond, texte = next((c for nom, c in COULEURS_STATUT.items() if str(statut).startswith(nom)),
                       ("#F3F4F6", "#374151"))
    return (f'<span style="padding:2px 10px;border-radius:9px;background:{fond};color:{texte};'
            f'font-weight:700;font-size:12px">{_e(statut)}</span>')


def tableau_runs(lignes):
    """Lignes du tableau, avec le resultat en pastille de couleur."""
    return [[projet, date, _pastille_statut(statut), arret] for projet, date, statut, arret in lignes]


def actualiser_runs():
    lignes, ids = runs_pour_tableau()
    return tableau_runs(lignes), ids


# ---------- Application generee : liens et plan de test ----------

def _fichiers_du_run(resultat) -> Path | None:
    """Dossier de sortie du run, s'il contient bien SES fichiers (pas archives)."""
    if not resultat:
        return None
    dossier = Path(resultat.get("dossier_docker", "output"))
    marqueur = dossier / FICHIER_ID_RUN
    if not marqueur.exists() or marqueur.read_text().strip() != resultat.get("id_run"):
        return None
    return dossier


def _ports_publies(compose: str) -> dict[int, int]:
    """{port du conteneur: port de la machine} lus dans docker-compose.yml."""
    return {int(cible): int(hote) for hote, cible in re.findall(r"[\"']?(\d{2,5}):(\d{2,5})[\"']?", compose)}


def liens_application(resultat) -> str:
    """Liens vers l'application generee par ce run (si ses fichiers sont dans output/)."""
    dossier = _fichiers_du_run(resultat)
    if dossier is None or not resultat.get("succes") or not (dossier / "docker-compose.yml").exists():
        return ""
    ports = _ports_publies((dossier / "docker-compose.yml").read_text(encoding="utf-8", errors="replace"))
    liens = []
    if 80 in ports:
        liens.append(("Ouvrir l'application", f"http://localhost:{ports[80]}"))
    if 8000 in ports:
        liens.append(("Ouvrir l'API", f"http://localhost:{ports[8000]}/docs"))
    if not liens:
        return ""
    boutons = "".join(
        f'<a href="{url}" target="_blank" style="flex:1;text-align:center;padding:9px;border-radius:8px;'
        f'border:1.5px solid #4F46E5;background:#EEF2FF;color:#4F46E5;font-weight:600;text-decoration:none">'
        f'{texte} ↗<br><span style="font-weight:400;font-size:12px">{url.split("//")[1]}</span></a>'
        for texte, url in liens)
    return ('<div style="font-size:13px;color:#4B5563;margin:2px 0 6px">Application generee par ce run '
            '<span style="color:#9CA3AF">(a lancer avant : docker compose up -d dans output)</span></div>'
            f'<div style="display:flex;gap:10px">{boutons}</div>')


def plan_de_test_du_run(resultat):
    """Bouton de telechargement du plan de test ecrit par le Test Agent."""
    dossier = _fichiers_du_run(resultat)
    plan = Path(resultat.get("dossier_backend", "")) / "PLAN_DE_TEST.md" if dossier else None
    if plan is not None and plan.exists():
        return gr.update(value=str(plan), visible=True)
    return gr.update(visible=False)


# ---------- Etat d'un run, en mots ----------

def run_en_cours() -> bool:
    return _run_actif is not None and not _run_actif.termine


def statut_du_run(resultat) -> str:
    if not resultat:
        return ""
    if resultat.get("_en_cours"):
        return "EN COURS"
    if resultat.get("erreur"):
        return "PLANTAGE"
    return "SUCCES" if resultat.get("succes") else "ECHEC"


def message_en_ce_moment(resultat) -> str:
    """Une phrase : ce que fait AutoDev en ce moment, ou ce qu'il faut faire."""
    if not resultat:
        return "Aucun run en cours. Lance un projet dans « Nouveau projet »."
    statut = statut_du_run(resultat)
    if statut == "SUCCES":
        return "Termine : l'application est prete dans output/ (backend, frontend, Docker et plan de test)."
    if statut == "PLANTAGE":
        etape = LIBELLES_NOEUDS.get(resultat.get("etape"), resultat.get("etape"))
        return (f"{etape} a plante : {resultat.get('erreur')}. Regle le probleme, puis clique sur Relancer "
                "(onglet « Runs existants ») : les etapes reussies ne sont pas refaites.")
    etats = etats_des_etapes(resultat)
    if statut == "ECHEC":
        for libelle, etat, detail in etats:
            if etat == "ko":
                if detail == "machine":
                    return (f"Probleme sur la machine a l'etape {libelle} (ex : port occupe). "
                            "Regle-le, puis clique sur Relancer.")
                return f"Echec a l'etape {libelle} apres toutes les corrections. Reformule la demande, puis relance."
        return "Le run s'est arrete."
    for libelle, etat, detail in etats:
        if etat == "en_cours":
            fin = " Tu peux fermer la page : le run continue."
            if detail.startswith("correction"):
                tentative = detail.split("tentative ")[-1]
                return (f"{libelle} : des erreurs ont ete trouvees, {CORRECTEURS.get(libelle, 'correction en cours')}"
                        f" — tentative {tentative}.{fin}")
            return MESSAGES_ETAPE.get(libelle, libelle) + fin
    return "Le run avance..."


def chrono_du_run(resultat) -> str:
    """Temps total et temps de l'etape en cours (seulement pour le run qui tourne)."""
    run = _run_actif
    if (run is None or run.termine or not resultat or not resultat.get("_en_cours")
            or run.id_run != resultat.get("id_run")):
        return ""
    maintenant = time.time()
    return (f"⏱ {_duree(maintenant - getattr(run, 'debut', maintenant))} · etape en cours depuis "
            f"{_duree(maintenant - getattr(run, 'debut_etape', maintenant))}")


def _resume_etape(libelle, resultat) -> str:
    """L'essentiel d'une etape terminee, en une ligne."""
    try:
        if libelle == "Product Owner":
            stories = resultat["user_stories"].user_stories
            n = {p: sum(1 for us in stories if us.priorite == p) for p in ("haute", "moyenne", "basse")}
            return f"{len(stories)} user stories · {n['haute']} haute, {n['moyenne']} moyenne, {n['basse']} basse"
        if libelle == "Architect":
            archi = resultat["architecture"]
            return " · ".join(s.split(" (")[0] for s in archi.stack_technique[:4]) + f" · {len(archi.structure_modules)} modules"
        if libelle == "Test Agent":
            plan = resultat["plan_tests"]
            revision = " · revises une fois" if resultat.get("tests_revises") else ""
            return f"{len(plan.cas)} cas de test · {len(plan.fichiers_tests)} fichiers{revision}"
        if libelle == "Developer":
            return f"{len(resultat['sortie_dev'].fichiers_generes)} fichiers generes"
        if libelle == "QA Backend":
            r = resultat["rapport_backend"]
            return f"{r.tests_passes}/{r.tests_passes + r.tests_echoues} tests · couverture {r.couverture_pct:.1f} %"
        if libelle == "Frontend":
            return f"{len(resultat['sortie_frontend'].fichiers_generes)} fichiers generes"
        if libelle == "QA Frontend":
            r = resultat["rapport_frontend"]
            return f"{len(r.fichiers_verifies)} fichiers verifies" + (f" · {len(r.erreurs)} erreur(s)" if r.erreurs else "")
        if libelle == "Dockerization":
            return f"{len(resultat['rapport_dockerisation'].fichiers_generes)} fichiers (Dockerfile, docker-compose…)"
        if libelle == "Validation Docker":
            r = resultat["rapport_validation_docker"]
            if not r.docker_disponible:
                return "non effectuee : Docker non joignable"
            return " · ".join(f"{e.nom} {'OK' if e.succes else 'ECHEC'}" for e in r.etapes) or "OK"
    except (KeyError, AttributeError, TypeError):
        return ""
    return ""


# ---------- Rendu HTML d'un run ----------

STYLE_CARTE = {
    "ok": ("#FFFFFF", "#10B981", "#111827", "✓ "),
    "en_cours": ("#FFFBF5", "#F97316", "#C2410C", "⏳ "),
    "ko": ("#FFFAFA", "#EF4444", "#B91C1C", "✗ "),
    "attention": ("#FEFCE8", "#EAB308", "#854D0E", "! "),
    "attente": ("#F9FAFB", "#D1D5DB", "#9CA3AF", ""),
}


def _puce(texte, fond, couleur, taille=12):
    return (f'<span style="padding:2px 9px;border-radius:9px;background:{fond};color:{couleur};'
            f'font-weight:700;font-size:{taille}px">{_e(texte)}</span>')


def _cartes(resultat, en_cours) -> str:
    cartes = []
    for libelle, etat, detail in etats_des_etapes(resultat):
        fond, bord, couleur, icone = STYLE_CARTE[etat]
        if etat == "ok":
            ligne = _resume_etape(libelle, resultat)
        elif etat == "en_cours":
            ligne = (_resume_etape(libelle, resultat) + " · " if detail.startswith("correction") else "") + (detail or "en cours…")
        elif etat == "ko":
            ligne = f"plantage : {resultat.get('erreur', '')}" if detail == "plantage" else (_resume_etape(libelle, resultat) + f" · {detail}")
        elif etat == "attention":
            ligne = _resume_etape(libelle, resultat)
        else:
            ligne = "en attente" if en_cours else "non atteint"
        cartes.append(
            f'<div style="border:1px solid #E5E7EB;border-left:5px solid {bord};border-radius:10px;'
            f'padding:9px 12px;background:{fond}"><div style="font-weight:700;font-size:14px;color:{couleur}">'
            f'{icone}{_e(libelle)}</div><div style="font-size:12.5px;color:#4B5563;margin-top:3px">{_e(ligne)}</div></div>')
    return ('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px">'
            + "".join(cartes) + "</div>")


def _chiffres(resultat) -> str:
    us = resultat.get("user_stories")
    plan = resultat.get("plan_tests")
    qa = resultat.get("rapport_backend")
    terminees = sum(1 for _, etat, _ in etats_des_etapes(resultat) if etat == "ok")
    valeurs = [
        (len(us.user_stories) if us else "—", "user stories"),
        (len(plan.cas) if plan else "—", "cas de test (ecrits avant le code)"),
        (f"{qa.tests_passes}/{qa.tests_passes + qa.tests_echoues}" if qa else "—", "tests reussis"),
        (f"{qa.couverture_pct:.0f} %" if qa else "—", "couverture du code"),
        (f"{terminees}/{len(ETAPES_BARRE)}", "etapes terminees"),
    ]
    return ('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0">'
            + "".join(f'<div style="border:1px solid #E5E7EB;border-radius:10px;padding:8px 12px;background:#FFFFFF">'
                      f'<div style="font-size:22px;font-weight:700;color:#111827">{_e(v)}</div>'
                      f'<div style="font-size:12px;color:#6B7280">{_e(t)}</div></div>' for v, t in valeurs)
            + "</div>")


def _details(resultat) -> str:
    """Le detail, replie : user stories, plan de test, architecture, erreurs."""
    blocs = []
    style_table = 'style="width:100%;border-collapse:collapse;font-size:13px;color:#111827"'
    style_th = 'style="text-align:left;padding:6px;border-bottom:1px solid #E5E7EB;color:#6B7280"'
    style_td = 'style="padding:6px;border-bottom:1px solid #F1F5F9"'
    us = resultat.get("user_stories")
    if us:
        lignes = "".join(
            f"<tr><td {style_td}>{_e(s.id)}</td><td {style_td}>{_e(s.titre)}</td>"
            f"<td {style_td}>{_puce(s.priorite, *COULEURS_PRIORITE.get(s.priorite, ('#F1F5F9', '#475569')))}</td>"
            f"<td {style_td}>{len(s.criteres_acceptation)}</td></tr>" for s in us.user_stories)
        blocs.append(("User stories", len(us.user_stories),
                      f"<table {style_table}><tr><th {style_th}>ID</th><th {style_th}>User story</th>"
                      f"<th {style_th}>Priorite</th><th {style_th}>Criteres</th></tr>{lignes}</table>"))
    plan = resultat.get("plan_tests")
    if plan:
        lignes = "".join(
            f"<tr><td {style_td}>{_e(c.id)}</td><td {style_td}>{_e(c.user_story)}</td>"
            f"<td {style_td}><code>{_e(c.methode)} {_e(c.route)}</code></td><td {style_td}>{_e(c.code_attendu)}</td>"
            f"<td {style_td}>{_e(c.scenario)}</td></tr>" for c in plan.cas)
        blocs.append(("Plan de test du Test Agent", len(plan.cas),
                      f"<table {style_table}><tr><th {style_th}>Cas</th><th {style_th}>US</th><th {style_th}>Requete</th>"
                      f"<th {style_th}>Code attendu</th><th {style_th}>Scenario</th></tr>{lignes}</table>"))
    archi = resultat.get("architecture")
    if archi:
        modules = "".join(f"<li>{_e(m)}</li>" for m in archi.structure_modules)
        blocs.append(("Architecture", len(archi.structure_modules),
                      f'<div style="font-size:13px;color:#111827"><b>Stack :</b> {_e(", ".join(archi.stack_technique))}'
                      f'<ul style="margin:6px 0 0 18px">{modules}</ul></div>'))
    erreurs = []
    for cle in ("rapport_backend", "rapport_frontend", "rapport_validation_docker"):
        rapport = resultat.get(cle)
        if rapport is not None and not rapport.succes:
            erreurs += [str(err) for err in rapport.erreurs]
    if erreurs:
        items = "".join(f'<li style="margin-bottom:4px"><pre style="white-space:pre-wrap;margin:0;font-size:12px">{_e(err[:1500])}</pre></li>'
                        for err in erreurs[:10])
        blocs.append(("Erreurs trouvees par les controles", len(erreurs), f'<ul style="margin:0 0 0 18px;color:#991B1B">{items}</ul>'))
    return "".join(
        f'<details style="margin-top:8px;border:1px solid #E5E7EB;border-radius:10px;padding:8px 12px;background:#FFFFFF">'
        f'<summary style="cursor:pointer;font-weight:700;font-size:14px;color:#111827">{_e(titre)} '
        f'<span style="color:#6B7280;font-weight:400">({n})</span></summary>'
        f'<div style="margin-top:8px">{contenu}</div></details>' for titre, n, contenu in blocs)


def _puces_etapes(resultat) -> str:
    puces = []
    for libelle, etat, detail in etats_des_etapes(resultat):
        fond, bord, texte, icone = STYLES_ETAT[etat]
        suffixe = f" · {detail}" if detail else ""
        puces.append(
            f'<span style="display:inline-block;margin:3px 0;padding:5px 9px;border-radius:8px;'
            f'border:1.5px solid {bord};background:{fond};color:{texte};font-weight:600;font-size:12.5px">'
            f"{icone}{_e(libelle)}{_e(suffixe)}</span>")
    return '<span style="color:#9CA3AF;margin:0 3px">→</span>'.join(puces)


def vue_run(resultat, avec_chrono=False) -> str:
    """Tout un run en HTML : statut, barre d'etapes, « en ce moment », chiffres, cartes, detail."""
    if not resultat:
        return ('<div style="border:1px dashed #D1D5DB;border-radius:12px;padding:28px;text-align:center;'
                'color:#6B7280;font-size:15px">Aucun run en cours. Lance un projet dans « Nouveau projet », '
                "ou choisis un run dans « Runs existants ».</div>")
    statut = statut_du_run(resultat)
    fond, couleur = COULEURS_STATUT.get(statut, ("#F3F4F6", "#374151"))
    besoin = resultat.get("besoin")
    titre = besoin.titre_projet if besoin else ""
    chrono = chrono_du_run(resultat) if avec_chrono else ""
    en_cours = statut == "EN COURS"
    fond_message = {"EN COURS": "#FFEDD5", "SUCCES": "#DCFCE7"}.get(statut, "#FEE2E2")
    couleur_message = {"EN COURS": "#7C2D12", "SUCCES": "#14532D"}.get(statut, "#7F1D1D")
    titre_message = {"EN COURS": "En ce moment", "SUCCES": "Resultat"}.get(statut, "A faire")
    return (
        f'<div style="border:1px solid {"#FDBA74" if en_cours else "#E5E7EB"};border-radius:12px;padding:14px 16px;'
        f'background:{"#FFFBF5" if en_cours else "#FFFFFF"}">'
        f'<div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px">'
        f'<div>{_puce(statut, fond, couleur, 13)} <b style="font-size:18px;margin-left:8px;color:#111827">{_e(titre)}</b>'
        f' <span style="color:#6B7280;font-size:13px">· {_e(resultat.get("id_run", ""))}</span></div>'
        f'<div style="font-size:13px;color:#C2410C;font-weight:600">{_e(chrono)}</div></div>'
        f'<div style="margin-top:10px">{_puces_etapes(resultat)}</div>'
        f'<div style="margin-top:10px;font-size:13.5px;color:{couleur_message};background:{fond_message};'
        f'border-radius:8px;padding:8px 12px"><b>{titre_message} :</b> {_e(message_en_ce_moment(resultat))}</div>'
        f"</div>{_chiffres(resultat)}{_cartes(resultat, en_cours)}"
        f'<div style="margin-top:10px">{liens_application(resultat)}</div>{_details(resultat)}')


def alerte_depuis_texte(texte) -> str:
    """Messages courts (entree refusee, rejeu impossible...) en encadre visible."""
    texte = (texte or "").strip()
    if not texte.startswith(("⚠️", "❌ Entree", "❌ Le run s'est arrete")):
        return ""
    return (f'<div style="border:1px solid #FCD34D;background:#FFFBEB;color:#78350F;border-radius:10px;'
            f'padding:10px 14px;font-size:14px;margin-bottom:8px">{_e(texte)}</div>')


# ---------- Evenements ----------

# Un seul bouton « Relancer » : le premier choix de la liste reprend le run la
# ou il s'est arrete (ancien « Reprendre »), les autres le rejouent a partir
# de l'etape choisie (ancien « Rejouer »).
REPRISE = "La ou il s'est arrete"


def choix_de_relance(id_run) -> list[str]:
    """Choix de la liste « Relancer a partir de » pour ce run : d'abord la ou
    il s'est arrete (s'il a plante ou ete interrompu), puis chaque etape."""
    etapes = list(ETAPES_REJOUABLES)
    if not id_run:
        return etapes
    try:
        suivante = point_de_reprise(id_run).next
    except RepriseImpossible:
        return etapes  # termine sans plantage : rien a reprendre
    if not suivante:
        return etapes
    nom = next((libelle for libelle, noeud in ETAPES_REJOUABLES.items() if noeud == suivante[0]), suivante[0])
    return [f"{REPRISE} ({nom})"] + etapes


def _etape_du_choix(choix) -> str:
    """« La ou il s'est arrete (Developer) » -> « Developer »."""
    if choix and choix.startswith(REPRISE):
        return choix[len(REPRISE):].strip(" ()")
    return choix or ""


def libelle_relancer(choix):
    etape = _etape_du_choix(choix)
    return gr.update(value=f"Relancer a partir de « {etape} »" if etape else "Relancer")


def relance_pour(id_run, resultat):
    """Liste et bouton « Relancer » pour le run choisi (bouton grise pendant
    un run). Sorties : liste, bouton."""
    choix = choix_de_relance(id_run)
    etape = _etape_du_choix(choix[0])
    occupe = run_en_cours() or bool(resultat and resultat.get("_en_cours"))
    return (gr.update(choices=choix, value=choix[0]),
            gr.update(value=f"Relancer a partir de « {etape} »", interactive=not occupe))


def relancer_pipeline(id_run, choix, sections_choisies):
    """Clic sur « Relancer » : reprise si le premier choix (la ou il s'est
    arrete) est selectionne, sinon rejeu a partir de l'etape choisie."""
    if choix and choix.startswith(REPRISE):
        yield from reprendre_pipeline(id_run, sections_choisies)
    else:
        yield from rejouer_pipeline(id_run, choix, sections_choisies)


def texte_id(id_run) -> str:
    return f"ID : {id_run}" if id_run else "ID : —"


def choisir_run(ids, evt: gr.SelectData):
    """Clic sur une ligne de l'historique : ce run s'affiche en dessous.
    Sorties : id_run, texte de l'ID, vue du run, liens, plan, liste et bouton Relancer."""
    ligne = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    if ligne is None or ligne >= len(ids):
        return (gr.update(),) * 7
    id_run = ids[ligne]
    resultat = etat_du_run(id_run)
    return (id_run, texte_id(id_run), vue_run(resultat), liens_application(resultat),
            plan_de_test_du_run(resultat), *relance_pour(id_run, resultat))


# « Runs existants » : le resultat d'un run s'affiche quand on clique sur sa ligne
VUE_CHOISIR_UN_RUN = ('<div style="border:1px dashed #D1D5DB;border-radius:12px;padding:28px;'
                      'text-align:center;color:#6B7280;font-size:15px">'
                      "Clique sur un run dans la liste pour voir son resultat ici.</div>")
TEXTE_AUCUN_RUN_CHOISI = "Choisis d'abord un run dans la liste"


def charger_page():
    """Ouverture de la page : l'historique. Aucun run n'est choisi : son
    resultat s'affiche quand on clique sur sa ligne.
    Sorties : tableau, ids, id_run, texte de l'ID, etat, vue choisie, liens,
    plan, liste et bouton Relancer."""
    lignes, ids = runs_pour_tableau()
    return (tableau_runs(lignes), ids, gr.update(), "ID : —", gr.update(), VUE_CHOISIR_UN_RUN, "",
            gr.update(visible=False), gr.update(),
            gr.update(value=TEXTE_AUCUN_RUN_CHOISI, interactive=False))


def vue_suivi(resultat):
    return vue_run(resultat, avec_chrono=True)


def rafraichir_suivi(resultat):
    """Toutes les 5 s : le chronometre et le point orange de l'onglet."""
    if run_en_cours():
        return vue_run(resultat, avec_chrono=True), gr.update(label="Run en cours ●")
    return gr.update(), gr.update(label="Run en cours")


def apres_changement_du_run(resultat):
    """Fin ou progression du run suivi : l'historique est remis a jour. A la
    fin du run, il devient le run choisi dans « Runs existants ».
    Sorties : tableau, ids, liste et bouton Relancer, texte de l'ID, vue choisie."""
    lignes, ids = runs_pour_tableau()
    if resultat and not resultat.get("_en_cours") and not run_en_cours():
        id_fini = resultat.get("id_run")
        return (tableau_runs(lignes), ids, *relance_pour(id_fini, resultat), texte_id(id_fini), vue_run(resultat))
    return (tableau_runs(lignes), ids) + (gr.update(),) * 4


# Lancer, Reprendre et Rejouer affichent l'onglet « Run en cours » : un petit
# script cote navigateur clique sur l'onglet, puis transmet les valeurs du
# formulaire a la fonction Python sans les modifier.
JS_ALLER_AU_RUN_EN_COURS = """(...valeurs) => {
    const onglet = [...document.querySelectorAll('button[role=tab]')]
        .find(b => b.innerText.trim().startsWith('Run en cours'));
    if (onglet) onglet.click();
    return valeurs;
}"""


with gr.Blocks(title="AutoDev — Generateur de backend et frontend automatique") as demo:
    gr.Markdown(
        "# AutoDev — Generateur de backend et frontend automatique\n"
        "Decris ton projet dans « Nouveau projet », suis-le dans « Run en cours », "
        "relance un run dans « Runs existants »."
    )

    with gr.Tabs(selected="nouveau") as onglets:
        with gr.Tab("Nouveau projet", id="nouveau"):
            titre = gr.Textbox(label="Titre du projet", placeholder="Ex: Todo App 1")
            description = gr.Textbox(label="Description", lines=3, placeholder="Decris ton projet en quelques phrases")
            utilisateurs = gr.Textbox(label="Utilisateurs cibles", placeholder="Ex: Etudiants, particuliers...")
            fonctionnalites = gr.Textbox(label="Fonctionnalites cles (separees par virgules)", placeholder="login, creer tache, marquer terminee")
            structure = gr.Textbox(label="Organisation de l'interface", lines=2, placeholder="Ex: pages/sections souhaitees, organisation generale (optionnel)")
            bouton_lancer = gr.Button("Lancer le pipeline", variant="primary")

        with gr.Tab("Run en cours", id="en_cours") as onglet_en_cours:
            alerte = gr.HTML()
            suivi = gr.HTML(vue_run(None))
            with gr.Accordion("Rapport detaille (texte brut)", open=False):
                resultat_texte = gr.Textbox(show_label=False, lines=22)

        with gr.Tab("Runs existants", id="runs"):
            with gr.Row(equal_height=False):
                with gr.Column(scale=11, elem_classes="carte"):
                    table_runs = gr.Dataframe(
                        headers=COLONNES_HISTORIQUE, datatype=["str", "str", "html", "str"],
                        interactive=False, wrap=True, elem_classes="table-runs",
                        label="Choisis un run (clique sur une ligne : plus besoin de copier l'ID)",
                    )
                    id_affiche = gr.Markdown("ID : —")
                    bouton_actualiser = gr.Button("Actualiser la liste", size="sm")
                with gr.Column(scale=9):
                    with gr.Column(elem_classes="carte"):
                        gr.Markdown(
                            "**Relancer le run choisi**\n\n"
                            "- Il a plante (credit, Ollama, port occupe) : regle le probleme et garde le "
                            "premier choix, AutoDev repart la ou il s'est arrete.\n"
                            "- Tu as modifie un agent : choisis l'etape d'ou repartir. "
                            "Les etapes d'avant ne sont pas refaites."
                        )
                        etape_relance = gr.Dropdown(
                            choices=list(ETAPES_REJOUABLES), value=list(ETAPES_REJOUABLES)[0],
                            label="Relancer a partir de",
                        )
                        bouton_relancer = gr.Button(TEXTE_AUCUN_RUN_CHOISI, variant="primary", interactive=False)
                    bouton_plan = gr.DownloadButton("Telecharger le plan de test", visible=False, size="sm")
            vue_choisie = gr.HTML(VUE_CHOISIR_UN_RUN)

    # Composants caches, utilises par les fonctions du pipeline
    liens = gr.HTML(visible=False)  # les liens sont affiches sous le run choisi
    id_run = gr.Textbox(visible=False)
    ids_runs = gr.State([])
    sections_choisies = gr.CheckboxGroup(choices=TOUTES_LES_SECTIONS, value=TOUTES_LES_SECTIONS, visible=False)
    user_stories_json = gr.Code(language="json", visible=False)
    resultat_state = gr.State(None)
    sorties_run = [resultat_texte, user_stories_json, resultat_state, bouton_lancer, bouton_relancer, id_run]

    # concurrency_limit=None : ces fonctions ne font que suivre un run qui tourne
    # dans son propre thread ; un suivi abandonne (page deconnectee) ne doit pas
    # bloquer les suivants. _demarrer_run empeche deux runs en parallele.
    bouton_lancer.click(
        fn=lancer_pipeline_complet,
        js=JS_ALLER_AU_RUN_EN_COURS,  # ouvre l'onglet « Run en cours »
        inputs=[titre, description, utilisateurs, fonctionnalites, structure, sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    bouton_relancer.click(
        fn=relancer_pipeline,
        js=JS_ALLER_AU_RUN_EN_COURS,  # ouvre l'onglet « Run en cours »
        inputs=[id_run, etape_relance, sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    demo.load(
        fn=suivre_run_actif,
        inputs=[sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    demo.load(fn=charger_page, outputs=[table_runs, ids_runs, id_run, id_affiche, resultat_state,
                                        vue_choisie, liens, bouton_plan, etape_relance, bouton_relancer])
    # Le suivi (onglet « Run en cours ») et l'historique suivent le run
    resultat_state.change(fn=vue_suivi, inputs=resultat_state, outputs=suivi)
    resultat_state.change(fn=apres_changement_du_run, inputs=resultat_state,
                          outputs=[table_runs, ids_runs, etape_relance, bouton_relancer, id_affiche, vue_choisie])
    resultat_texte.change(fn=alerte_depuis_texte, inputs=resultat_texte, outputs=alerte)
    minuteur = gr.Timer(5)
    minuteur.tick(fn=rafraichir_suivi, inputs=resultat_state, outputs=[suivi, onglet_en_cours])
    # Onglet « Runs existants »
    table_runs.select(
        fn=choisir_run, inputs=[ids_runs],
        outputs=[id_run, id_affiche, vue_choisie, liens, bouton_plan, etape_relance, bouton_relancer],
    )
    bouton_actualiser.click(fn=actualiser_runs, outputs=[table_runs, ids_runs])
    etape_relance.change(fn=libelle_relancer, inputs=etape_relance, outputs=bouton_relancer)


def identifiants_formulaire() -> tuple[str, str] | None:
    """Identifiant et mot de passe du formulaire (.env), ou None s'ils manquent."""
    utilisateur = os.environ.get("GRADIO_AUTH_USER")
    mot_de_passe = os.environ.get("GRADIO_AUTH_PASSWORD")
    return (utilisateur, mot_de_passe) if utilisateur and mot_de_passe else None


def lancer_formulaire(**options):
    """Lance le formulaire, protege par mot de passe si .env le definit."""
    options.setdefault("css", CSS_AUTODEV)
    identifiants = identifiants_formulaire()
    if identifiants:
        return demo.launch(auth=identifiants, **options)
    print(
        "ATTENTION: GRADIO_AUTH_USER / GRADIO_AUTH_PASSWORD non definis dans .env — "
        "le formulaire est lance SANS authentification. N'importe qui avec l'URL peut "
        "declencher le pipeline (et consommer tes credits API). Definis ces 2 variables "
        "dans .env pour proteger l'acces."
    )
    return demo.launch(**options)


if __name__ == "__main__":
    lancer_formulaire()
