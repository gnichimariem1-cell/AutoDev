import json

import pytest
from unittest.mock import patch, MagicMock

from src.agent_validation_docker import validation_docker
from src.agent_validation_docker.validation_docker import valider_dockerisation

CONFIG = {
    "services": {
        "app": {"ports": [{"target": 8000, "published": "8000"}]},
        "frontend": {"ports": [{"target": 80, "published": "8080"}]},
        "db": {},
    }
}


@pytest.fixture(autouse=True)
def ports_libres():
    with patch.object(validation_docker, "_port_occupe", return_value=False) as mock:
        yield mock


def _dossier_docker(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim\nUSER app")
    (tmp_path / "docker-compose.yml").write_text("services: {}")
    return str(tmp_path)


def _faux_compose(echecs=None):
    """Simule `docker compose <args>` : renvoie un echec pour les sous-commandes listees."""
    echecs = echecs or {}

    def executer(compose, args, dossier, timeout):
        commande = args[0]
        if commande in echecs:
            return MagicMock(returncode=1, stdout="", stderr=echecs[commande])
        stdout = json.dumps(CONFIG) if commande == "config" else "logs du conteneur"
        return MagicMock(returncode=0, stdout=stdout, stderr="")

    return MagicMock(side_effect=executer)


@patch.object(validation_docker, "_commande_compose", return_value=None)
def test_docker_non_joignable(mock_compose, tmp_path):
    rapport = valider_dockerisation(str(tmp_path))
    assert rapport.docker_disponible is False
    assert rapport.succes is False


@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_fichiers_manquants(mock_compose, tmp_path):
    rapport = valider_dockerisation(str(tmp_path))
    assert rapport.succes is False
    assert "Dockerfile" in rapport.erreurs[0]


@patch.object(validation_docker, "_attendre_reponse_http", return_value=None)
@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_validation_reussie_et_nettoyage(mock_compose, mock_http, tmp_path):
    faux = _faux_compose()
    with patch.object(validation_docker, "_executer", faux):
        rapport = valider_dockerisation(_dossier_docker(tmp_path))

    assert rapport.succes is True
    assert [e.nom for e in rapport.etapes] == [
        "fichiers", "non-root", "config", "ports", "build", "demarrage", "service app", "service frontend",
    ]
    mock_http.assert_any_call("http://localhost:8000/", validation_docker.DEMARRAGE_TIMEOUT)
    assert faux.call_args_list[-1].args[1][0] == "down"


@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_echec_build_nettoie_quand_meme(mock_compose, tmp_path):
    faux = _faux_compose(echecs={"build": "pip install a echoue"})
    with patch.object(validation_docker, "_executer", faux):
        rapport = valider_dockerisation(_dossier_docker(tmp_path))

    assert rapport.succes is False
    assert rapport.etapes[-1].nom == "build"
    assert "pip install a echoue" in rapport.erreurs[0]
    assert faux.call_args_list[-1].args[1][0] == "down"


@patch.object(validation_docker, "_attendre_reponse_http", return_value="connection refused")
@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_service_injoignable_remonte_les_logs(mock_compose, mock_http, tmp_path):
    with patch.object(validation_docker, "_executer", _faux_compose()):
        rapport = valider_dockerisation(_dossier_docker(tmp_path))

    assert rapport.succes is False
    assert "service app" in rapport.erreurs[0]
    assert "logs du conteneur" in rapport.erreurs[0]


@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_port_occupe_est_une_erreur_environnement(mock_compose, ports_libres, tmp_path):
    ports_libres.side_effect = lambda port: port == 8000
    faux = _faux_compose()
    with patch.object(validation_docker, "_executer", faux):
        rapport = valider_dockerisation(_dossier_docker(tmp_path))

    assert rapport.succes is False
    assert rapport.erreur_environnement is True
    assert "8000" in rapport.erreurs[0]
    assert [c.args[1][0] for c in faux.call_args_list] == ["config"]


@pytest.mark.parametrize("dockerfile", [
    "FROM python:3.11-slim\nCMD [\"uvicorn\"]",                      # aucun USER
    "FROM python:3.11-slim\nUSER root",                               # USER root
    "FROM python:3.11 AS build\nUSER app\nFROM python:3.11-slim",      # USER seulement dans l'etape de build
])
@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_sec07_dockerfile_en_root_refuse(mock_compose, tmp_path, dockerfile):
    (tmp_path / "Dockerfile").write_text(dockerfile)
    (tmp_path / "docker-compose.yml").write_text("services: {}")
    faux = _faux_compose()
    with patch.object(validation_docker, "_executer", faux):
        rapport = valider_dockerisation(str(tmp_path))
    assert rapport.succes is False
    assert rapport.erreur_environnement is False   # erreur de code : corrigee par le Dockerization Agent
    assert rapport.etapes[-1].nom == "non-root"
    faux.assert_not_called()                        # rien n'est construit


def test_sec07_utilisateur_final():
    assert validation_docker.utilisateur_final("FROM a\nUSER app\nFROM b\nUSER web") == "web"
    assert validation_docker.utilisateur_final("FROM a\nRUN x") is None


# Trouve par l'Agent E2E (run Cabinet medical) : le frontend montait ./frontend par un volume.
# Lance depuis le conteneur AutoDev, le dossier etait vide et nginx repondait 404,
# mais la Validation Docker acceptait (404 < 500).

@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_dossier_monte_par_un_volume_refuse(mock_compose, tmp_path):
    config = {"services": {
        "app": {"ports": [{"target": 8000, "published": "8000"}]},
        "frontend": {"ports": [{"target": 80, "published": "8080"}], "volumes": [
            {"type": "bind", "source": "/app/output/frontend", "target": "/usr/share/nginx/html"}]},
        "db": {"volumes": [{"type": "volume", "source": "db_data", "target": "/var/lib/postgresql/data"}]},
    }}
    faux = MagicMock(return_value=MagicMock(returncode=0, stdout=json.dumps(config), stderr=""))
    with patch.object(validation_docker, "_executer", faux):
        rapport = valider_dockerisation(_dossier_docker(tmp_path))

    assert rapport.succes is False and rapport.erreur_environnement is False  # envoye au Dockerization Agent
    assert "frontend : /app/output/frontend -> /usr/share/nginx/html" in rapport.erreurs[0]
    assert "db :" not in rapport.erreurs[0]  # un volume nomme (db_data) est autorise
    assert "COPY" in rapport.erreurs[0]


@patch.object(validation_docker, "_attendre_reponse_http", return_value=None)
@patch.object(validation_docker, "_commande_compose", return_value=["docker", "compose"])
def test_frontend_doit_repondre_200(mock_compose, mock_http, tmp_path):
    with patch.object(validation_docker, "_executer", _faux_compose()):
        valider_dockerisation(_dossier_docker(tmp_path))
    mock_http.assert_any_call("http://localhost:8080/", validation_docker.DEMARRAGE_TIMEOUT, exige_200=True)


def test_reponse_404_refusee_seulement_si_200_exige():
    with patch.object(validation_docker.requests, "get", return_value=MagicMock(status_code=404)), \
            patch.object(validation_docker.time, "sleep"):
        assert validation_docker._attendre_reponse_http("http://x/", 0.05) is None
        assert validation_docker._attendre_reponse_http("http://x/", 0.05, exige_200=True) == "code HTTP 404"
