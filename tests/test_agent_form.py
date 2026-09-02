from src.agent_form.app import collecter_besoin

def test_collecter_besoin_produit_objet_valide():
    besoin = collecter_besoin(
        "Mon app", "Une app de todo", "Étudiants",
        "login, création tâche, notifications", "Python only", "2 semaines"
    )
    assert besoin.titre_projet == "Mon app"
    assert besoin.fonctionnalites_cles == ["login", "création tâche", "notifications"]