from src.agent_form.app import collecter_besoin

def test_collecter_besoin_produit_objet_valide():
    besoin = collecter_besoin(
        "Mon app", "Une app de todo", "Étudiants",
        "login, création tâche, notifications", "Une page d'accueil et un tableau de bord"
    )
    assert besoin.titre_projet == "Mon app"
    assert besoin.fonctionnalites_cles == ["login", "création tâche", "notifications"]
    assert besoin.structure_projet == "Une page d'accueil et un tableau de bord"

from unittest.mock import patch, MagicMock

from src.agent_form.app import construire_rapport_detaille, lancer_pipeline_complet, reprendre_pipeline


def test_rapport_en_cours_marque_les_etapes_en_attente():
    texte = construire_rapport_detaille({"succes": True, "_en_cours": "architect", "architecture": None})
    assert texte.startswith("⏳ EN COURS — derniere etape terminee : Architect Agent")
    assert "(en attente)" in texte
    assert "(non atteint)" not in texte


def test_rapport_plantage_affiche_l_erreur():
    texte = construire_rapport_detaille(
        {"succes": False, "etape": "developer", "erreur": "RuntimeError : credit Claude epuise"}
    )
    assert "PLANTAGE a l'etape \"Developer Agent\"" in texte
    assert "credit Claude epuise" in texte
    assert "(non atteint)" in texte


def test_lancer_pipeline_complet_met_a_jour_apres_chaque_etape():
    plantage = {"id_run": "run-1", "succes": True, "etape": "architect", "erreur": "RuntimeError : boom"}
    etats = [
        ("po", {"id_run": "run-1", "succes": True, "user_stories": None}),
        ("architect", plantage),
        ("echec", dict(plantage, succes=False)),
    ]
    with patch("src.agent_form.app.executer_pipeline_en_direct", return_value=iter(etats)):
        sorties = list(lancer_pipeline_complet("t", "d", "u", "a, b", "", None))

    # demarrage + po + architect + final (pas d'affichage intermediaire pour "echec")
    assert len(sorties) == 4
    assert sorties[1][0].startswith("⏳ EN COURS — derniere etape terminee : Product Owner Agent")
    assert sorties[2][0].startswith("⏳ ARRET EN COURS — plantage de : Architect Agent")
    message_final, _, resultat_final, bouton_lancer, bouton_reprendre, id_run = sorties[-1]
    assert "PLANTAGE" in message_final
    assert "_en_cours" not in resultat_final
    assert id_run == "run-1"
    assert bouton_lancer["interactive"] is True and bouton_reprendre["interactive"] is True
    assert all(s[3]["interactive"] is False and s[4]["interactive"] is False for s in sorties[:-1])


def test_reprendre_pipeline_impossible_affiche_un_message():
    sorties = list(reprendre_pipeline("run-inconnu", None))
    assert len(sorties) == 1
    assert sorties[0][0].startswith("⚠️ Reprise impossible : Aucun run 'run-inconnu'")
    assert sorties[0][3]["interactive"] is True


def test_reprendre_pipeline_suit_la_reprise():
    sauvegarde = MagicMock(next=("developer",))
    etats = [("developer", {"id_run": "run-1", "succes": True}), ("qa_backend", {"id_run": "run-1", "succes": True})]
    with patch("src.agent_form.app.point_de_reprise", return_value=sauvegarde), \
         patch("src.agent_form.app.reprendre_pipeline_en_direct", return_value=iter(etats)):
        sorties = list(reprendre_pipeline(" run-1 ", None))

    assert sorties[0][0] == "⏳ Reprise du run run-1 a l'etape developer..."
    assert sorties[-1][0].startswith("✅ SUCCES")


import threading

import pytest

from src.agent_form import app


@pytest.fixture(autouse=True)
def aucun_run_actif():
    app._run_actif = None
    yield
    app._run_actif = None


def _evenements_bloques(etats, debloquer: threading.Event):
    """Pipeline simule qui s'arrete apres le premier etat jusqu'a debloquer.set()."""
    yield etats[0]
    debloquer.wait(5)
    yield from etats[1:]


def test_le_run_continue_si_la_page_se_deconnecte():
    debloquer = threading.Event()
    etats = [("po", {"id_run": "run-1", "succes": True}), ("architect", {"id_run": "run-1", "succes": True})]
    with patch("src.agent_form.app.executer_pipeline_en_direct",
               return_value=_evenements_bloques(etats, debloquer)):
        suivi = lancer_pipeline_complet("t", "d", "u", "a", "", None)
        next(suivi)          # message de demarrage
        next(suivi)          # etape po
        suivi.close()        # la page se deconnecte : Gradio abandonne le suivi
        debloquer.set()

    run = app._run_actif
    nouveaux, termine = run.attendre(0, timeout=5)
    while not termine:
        nouveaux, termine = run.attendre(len(run.evenements), timeout=5)
    assert [noeud for noeud, _ in run.evenements] == ["po", "architect"]


def test_rafraichissement_pendant_une_etape_longue(monkeypatch):
    monkeypatch.setattr(app, "INTERVALLE_RAFRAICHISSEMENT", 0.05)
    debloquer = threading.Event()
    etats = [("po", {"id_run": "run-1", "succes": True}), ("architect", {"id_run": "run-1", "succes": True})]
    with patch("src.agent_form.app.executer_pipeline_en_direct",
               return_value=_evenements_bloques(etats, debloquer)):
        suivi = lancer_pipeline_complet("t", "d", "u", "a", "", None)
        sorties = [next(suivi), next(suivi), next(suivi)]
        debloquer.set()
        sorties += list(suivi)

    assert "Etape suivante en cours depuis" in sorties[2][0]
    assert sorties[2][5] == "run-1"
    assert sorties[-1][0].startswith("✅ SUCCES")


def test_un_seul_run_a_la_fois():
    debloquer = threading.Event()
    etats = [("po", {"id_run": "run-1", "succes": True}), ("architect", {"id_run": "run-1", "succes": True})]
    with patch("src.agent_form.app.executer_pipeline_en_direct",
               return_value=_evenements_bloques(etats, debloquer)):
        premier = lancer_pipeline_complet("t", "d", "u", "a", "", None)
        next(premier), next(premier)
        second = list(lancer_pipeline_complet("t", "d", "u", "a", "", None))
        debloquer.set()
        list(premier)

    assert len(second) == 1
    assert "Un run est deja en cours (ID : run-1)" in second[0][0]


def test_rechargement_de_la_page_affiche_le_dernier_run():
    etats = [("po", {"id_run": "run-1", "succes": True}), ("architect", {"id_run": "run-1", "succes": True})]
    with patch("src.agent_form.app.executer_pipeline_en_direct", return_value=iter(etats)):
        list(lancer_pipeline_complet("t", "d", "u", "a", "", None))

    sorties = list(app.suivre_run_actif(None))
    assert sorties[0][0] == "⏳ Reconnexion au run run-1..."
    assert sorties[-1][0].startswith("✅ SUCCES")
    assert sorties[-1][5] == "run-1"


def test_page_ouverte_sans_run():
    sorties = list(app.suivre_run_actif(None))
    assert len(sorties) == 1
    assert sorties[0][3]["interactive"] is True
