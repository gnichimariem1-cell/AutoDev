"""Relance automatique d'un agent par l'orchestrateur (@_proteger dans noeuds.py)."""
import subprocess

import requests

from src.agent_orchestrateur import noeuds
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from tests.sorties import BESOIN, SORTIE_DEV, SORTIE_FRONTEND


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