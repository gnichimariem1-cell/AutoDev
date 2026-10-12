"""Historique des runs et onglets « Run en cours » / « Runs existants »."""
from types import SimpleNamespace

from src.agent_orchestrateur.orchestrateur import executer_pipeline, historique_runs, etat_du_run
from src.agent_form.app import (
    runs_pour_tableau, tableau_runs, liens_application, plan_de_test_du_run, relance_pour, choix_de_relance, relancer_pipeline,
    choisir_run, charger_page, vue_run, message_en_ce_moment, alerte_depuis_texte, statut_du_run,
)
from tests.sorties import BESOIN, QA_KO


def _par_id(runs):
    return {r["id_run"]: r for r in runs}


def test_historique_avec_une_base_neuve(tmp_path):
    """Premier lancement d'AutoDev : aucune sauvegarde, la page doit quand meme s'ouvrir."""
    from src.agent_orchestrateur import orchestrateur
    from src.agent_orchestrateur.graphe import construire_graphe
    from src.agent_orchestrateur.sauvegarde import creer_checkpointer
    import os
    ancien, ancienne_base = orchestrateur.GRAPHE, os.environ.get("CHECKPOINT_DB")
    os.environ["CHECKPOINT_DB"] = str(tmp_path / "neuve.sqlite")
    try:
        orchestrateur.GRAPHE = construire_graphe(checkpointer=creer_checkpointer())
        assert historique_runs() == []
    finally:
        orchestrateur.GRAPHE = ancien
        os.environ["CHECKPOINT_DB"] = ancienne_base or ":memory:"


def test_historique_succes_et_plantage(agents):
    ok = executer_pipeline(BESOIN)
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    ko = executer_pipeline(BESOIN)

    runs = historique_runs()
    ids = [r["id_run"] for r in runs]
    assert ids.index(ko["id_run"]) < ids.index(ok["id_run"])  # le plus recent d'abord
    runs = _par_id(runs)
    assert runs[ok["id_run"]]["statut"] == "SUCCES"
    assert runs[ko["id_run"]]["statut"] == "PLANTAGE"
    assert runs[ko["id_run"]]["etape"] == "developer"
    assert runs[ok["id_run"]]["titre"] == "Todo App"
    assert runs[ok["id_run"]]["archive"] is True   # fichiers archives par le run suivant
    assert runs[ko["id_run"]]["archive"] is False


