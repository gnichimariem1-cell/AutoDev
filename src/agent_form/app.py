import gradio as gr
from src.common.schemas import BesoinUtilisateur
from src.agent_orchestrateur.orchestrateur import (
    executer_pipeline_en_direct, reprendre_pipeline_en_direct, point_de_reprise, RepriseImpossible,
)

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
    "developer": "Developer Agent",
    "qa_backend": "QA Agent (backend)",
    "correction_backend": "Correction du backend",
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


def _suivre_dans_la_vue(evenements, sections_choisies, id_run_affiche=""):
    """Generateur : Gradio met a jour l'affichage a chaque `yield`, donc apres
    chaque etape du pipeline. Sorties : rapport, User Stories JSON, etat,
    bouton Lancer, bouton Reprendre, ID du run."""
    resultat = None
    for noeud, etat in evenements:
        resultat = dict(etat, _en_cours=noeud)
        if noeud == "echec":
            continue  # le yield final ci-dessous affiche directement l'echec
        yield (construire_rapport_detaille(resultat, sections_choisies), _user_stories_json(resultat),
               resultat, *_boutons(False), resultat["id_run"])

    resultat.pop("_en_cours")
    yield (construire_rapport_detaille(resultat, sections_choisies), _user_stories_json(resultat),
           resultat, *_boutons(True), resultat["id_run"])


def lancer_pipeline_complet(titre, description, utilisateurs, fonctionnalites, structure, sections_choisies):
    besoin = collecter_besoin(titre, description, utilisateurs, fonctionnalites, structure)
    yield "⏳ Pipeline lance — Product Owner Agent en cours...", "{}", None, *_boutons(False), ""
    yield from _suivre_dans_la_vue(executer_pipeline_en_direct(besoin), sections_choisies)


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
    yield f"⏳ Reprise du run {id_run} a l'etape {etape}...", gr.update(), gr.update(), *_boutons(False), id_run
    yield from _suivre_dans_la_vue(reprendre_pipeline_en_direct(id_run), sections_choisies)


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

    bouton_lancer.click(
        fn=lancer_pipeline_complet,
        inputs=[titre, description, utilisateurs, fonctionnalites, structure, sections_choisies],
        outputs=sorties_run,
    )
    bouton_reprendre.click(
        fn=reprendre_pipeline,
        inputs=[id_run, sections_choisies],
        outputs=sorties_run,
    )
    sections_choisies.change(
        fn=rafraichir_affichage,
        inputs=[sections_choisies, resultat_state],
        outputs=[resultat_texte],
    )

if __name__ == "__main__":
    demo.launch()
