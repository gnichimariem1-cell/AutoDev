"""Agent E2E (etape 1 : API, rapport seulement) : ecriture des scenarios,
execution reelle avec pytest, et place dans le pipeline."""
import http.server
import json
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
    reponse = json.dumps({"scenarios": [{"id": "E01", "type": "api", "user_story": "US1", "description": "creer"}]})

    def claude(commande, **kwargs):
        assert "Bash" not in commande[commande.index("--allowedTools") + 1]  # l'agent ne lance rien
        assert "nouvel_email" in kwargs["input"] and "test_api_e2e.py" in kwargs["input"]
        (dossier / "test_api_e2e.py").write_text("def test_E01(): pass\n")
        (dossier / "conftest.py").write_text("# modifie par l'IA\n")
        return MagicMock(returncode=0, stdout=f"```json\n{reponse}\n```", stderr="")
    mock_run.side_effect = claude

    plan = e2e.generer_tests_e2e(USER_STORIES, "Titre : Todo", "b", str(dossier))
    assert [s.id for s in plan.scenarios] == ["E01"]
    assert plan.fichiers == [str(dossier / "test_api_e2e.py")]
    assert "def api_url" in (dossier / "conftest.py").read_text()  # conftest remis par AutoDev


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
    """Vrais scenarios lances par pytest sur un vrai serveur HTTP."""
    d = str(tmp_path)
    e2e.ecrire_fichiers_autodev(d)
    (tmp_path / "test_api_e2e.py").write_text(
        "import httpx\n"
        "def test_E01_ok(api_url):\n    assert httpx.get(api_url + '/ok').status_code == 200\n"
        "def test_E02_regle(api_url):\n"
        "    r = httpx.get(api_url + '/regle')\n    assert r.status_code == 409, f'attendu 409, obtenu {r.status_code}'\n")
    rapport = e2e.lancer_scenarios(e2e.lister_tests_e2e(d), d, serveur)
    assert rapport.total == 2 and rapport.reussis == 1 and not rapport.succes
    assert [x.id for x in rapport.echecs] == ["E02"]
    assert "attendu 409, obtenu 500" in rapport.echecs[0].message


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
    agents.generer_tests_e2e.assert_called_once()


def test_scenario_en_echec_ne_bloque_pas_le_run(agents):
    """Etape 1 : rapport seulement, aucune correction."""
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


def test_interface_echec_e2e_en_attention():
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
    assert "en echec : E02" in app._resume_etape("Tests E2E", resultat)
