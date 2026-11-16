# Règles des agents d'AutoDev

Chaque agent IA d'AutoDev a ici **son fichier de règles**. Au moment de travailler, l'agent lit son
fichier et l'ajoute à sa consigne (module `src/common/regles.py`). Modifier une règle, c'est donc
modifier ce texte : aucun code Python à changer.

| Fichier | Agent | Rôle |
| --- | --- | --- |
| `product_owner.md` | Product Owner | User stories, priorités, critères d'acceptation |
| `architect.md` | Architect | Stack, modules, sans écrire de code |
| `test_agent.md` | Test Agent | Plan de test et tests écrits avant le code (TDD) |
| `developer.md` | Developer | Backend qui fait passer les tests |
| `frontend.md` | Frontend | Pages HTML, CSS et JavaScript |
| `dockerization.md` | Dockerization | Dockerfile, docker-compose, .env |
| `agent_e2e.md` | Agent E2E | Scénarios de bout en bout (API et navigateur) |

## Format d'une règle

- **La règle**, en une phrase que l'agent peut appliquer.
  Pourquoi : la raison, pour que l'agent (et le lecteur) comprenne.
  Origine : le bug ou le run qui l'a fait naître, s'il y en a un.
  Contrôle : ce qu'AutoDev vérifie lui-même, sans IA, s'il y a un contrôle.

Le texte entre accolades, comme `{dossier_frontend}`, est remplacé par le vrai dossier au moment du run.

## Ajouter une règle

1. Écrire la règle dans le fichier de l'agent, avec son « Pourquoi » et son « Origine ».
2. Si elle est importante, ajouter un test qui vérifie qu'elle arrive bien dans la consigne
   (voir `tests/test_regles.py`).
3. Lancer les tests : `docker compose run --rm autodev python -m pytest -q`.

Les tests vérifient que chaque agent a son fichier et le reçoit dans sa consigne : une règle ne peut
pas se perdre sans qu'un test échoue.
