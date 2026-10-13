"""Relance automatique d'un agent par l'orchestrateur (@_proteger dans noeuds.py)."""
import subprocess
from pathlib import Path

import requests

from src.agent_orchestrateur import noeuds
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from tests.sorties import BESOIN, SORTIE_DEV, SORTIE_DOCKER, SORTIE_FRONTEND


def test_erreurs_passageres_reconnues():
    assert noeuds.est_erreur_passagere(TimeoutError("lent"))
    assert noeuds.est_erreur_passagere(subprocess.TimeoutExpired("claude", 1200))
    assert noeuds.est_erreur_passagere(requests.ConnectionError("Ollama injoignable"))
    assert noeuds.est_erreur_passagere(RuntimeError("API Error: 529 Overloaded"))


def test_erreurs_durables_reconnues():
    assert not noeuds.est_erreur_passagere(RuntimeError("credit Claude epuise"))
    assert not noeuds.est_erreur_passagere(ValueError("JSON invalide"))


def test_erreur_passagere_relancee_puis_reussie(agents, monkeypatch):
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 3)
    agents.generer_frontend.side_effect = [TimeoutError("lent"), TimeoutError("lent"), SORTIE_FRONTEND]
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    assert agents.generer_frontend.call_count == 3


def test_erreur_passagere_abandon_apres_dernier_essai(agents, monkeypatch):
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 2)
    agents.generer_code.side_effect = subprocess.TimeoutExpired("claude", 1200)
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False
    assert resultat["etape"] == "developer"
    assert agents.generer_code.call_count == 2


def test_erreur_durable_pas_relancee(agents, monkeypatch):
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 3)
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False
    assert agents.generer_code.call_count == 1


def test_relance_desactivable(agents, monkeypatch):
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 1)
    agents.generer_code.side_effect = [TimeoutError("lent"), SORTIE_DEV]
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False
    assert agents.generer_code.call_count == 1

def test_timeout_dockerization_pas_relance(agents, monkeypatch):
    """Issue #2 : relancer la Dockerization apres un timeout reproduisait le meme blocage."""
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 3)
    agents.generer_dockerisation.side_effect = subprocess.TimeoutExpired("claude", 300)
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False
    assert resultat["etape"] == "dockerization"
    assert agents.generer_dockerisation.call_count == 1


def test_erreur_reseau_dockerization_toujours_relancee(agents, monkeypatch):
    monkeypatch.setattr(noeuds, "ESSAIS_AGENT", 2)
    agents.generer_dockerisation.side_effect = [requests.ConnectionError("coupure"), SORTIE_DOCKER]
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    assert agents.generer_dockerisation.call_count == 2


def test_compose_genere_nomme_avec_l_id_du_run(agents):
    """Issue #1 : chaque run a son propre projet compose, donc ses propres volumes."""
    def ecrire_compose(dossier_backend, dossier_frontend, dossier_docker):
        (Path(dossier_docker) / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
        return SORTIE_DOCKER
    agents.generer_dockerisation.side_effect = ecrire_compose
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True
    compose = (Path(resultat["dossier_docker"]) / "docker-compose.yml").read_text(encoding="utf-8")
    assert compose.startswith(f"name: {resultat['id_run']}\n")


def test_besoin_transmis_aux_agents_claude(agents):
    """Issue #4 : Test Agent, Developer et Frontend recoivent le besoin du formulaire."""
    executer_pipeline(BESOIN)
    for agent in (agents.generer_plan_et_tests, agents.generer_code, agents.generer_frontend):
        assert agent.call_args.kwargs["besoin"] == BESOIN
