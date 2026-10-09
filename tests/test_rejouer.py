"""Rejouer un run termine a partir d'une etape (apres modification d'un agent)."""
import pytest

from src.agent_orchestrateur.orchestrateur import (
    executer_pipeline, rejouer_pipeline_en_direct, point_de_rejeu, RepriseImpossible,
)
from tests.sorties import BESOIN, QA_KO, QA_OK


def _rejouer(id_run, etape):
    return [(noeud, dict(etat)) for noeud, etat in rejouer_pipeline_en_direct(id_run, etape)]


def test_rejouer_la_validation_docker_seulement(agents):
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is True

    evenements = _rejouer(resultat["id_run"], "validation_docker")

    assert [noeud for noeud, _ in evenements] == ["validation_docker"]
    assert evenements[-1][1]["succes"] is True
    assert agents.valider_dockerisation.call_count == 2
    agents.generer_user_stories.assert_called_once()
    agents.generer_code.assert_called_once()


def test_rejouer_a_partir_du_frontend_garde_le_backend(agents):
    resultat = executer_pipeline(BESOIN)

    noeuds = [noeud for noeud, _ in _rejouer(resultat["id_run"], "frontend")]

    assert noeuds == ["frontend", "qa_frontend", "dockerization", "validation_docker"]
    assert agents.generer_frontend.call_count == 2
    agents.generer_plan_et_tests.assert_called_once()
    agents.generer_code.assert_called_once()


def test_rejouer_reutilise_les_user_stories(agents):
    resultat = executer_pipeline(BESOIN)

    evenements = _rejouer(resultat["id_run"], "test_agent")

    assert evenements[0][0] == "test_agent"
    assert evenements[0][1]["user_stories"] == resultat["user_stories"]
    agents.generer_user_stories.assert_called_once()
    assert agents.generer_plan_et_tests.call_count == 2


def test_rejouer_le_qa_backend_repart_de_la_premiere_tentative(agents):
    agents.lancer_tests.side_effect = [QA_KO, QA_OK, QA_OK]
    resultat = executer_pipeline(BESOIN)
    assert resultat["tentative_backend"] == 2

    evenements = _rejouer(resultat["id_run"], "qa_backend")

    assert evenements[0][0] == "qa_backend"
    assert evenements[0][1]["tentative_backend"] == 1


def test_rejouer_un_run_inconnu(agents):
    with pytest.raises(RepriseImpossible, match="Aucun run"):
        point_de_rejeu("run-inexistant", "developer")


def test_rejouer_une_etape_jamais_atteinte(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    resultat = executer_pipeline(BESOIN)

    with pytest.raises(RepriseImpossible, match="jamais atteint"):
        point_de_rejeu(resultat["id_run"], "frontend")


def test_rejouer_refuse_si_les_fichiers_ont_ete_archives(agents):
    premier = executer_pipeline(BESOIN)
    executer_pipeline(BESOIN)  # un nouveau run archive les fichiers du premier

    with pytest.raises(RepriseImpossible, match="archives"):
        point_de_rejeu(premier["id_run"], "frontend")


def test_bouton_rejouer_dans_la_page(agents):
    from src.agent_form.app import rejouer_pipeline
    resultat = executer_pipeline(BESOIN)

    sorties = list(rejouer_pipeline(resultat["id_run"], "Validation Docker", None))

    assert "Rejeu du run" in sorties[0][0]
    assert "SUCCES" in sorties[-1][0]
