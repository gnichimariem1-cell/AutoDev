"""Tests de l'interface du formulaire (src/agent_form/app.py)."""

# --- Barre d'etapes ---
from types import SimpleNamespace as _NS

from src.agent_form.app import etats_des_etapes, barre_etapes


def _etats(resultat):
    return {libelle: (etat, detail) for libelle, etat, detail in etats_des_etapes(resultat)}


def test_barre_vide_sans_run():
    assert barre_etapes(None) == ""


def test_barre_pendant_le_developer():
    resultat = {"id_run": "r1", "_en_cours": "test_agent", "user_stories": object(),
                "architecture": object(), "plan_tests": _NS(cas=[1, 2, 3])}
    e = _etats(resultat)
    assert e["Product Owner"][0] == "ok" and e["Test Agent"] == ("ok", "3 cas")
    assert e["Developer"][0] == "en_cours"
    assert e["QA Backend"][0] == "attente"
    assert "en cours" in barre_etapes(resultat)


def test_barre_correction_backend_en_cours():
    rapport = _NS(succes=False, tests_passes=35, tests_echoues=2)
    resultat = {"id_run": "r1", "_en_cours": "qa_backend", "user_stories": 1, "architecture": 1,
                "plan_tests": _NS(cas=[]), "sortie_dev": 1, "rapport_backend": rapport,
                "tentative_backend": 2}
    assert _etats(resultat)["QA Backend"] == ("en_cours", "correction · tentative 2/3")
    assert _etats(resultat)["Frontend"][0] == "attente"


def test_barre_plantage_affiche_l_etape_en_rouge():
    resultat = {"id_run": "r1", "succes": False, "etape": "architect", "erreur": "RuntimeError : credit",
                "user_stories": 1}
    e = _etats(resultat)
    assert e["Product Owner"][0] == "ok"
    assert e["Architect"] == ("ko", "plantage")
    assert e["Test Agent"][0] == "attente"
    assert "arrete" in barre_etapes(resultat)


def test_barre_port_occupe_erreur_machine():
    validation = _NS(succes=False, docker_disponible=True, erreur_environnement=True)
    resultat = {"id_run": "r1", "succes": False, "etape": "docker", "rapport_validation_docker": validation,
                "tentative_docker": 1}
    assert _etats(resultat)["Validation Docker"] == ("ko", "machine")


def test_barre_validation_non_effectuee():
    validation = _NS(succes=False, docker_disponible=False, erreur_environnement=False)
    resultat = {"id_run": "r1", "succes": True, "rapport_validation_docker": validation}
    assert _etats(resultat)["Validation Docker"] == ("attention", "non effectuee")


def test_barre_succes_complet():
    ok = _NS(succes=True, tests_passes=37, tests_echoues=0, docker_disponible=True)
    resultat = {"id_run": "r1", "succes": True, "user_stories": 1, "architecture": 1,
                "plan_tests": _NS(cas=list(range(37))), "sortie_dev": 1, "rapport_backend": ok,
                "sortie_frontend": 1, "rapport_frontend": ok, "rapport_dockerisation": 1,
                "rapport_validation_docker": ok, "plan_e2e": _NS(active=True, scenarios=[1, 2, 3]),
                "rapport_e2e": _NS(succes=True, docker_disponible=True, reussis=3, total=3)}
    e = _etats(resultat)
    assert all(etat == "ok" for etat, _ in e.values())
    assert e["Agent E2E"] == ("ok", "3 scenarios") and e["Tests E2E"] == ("ok", "3/3")
    assert e["QA Backend"] == ("ok", "37/37")
    assert "termine avec succes" in barre_etapes(resultat)

def test_erreurs_e2e_affichees_dans_le_detail():
    """Les scenarios E2E en echec apparaissent dans « Erreurs trouvees par les controles »."""
    from src.agent_form.app import _details
    from tests import sorties as s
    resultat = {"id_run": "r1", "succes": True, "rapport_e2e": s.E2E_KO}
    assert "Erreurs trouvees par les controles" in _details(resultat)
    assert "attendu 422, obtenu 201" in _details(resultat)
    desactive = _NS(docker_disponible=False, succes=False, erreurs=["Tests E2E desactives (E2E_ACTIF=0)."])
    assert "Erreurs trouvees" not in _details({"id_run": "r1", "succes": True, "rapport_e2e": desactive})


