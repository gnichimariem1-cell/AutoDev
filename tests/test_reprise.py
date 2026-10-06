import pytest

from src.agent_orchestrateur.orchestrateur import (
    executer_pipeline, executer_pipeline_en_direct, reprendre_pipeline_en_direct,
    point_de_reprise, RepriseImpossible,
)
from src.common.schemas import RapportValidationDocker
from tests.sorties import BESOIN, SORTIE_DEV, QA_KO, DOCKER_OK


def _reprendre(id_run):
    return [(noeud, dict(etat)) for noeud, etat in reprendre_pipeline_en_direct(id_run)]


def test_reprise_apres_plantage_repart_du_noeud_qui_a_plante(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    resultat = executer_pipeline(BESOIN)
    assert resultat["etape"] == "developer"

    # le probleme est regle (credit recharge) : on reprend
    agents.generer_code.side_effect = None
    agents.generer_code.return_value = SORTIE_DEV
    evenements = _reprendre(resultat["id_run"])

    assert evenements[0][0] == "developer"
    etat_final = evenements[-1][1]
    assert etat_final["succes"] is True
    assert "erreur" not in etat_final
    assert etat_final["id_run"] == resultat["id_run"]
    # les etapes deja reussies ne sont pas refaites
    agents.generer_user_stories.assert_called_once()
    agents.generer_architecture.assert_called_once()
    assert agents.generer_code.call_count == 2


def test_reprise_apres_plantage_pendant_une_correction_garde_les_compteurs(agents):
    agents.lancer_tests.return_value = QA_KO
    agents.appliquer_corrections.side_effect = TimeoutError("trop long")
    resultat = executer_pipeline(BESOIN)
    assert resultat["etape"] == "correction_backend"

    agents.appliquer_corrections.side_effect = None
    agents.appliquer_corrections.return_value = SORTIE_DEV
    evenements = _reprendre(resultat["id_run"])

    assert evenements[0][0] == "correction_backend"
    # la tentative 1 a deja eu lieu avant le plantage : la boucle reprend a 2
    assert evenements[1][0] == "qa_backend"
    assert evenements[1][1]["tentative_backend"] == 2


def test_reprise_apres_arret_de_l_application_en_plein_run(agents):
    run = executer_pipeline_en_direct(BESOIN)
    for noeud, etat in run:
        if noeud == "architect":
            id_run = etat["id_run"]
            break
    run.close()  # simule la fermeture de l'application avant le Developer

    assert point_de_reprise(id_run).next == ("developer",)
    evenements = _reprendre(id_run)

    assert evenements[0][0] == "developer"
    assert evenements[-1][1]["succes"] is True
    agents.generer_user_stories.assert_called_once()


def test_pas_de_reprise_pour_un_run_reussi(agents):
    resultat = executer_pipeline(BESOIN)
    with pytest.raises(RepriseImpossible, match="sans plantage"):
        point_de_reprise(resultat["id_run"])


def test_pas_de_reprise_pour_un_echec_de_qa(agents):
    agents.lancer_tests.return_value = QA_KO
    resultat = executer_pipeline(BESOIN)
    with pytest.raises(RepriseImpossible, match="sans plantage"):
        point_de_reprise(resultat["id_run"])


def test_reprise_apres_echec_docker_du_a_la_machine(agents):
    agents.valider_dockerisation.return_value = RapportValidationDocker(
        docker_disponible=True, succes=False, erreur_environnement=True,
        erreurs=["ports : port(s) deja occupe(s) sur la machine : 8000"],
    )
    resultat = executer_pipeline(BESOIN)
    assert resultat["succes"] is False and resultat["etape"] == "docker"

    # les ports sont liberes : on relance seulement la validation Docker
    agents.valider_dockerisation.return_value = DOCKER_OK
    evenements = _reprendre(resultat["id_run"])

    assert evenements[0][0] == "validation_docker"
    assert evenements[-1][1]["succes"] is True
    agents.generer_dockerisation.assert_called_once()
    agents.appliquer_corrections_dockerisation.assert_not_called()


def test_pas_de_reprise_pour_un_run_inconnu():
    with pytest.raises(RepriseImpossible, match="Aucun run"):
        point_de_reprise("run-qui-n-existe-pas")


def test_chaque_run_a_un_identifiant_unique(agents):
    id1 = executer_pipeline(BESOIN)["id_run"]
    id2 = executer_pipeline(BESOIN)["id_run"]
    assert id1 != id2
    assert id1.startswith("todo-app-")
