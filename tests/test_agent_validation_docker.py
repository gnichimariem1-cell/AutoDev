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
    (tmp_path / "Dockerfile").write_text("FROM python:3.11-slim")
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
        "fichiers", "config", "ports", "build", "demarrage", "service app", "service frontend",
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
