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
