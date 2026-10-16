"""Agent E2E (etape 2 : API + navigateur, rapport seulement) : ecriture des scenarios,
execution reelle avec pytest, relais localhost, et place dans le pipeline."""
import http.server
import json
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.agent_e2e import e2e
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.common.schemas import RapportValidationDocker
from tests.sorties import BESOIN, USER_STORIES, E2E_KO


@patch("src.agent_e2e.e2e.subprocess.run")
def test_generer_tests_e2e(mock_run, tmp_path):
    dossier = tmp_path / "e2e"
    reponse = json.dumps({"scenarios": [
        {"id": "E01", "type": "api", "user_story": "US1", "description": "creer"},
        {"id": "E02", "type": "interface", "user_story": "US1", "description": "creer dans la page"}]})

    def claude(commande, **kwargs):
        assert "Bash" not in commande[commande.index("--allowedTools") + 1]  # l'agent ne lance rien
        consigne = kwargs["input"]
        assert "test_api_e2e.py" in consigne and "test_interface_e2e.py" in consigne
        assert "frontend dans le_front/" in consigne and "front_url" in consigne
        (dossier / "test_api_e2e.py").write_text("def test_E01(): pass\n")
        (dossier / "test_interface_e2e.py").write_text("def test_E02(): pass\n")
        (dossier / "conftest.py").write_text("# modifie par l'IA\n")
        return MagicMock(returncode=0, stdout=f"```json\n{reponse}\n```", stderr="")
    mock_run.side_effect = claude

    plan = e2e.generer_tests_e2e(USER_STORIES, "Titre : Todo", "b", str(dossier), dossier_frontend="le_front")
    assert [(s.id, s.type) for s in plan.scenarios] == [("E01", "api"), ("E02", "interface")]
    assert len(plan.fichiers) == 2
    conftest = (dossier / "conftest.py").read_text()
    assert "def api_url" in conftest and "def front_url" in conftest  # conftest remis par AutoDev


@patch("src.agent_e2e.e2e.subprocess.run", return_value=MagicMock(returncode=0, stdout="{}", stderr=""))
def test_generer_tests_e2e_sans_fichier_plante(mock_run, tmp_path):
    with pytest.raises(RuntimeError, match="aucun fichier"):
        e2e.generer_tests_e2e(USER_STORIES, "x", "b", str(tmp_path / "e2e"))


