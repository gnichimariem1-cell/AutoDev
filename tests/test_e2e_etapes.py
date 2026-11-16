"""Agent E2E etape 6 : un scenario d'interface par page et des captures aux etapes cles."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent_e2e import e2e
from src.common.regles import regles_de
from src.common.schemas import CaptureE2E
from tests.sorties import USER_STORIES


def test_consigne_et_regles():
    regles = regles_de("agent_e2e")
    assert "Chaque page principale" in regles and 'etape("nom_court")' in regles
    assert "def etape(request)" in e2e.CONFTEST and "E2E_DOSSIER_ETAPES" in e2e.CONFTEST


def test_agent_e2e_recoit_la_fixture_etape(tmp_path):
    def claude(*args, **kwargs):
        (tmp_path / "e2e" / "test_interface_e2e.py").write_text("def test_E01_x(): pass\n")
        return MagicMock(returncode=0, stdout='{"scenarios": []}', stderr="")

    with patch("src.agent_e2e.e2e.subprocess.run", side_effect=claude) as mock_run:
        e2e.generer_tests_e2e(USER_STORIES, "demande", dossier=str(tmp_path / "e2e"))
    consigne = mock_run.call_args.kwargs["input"]
    assert 'etape("nom")' in consigne and "entre 6 et 12" in consigne and "3 a 6" not in consigne


def test_lister_captures_avec_etapes(tmp_path):
    dossier = tmp_path / "e2e"
    fin = dossier / "captures" / "test-interface-e2e-py-test-e21-connexion-chromium"
    fin.mkdir(parents=True)
    (fin / "test-finished-1.png").write_bytes(b"png")
    for nom in ("02-apres_clic.png", "01-page_ouverte.png"):
        (dossier / "etapes" / "E21").mkdir(parents=True, exist_ok=True)
        (dossier / "etapes" / "E21" / nom).write_bytes(b"png")
    (dossier / "etapes" / "E22").mkdir()
    (dossier / "etapes" / "E22" / "01-liste.png").write_bytes(b"png")
    captures = {c.id: c for c in e2e.lister_captures(str(dossier))}
    assert [Path(p).name for p in captures["E21"].etapes] == ["01-page_ouverte.png", "02-apres_clic.png"]
    assert captures["E21"].image.endswith("test-finished-1.png")
    assert captures["E22"].image == "" and len(captures["E22"].etapes) == 1


def test_etapes_reelles_avec_chromium(tmp_path):
    """Vrai Chromium : etape("...") ecrit une capture numerotee par etape."""
    if not e2e.navigateur_disponible():
        pytest.skip("Chromium absent sur ce poste (present dans l'image AutoDev)")
    dossier = tmp_path / "e2e"
    dossier.mkdir()
    e2e.ecrire_fichiers_autodev(str(dossier))
    (dossier / "test_interface_e2e.py").write_text(
        "from playwright.sync_api import Page, expect\n"
        "def test_E03_page(page: Page, etape):\n"
        "    page.set_content('<h1>GenieLab</h1>')\n"
        "    etape('page ouverte')\n"
        "    page.set_content('<p>Fini</p>')\n"
        "    etape('resultat affiche')\n"
        "    expect(page.get_by_text('Fini')).to_be_visible()\n")
    rapport = e2e.lancer_scenarios([str(dossier / "test_interface_e2e.py")], str(dossier), "http://localhost:1",
                                   front_url="http://localhost:1", captures=True)
    assert rapport.succes is True
    assert [Path(p).name for p in rapport.captures[0].etapes] == ["01-page_ouverte.png", "02-resultat_affiche.png"]


def test_etapes_affichees_dans_le_detail(tmp_path):
    from PIL import Image
    from src.agent_form import app
    from tests.test_agent_e2e import E2E_OK
    image = tmp_path / "01-formulaire_rempli.png"
    Image.new("RGB", (1280, 720), "white").save(image)
    rapport = E2E_OK.model_copy(update={"captures": [CaptureE2E(id="E21", etapes=[str(image)])]})
    detail = app._details({"id_run": "r1", "succes": True, "rapport_e2e": rapport})
    assert "formulaire rempli" in detail and "data:image/jpeg;base64," in detail
