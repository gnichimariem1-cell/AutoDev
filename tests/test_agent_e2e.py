"""Agent E2E (etape 3) : ecriture des scenarios, execution reelle avec pytest, relais
localhost, place dans le pipeline et boucle de correction."""
import http.server
import json
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.agent_e2e import e2e
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from src.common.schemas import RapportValidationDocker
from src.agent_orchestrateur.etat import MAX_TENTATIVES
from src.common.schemas import RapportE2E, EchecE2E
from tests.sorties import BESOIN, USER_STORIES, E2E_KO, E2E_OK, QA_OK, QA_KO


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
        assert "ne peut pas etre rouvert avec `with`" in consigne  # scenario E23 du run Cabinet
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
    """Encore en echec apres MAX_TENTATIVES essais : le run reste en succes, avec le rapport."""
    agents.executer_tests_e2e.return_value = E2E_KO
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    assert resultat["rapport_e2e"].echecs[0].id == "E02"
    assert resultat["tentative_e2e"] == MAX_TENTATIVES
    assert agents.appliquer_corrections.call_count == MAX_TENTATIVES - 1


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


# --- Etape 3 : boucle de correction ---

E2E_KO_INTERFACE = RapportE2E(docker_disponible=True, succes=False, total=2, reussis=1, echecs=[EchecE2E(
    id="E02", type="interface", test="test_interface_e2e.py::test_E02",
    message="E           playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.")])
E2E_KO_SCENARIO = RapportE2E(docker_disponible=True, succes=False, total=2, reussis=1, echecs=[EchecE2E(
    id="E23", type="interface", test="test_interface_e2e.py::test_E23",
    message="E           RuntimeError: Cannot open a client instance more than once.")])


def test_cause_de_l_echec():
    """Messages reels du run Cabinet medical."""
    assert e2e.cause_de_l_echec(E2E_KO.echecs[0]) == "application"            # assertion fausse
    assert e2e.cause_de_l_echec(E2E_KO_INTERFACE.echecs[0]) == "application"  # element absent de la page
    assert e2e.cause_de_l_echec(E2E_KO_SCENARIO.echecs[0]) == "scenario"      # bug dans le code du test
    assert e2e.cause_de_l_echec(EchecE2E(id="collecte", message="SyntaxError")) == "scenario"
    assert e2e.cause_de_l_echec(EchecE2E(id="E01", message="E   NameError: name 'x' is not defined")) == "scenario"
    assert e2e.cause_de_l_echec(EchecE2E(id="E01", message="E   httpx.ConnectError: refused")) == "application"


