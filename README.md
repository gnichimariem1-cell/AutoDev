# AutoDev — MVP Multi-Agents

Pipeline automatisé qui génère un backend FastAPI **et** un frontend web complets à partir d'un besoin utilisateur, via des agents IA orchestrés.

## Architecture
Formulaire utilisateur (Gradio)
→ Product Owner Agent (Qwen3 via Ollama)
→ Developer Agent (Claude Code + FastAPI)
→ QA Agent Backend (Pytest + coverage.py)
  ↳ boucle de correction (max 3 tentatives)
→ Frontend Agent (Claude Code + HTML/CSS/JS vanilla, consomme l'API backend)
→ QA Agent Frontend (verification index.html + validite syntaxique JS)
  ↳ boucle de correction (max 3 tentatives)
→ Livrables finaux (output/backend/ et output/frontend/)

## Installation

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
ollama pull qwen3
```

## Lancer avec Docker

Le pipeline lui-meme (formulaire Gradio + les 3 agents) peut tourner dans un conteneur.

```bash
cp .env.example .env
# completer .env : ANTHROPIC_API_KEY (agent Developer) et, si besoin, OLLAMA_URL
docker compose up -d --build
```

Le formulaire est alors accessible sur http://localhost:7860.

Details :
- **Ollama** (agent Product Owner) doit tourner sur la machine hote (`ollama serve`, modele
  recupere via `ollama pull qwen3`). Le conteneur le joint via `OLLAMA_URL` (par defaut
  `http://host.docker.internal:11434/api/generate`, deja configure dans `docker-compose.yml`).
- **Claude Code** (agent Developer) tourne dans le conteneur en mode non-interactif : fournir
  `ANTHROPIC_API_KEY` dans `.env`, ou monter une session deja authentifiee sur l'hote en
  decommentant les volumes `~/.claude` / `~/.claude.json` dans `docker-compose.yml`.
- Les backends generes sont ecrits dans `./output`, monte en volume pour persister sur l'hote.
- Raccourcis Makefile : `make docker-build`, `make docker-up`, `make docker-logs`, `make docker-down`.

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