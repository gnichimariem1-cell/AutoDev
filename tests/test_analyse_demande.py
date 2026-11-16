"""Analyse de la demande par le Product Owner avant le lancement d'un run :
claire -> le run part ; ambigue -> 2 ou 3 scenarios ; vague -> questions. Une demande
floue ne lance jamais de run (ni depuis le formulaire, ni depuis la file, ni au debut du pipeline)."""
import html
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.agent_po import analyse_demande
from src.agent_po.analyse_demande import (
    analyser_demande, analyse_par_les_regles, combiner, signaux_de_flou, QUESTIONS_PAR_DEFAUT,
)
from src.agent_orchestrateur.file_attente import cause_de_l_arret
from src.common.schemas import AnalyseDemande, BesoinUtilisateur, ScenarioDemande

# Les deux formulaires vagues de l'exemple, et un formulaire bien rempli
VAGUE = BesoinUtilisateur(titre_projet="Mon app", description="Une application pour gerer des trucs au quotidien.",
                          utilisateurs_cibles="des gens", fonctionnalites_cles=["gerer", "voir"])
TRES_VAGUE = BesoinUtilisateur(titre_projet="App", description="Fais une app utile.",
                               utilisateurs_cibles="tout le monde", fonctionnalites_cles=["tout"])
CLAIRE = BesoinUtilisateur(
    titre_projet="Todo etudiants",
    description="Une application de liste de taches pour les etudiants, avec des echeances et des priorites "
                "pour organiser leurs devoirs.",
    utilisateurs_cibles="Etudiants", fonctionnalites_cles=["login", "creer tache", "marquer terminee"])


def _scenario(titre):
    return ScenarioDemande(titre_projet=titre, description=f"Application {titre}.", utilisateurs_cibles="Particuliers",
                           fonctionnalites_cles=["ajouter", "lister", "supprimer", "rechercher"], difference=f"axe {titre}",
                           nom_court=f"Version {titre}")


AMBIGUE = AnalyseDemande(clarte="ambigue", manques=["domaine"],
                         scenarios=[_scenario("Taches"), _scenario("Inventaire"), _scenario("Depenses")])


def _reponse_claude(analyse: AnalyseDemande | dict, code=0):
    texte = json.dumps(analyse if isinstance(analyse, dict) else analyse.model_dump())
    return SimpleNamespace(returncode=code, stdout=f"```json\n{texte}\n```", stderr="")


# --- Regles ---

def test_les_formulaires_vagues_ont_plusieurs_signaux():
    assert len(signaux_de_flou(VAGUE)) >= 3
    assert len(signaux_de_flou(TRES_VAGUE)) >= 3


def test_un_formulaire_bien_rempli_n_a_aucun_signal():
    assert signaux_de_flou(CLAIRE) == []


def test_l_ia_trop_indulgente_est_corrigee_par_les_regles():
    decision = combiner(AnalyseDemande(clarte="claire"), signaux_de_flou(VAGUE))
    assert decision.clarte == "vague" and decision.questions == QUESTIONS_PAR_DEFAUT and decision.manques


def test_une_demande_raisonnable_n_est_pas_bloquee_par_un_seul_signal():
    assert combiner(AnalyseDemande(clarte="claire"), ["description tres courte"]).clarte == "claire"


def test_un_seul_scenario_n_est_pas_un_choix():
    decision = combiner(AnalyseDemande(clarte="ambigue", scenarios=[_scenario("Taches")]), [])
    assert decision.clarte == "vague" and decision.scenarios == [] and decision.questions


def test_au_plus_trois_scenarios_et_aucun_si_vague():
    quatre = AMBIGUE.model_copy(update={"scenarios": AMBIGUE.scenarios + [_scenario("Recettes")]})
    assert len(combiner(quatre, []).scenarios) == 3
    assert combiner(AMBIGUE.model_copy(update={"clarte": "vague"}), []).scenarios == []


def test_repli_sur_les_regles_seules():
    assert analyse_par_les_regles(VAGUE).clarte == "vague"
    assert analyse_par_les_regles(CLAIRE).clarte == "claire"


# --- Appel a Claude ---

@patch("src.agent_po.analyse_demande.subprocess.run")
def test_analyser_demande_interroge_claude_sans_les_champs_de_suivi(mock_run):
    mock_run.return_value = _reponse_claude(AMBIGUE)
    analyse = analyser_demande(VAGUE.model_copy(update={"origine": "secret interne"}))
    assert analyse.clarte == "ambigue" and len(analyse.scenarios) == 3
    consigne = mock_run.call_args.kwargs["input"]
    assert "gerer des trucs" in consigne and "secret interne" not in consigne and "demande_verifiee" not in consigne


@patch("src.agent_po.analyse_demande.subprocess.run")
def test_analyser_demande_remonte_l_erreur_de_claude(mock_run):
    mock_run.return_value = SimpleNamespace(returncode=1, stdout="Please run /login", stderr="")
    with pytest.raises(RuntimeError, match="login"):
        analyser_demande(CLAIRE)


