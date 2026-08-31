from src.agent_form.app import collecter_besoin
import json

def test_collecter_besoin_produit_json_valide():
    resultat = collecter_besoin(
        "Mon app", "Une app de todo", "Étudiants",
        "login, création tâche, notifications", "Python only", "2 semaines"
    )
    data = json.loads(resultat)
    assert data["titre_projet"] == "Mon app"
    assert data["fonctionnalites_cles"] == ["login", "création tâche", "notifications"]