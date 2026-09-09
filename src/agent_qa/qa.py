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
    resultat = subprocess.run(
        ["pytest", dossier_code, "--cov", dossier_code,
         "--cov-report=json", "--json-report", "--json-report-file=rapport_pytest.json"],
        capture_output=True, text=True, env=_env_sans_ros(),
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
    tests_echoues = rapport["summary"].get("failed", 0)
    erreurs = [t["nodeid"] for t in rapport["tests"] if t["outcome"] == "failed"]

    return RapportQA(
        tests_passes=tests_passes,
        tests_echoues=tests_echoues,
        couverture_pct=couverture["totals"]["percent_covered"],
        succes=(tests_echoues == 0),
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