@patch("src.agent_po.product_owner.requests.post")
def test_le_po_ne_recoit_pas_les_champs_de_suivi(mock_post):
    from src.agent_po.product_owner import generer_user_stories
    reponse = {"user_stories": [{"id": "US1", "titre": "Login", "description": "creer tache marquer terminee",
                                 "criteres_acceptation": ["c"], "priorite": "haute"}]}
    mock_post.return_value = SimpleNamespace(json=lambda: {"response": json.dumps(reponse)}, raise_for_status=lambda: None)
    generer_user_stories(CLAIRE.model_copy(update={"demande_verifiee": True, "origine": "scenario B"}))
    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "demande_verifiee" not in prompt and "scenario B" not in prompt


# --- Garde-fou au debut du pipeline ---

@pytest.fixture
def analyse_active(monkeypatch):
    monkeypatch.setenv("ANALYSE_DEMANDE", "1")


def test_pipeline_arrete_une_demande_vague_non_verifiee(agents, analyse_active):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    with patch("src.agent_orchestrateur.noeuds.analyser_demande", return_value=AMBIGUE) as analyse:
        resultat = executer_pipeline(VAGUE)
    analyse.assert_called_once()
    agents.generer_user_stories.assert_not_called()
    agents.generer_code.assert_not_called()
    assert resultat["succes"] is False and resultat["etape"] == "po"
    assert resultat["demande_a_preciser"].clarte == "ambigue"
    # Dans la file : c'est le projet qui est en cause, pas la machine (pas de pause)
    assert cause_de_l_arret(resultat) == "projet"


def test_pipeline_ne_reverifie_pas_une_demande_deja_analysee(agents, analyse_active):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    with patch("src.agent_orchestrateur.noeuds.analyser_demande") as analyse:
        resultat = executer_pipeline(CLAIRE.model_copy(update={"demande_verifiee": True}))
    analyse.assert_not_called()
    assert resultat["succes"] is True


def test_pipeline_continue_si_la_demande_non_verifiee_est_claire(agents, analyse_active):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    with patch("src.agent_orchestrateur.noeuds.analyser_demande", return_value=AnalyseDemande(clarte="claire")):
        resultat = executer_pipeline(CLAIRE)
    assert resultat["succes"] is True
    agents.generer_user_stories.assert_called_once()


def test_claude_injoignable_au_debut_du_run_est_un_probleme_machine(agents, analyse_active):
    from src.agent_orchestrateur.orchestrateur import executer_pipeline
    erreur = RuntimeError("Analyse de la demande (Claude) a echoue : Please run /login")
    with patch("src.agent_orchestrateur.noeuds.analyser_demande", side_effect=erreur):
        resultat = executer_pipeline(CLAIRE)
    assert resultat["etape"] == "po" and "demande_a_preciser" not in resultat
    assert cause_de_l_arret(resultat) == "machine"


# --- Formulaire ---

@pytest.fixture
def app(analyse_active):
    from src.agent_form import app as module
    return module


def _formulaire(besoin: BesoinUtilisateur):
    return (besoin.titre_projet, besoin.description, besoin.utilisateurs_cibles,
            ", ".join(besoin.fonctionnalites_cles), "")


def test_demande_claire_part_directement_et_est_marquee_verifiee(app):
    with patch.object(app, "analyser_demande", return_value=AnalyseDemande(clarte="claire")):
        besoin, panneau, analyse = app.analyser_avant_lancement(*_formulaire(CLAIRE), None)
    assert besoin.demande_verifiee is True and panneau == "" and analyse is None


def test_demande_ambigue_propose_les_scenarios_sans_lancer(app):
    with patch.object(app, "analyser_demande", return_value=AMBIGUE):
        besoin, panneau, analyse = app.analyser_avant_lancement(*_formulaire(VAGUE), None)
    assert besoin is None and analyse is AMBIGUE
    assert "Scenario A" in panneau and "Inventaire" in panneau and "Scenario C" in panneau
    boutons = app._boutons_scenarios(analyse)
    assert boutons[1]["value"] == "Choisir B : Version Inventaire" and boutons[3]["visible"] is True


def test_demande_vague_affiche_les_questions(app):
    vague = AnalyseDemande(clarte="vague", questions=["Que doit-on pouvoir creer ?"])
    with patch.object(app, "analyser_demande", return_value=vague):
        besoin, panneau, _ = app.analyser_avant_lancement(*_formulaire(TRES_VAGUE), None)
    assert besoin is None and "trop vague" in panneau and "Que doit-on pouvoir creer ?" in panneau


def test_entree_refusee_avant_toute_analyse(app):
    with patch.object(app, "analyser_demande") as analyse:
        besoin, panneau, _ = app.analyser_avant_lancement("", "x", "y", "z", "", None)
    analyse.assert_not_called()
    assert besoin is None and "Entree refusee" in panneau


