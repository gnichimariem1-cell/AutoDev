from src.common.schemas import BesoinUtilisateur
from src.agent_po.product_owner import generer_user_stories
from src.agent_dev.developer import generer_code, appliquer_corrections
from src.agent_qa.qa import lancer_tests

MAX_TENTATIVES = 3

def executer_pipeline(besoin: BesoinUtilisateur, dossier_sortie="output/backend"):
    user_stories = generer_user_stories(besoin)
    sortie_dev = generer_code(user_stories, dossier_sortie)

    for tentative in range(1, MAX_TENTATIVES + 1):
        rapport = lancer_tests(dossier_sortie)
        if rapport.succes:
            return {"succes": True, "user_stories": user_stories, "rapport": rapport, "tentative": tentative}
        if tentative == MAX_TENTATIVES:
            return {"succes": False, "user_stories": user_stories, "rapport": rapport, "tentative": tentative}
        sortie_dev = appliquer_corrections(rapport.erreurs, dossier_sortie)

    return {"succes": False}