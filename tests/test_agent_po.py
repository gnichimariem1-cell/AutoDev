from unittest.mock import patch, MagicMock
from src.agent_po.product_owner import generer_user_stories
from src.common.schemas import BesoinUtilisateur
import json

@patch("src.agent_po.product_owner.requests.post")
def test_generer_user_stories_parse_reponse_ollama(mock_post):
    fausse_reponse = {
        "user_stories": [{
            "id": "US1", "titre": "Login utilisateur",
            "description": "En tant qu'utilisateur je veux me connecter",
            "criteres_acceptation": ["formulaire valide", "erreur si mdp faux"],
            "priorite": "haute",
        }]
    }
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"response": json.dumps(fausse_reponse)},
        raise_for_status=lambda: None,
    )
    besoin = BesoinUtilisateur(
        titre_projet="x", description="y", utilisateurs_cibles="z",
        fonctionnalites_cles=["login"],
    )
    resultat = generer_user_stories(besoin)
    assert len(resultat.user_stories) == 1
    assert resultat.user_stories[0].priorite == "haute"
    requete = mock_post.call_args.kwargs["json"]
    assert requete["format"]["properties"]["user_stories"]["type"] == "array"
    assert requete["think"] is False


@patch("src.agent_po.product_owner.requests.post")
def test_consigne_contient_les_regles_de_priorite(mock_post):
    reponse = {"user_stories": [{"id": "US1", "titre": "t", "description": "d",
                                 "criteres_acceptation": ["c"], "priorite": "basse"}]}
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {"response": json.dumps(reponse)},
        raise_for_status=lambda: None,
    )
    besoin = BesoinUtilisateur(
        titre_projet="x", description="y", utilisateurs_cibles="z",
        fonctionnalites_cles=["login", "historique", "supprimer"],
    )
    generer_user_stories(besoin)
    prompt = mock_post.call_args.kwargs["json"]["prompt"]
    assert "MoSCoW" in prompt
    assert "ne peuvent pas toutes etre" in prompt


# --- Chaque fonctionnalite du formulaire doit avoir sa user story ---

def _story(id_, titre, description="d", priorite="haute"):
    return {"id": id_, "titre": titre, "description": description,
            "criteres_acceptation": ["c"], "priorite": priorite}


def _reponses_ollama(*reponses):
    return [MagicMock(status_code=200, raise_for_status=lambda: None,
                      json=(lambda r=r: {"response": json.dumps({"user_stories": r})}))
            for r in reponses]


BESOIN_CHATBOT = BesoinUtilisateur(
    titre_projet="Chatbot", description="d", utilisateurs_cibles="equipe",
    fonctionnalites_cles=["se connecter", "se deconnecter", "poser une question"],
)


@patch("src.agent_po.product_owner.requests.post")
def test_fonctionnalite_oubliee_redemandee(mock_post):
    mock_post.side_effect = _reponses_ollama(
        [_story("US1", "Se connecter"), _story("US2", "Poser une question")],
        [_story("US1", "Se connecter"), _story("US2", "Poser une question"),
         _story("US3", "Se déconnecter", priorite="moyenne")],
    )
    sortie = generer_user_stories(BESOIN_CHATBOT)
    assert mock_post.call_count == 2
    assert "se deconnecter" in mock_post.call_args.kwargs["json"]["prompt"]
    assert [us.titre for us in sortie.user_stories][-1] == "Se déconnecter"


@patch("src.agent_po.product_owner.requests.post")
def test_fonctionnalite_toujours_oubliee_ajoutee_automatiquement(mock_post):
    oubli = [_story("US1", "Se connecter"), _story("US2", "Poser une question")]
    mock_post.side_effect = _reponses_ollama(oubli, oubli)
    sortie = generer_user_stories(BESOIN_CHATBOT)
    derniere = sortie.user_stories[-1]
    assert derniere.id == "US3" and derniere.priorite == "moyenne"
    assert "se deconnecter" in derniere.description


@patch("src.agent_po.product_owner.requests.post")
def test_aucune_redemande_si_tout_est_couvert(mock_post):
    mock_post.side_effect = _reponses_ollama([
        _story("US1", "Connexion", "L'utilisateur se connecte avec son compte"),
        _story("US2", "Déconnexion", "L'utilisateur se déconnecte"),
        _story("US3", "Poser une question au chatbot"),
    ])
    generer_user_stories(BESOIN_CHATBOT)
    assert mock_post.call_count == 1


def test_fonctionnalite_fusionnee_est_couverte():
    from src.agent_po.product_owner import fonctionnalites_manquantes
    from src.common.schemas import SortiePO
    sortie = SortiePO.model_validate({"user_stories": [
        _story("US1", "Poser une question", "La premiere question cree une conversation")]})
    assert fonctionnalites_manquantes(["creer une conversation", "supprimer une conversation"], sortie) \
        == ["supprimer une conversation"]


def test_po_avec_claude(monkeypatch):
    """PO_MOTEUR=claude : le Product Owner passe par Claude Code, pas par Ollama."""
    from unittest.mock import MagicMock, patch
    from src.common.schemas import BesoinUtilisateur
    monkeypatch.setenv("PO_MOTEUR", "claude")
    reponse = ('```json\n{"user_stories": [{"id": "US1", "titre": "Creer une tache", '
               '"description": "L\'utilisateur cree une tache", "criteres_acceptation": ["titre obligatoire"], '
               '"priorite": "haute"}]}\n```')
    besoin = BesoinUtilisateur(titre_projet="Taches", description="Gerer des taches",
                               utilisateurs_cibles="Etudiants", fonctionnalites_cles=["creer une tache"])
    with patch("src.agent_po.product_owner.subprocess.run",
               return_value=MagicMock(returncode=0, stdout=reponse, stderr="")) as claude, \
         patch("src.agent_po.product_owner.requests.post") as ollama:
        sortie = generer_user_stories(besoin)
    assert claude.called and not ollama.called
    assert sortie.user_stories[0].titre == "Creer une tache"


def test_po_moteur_par_defaut_ollama(monkeypatch):
    """Sans PO_MOTEUR (ou valeur inconnue), rien ne change : Ollama."""
    from src.agent_po.product_owner import moteur_po
    monkeypatch.delenv("PO_MOTEUR", raising=False)
    assert moteur_po() == "ollama"
    monkeypatch.setenv("PO_MOTEUR", "autre")
    assert moteur_po() == "ollama"
    monkeypatch.setenv("PO_MOTEUR", " Claude ")
    assert moteur_po() == "claude"


import pytest


@pytest.fixture(autouse=True)
def _po_moteur_ollama_par_defaut(monkeypatch):
    """Les tests ne dependent pas du .env du poste : Ollama par defaut."""
    monkeypatch.setenv("PO_MOTEUR", "ollama")
