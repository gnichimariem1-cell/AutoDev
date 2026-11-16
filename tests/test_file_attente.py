"""File d'attente : les projets passent l'un apres l'autre ; une erreur du projet
n'arrete pas la file, une erreur de la machine la met en pause."""
from types import SimpleNamespace

import pytest

from src.agent_orchestrateur import file_attente as fa
from src.agent_orchestrateur.file_attente import FileAttente, cause_de_l_arret
from src.common.schemas import BesoinUtilisateur, RapportValidationDocker


def besoin(titre):
    return BesoinUtilisateur(titre_projet=titre, description="d", utilisateurs_cibles="u",
                             fonctionnalites_cles=["f"])


class FauxRun:
    """Run deja termine, avec son etat final."""

    def __init__(self, etat, exception=None):
        self.id_run = etat.get("id_run", "")
        self.evenements = [("fin", etat)] if etat else []
        self.exception = exception
        self.termine = True

    def attendre(self, deja_vus, timeout):
        return [], True


SUCCES = {"succes": True}
ECHEC_PROJET = {"succes": False, "etape": "e2e"}
PORTS = {"succes": False, "etape": "docker", "rapport_validation_docker": RapportValidationDocker(
    docker_disponible=True, succes=False, erreur_environnement=True,
    erreurs=["ports : port(s) deja occupe(s) sur la machine : 8000"])}
CONNEXION = {"succes": False, "etape": "po", "erreur": "RuntimeError : Product Owner (Claude) a échoué : "
             "Failed to authenticate: this login reached its time limit. Run `claude auth login`"}


def file_avec(resultats, reprises=None, **options):
    """resultats : titre -> etat final du run (ou liste d'etats, un par passage)."""
    lances, repris = [], []

    def nouveau(b):
        lances.append(b.titre_projet)
        etat = resultats[b.titre_projet]
        etat = etat.pop(0) if isinstance(etat, list) else etat
        return FauxRun(dict(etat, id_run=f"run-{b.titre_projet}"))

    def reprise(id_run):
        repris.append(id_run)
        return FauxRun(dict((reprises or {}).get(id_run, SUCCES), id_run=id_run))

    file = FileAttente(nouveau, reprise, chemin=options.pop("chemin", None), attente_si_occupe=0, **options)
    return file, lances, repris


def statuts(file):
    return [(e.titre, e.statut) for e in file.copie()]


def test_cause_de_l_arret():
    assert cause_de_l_arret(SUCCES) == "succes"
    assert cause_de_l_arret(ECHEC_PROJET) == "projet"
    assert cause_de_l_arret({"succes": False, "etape": "developer", "erreur": "ValueError : JSON invalide"}) == "projet"
    assert cause_de_l_arret(PORTS) == "machine"
    assert cause_de_l_arret(CONNEXION) == "machine"
    assert cause_de_l_arret({}, exception=RuntimeError("thread")) == "machine"


def test_les_projets_passent_l_un_apres_l_autre():
    file, lances, _ = file_avec({"A": SUCCES, "B": SUCCES, "C": SUCCES})
    for titre in "ABC":
        file.ajouter(besoin(titre))
    file.attendre_fin()
    assert lances == ["A", "B", "C"]
    assert statuts(file) == [("A", "termine"), ("B", "termine"), ("C", "termine")]
    assert file.copie()[1].id_run == "run-B"


def test_un_projet_en_echec_n_arrete_pas_la_file():
    file, lances, _ = file_avec({"A": ECHEC_PROJET, "B": SUCCES})
    file.ajouter(besoin("A"))
    file.ajouter(besoin("B"))
    file.attendre_fin()
    assert statuts(file) == [("A", "echec"), ("B", "termine")]
    assert "e2e" in file.copie()[0].message and not file.en_pause


def test_probleme_machine_met_la_file_en_pause_puis_reprise():
    file, lances, repris = file_avec({"A": CONNEXION, "B": SUCCES, "C": SUCCES})
    file.ajouter(besoin("A"))
    file.ajouter(besoin("B"))
    file.attendre_fin()
    assert statuts(file) == [("A", "arrete (machine)"), ("B", "en attente")]
    assert file.en_pause and "authenticate" in file.raison_pause
    assert "claude auth login" in fa.conseil(file.raison_pause)
    file.ajouter(besoin("C"))  # en pause : rien ne demarre
    file.attendre_fin()
    assert lances == ["A"]

    file.reprendre()  # la connexion est reglee
    file.attendre_fin()
    assert repris == ["run-A"]  # A repris la ou il s'etait arrete, pas relance du debut
    assert lances == ["A", "B", "C"]
    assert statuts(file) == [("A", "termine"), ("B", "termine"), ("C", "termine")]


