from pathlib import Path

from src.agent_orchestrateur.orchestrateur import (
    archiver_sorties, executer_pipeline, reprendre_pipeline_en_direct,
)
from tests.sorties import BESOIN, SORTIE_DEV


def test_dossier_absent_cree_sans_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert archiver_sorties("output", "run-1") is None
    assert Path("output/.id_run").read_text() == "run-1"
    assert not Path("archives").exists()


def test_sorties_archivees_sous_l_id_du_run_precedent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    archiver_sorties("output", "run-1")
    Path("output/backend").mkdir()
    Path("output/backend/main.py").write_text("ancien")

    archive = archiver_sorties("output", "run-2")

    assert archive == Path("archives/run-1")
    assert Path("archives/run-1/backend/main.py").read_text() == "ancien"
    assert [p.name for p in Path("output").iterdir()] == [".id_run"]
    assert Path("output/.id_run").read_text() == "run-2"


def test_sorties_sans_marqueur_archivees_sous_leur_date(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("output").mkdir()
    Path("output/Dockerfile").write_text("FROM python")

    archive = archiver_sorties("output", "run-1")

    assert archive.parent == Path("archives") and archive.name.startswith("output-")
    assert (archive / "Dockerfile").exists()


def test_nom_d_archive_deja_pris(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("archives/run-1").mkdir(parents=True)
    archiver_sorties("output", "run-1")
    Path("output/f.txt").write_text("x")

    archive = archiver_sorties("output", "run-2")

    assert archive.name.startswith("run-1-") and (archive / "f.txt").exists()


def test_nouveau_run_archive_le_precedent(agents):
    id1 = executer_pipeline(BESOIN)["id_run"]
    Path("output/backend").mkdir(parents=True, exist_ok=True)
    Path("output/backend/main.py").write_text("run 1")

    id2 = executer_pipeline(BESOIN)["id_run"]

    assert Path(f"archives/{id1}/backend/main.py").read_text() == "run 1"
    assert Path("output/.id_run").read_text() == id2
    assert not Path("output/backend/main.py").exists()


def test_reprise_garde_les_sorties(agents):
    agents.generer_code.side_effect = RuntimeError("credit Claude epuise")
    resultat = executer_pipeline(BESOIN)
    Path("output/backend").mkdir(parents=True, exist_ok=True)
    Path("output/backend/main.py").write_text("en cours")

    agents.generer_code.side_effect = None
    agents.generer_code.return_value = SORTIE_DEV
    list(reprendre_pipeline_en_direct(resultat["id_run"]))

    assert Path("output/backend/main.py").read_text() == "en cours"
    assert not Path("archives").exists()
