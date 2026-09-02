import subprocess
import json
from src.common.schemas import RapportQA

def lancer_tests(dossier_code: str) -> RapportQA:
    resultat = subprocess.run(
        ["pytest", dossier_code, "--cov", dossier_code,
         "--cov-report=json", "--json-report", "--json-report-file=rapport_pytest.json"],
        capture_output=True, text=True,
    )
    with open("rapport_pytest.json") as f:
        rapport = json.load(f)
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