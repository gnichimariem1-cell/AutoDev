"""SEC-01 a SEC-03 : authentification du formulaire, testee automatiquement.

Le vrai formulaire est lance sur un port local, puis on essaie de se connecter.
"""
import pytest
import requests

from src.agent_form import app

UTILISATEUR, MOT_DE_PASSE = "testeur", "mot-de-passe-de-test"


@pytest.fixture
def formulaire(monkeypatch):
    monkeypatch.setenv("GRADIO_AUTH_USER", UTILISATEUR)
    monkeypatch.setenv("GRADIO_AUTH_PASSWORD", MOT_DE_PASSE)
    app.lancer_formulaire(prevent_thread_lock=True, server_name="127.0.0.1", quiet=True)
    yield app.demo.local_url
    app.demo.close()


def test_sec01_mauvais_mot_de_passe_refuse(formulaire):
    reponse = requests.post(formulaire + "login", data={"username": UTILISATEUR, "password": "faux"}, timeout=10)
    assert reponse.status_code == 400
    # Sans connexion, le formulaire reste inaccessible
    assert requests.get(formulaire + "config", timeout=10).status_code == 401


def test_sec02_bons_identifiants_acceptes(formulaire):
    session = requests.Session()
    reponse = session.post(formulaire + "login", data={"username": UTILISATEUR, "password": MOT_DE_PASSE}, timeout=10)
    assert reponse.status_code == 200
    assert session.get(formulaire + "config", timeout=10).status_code == 200


def test_sec03_sans_identifiants_pas_de_mot_de_passe(monkeypatch):
    monkeypatch.delenv("GRADIO_AUTH_USER", raising=False)
    monkeypatch.delenv("GRADIO_AUTH_PASSWORD", raising=False)
    assert app.identifiants_formulaire() is None
