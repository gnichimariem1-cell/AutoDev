"""Test Agent (etape 1) : plan de test et tests ecrits AVANT le code."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.agent_test.testeur import generer_plan_et_tests, reviser_tests, lire_tests, restaurer_tests
from src.common.schemas import SortieTestAgent, CasDeTest
from tests.sorties import USER_STORIES

PLAN_JSON = json.dumps({"cas": [
    {"id": "T01", "user_story": "US1", "scenario": "Creer une tache", "methode": "POST",
     "route": "/tasks", "code_attendu": 201, "resultat_attendu": "tache creee"},
    {"id": "T02", "user_story": "US1", "scenario": "Titre manquant", "methode": "POST",
     "route": "/tasks", "code_attendu": 422, "resultat_attendu": "erreur de validation"},
]})
PLAN = SortieTestAgent(cas=[CasDeTest(id="T01", user_story="US1", scenario="Creer une tache",
                                      methode="POST", route="/tasks", code_attendu=201,
                                      resultat_attendu="tache creee")])


def _claude_qui_ecrit_un_test(dossier, reponse):
    def faux_run(*args, **kwargs):
        (Path(dossier) / "tests" / "test_taches.py").write_text("def test_T01_creer_tache():\n    pass\n")
        return MagicMock(returncode=0, stdout=reponse, stderr="")
    return faux_run


@patch("src.agent_test.testeur.subprocess.run")
def test_generer_plan_et_tests(mock_run, tmp_path):
    mock_run.side_effect = _claude_qui_ecrit_un_test(tmp_path, f"Tests ecrits.\n```json\n{PLAN_JSON}\n```")

    plan = generer_plan_et_tests(USER_STORIES, str(tmp_path))

    assert [c.id for c in plan.cas] == ["T01", "T02"]
    assert plan.cas[1].code_attendu == 422
    assert any("test_taches.py" in f for f in plan.fichiers_tests)
    plan_md = (tmp_path / "PLAN_DE_TEST.md").read_text(encoding="utf-8")
    assert "| T02 | US1 | Titre manquant | POST /tasks | 422 |" in plan_md
    prompt = mock_run.call_args.kwargs["input"]
    assert "AVANT le code" in prompt and "from app.main import app" in prompt


@patch("src.agent_test.testeur.subprocess.run")
def test_generer_plan_echoue_sans_fichier_de_tests(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout=PLAN_JSON, stderr="")
    with pytest.raises(RuntimeError, match="aucun fichier de tests"):
        generer_plan_et_tests(USER_STORIES, str(tmp_path))


@patch("src.agent_test.testeur.subprocess.run")
def test_generer_plan_echoue_si_claude_code_echoue(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
    with pytest.raises(RuntimeError, match="Test Agent"):
        generer_plan_et_tests(USER_STORIES, str(tmp_path))


@patch("src.agent_test.testeur.subprocess.run")
def test_reviser_tests_interdit_d_affaiblir_les_tests(mock_run, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    reviser_tests(["test_T01 echoue"], str(tmp_path), PLAN)
    prompt = mock_run.call_args.kwargs["input"]
    assert "NE CHANGE PAS le test" in prompt
    assert "ne rends aucun test moins exigeant" in prompt


def test_restaurer_tests_annule_modification_suppression_et_ajout(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text("assert 1 == 1")
    (tests / "test_b.py").write_text("assert 2 == 2")
    originaux = lire_tests(str(tmp_path))

    (tests / "test_a.py").write_text("pass  # test affaibli")
    (tests / "test_b.py").unlink()
    (tests / "test_c.py").write_text("pass  # test ajoute")

    touches = restaurer_tests(str(tmp_path), originaux)

    assert len(touches) == 3
    assert lire_tests(str(tmp_path)) == originaux


def test_restaurer_tests_ne_touche_rien_si_intacts(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert True")
    assert restaurer_tests(str(tmp_path), lire_tests(str(tmp_path))) == []

# --- Etape 2 : le Test Agent dans le pipeline ---

def test_test_agent_entre_architect_et_developer(agents):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline_en_direct
    from tests.sorties import BESOIN
    noeuds = [noeud for noeud, _ in executer_pipeline_en_direct(BESOIN)]
    assert noeuds[:4] == ["po", "architect", "test_agent", "developer"]


def test_plantage_du_test_agent(agents):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    from tests.sorties import BESOIN
    agents.generer_plan_et_tests.side_effect = RuntimeError("credit Claude epuise")

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is False
    assert resultat["etape"] == "test_agent"
    agents.generer_code.assert_not_called()


def test_rapport_affiche_le_test_agent(agents):
    from src.agent_form.app import construire_rapport_detaille
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    from tests.sorties import BESOIN
    rapport = construire_rapport_detaille(executer_pipeline(BESOIN))
    assert "2b. Test Agent — OK" in rapport
    assert "T01 POST /tasks -> 201" in rapport


# --- Etape 3 : le Developer ne touche plus aux tests ---

@patch("src.agent_dev.developer.subprocess.run")
def test_developer_n_ecrit_plus_les_tests(mock_run, tmp_path):
    from src.agent_dev.developer import generer_code
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    generer_code(USER_STORIES, dossier_sortie=str(tmp_path))
    prompt = mock_run.call_args.kwargs["input"]
    assert "Les tests existent DEJA" in prompt
    assert "Inclus des tests pytest" not in prompt
    assert "from app.main import app" in prompt


def test_tests_modifies_par_la_correction_sont_restaures(agents):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    from tests.sorties import BESOIN, PLAN_TESTS, QA_KO, QA_OK
    fichier = Path("output/backend/tests/test_taches.py")

    def ecrire_tests(*args, **kwargs):
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text("def test_T01():\n    assert reponse.status_code == 201\n")
        return PLAN_TESTS

    appels = []

    def corriger(*args, **kwargs):
        # 1re correction : tentative de triche ; 2e : vraie correction du code
        appels.append(args)
        if len(appels) == 1:
            fichier.write_text("def test_T01():\n    pass\n")

    agents.generer_plan_et_tests.side_effect = ecrire_tests
    agents.appliquer_corrections.side_effect = corriger
    agents.lancer_tests.side_effect = [QA_KO, QA_OK, QA_OK]

    resultat = executer_pipeline(BESOIN)

    assert "status_code == 201" in fichier.read_text()
    erreurs_envoyees = agents.appliquer_corrections.call_args_list[1].args[0]
    assert any("ont ete restaures" in e for e in erreurs_envoyees)
    assert resultat["succes"] is True


def test_revision_des_tests_puis_succes(agents):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    from tests.sorties import BESOIN, QA_KO, QA_OK
    agents.lancer_tests.side_effect = [QA_KO, QA_KO, QA_KO, QA_OK]

    resultat = executer_pipeline(BESOIN)

    assert resultat["succes"] is True
    agents.reviser_tests.assert_called_once()
    assert resultat["tests_revises"] is True
