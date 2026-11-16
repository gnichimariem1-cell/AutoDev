"""Agent E2E etape 7 : histoire des essais (journal, detail, premier essai)."""
import logging

from src.agent_e2e import e2e
from src.common.schemas import EchecE2E, EssaiE2E, RapportE2E
from src.agent_orchestrateur.orchestrateur import executer_pipeline
from tests.sorties import BESOIN, E2E_KO, E2E_OK
from tests.test_agent_e2e import E2E_KO_INTERFACE, E2E_KO_SCENARIO

MESSAGE = ("    def test_E29_assistant(page):\n>       expect(page.get_by_role('alert')).to_be_visible()\n"
           "E       AssertionError: Locator expected to be visible\n"
           "E       Call log:\n\ntest_interface_e2e.py:310: AssertionError")


def test_message_court_et_destinataire():
    assert e2e.message_court(MESSAGE) == "AssertionError: Locator expected to be visible | Call log:"
    assert e2e.message_court("x" * 500, 40) == "x" * 40
    assert e2e.destinataire(E2E_KO.echecs[0]) == "Developer"
    assert e2e.destinataire(E2E_KO_INTERFACE.echecs[0]) == "Frontend"
    assert e2e.destinataire(E2E_KO_SCENARIO.echecs[0]) == "Agent E2E"


def test_essais_gardes_et_journal(agents, caplog):
    agents.executer_tests_e2e.side_effect = [E2E_KO, E2E_KO_INTERFACE, E2E_OK]
    with caplog.at_level(logging.WARNING):
        resultat = executer_pipeline(BESOIN)
    essais = resultat["rapport_e2e"].essais
    assert [(e.numero, e.reussis, e.total) for e in essais] == [(1, 1, 2), (2, 1, 2), (3, 2, 2)]
    assert essais[0].echecs[0].id == "E02" and essais[0].echecs[0].cause == "Developer"
    assert essais[1].echecs[0].cause == "Frontend" and essais[2].echecs == []
    assert "Timeout 30000ms exceeded" in essais[1].echecs[0].message
    journal = caplog.text
    assert "E02 (api -> Developer)" in journal and "E02 (interface -> Frontend)" in journal


def test_essais_affiches(tmp_path):
    from src.agent_form import app
    rapport = E2E_OK.model_copy(update={"essais": [
        EssaiE2E(numero=1, reussis=24, total=29, echecs=[
            EchecE2E(id="E29", type="interface", cause="Frontend", message="AssertionError: <alerte> absente")]),
        EssaiE2E(numero=2, reussis=29, total=29)]})
    resultat = {"id_run": "r1", "succes": True, "rapport_e2e": rapport, "tentative_e2e": 2}
    assert "premier essai : 24/29" in app._resume_etape("Tests E2E", resultat)
    detail = app._details(resultat)
    assert "Essais des Tests E2E" in detail and "Frontend" in detail
    assert "&lt;alerte&gt; absente" in detail and "tout passe" in detail
    sans_echec = dict(resultat, rapport_e2e=E2E_OK.model_copy(update={"essais": [EssaiE2E(numero=1, reussis=2, total=2)]}))
    assert "Essais des Tests E2E" not in app._details(sans_echec)
