import os
import re
import threading
import time

from dotenv import load_dotenv

# Charge .env avant tout import qui lit l'environnement : les sous-processus `claude`
# heritent ainsi de ANTHROPIC_API_KEY / CLAUDE_CONFIG_DIR (compte Claude du projet).
# Les variables deja definies (ex. par docker compose) restent prioritaires.
load_dotenv()

import gradio as gr
from src.common.schemas import BesoinUtilisateur
from src.agent_orchestrateur.orchestrateur import (
    executer_pipeline_en_direct, reprendre_pipeline_en_direct, point_de_reprise, RepriseImpossible,
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
        self._condition = threading.Condition()
        threading.Thread(target=self._executer, args=(evenements,), daemon=True).start()

    def _executer(self, evenements):
        try:
            for noeud, etat in evenements:
                with self._condition:
                    self.id_run = etat.get("id_run", self.id_run)
                    self.evenements.append((noeud, dict(etat)))
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


def suivre_run_actif(sections_choisies):
    """A l'ouverture (ou au rechargement) de la page : se rattache au run en
    cours, ou affiche le resultat du dernier run, avec son ID pre-rempli."""
    run = _run_actif
    if run is None:
        yield gr.update(), gr.update(), gr.update(), *_boutons(True), gr.update()
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


with gr.Blocks(title="AutoDev — Generateur de backend et frontend automatique") as demo:
    gr.Markdown(
        "# AutoDev — Generateur de backend et frontend automatique\n"
        "Remplis le formulaire ci-dessous. Le pipeline va automatiquement generer un backend FastAPI "
        "et un frontend web, testes et prets a l'emploi (compte 3 a 10 minutes)."
    )

    with gr.Row():
        with gr.Column():
            titre = gr.Textbox(label="Titre du projet", placeholder="Ex: Todo App 1")
            description = gr.Textbox(label="Description", lines=3, placeholder="Decris ton projet en quelques phrases")
            utilisateurs = gr.Textbox(label="Utilisateurs cibles", placeholder="Ex: Etudiants, particuliers...")
            fonctionnalites = gr.Textbox(label="Fonctionnalites cles (separees par virgules)", placeholder="login, creer tache, marquer terminee")
            structure = gr.Textbox(label="Organisation de l'interface", lines=2, placeholder="Ex: pages/sections souhaitees, organisation generale (optionnel)")
            bouton_lancer = gr.Button("Lancer le pipeline", variant="primary")
            with gr.Row():
                id_run = gr.Textbox(
                    label="ID du run",
                    placeholder="rempli automatiquement apres chaque run",
                    info="Apres un plantage (credit Claude epuise, Ollama arrete...), "
                         "corrige le probleme puis clique sur Reprendre : les etapes deja reussies ne sont pas refaites.",
                    scale=3,
                )
                bouton_reprendre = gr.Button("Reprendre", scale=1)

        with gr.Column():
            sections_choisies = gr.CheckboxGroup(
                choices=TOUTES_LES_SECTIONS,
                value=TOUTES_LES_SECTIONS,
                label="Sections a afficher (coche/decoche a tout moment, meme apres le run)",
            )
            resultat_texte = gr.Textbox(label="Resultat du pipeline — detail agent par agent", lines=28)
            user_stories_json = gr.Code(label="User Stories (JSON)", language="json", lines=14)

    resultat_state = gr.State(None)
    sorties_run = [resultat_texte, user_stories_json, resultat_state, bouton_lancer, bouton_reprendre, id_run]

    # concurrency_limit=None : ces fonctions ne font que suivre un run qui tourne
    # dans son propre thread ; un suivi abandonne (page deconnectee) ne doit pas
    # bloquer les suivants. _demarrer_run empeche deux runs en parallele.
    bouton_lancer.click(
        fn=lancer_pipeline_complet,
        inputs=[titre, description, utilisateurs, fonctionnalites, structure, sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    bouton_reprendre.click(
        fn=reprendre_pipeline,
        inputs=[id_run, sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    demo.load(
        fn=suivre_run_actif,
        inputs=[sections_choisies],
        outputs=sorties_run,
        concurrency_limit=None,
    )
    sections_choisies.change(
        fn=rafraichir_affichage,
        inputs=[sections_choisies, resultat_state],
        outputs=[resultat_texte],
    )

if __name__ == "__main__":
    utilisateur = os.environ.get("GRADIO_AUTH_USER")
    mot_de_passe = os.environ.get("GRADIO_AUTH_PASSWORD")
    if utilisateur and mot_de_passe:
        demo.launch(auth=(utilisateur, mot_de_passe))
    else:
        print(
            "ATTENTION: GRADIO_AUTH_USER / GRADIO_AUTH_PASSWORD non definis dans .env — "
            "le formulaire est lance SANS authentification. N'importe qui avec l'URL peut "
            "declencher le pipeline (et consommer tes credits API). Definis ces 2 variables "
            "dans .env pour proteger l'acces."
        )
        demo.launch()