def test_claude_injoignable_les_regles_jugent_seules(app):
    with patch.object(app, "analyser_demande", side_effect=RuntimeError("Please run /login")):
        refus, panneau, _ = app.analyser_avant_lancement(*_formulaire(VAGUE), None)
        accepte, _, _ = app.analyser_avant_lancement(*_formulaire(CLAIRE), None)
    assert refus is None and "trop vague" in panneau
    # Acceptee mais non verifiee : le pipeline refera l'analyse au debut du run
    assert accepte is not None and accepte.demande_verifiee is False


def test_choisir_un_scenario_remplit_le_formulaire_puis_lance_sans_nouvelle_analyse(app):
    etat_analyse = dict(AMBIGUE.model_dump(), _origine="demande d'origine « Mon app »")
    sorties = app.choisir_scenario(1, etat_analyse)
    titre, description, utilisateurs, fonctionnalites, scenario_rempli, panneau = sorties[:6]
    assert titre == "Inventaire" and fonctionnalites == "ajouter, lister, supprimer, rechercher"
    assert "Scenario B rempli" in panneau
    assert "scenario B choisi parmi 3" in scenario_rempli["origine"] and "Mon app" in scenario_rempli["origine"]

    with patch.object(app, "analyser_demande") as analyse:
        besoin, _, _ = app.analyser_avant_lancement(titre, description, utilisateurs, fonctionnalites, "", scenario_rempli)
    analyse.assert_not_called()
    assert besoin.demande_verifiee is True and besoin.origine == scenario_rempli["origine"]


def test_scenario_modifie_est_reanalyse_et_garde_sa_trace(app):
    _, description, utilisateurs, fonctionnalites, scenario_rempli = app.choisir_scenario(0, AMBIGUE.model_dump())[:5]
    with patch.object(app, "analyser_demande", return_value=AnalyseDemande(clarte="claire")) as analyse:
        besoin, _, _ = app.analyser_avant_lancement("Taches perso", description, utilisateurs, fonctionnalites, "",
                                                    scenario_rempli)
    analyse.assert_called_once()
    assert "modifie ensuite" in besoin.origine


def test_aucun_scenario_ne_convient_affiche_les_questions(app):
    panneau, scenario_rempli, *boutons = app.aucun_scenario(AMBIGUE.model_dump())
    assert "Aucun scenario ne convient" in panneau and html.escape(QUESTIONS_PAR_DEFAUT[0]) in panneau
    assert scenario_rempli is None
    assert all(b["visible"] is False for b in boutons)


def test_une_demande_floue_n_entre_pas_dans_la_file(app, monkeypatch):
    from src.agent_orchestrateur.file_attente import FileAttente
    file = FileAttente(lambda b: None, lambda i: None, chemin=None)
    monkeypatch.setattr(app, "FILE", file)
    with patch.object(app, "analyser_demande", return_value=AMBIGUE):
        sorties = list(app.preparer_ajout_file(*_formulaire(VAGUE), None))
    besoin_pret = sorties[-1][2]
    assert besoin_pret is None
    assert app.ajouter_si_pret(besoin_pret)[0] == "" and file.copie() == []


def test_une_demande_claire_entre_dans_la_file_deja_verifiee(app, monkeypatch):
    from src.agent_orchestrateur.file_attente import FileAttente
    file = FileAttente(lambda b: None, lambda i: None, chemin=None)
    file.mettre_en_pause("test")  # le travailleur ne demarre pas de run
    monkeypatch.setattr(app, "FILE", file)
    with patch.object(app, "analyser_demande", return_value=AnalyseDemande(clarte="claire")):
        sorties = list(app.preparer_ajout_file(*_formulaire(CLAIRE), None))
    message, _ = app.ajouter_si_pret(sorties[-1][2])
    assert "ajoute a la file" in message
    assert file.copie()[0].besoin["demande_verifiee"] is True


def test_rapport_d_un_run_arrete_pour_demande_a_preciser(app):
    resultat = {"id_run": "x", "besoin": VAGUE, "succes": False, "etape": "po",
                "erreur": "Demande a preciser", "demande_a_preciser": AMBIGUE}
    assert app.statut_du_run(resultat) == "A PRECISER"
    assert "aucun code genere" in app.message_en_ce_moment(resultat)
    rapport = app.construire_rapport_detaille(resultat)
    assert "DEMANDE A PRECISER" in rapport and "Scenario B : Inventaire" in rapport
    assert ("Product Owner", "ko", "a preciser") in app.etats_des_etapes(resultat)


def test_analyse_desactivee_par_env(app, monkeypatch):
    monkeypatch.setenv("ANALYSE_DEMANDE", "0")
    assert analyse_demande.analyse_active() is False
    with patch.object(app, "analyser_demande") as analyse:
        besoin, _, _ = app.analyser_avant_lancement(*_formulaire(VAGUE), None)
    analyse.assert_not_called()
    assert besoin is not None and besoin.demande_verifiee is False