def test_ports_occupes_conseil():
    file, _, _ = file_avec({"A": PORTS})
    file.ajouter(besoin("A"))
    file.attendre_fin()
    assert file.en_pause and "publish=8000" in fa.conseil(file.raison_pause)


def test_reprise_impossible_passe_au_suivant():
    def reprise(id_run):
        raise RuntimeError("archive par un run plus recent")

    file = FileAttente(lambda b: FauxRun(dict(CONNEXION, id_run="run-A")), reprise, chemin=None, attente_si_occupe=0)
    file.ajouter(besoin("A"))
    file.attendre_fin()
    file.reprendre()
    file.attendre_fin()
    assert statuts(file) == [("A", "echec")] and "archive" in file.copie()[0].message


def test_attend_si_un_run_lance_a_la_main_tourne():
    reponses = [None, None, FauxRun(dict(SUCCES, id_run="r"))]  # occupe deux fois, puis libre
    file = FileAttente(lambda b: reponses.pop(0), lambda i: None, chemin=None, attente_si_occupe=0)
    file.ajouter(besoin("A"))
    file.attendre_fin()
    assert statuts(file) == [("A", "termine")] and reponses == []


def test_vider_garde_le_run_en_cours_et_les_resultats():
    file, _, _ = file_avec({"A": CONNEXION})
    file.ajouter(besoin("A"))
    file.attendre_fin()
    file.ajouter(besoin("B"))
    file.ajouter(besoin("C"))
    assert file.vider() == 2
    assert statuts(file) == [("A", "arrete (machine)")]


def test_file_gardee_apres_un_redemarrage(tmp_path):
    chemin = tmp_path / "file.json"
    file, _, _ = file_avec({"A": SUCCES}, chemin=str(chemin))
    file.mettre_en_pause()
    file.ajouter(besoin("A"))
    file.ajouter(besoin("B"))
    # AutoDev s'arrete pendant le run de A
    file.elements[0].statut, file.elements[0].id_run = "en cours", "run-A"
    file._sauver()

    relue = FileAttente(lambda b: None, lambda i: None, chemin=str(chemin))
    assert statuts(relue) == [("A", "en attente"), ("B", "en attente")]
    assert relue.elements[0].reprise and relue.en_pause and "redemarre" in relue.raison_pause
    assert relue.elements[0].besoin["titre_projet"] == "A"


def test_fichier_illisible(tmp_path):
    chemin = tmp_path / "file.json"
    chemin.write_text("{pas du json", encoding="utf-8")
    assert FileAttente(lambda b: None, lambda i: None, chemin=str(chemin)).elements == []


# --- Interface ---

@pytest.fixture
def file_vue(monkeypatch):
    from src.agent_form import app
    file, lances, _ = file_avec({"Inventaire": SUCCES})
    monkeypatch.setattr(app, "FILE", file)
    return app, file, lances


def test_ajouter_a_la_file_depuis_le_formulaire(file_vue):
    app, file, lances = file_vue
    message, vue = app.ajouter_a_la_file("Inventaire", "Gestion de l'inventaire du labo", "membres", "ajouter, lister", "")
    file.attendre_fin()
    assert "ajoute a la file" in message and lances == ["Inventaire"]
    assert "attente</b> (1)" in app.vue_file() and "termine" in app.vue_file()


def test_entree_refusee_n_ajoute_rien(file_vue):
    app, file, lances = file_vue
    message, _ = app.ajouter_a_la_file("", "x", "y", "z", "")
    assert "Entree refusee" in message and file.copie() == []


def test_vue_file_en_pause_donne_le_conseil(file_vue):
    app, file, _ = file_vue
    file.mettre_en_pause("Projet A : Failed to authenticate")
    vue = app.vue_file()
    assert "En pause" in vue and "claude auth login" in vue and "Reprendre la file" in vue
    file.ajouter(besoin("Inventaire"))
    assert "(0)" in app.vider_la_file()  # en pause : le projet ajoute est retire, rien ne demarre