def test_echec_api_corrige_par_le_developer(agents):
    agents.executer_tests_e2e.side_effect = [E2E_KO, E2E_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True and resultat["rapport_e2e"].succes is True
    assert resultat["tentative_e2e"] == 2
    consignes = agents.appliquer_corrections.call_args.args[0]
    assert "E02" in consignes[1] and "ne les modifie pas" in consignes[0]
    agents.appliquer_corrections_frontend.assert_not_called()
    agents.corriger_scenarios_e2e.assert_not_called()
    assert agents.lancer_tests.call_count == 2  # QA backend, puis les tests unitaires apres la correction


def test_echec_interface_corrige_par_le_frontend(agents):
    agents.executer_tests_e2e.side_effect = [E2E_KO_INTERFACE, E2E_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["rapport_e2e"].succes is True
    assert "navigateur" in agents.appliquer_corrections_frontend.call_args.args[0][0]
    agents.appliquer_corrections.assert_not_called()


def test_scenario_mal_ecrit_corrige_par_l_agent_e2e(agents):
    """Le cas E23 : l'application n'est pas en cause, elle n'est pas modifiee."""
    agents.executer_tests_e2e.side_effect = [E2E_KO_SCENARIO, E2E_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["rapport_e2e"].succes is True
    assert agents.corriger_scenarios_e2e.call_args.args[0][0].id == "E23"
    agents.appliquer_corrections.assert_not_called()
    agents.appliquer_corrections_frontend.assert_not_called()


def test_tests_unitaires_casses_par_la_correction(agents):
    """La correction casse les tests unitaires : le Developer recommence, avant de relancer Docker."""
    agents.executer_tests_e2e.side_effect = [E2E_KO, E2E_OK]
    agents.lancer_tests.side_effect = [QA_OK, QA_KO, QA_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["rapport_e2e"].succes is True and resultat["tentative_e2e"] == 3
    assert agents.executer_tests_e2e.call_count == 2
    assert "tests unitaires" in agents.appliquer_corrections.call_args_list[1].args[0][1]


def test_erreur_machine_pas_de_correction(agents):
    """Port occupe pendant les Tests E2E : aucune correction, le run s'arrete et se reprend avec Relancer."""
    from src.agent_orchestrateur.orchestrateur import point_de_reprise, reprendre_pipeline_en_direct
    from src.agent_form import app
    agents.executer_tests_e2e.return_value = RapportE2E(
        docker_disponible=True, succes=False, erreur_environnement=True, erreurs=["port(s) deja occupe(s) : 8000"])
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False and resultat["etape"] == "e2e" and resultat["tentative_e2e"] == 1
    agents.appliquer_corrections.assert_not_called()
    etats = {libelle: (etat, detail) for libelle, etat, detail in app.etats_des_etapes(resultat)}
    assert etats["Tests E2E"] == ("ko", "machine")
    assert "Probleme sur la machine a l'etape Tests E2E" in app.message_en_ce_moment(resultat)
    assert app.runs_pour_tableau()[0][0][3] == "Tests E2E (machine)"

    # La machine est liberee : Relancer reprend aux Tests E2E, sans refaire les agents
    assert point_de_reprise(resultat["id_run"]).next == ("e2e",)
    agents.executer_tests_e2e.return_value = E2E_OK
    noeuds = [noeud for noeud, _ in reprendre_pipeline_en_direct(resultat["id_run"])]
    assert noeuds == ["e2e"]
    agents.generer_tests_e2e.assert_called_once()


def test_application_qui_ne_demarre_plus_va_au_developer(agents):
    agents.executer_tests_e2e.side_effect = [
        RapportE2E(docker_disponible=True, succes=False, erreurs=["demarrage de l'application : exit 1"]), E2E_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["rapport_e2e"].succes is True
    assert "demarrage" in agents.appliquer_corrections.call_args.args[0][1]


def test_scenarios_proteges(tmp_path):
    dossier = tmp_path / "e2e"
    dossier.mkdir()
    (dossier / "test_api_e2e.py").write_text("def test_E01(): assert 1 == 2\n")
    originaux = e2e.lire_tests_e2e(str(dossier))
    (dossier / "test_api_e2e.py").write_text("def test_E01(): pass\n")  # affaibli par un autre agent
    (dossier / "test_ajoute.py").write_text("def test_x(): pass\n")
    touches = e2e.restaurer_tests_e2e(str(dossier), originaux)
    assert len(touches) == 2
    assert (dossier / "test_api_e2e.py").read_text() == "def test_E01(): assert 1 == 2\n"
    assert not (dossier / "test_ajoute.py").exists()
    assert (dossier / "conftest.py").exists()


def test_affichage_pendant_la_correction():
    from src.agent_form import app
    resultat = {"id_run": "r1", "_en_cours": "en_cours", "plan_e2e": _NS_PLAN, "rapport_e2e": E2E_KO,
                "tentative_e2e": 1}
    etats = {libelle: (etat, detail) for libelle, etat, detail in app.etats_des_etapes(resultat)}
    assert etats["Tests E2E"] == ("en_cours", f"correction · tentative 1/{MAX_TENTATIVES}")
    fini = dict(resultat, succes=True, rapport_e2e=E2E_OK, tentative_e2e=2)
    fini.pop("_en_cours")
    assert "corriges en 2 essais" in app._resume_etape("Tests E2E", fini)


_NS_PLAN = __import__("tests.sorties", fromlist=["PLAN_E2E"]).PLAN_E2E


def test_tableau_des_scenarios_dans_le_detail():
    from src.agent_form import app
    from tests import sorties as s
    detail = app._details({"id_run": "r1", "succes": True, "plan_e2e": s.PLAN_E2E, "rapport_e2e": E2E_KO})
    assert "Scenarios E2E (Agent E2E)" in detail
    assert "Titre vide refuse" in detail and "✗ echec" in detail and "✓ OK" in detail


@patch("src.agent_dockerization.dockerization.subprocess.run")
def test_dockerignore_du_frontend_demande(mock_run):
    from src.agent_dockerization.dockerization import generer_dockerisation
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_dockerisation("output/backend", "output/frontend", "sortie_test")
    assert "output/frontend/.dockerignore" in mock_run.call_args.kwargs["input"]
