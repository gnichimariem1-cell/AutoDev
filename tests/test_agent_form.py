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

from src.agent_form.app import construire_rapport_detaille, lancer_pipeline_complet


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
    plantage = {"succes": True, "etape": "architect", "erreur": "RuntimeError : boom"}
    etats = [
        ("po", {"succes": True, "user_stories": None}),
        ("architect", plantage),
        ("echec", dict(plantage, succes=False)),
    ]
    with patch("src.agent_form.app.executer_pipeline_en_direct", return_value=iter(etats)):
        sorties = list(lancer_pipeline_complet("t", "d", "u", "a, b", "", None))

    # demarrage + po + architect + final (pas d'affichage intermediaire pour "echec")
    assert len(sorties) == 4
    assert sorties[1][0].startswith("⏳ EN COURS — derniere etape terminee : Product Owner Agent")
    assert sorties[2][0].startswith("⏳ ARRET EN COURS — plantage de : Architect Agent")
    message_final, _, resultat_final, bouton = sorties[-1]
    assert "PLANTAGE" in message_final
    assert "_en_cours" not in resultat_final
    assert bouton["interactive"] is True
    assert all(s[3]["interactive"] is False for s in sorties[:-1])
