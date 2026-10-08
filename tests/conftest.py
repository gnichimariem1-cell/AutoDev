import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Les tests ne doivent pas ecrire dans checkpoints/pipeline.sqlite : base en memoire.
os.environ.setdefault("CHECKPOINT_DB", ":memory:")

from tests import sorties  # noqa: E402

SORTIES_PAR_DEFAUT = {
    "generer_user_stories": sorties.USER_STORIES,
    "generer_architecture": sorties.ARCHITECTURE,
    "generer_code": sorties.SORTIE_DEV,
    "appliquer_corrections": sorties.SORTIE_DEV,
    "lancer_tests": sorties.QA_OK,
    "generer_frontend": sorties.SORTIE_FRONTEND,
    "appliquer_corrections_frontend": sorties.SORTIE_FRONTEND,
    "lancer_tests_frontend": sorties.FE_OK,
    "generer_dockerisation": sorties.SORTIE_DOCKER,
    "appliquer_corrections_dockerisation": sorties.SORTIE_DOCKER,
    "valider_dockerisation": sorties.DOCKER_OK,
}


@pytest.fixture
def agents(tmp_path, monkeypatch):
    """Remplace tous les agents appeles par le graphe par des mocks qui
    reussissent du premier coup ; chaque test modifie ceux qui l'interessent
    (ex : agents.lancer_tests.return_value = QA_KO).
    Le test s'execute dans tmp_path : l'archivage des sorties en debut de run ne
    touche ni output/ ni archives/ du projet."""
    monkeypatch.chdir(tmp_path)
    with ExitStack() as pile:
        mocks = {
            nom: pile.enter_context(patch(f"src.agent_orchestrateur.noeuds.{nom}", return_value=sortie))
            for nom, sortie in SORTIES_PAR_DEFAUT.items()
        }
        yield SimpleNamespace(**mocks)
