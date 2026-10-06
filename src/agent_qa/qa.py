import os
import subprocess
import json
import shutil
from pathlib import Path
from src.common.schemas import RapportQA, RapportQAFrontend

def _env_sans_ros() -> dict:
    """Retire les chemins ROS de PYTHONPATH pour éviter que pytest ne charge
    les plugins launch_testing/launch_ros (qui dépendent de paquets absents du venv)."""
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    chemins_filtres = [
        p for p in pythonpath.split(os.pathsep) if p and "/opt/ros" not in p
    ]
    if chemins_filtres:
        env["PYTHONPATH"] = os.pathsep.join(chemins_filtres)
    else:
        env.pop("PYTHONPATH", None)
    return env


def lancer_tests(dossier_code: str) -> RapportQA:
    env = _env_sans_ros()

    requirements = os.path.join(dossier_code, "requirements.txt")
    if os.path.exists(requirements):
        resultat_install = subprocess.run(
            ["pip", "install", "-r", requirements],
            capture_output=True, text=True, env=env,
        )
        if resultat_install.returncode != 0:
            raise RuntimeError(
                "Echec de l'installation des dependances du backend genere "
                f"({requirements}).\n"
                f"stdout : {resultat_install.stdout[-2000:]}\n"
                f"stderr : {resultat_install.stderr[-2000:]}"
            )

    # Le backend genere importe ses modules depuis sa racine (ex : `from app.main import app`)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [os.path.abspath(dossier_code), env.get("PYTHONPATH")] if p
    )
    # Evite de relire le rapport d'un run precedent si pytest plante avant de l'ecrire
    for ancien in ("rapport_pytest.json", "coverage.json"):
        if os.path.exists(ancien):
            os.remove(ancien)

    resultat = subprocess.run(
        ["pytest", dossier_code, "--cov", dossier_code,
         "--cov-report=json", "--json-report", "--json-report-file=rapport_pytest.json"],
        capture_output=True, text=True, env=env,
    )

    if not os.path.exists("rapport_pytest.json"):
        raise RuntimeError(
            "pytest n'a pas produit de rapport (rapport_pytest.json manquant), "
            "probablement une erreur avant la collecte des tests.\n"
            f"Code de retour : {resultat.returncode}\n"
            f"stdout : {resultat.stdout[-2000:]}\n"
            f"stderr : {resultat.stderr[-2000:]}"
        )

    with open("rapport_pytest.json") as f:
        rapport = json.load(f)

    if not os.path.exists("coverage.json"):
        raise RuntimeError(
            "pytest-cov n'a pas produit coverage.json.\n"
            f"stdout : {resultat.stdout[-2000:]}\n"
            f"stderr : {resultat.stderr[-2000:]}"
        )

    with open("coverage.json") as f:
        couverture = json.load(f)

    tests_passes = rapport["summary"].get("passed", 0)
    # "error" : echec pendant le setup/teardown d'un test (ex : fixture qui plante)
    tests_echoues = rapport["summary"].get("failed", 0) + rapport["summary"].get("error", 0)
    erreurs = [
        t["nodeid"] for t in rapport.get("tests", []) if t["outcome"] in ("failed", "error")
    ]
    # Fichiers de test qui n'ont pas pu etre importes (ex : ImportError)
    erreurs += [
        f"Erreur de collecte {c['nodeid']} : {c.get('longrepr', '')[-1000:]}"
        for c in rapport.get("collectors", []) if c["outcome"] == "failed"
    ]
    if rapport["summary"].get("total", tests_passes + tests_echoues) == 0:
        erreurs.append(
            f"Aucun test pytest trouve dans {dossier_code} : ecris des tests (dossier tests/, "
            "fichiers test_*.py) couvrant les endpoints de l'API."
        )

    return RapportQA(
        tests_passes=tests_passes,
        tests_echoues=tests_echoues,
        couverture_pct=couverture["totals"]["percent_covered"],
        succes=(len(erreurs) == 0),
        erreurs=erreurs,
    )


def lancer_tests_frontend(dossier_code: str) -> RapportQAFrontend:
    """Verifie le frontend genere : presence d'index.html et validite syntaxique
    des fichiers JS (via `node --check`, si node est disponible)."""
    dossier = Path(dossier_code)
    erreurs = []

    index_html = dossier / "index.html"
    if not index_html.exists():
        erreurs.append(f"{index_html} est manquant.")

    fichiers_js = list(dossier.rglob("*.js"))
    fichiers_verifies = [str(index_html)] + [str(f) for f in fichiers_js]

    node_bin = shutil.which("node")
    if node_bin:
        for fichier in fichiers_js:
            resultat = subprocess.run(
                [node_bin, "--check", str(fichier)],
                capture_output=True, text=True,
            )
            if resultat.returncode != 0:
                erreurs.append(f"{fichier} : {resultat.stderr.strip()}")

    return RapportQAFrontend(
        fichiers_verifies=fichiers_verifies,
        succes=(len(erreurs) == 0),
        erreurs=erreurs,
    )