def test_tableau_lisible_et_en_couleur(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    ko = executer_pipeline(BESOIN)
    lignes, ids = runs_pour_tableau()
    ligne = lignes[ids.index(ko["id_run"])]
    assert ligne == ["Todo App", ligne[1], "PLANTAGE", "Developer Agent"]
    assert "#FEF2F2" in str(tableau_runs(lignes))  # pastille rouge sur PLANTAGE


def test_clic_sur_une_ligne_affiche_le_run(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    ko = executer_pipeline(BESOIN)
    _, ids = runs_pour_tableau()
    sorties = choisir_run(ids, SimpleNamespace(index=[ids.index(ko["id_run"]), 0]))
    assert sorties[0] == ko["id_run"]
    assert "PLANTAGE" in sorties[2] and "Relancer" in sorties[2]
    assert sorties[6]["interactive"] is True


def test_vue_d_un_run_reussi(agents):
    ok = executer_pipeline(BESOIN)
    html = vue_run(ok)
    assert "SUCCES" in html and "Todo App" in html
    assert "user stories" in html and "cas de test" in html
    assert "Plan de test du Test Agent" in html  # detail replie
    assert statut_du_run(ok) == "SUCCES"


def test_vue_echappe_le_texte_des_agents(agents):
    resultat = executer_pipeline(BESOIN)
    resultat["erreur"], resultat["etape"] = "<script>alert(1)</script>", "developer"
    html = vue_run(resultat)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_message_pendant_une_correction(agents):
    resultat = executer_pipeline(BESOIN)
    en_cours = dict(resultat, _en_cours="qa_backend", succes=False, rapport_backend=QA_KO, tentative_backend=2)
    for cle in ("sortie_frontend", "rapport_frontend", "rapport_dockerisation", "rapport_validation_docker"):
        en_cours.pop(cle, None)
    message = message_en_ce_moment(en_cours)
    assert "le Developer corrige le code" in message and "tentative 2/3" in message
    assert "EN COURS" in vue_run(en_cours)


def test_messages_sans_run_et_alerte():
    assert "Aucun run en cours" in message_en_ce_moment(None)
    assert "Aucun run en cours" in vue_run(None)
    assert "Choisis" in alerte_depuis_texte("⚠️ Choisis l'etape a partir de laquelle rejouer.")
    assert alerte_depuis_texte("✅ SUCCES — pipeline complet") == ""


def test_relancer_un_run_reussi_commence_au_product_owner(agents):
    ok = executer_pipeline(BESOIN)
    choix = choix_de_relance(ok["id_run"])
    assert choix[0] == "Product Owner"  # rien a reprendre : pas de « La ou il s'est arrete »
    liste, bouton = relance_pour(ok["id_run"], ok)
    assert liste["value"] == "Product Owner"
    assert bouton["value"] == "Relancer a partir de « Product Owner »" and bouton["interactive"] is True


def test_relancer_un_run_qui_a_plante(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    ko = executer_pipeline(BESOIN)
    choix = choix_de_relance(ko["id_run"])
    assert choix[0] == "La ou il s'est arrete (Developer)"
    assert "Product Owner" in choix[1:]
    assert relance_pour(ko["id_run"], ko)[1]["value"] == "Relancer a partir de « Developer »"


def test_relancer_premier_choix_reprend_le_run(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    ko = executer_pipeline(BESOIN)
    agents.generer_code.side_effect = None  # probleme regle
    sorties = list(relancer_pipeline(ko["id_run"], choix_de_relance(ko["id_run"])[0], None))
    assert sorties[-1][2]["succes"] is True
    assert agents.generer_user_stories.call_count == 1  # le Product Owner n'est pas refait


def test_relancer_une_etape_rejoue_le_run(agents):
    ok = executer_pipeline(BESOIN)
    sorties = list(relancer_pipeline(ok["id_run"], "Validation Docker", None))
    assert sorties[-1][2]["succes"] is True
    assert agents.generer_user_stories.call_count == 1


def test_liens_vers_l_application_generee(agents, tmp_path):
    resultat = executer_pipeline(BESOIN)
    (tmp_path / "output" / "docker-compose.yml").write_text(
        'services:\n  app:\n    ports:\n      - "8000:8000"\n  frontend:\n    ports:\n      - "8080:80"\n')
    html = liens_application(resultat)
    assert "http://localhost:8080" in html and "http://localhost:8000/docs" in html


def test_pas_de_liens_si_les_fichiers_sont_archives(agents):
    premier = executer_pipeline(BESOIN)
    executer_pipeline(BESOIN)
    assert liens_application(premier) == ""
    assert plan_de_test_du_run(premier)["visible"] is False
    assert etat_du_run("run-qui-n-existe-pas") == {}


def test_ouverture_aucun_run_choisi(agents):
    """A l'ouverture, « Runs existants » demande de cliquer sur un run."""
    executer_pipeline(BESOIN)
    sorties = charger_page()
    assert len(sorties[0]) >= 1                      # la liste est remplie
    assert "Clique sur un run" in sorties[5]         # pas de resultat affiche
    assert sorties[9]["interactive"] is False        # Relancer grise


def test_clic_affiche_le_resultat_et_active_relancer(agents):
    ok = executer_pipeline(BESOIN)
    _, ids = runs_pour_tableau()
    sorties = choisir_run(ids, SimpleNamespace(index=[ids.index(ok["id_run"]), 0]))
    assert "SUCCES" in sorties[2] and "Clique sur un run" not in sorties[2]
    assert sorties[6]["interactive"] is True


def test_suivi_affiche_le_run_des_le_debut(monkeypatch):
    """Pendant la premiere etape, il n'y a pas encore d'etat : l'onglet doit
    quand meme montrer un run EN COURS, pas « Aucun run en cours »."""
    from src.agent_form import app
    monkeypatch.setattr(app, "_run_actif", SimpleNamespace(id_run="", termine=False, debut=0, debut_etape=0))
    html = app.vue_suivi(None)
    assert "EN COURS" in html and "Aucun run en cours" not in html
    assert "Le Product Owner" in html  # premiere etape en cours


def test_clic_sur_le_run_qui_tourne(agents, monkeypatch):
    """Dans « Runs existants », le run qui tourne s'affiche EN COURS, sans
    « La ou il s'est arrete »."""
    from src.agent_form import app
    ok = executer_pipeline(BESOIN)
    monkeypatch.setattr(app, "_run_actif", SimpleNamespace(id_run=ok["id_run"], termine=False, debut=0, debut_etape=0))
    _, ids = runs_pour_tableau()
    sorties = choisir_run(ids, SimpleNamespace(index=[ids.index(ok["id_run"]), 0]))
    assert "EN COURS" in sorties[2] and "Termine" not in sorties[2]
    assert sorties[5]["value"] == "Product Owner"
    assert sorties[6]["interactive"] is False


def test_suivi_sans_run_qui_tourne(monkeypatch):
    from src.agent_form import app
    monkeypatch.setattr(app, "_run_actif", None)
    assert "Aucun run en cours" in app.vue_suivi(None)


def test_debut_de_relance_efface_l_ancien_rapport(monkeypatch):
    """Relancer a partir de Validation Docker apres un port occupe : l'etape
    s'affiche « en cours », pas « correction », et les etapes d'avant restent vertes."""
    from src.agent_form import app
    ancien = {"id_run": "r1", "succes": False, "etape": "docker", "user_stories": 1, "architecture": 1,
              "plan_tests": SimpleNamespace(cas=[]), "sortie_dev": 1,
              "rapport_backend": SimpleNamespace(succes=True, tests_passes=1, tests_echoues=0),
              "sortie_frontend": 1, "rapport_frontend": SimpleNamespace(succes=True),
              "rapport_dockerisation": 1,
              "rapport_validation_docker": SimpleNamespace(succes=False, docker_disponible=True,
                                                           erreur_environnement=True)}
    monkeypatch.setattr(app, "_run_actif", SimpleNamespace(id_run="r1", termine=False, debut=0, debut_etape=0))
    monkeypatch.setitem(app._DEPART_DU_RUN, "r1", "validation_docker")
    etats = {libelle: (etat, detail) for libelle, etat, detail in app.etats_des_etapes(app._etat_pour_le_suivi(ancien))}
    assert etats["Validation Docker"] == ("en_cours", "")
    assert etats["Dockerization"][0] == "ok"
    message = app.message_en_ce_moment(app._etat_pour_le_suivi(ancien))
    assert "corrige" not in message and "Docker Validation Agent" in message