class _Api(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/ok" else 500)
        self.end_headers()
        self.wfile.write(b"reponse")

    def log_message(self, *args):
        pass


@pytest.fixture
def serveur():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_lancer_scenarios_reels(tmp_path, serveur):
    """Vrais scenarios lances par pytest ; un echec d'interface est classe « interface »."""
    d = str(tmp_path)
    e2e.ecrire_fichiers_autodev(d)
    (tmp_path / "test_api_e2e.py").write_text(
        "import httpx\n"
        "def test_E01_ok(api_url):\n    assert httpx.get(api_url + '/ok').status_code == 200\n"
        "def test_E02_regle(api_url):\n"
        "    r = httpx.get(api_url + '/regle')\n    assert r.status_code == 409, f'attendu 409, obtenu {r.status_code}'\n")
    (tmp_path / "test_interface_e2e.py").write_text(
        "def test_E03_page(front_url):\n    assert front_url.endswith('/front'), 'mauvaise adresse'\n"
        "def test_E04_bouton():\n    assert False, 'bouton Reserver absent'\n")
    rapport = e2e.lancer_scenarios(e2e.lister_tests_e2e(d), d, serveur, front_url=serveur + "/front")
    assert rapport.total == 4 and rapport.reussis == 2 and not rapport.succes
    assert [(x.id, x.type) for x in rapport.echecs] == [("E02", "api"), ("E04", "interface")]
    assert "attendu 409, obtenu 500" in rapport.echecs[0].message
    assert any(err.startswith("[E2E interface] E04") for err in rapport.erreurs)


def test_relais_tcp(serveur):
    port_distant = int(serveur.rsplit(":", 1)[1])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port_local = s.getsockname()[1]
    relais = e2e._Relais(port_local, "127.0.0.1", port_distant)
    threading.Thread(target=relais.serve_forever, daemon=True).start()
    try:
        import httpx
        assert httpx.get(f"http://127.0.0.1:{port_local}/ok").text == "reponse"
    finally:
        e2e.arreter_relais([relais])
    assert e2e.demarrer_relais("localhost", [8000]) == []  # en local : pas de relais


def test_sans_navigateur_seuls_les_scenarios_api(tmp_path):
    (tmp_path / "e2e").mkdir()
    (tmp_path / "e2e" / "test_interface_e2e.py").write_text("def test_E01(): pass\n")
    with patch("src.agent_e2e.e2e.vd._commande_compose", return_value=["docker", "compose"]), \
         patch("src.agent_e2e.e2e.navigateur_disponible", return_value=False):
        rapport = e2e.executer_tests_e2e(str(tmp_path))
    assert rapport.docker_disponible is False and rapport.navigateur is False
    assert "Navigateur non installe" in rapport.remarque


def test_sans_docker_ou_sans_scenario(tmp_path):
    with patch("src.agent_e2e.e2e.vd._commande_compose", return_value=None):
        assert e2e.executer_tests_e2e(str(tmp_path)).docker_disponible is False
    with patch("src.agent_e2e.e2e.vd._commande_compose", return_value=["docker", "compose"]):
        rapport = e2e.executer_tests_e2e(str(tmp_path))
    assert rapport.docker_disponible is False and "Aucun scenario" in rapport.erreurs[0]
    with pytest.raises(ValueError):
        e2e.lancer_scenarios([], str(tmp_path), "u")


def test_pipeline_avec_tests_e2e(agents):
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    assert resultat["rapport_e2e"].reussis == 2
    assert agents.generer_tests_e2e.call_args.kwargs["dossier_frontend"] == "output/frontend"


def test_scenario_en_echec_ne_bloque_pas_le_run(agents):
    """Rapport seulement, aucune correction (ce sera l'etape 3)."""
    agents.executer_tests_e2e.return_value = E2E_KO
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    assert resultat["rapport_e2e"].echecs[0].id == "E02"
    agents.appliquer_corrections.assert_not_called()


def test_e2e_desactive(agents, monkeypatch):
    monkeypatch.setenv("E2E_ACTIF", "0")
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True and resultat["rapport_e2e"].docker_disponible is False
    agents.generer_tests_e2e.assert_not_called()
    agents.executer_tests_e2e.assert_not_called()


def test_sans_docker_pas_de_scenarios(agents):
    agents.valider_dockerisation.return_value = RapportValidationDocker(docker_disponible=False, succes=False)
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    agents.generer_tests_e2e.assert_not_called()


def test_interface_resume_e2e():
    from src.agent_form import app
    from tests import sorties as s
    resultat = {"id_run": "r1", "succes": True, "user_stories": s.USER_STORIES, "architecture": s.ARCHITECTURE,
                "plan_tests": s.PLAN_TESTS, "sortie_dev": s.SORTIE_DEV, "rapport_backend": s.QA_OK,
                "sortie_frontend": s.SORTIE_FRONTEND, "rapport_frontend": s.FE_OK,
                "rapport_dockerisation": s.SORTIE_DOCKER, "rapport_validation_docker": s.DOCKER_OK,
                "plan_e2e": s.PLAN_E2E, "rapport_e2e": E2E_KO}
    etats = {libelle: (etat, detail) for libelle, etat, detail in app.etats_des_etapes(resultat)}
    assert etats["Agent E2E"] == ("ok", "2 scenarios")
    assert etats["Tests E2E"] == ("attention", "1/2")
    assert app._resume_etape("Agent E2E", resultat) == "2 scenarios · 2 API, 0 interface"
    assert "en echec : E02" in app._resume_etape("Tests E2E", resultat)
    sans_nav = dict(resultat, rapport_e2e=E2E_KO.model_copy(update={"navigateur": False}))
    assert "API seulement" in app._resume_etape("Tests E2E", sans_nav)
