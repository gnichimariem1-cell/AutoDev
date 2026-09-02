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