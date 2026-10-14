# AutoDev — génération d'applications par agents IA

AutoDev transforme une demande écrite dans un formulaire en une application web complète : backend FastAPI, frontend HTML/CSS/JavaScript, tests et configuration Docker. Le travail est fait par une chaîne d'agents spécialisés, orchestrés par LangGraph, qui se vérifient et se corrigent entre eux.

## Sommaire

- [Le pipeline](#le-pipeline)
- [Architecture du code](#architecture-du-code)
- [Prérequis](#prérequis)
- [Configuration (.env)](#configuration-env)
- [Lancer AutoDev avec Docker](#lancer-autodev-avec-docker)
- [Utiliser l'interface](#utiliser-linterface)
- [L'application générée](#lapplication-générée)
- [Tests](#tests)
- [Lancer sans Docker](#lancer-sans-docker)
- [Bonnes pratiques et limites connues](#bonnes-pratiques-et-limites-connues)

## Le pipeline

Chaque run passe par 9 étapes. L'orchestrateur transmet le travail d'un agent au suivant dans un état partagé et le sauvegarde après chaque étape.

| # | Étape | Technologie | Rôle |
|---|---|---|---|
| 1 | Product Owner | Ollama (qwen3, local) | Écrit les user stories, leurs priorités (MoSCoW) et leurs critères d'acceptation |
| 2 | Architect | Claude Code | Choisit la stack, découpe l'application en modules et écrit le contrat d'API, sans écrire de code |
| 3 | Test Agent | Claude Code | Écrit le plan de test et les tests pytest **avant** le code (TDD) ; seul agent autorisé à corriger un test |
| 4 | Developer | Claude Code | Écrit le backend FastAPI pour faire passer les tests, sans pouvoir les modifier |
| 5 | QA Backend | pytest + coverage (sans IA) | Lance les tests et mesure la couverture |
| 6 | Frontend | Claude Code | Écrit l'interface HTML/CSS/JavaScript qui appelle l'API |
| 7 | QA Frontend | Contrôles statiques (sans IA) | Vérifie les fichiers et la syntaxe JavaScript |
| 8 | Dockerization | Claude Code (lecture/écriture seulement) | Écrit `Dockerfile`, `docker-compose.yml` et `.env` pour backend + frontend + base |
| 9 | Validation Docker | Docker (sans IA) | Construit et démarre l'application, vérifie que les services répondent et ne tournent pas en root |

**Boucles de correction** (`MAX_TENTATIVES`, 3 par défaut) :

```
QA Backend        --échec-->  Developer       (puis Test Agent si les tests sont en cause)
QA Frontend       --échec-->  Frontend
Validation Docker --échec-->  Dockerization
```

Une erreur de la machine (port occupé, Docker arrêté) n'est pas envoyée à un agent : le run s'arrête avec un message qui dit quoi corriger, puis on clique sur **Relancer**.

Le graphe peut être affiché avec `make graphe`. Le détail des étapes est dans [`docs/pipeline.md`](docs/pipeline.md).

## Architecture du code

Organisation MVC :

- **Vue** : `src/agent_form/app.py`, l'interface Gradio (formulaire, suivi du run, liste des runs).
- **Contrôleur** : `src/agent_orchestrateur/`, l'orchestrateur LangGraph.
  - `graphe.py` : les étapes et les flèches du graphe ;
  - `noeuds.py` : l'appel de chaque agent ;
  - `routage.py` : le choix de l'étape suivante (suite, correction, arrêt) ;
  - `etat.py` : l'état partagé ;
  - `sauvegarde.py` : la sauvegarde SQLite après chaque étape ;
  - `orchestrateur.py` : lancement, reprise, rejeu, archivage, historique des runs.
- **Modèle** : les agents, un dossier chacun dans `src/` : `agent_po`, `agent_architect`, `agent_test`, `agent_dev`, `agent_qa`, `agent_frontend`, `agent_dockerization`, `agent_validation_docker`.
- **Commun** : `src/common/schemas.py`, les formats échangés entre agents (Pydantic).

```
AutoDev/
├── src/                  code d'AutoDev (Vue, Contrôleur, agents)
├── tests/                tests automatiques d'AutoDev (IA simulée)
├── docs/                 documentation du pipeline
├── output/               application générée par le dernier run (non versionné)
├── archives/             applications des runs précédents (non versionné)
├── checkpoints/          sauvegardes des runs, pipeline.sqlite (non versionné)
├── logs/                 journal pipeline.log
├── docker-compose.yml             lancement d'AutoDev
├── docker-compose.validation.yml  accès au Docker du PC pour la Validation Docker
└── .env.example          modèle de configuration
```

## Prérequis

- **Docker Desktop** (ou Docker Engine avec Compose v2).
- **Ollama** sur la machine hôte, avec le modèle du Product Owner :
  ```bash
  ollama pull qwen3
  ```
- **Un compte Claude** (session Claude Code) ou une clé API Anthropic.

## Configuration (.env)

```bash
cp .env.example .env
```

Puis remplir `.env`. Ce fichier contient des secrets : il n'est jamais versionné (vérifié par l'intégration continue).

| Variable | Rôle |
|---|---|
| `GRADIO_AUTH_USER`, `GRADIO_AUTH_PASSWORD` | Identifiants de connexion au formulaire (obligatoires) |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Adresse et modèle d'Ollama pour le Product Owner |
| `ANTHROPIC_API_KEY` ou `CLAUDE_CONFIG_DIR` | Compte utilisé par les agents Claude Code (clé API, ou session dédiée) |
| `DOCKER_VALIDATION_HOST` | Hôte où joindre l'application pendant la Validation Docker |
| `DOCKER_BUILD_TIMEOUT`, `DOCKER_DEMARRAGE_TIMEOUT` | Délais de la Validation Docker (secondes) |
| `CHECKPOINT_DB` | Fichier de sauvegarde des runs |
| `ESSAIS_AGENT`, `ATTENTE_RELANCE` | Relance automatique d'un agent après une erreur passagère |

Après une modification de `.env`, recréer le conteneur : `docker compose up -d --force-recreate`.

## Lancer AutoDev avec Docker

```bash
docker compose -f docker-compose.yml -f docker-compose.validation.yml up -d --build
```

Le second fichier donne au conteneur l'accès au Docker du PC. Sans lui, la Validation Docker affiche « NON EFFECTUEE ».

Première fois seulement, connecter Claude Code dans le conteneur :

```bash
docker compose exec -it autodev claude
# puis taper /login et suivre les instructions
```

Vérifier la connexion :

```bash
docker compose exec autodev claude -p "reponds juste OK"
```

Le formulaire est sur **http://localhost:7860**.

Raccourcis : `make docker-build`, `make docker-up`, `make docker-logs`, `make docker-down`.

## Utiliser l'interface

L'interface a trois onglets :

1. **Nouveau projet** : décrire le projet (titre, description, utilisateurs cibles, fonctionnalités clés, interface) puis **Lancer le pipeline**. Un texte vide, trop long, ou qui tente de donner des ordres à l'IA est refusé avant tout appel à l'IA.
2. **Run en cours** : statut, chronomètre, barre des 9 étapes, une carte par agent, et le détail (user stories, architecture, plan de test, erreurs).
3. **Runs existants** : la liste des runs. Un clic affiche le résultat d'un run. Le bouton **Relancer** :
   - reprend un run planté ou interrompu là où il s'est arrêté ;
   - ou repart d'une étape choisie après la modification d'un agent.

   Les étapes déjà réussies ne sont ni refaites ni repayées.

Chaque run a un identifiant unique (titre + date + heure + 4 caractères), écrit dans `output/.id_run` et dans `logs/pipeline.log`.

## L'application générée

L'application du dernier run est dans `output/` :

```
output/
├── backend/        API FastAPI, tests, PLAN_DE_TEST.md, README.md
├── frontend/       pages HTML, CSS, JavaScript
├── docker-compose.yml
├── .env            mots de passe générés (non versionné)
└── .id_run
```

Pour la lancer :

```bash
cd output
docker compose up -d
cd ..
```

- Frontend : http://localhost:8080
- Documentation de l'API : http://localhost:8000/docs

Chaque application a son propre nom de projet Docker Compose (`name:` = identifiant du run), donc ses propres conteneurs et volumes.

Au lancement d'un nouveau run, l'ancien contenu de `output/` est déplacé dans `archives/<identifiant du run>/`.

Pour arrêter l'application : `docker compose down` dans `output/` (ajouter `-v` pour effacer aussi sa base de données).

## Tests

Les tests automatiques d'AutoDev simulent l'IA : ils sont rapides, gratuits et reproductibles.

```bash
docker compose run --rm --build autodev python -m pytest -q
```

Avec la couverture, hors Docker : `make test`.

L'intégration continue (GitHub Actions, `.github/workflows/ci.yml`) s'exécute à chaque push :

- les tests et la couverture ;
- l'absence de fichier `.env` versionné et de secret dans l'historique Git (gitleaks) ;
- la construction de l'image Docker d'AutoDev.

## Lancer sans Docker

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows (PowerShell)
source .venv/bin/activate         # Linux / macOS
pip install -r requirements.txt
python -m src.agent_form.app      # ou : make run
```

Utilisation directe en Python :

```python
from src.common.schemas import BesoinUtilisateur
from src.agent_orchestrateur.orchestrateur import executer_pipeline

besoin = BesoinUtilisateur(
    titre_projet="Gestion de taches",
    description="Application pour gerer ses taches personnelles",
    utilisateurs_cibles="Particuliers",
    fonctionnalites_cles=["creer un compte", "se connecter", "creer une tache"],
)
resultat = executer_pipeline(besoin)
```

## Bonnes pratiques et limites connues

- **Ne jamais reconstruire AutoDev (`up --build`) pendant un run** : le run est coupé. Si cela arrive, recharger la page puis cliquer sur **Relancer**.
- **Arrêter l'application générée** (`docker compose down` dans `output/`) avant un nouveau run : sinon les ports 8000 et 8080 sont occupés.
- **Windows** : ne laisser ni explorateur ni terminal ouvert dans `output/` au lancement d'un run, sinon l'archivage échoue.
- **Product Owner lent sans carte graphique** : de quelques dizaines de secondes à plus de 10 minutes selon le poste. Au-delà du délai, le run s'arrête (PLANTAGE) : relancer Ollama si besoin, puis **Relancer**.
- Seul le dernier run (celui de `output/`) peut être rejoué à partir d'une étape.
- Pour effacer l'historique des runs : `make nettoyer-sauvegardes`.