def test_les_sections_ouvertes_restent_ouvertes(monkeypatch):
    """Le suivi est redessine toutes les 5 s : le script de la page rouvre les sections."""
    from src.agent_form import app
    options = {}
    monkeypatch.setattr(app.demo, "launch", lambda **kw: options.update(kw))
    monkeypatch.delenv("GRADIO_AUTH_USER", raising=False)
    monkeypatch.delenv("GRADIO_AUTH_PASSWORD", raising=False)
    app.lancer_formulaire()
    assert "MutationObserver" in options["head"] and "toggle" in options["head"]
    # AutoDev redemarre : la page le detecte (app_id change) et propose de recharger
    assert "app_id" in options["head"] and "AutoDev a redémarré" in options["head"]


def test_docker_non_joignable_validation_incomplete():
    """Docker non joignable : le run se termine, mais il est affiche VALIDATION INCOMPLETE, pas SUCCES."""
    from types import SimpleNamespace as NS
    from src.agent_form import app
    sans_docker = {"succes": True, "rapport_validation_docker": NS(succes=False, docker_disponible=False),
                   "rapport_e2e": NS(docker_disponible=False, succes=False, erreurs=["Docker n'est pas joignable."])}
    assert app.statut_du_run(sans_docker) == "VALIDATION INCOMPLETE"
    assert "Validation Docker" in app.message_en_ce_moment(sans_docker)
    desactive = {"succes": True, "rapport_validation_docker": NS(succes=True, docker_disponible=True),
                 "rapport_e2e": NS(docker_disponible=False, succes=False, erreurs=["Tests E2E desactives (E2E_ACTIF=0)."])}
    assert app.statut_du_run(desactive) == "SUCCES"
    assert app.statut_du_run({"succes": True}) == "SUCCES"


# ---------- Remarque 6 : un run avec des echecs E2E restants n'est pas un SUCCES ----------

def test_echecs_e2e_restants_ne_sont_pas_un_succes():
    from types import SimpleNamespace
    from src.agent_form import app
    echec = SimpleNamespace(id="E27")
    rapport = SimpleNamespace(echecs=[echec], reussis=29, total=30, docker_disponible=True, erreurs=[])
    resultat = {"succes": True, "rapport_e2e": rapport}
    assert app.statut_du_run(resultat) == "ECHECS E2E"
    assert "E27" in app.message_en_ce_moment(resultat)
    assert "29/30" in app.message_en_ce_moment(resultat)
    tout_ok = {"succes": True, "rapport_e2e": SimpleNamespace(echecs=[], docker_disponible=True, erreurs=[])}
    assert app.statut_du_run(tout_ok) == "SUCCES"
    assert app.COULEURS_STATUT["ECHECS E2E"][1] == "#B45309"   # orange, pas rouge


# ---------- Remarque 6, partie 2 : validation incomplete, blocage machine, filtres exacts ----------

def test_chromium_absent_validation_incomplete():
    from types import SimpleNamespace
    from src.agent_form import app
    sans_navigateur = {"succes": True,
                       "rapport_validation_docker": SimpleNamespace(succes=True, docker_disponible=True),
                       "rapport_e2e": SimpleNamespace(docker_disponible=True, succes=True, navigateur=False,
                                                      echecs=[], erreurs=[])}
    assert app.statut_du_run(sans_navigateur) == "VALIDATION INCOMPLETE"
    assert "navigateur" in app.message_en_ce_moment(sans_navigateur)


def test_port_occupe_blocage_machine():
    from types import SimpleNamespace
    from src.agent_form import app
    port_occupe = {"succes": False, "etape": "docker",
                   "rapport_validation_docker": SimpleNamespace(succes=False, docker_disponible=True,
                                                                erreur_environnement=True)}
    assert app.statut_du_run(port_occupe) == "BLOCAGE MACHINE"
    code_ko = {"succes": False, "etape": "docker",
               "rapport_validation_docker": SimpleNamespace(succes=False, docker_disponible=True,
                                                            erreur_environnement=False)}
    assert app.statut_du_run(code_ko) == "ECHEC"


def test_filtre_echec_ne_montre_pas_les_echecs_e2e(monkeypatch):
    from src.agent_form import app
    runs = [{"id_run": "a", "titre": "Labo IA", "date": "", "statut": "ECHECS E2E", "etape": "e2e", "archive": False},
            {"id_run": "b", "titre": "Conges", "date": "", "statut": "BLOCAGE MACHINE",
             "etape": "docker (machine)", "archive": True},
            {"id_run": "c", "titre": "Blog", "date": "", "statut": "ECHEC", "etape": "qa_backend", "archive": True}]
    monkeypatch.setattr(app, "historique_runs", lambda *a, **k: runs)
    assert app.runs_pour_tableau("Échec")[1] == ["c"]
    assert app.runs_pour_tableau("Échecs E2E")[1] == ["a"]
    assert app.runs_pour_tableau("Blocage machine")[1] == ["b"]