def test_suivi_d_un_run_lance_par_la_file(monkeypatch):
    """La page n'a pas lance ce run : elle l'affiche quand meme, a sa derniere etape."""
    from src.agent_form import app
    etat = {"id_run": "inventaire-1", "besoin": besoin("Inventaire"), "succes": True}
    run = SimpleNamespace(id_run="inventaire-1", termine=False, debut=0, debut_etape=0,
                          evenements=[("po", etat)])
    monkeypatch.setattr(app, "_run_actif", run)
    suivi = app._etat_pour_le_suivi(None)
    assert suivi["id_run"] == "inventaire-1" and suivi["_en_cours"] == "po"


# --- Etape 2 : remettre dans la file un projet en echec ---

def test_remettre_un_projet_en_echec():
    file, lances, _ = file_avec({"Stock": [ECHEC_PROJET, SUCCES], "Achat": SUCCES})
    file.ajouter(besoin("Stock"))
    file.ajouter(besoin("Achat"))
    file.attendre_fin()
    assert [e.titre for e in file.echecs()] == ["Stock"]

    nouveau = file.remettre(1)
    file.attendre_fin()
    assert nouveau.numero == 3 and nouveau.besoin["titre_projet"] == "Stock"
    assert lances == ["Stock", "Achat", "Stock"]  # repart du debut, comme un nouveau projet
    assert statuts(file) == [("Stock", "remis dans la file"), ("Achat", "termine"), ("Stock", "termine")]
    assert "n° 3" in file.copie()[0].message and file.echecs() == []


def test_remettre_seulement_un_echec():
    file, _, _ = file_avec({"A": SUCCES, "B": CONNEXION})
    file.ajouter(besoin("A"))
    file.attendre_fin()
    file.ajouter(besoin("B"))
    file.attendre_fin()
    assert file.remettre(1) is None  # termine : rien a remettre
    assert file.remettre(2) is None  # arrete (machine) : c'est « Reprendre la file »
    assert file.remettre(99) is None


def test_bouton_remettre_dans_la_vue(file_vue):
    app, file, lances = file_vue
    file._demarrer_nouveau = lambda b: (lances.append(b.titre_projet) or FauxRun(dict(ECHEC_PROJET, id_run="r1")))
    file.ajouter(besoin("Stock"))
    file.attendre_fin()
    assert app.choix_des_echecs() == ["n° 1 · Stock"]
    _, liste, affiches = app.rafraichir_file(None)
    assert affiches == ["n° 1 · Stock"]
    assert app.liste_des_echecs(affiches)[0] == {"__type__": "update"}  # inchange : le choix n'est pas perdu

    file._demarrer_nouveau = lambda b: (lances.append(b.titre_projet) or FauxRun(dict(SUCCES, id_run="r2")))
    vue, liste, affiches = app.remettre_dans_la_file("n° 1 · Stock", affiches)
    file.attendre_fin()
    assert lances == ["Stock", "Stock"] and affiches == []
    assert "remis dans la file" in app.vue_file() and "termine" in app.vue_file()


# --- Limite d'utilisation du compte Claude : probleme de la machine, pas du projet ---

LIMITE = {"succes": False, "etape": "e2e", "erreur": "RuntimeError : Agent E2E a échoué : "
          "You've hit your 5-hour limit · resets 6:40pm (UTC)"}


def test_limite_du_compte_met_la_file_en_pause():
    assert cause_de_l_arret(LIMITE) == "machine"
    file, lances, repris = file_avec({"Achat": LIMITE, "Stock": SUCCES})
    file.ajouter(besoin("Achat"))
    file.ajouter(besoin("Stock"))
    file.attendre_fin()
    assert lances == ["Achat"]  # Stock ne demarre pas : il planterait et archiverait Achat
    assert statuts(file) == [("Achat", "arrete (machine)"), ("Stock", "en attente")]
    conseil_affiche = fa.conseil(file.raison_pause)
    assert "Limite d'utilisation" in conseil_affiche and "6:40pm (UTC)" in conseil_affiche
    file.reprendre()
    file.attendre_fin()
    assert repris == ["run-Achat"] and statuts(file)[1] == ("Stock", "termine")


def test_erreur_du_projet_reste_du_projet():
    # une erreur ordinaire du code genere ne doit pas etre prise pour une limite
    assert cause_de_l_arret({"succes": False, "etape": "developer",
                             "erreur": "AssertionError : la page affiche 3 elements, limite attendue 2"}) == "projet"
