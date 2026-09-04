# AutoDev — MVP 3 Agents

Pipeline automatisé qui génère un backend FastAPI complet à partir d'un besoin utilisateur, via 3 agents IA orchestrés.

## Architecture
Formulaire utilisateur (Gradio)
→ Product Owner Agent (Qwen3 via Ollama)
→ Developer Agent (Claude Code + FastAPI)
→ QA Agent (Pytest + coverage.py)
↳ boucle de correction (max 3 tentatives)
→ Livrables finaux

## Installation

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
ollama pull qwen3
```
## Lancer la base de données PostgreSQL (via Docker)

Se placer dans le dossier du backend genere :

    cd output/backend

Puis lancer la base de donnees. Utiliser la commande correspondant a votre version de Docker :

**Docker recent (Docker Desktop, Docker Engine 20.10+) :**

    docker compose up -d db

**Anciennes installations (docker-compose en script Python separe) :**

    docker-compose up -d db

Pour savoir laquelle utiliser, tester d'abord :

    docker compose version

Si cette commande echoue ("commande inconnue"), utiliser `docker-compose` (avec le tiret) a la place.

### Verifier que la base tourne

    docker ps

Un conteneur nomme `backend-db-1` (ou similaire) doit apparaitre, avec le port 5432 ouvert.
### Verifier que la base tourne

    docker ps

Un conteneur nomme `backend-db-1` (ou similaire) doit apparaitre, avec le port 5432 ouvert.

## Lancer le formulaire

```bash
python -m src.agent_form.app
```

## Lancer les tests

```bash
pytest --cov=src --cov-report=term-missing
```

## Lancer le pipeline complet

```python
from src.common.schemas import BesoinUtilisateur
from src.orchestrator import executer_pipeline

besoin = BesoinUtilisateur(
    titre_projet="...",
    description="...",
    utilisateurs_cibles="...",
    fonctionnalites_cles=["..."],
)
resultat = executer_pipeline(besoin)
```