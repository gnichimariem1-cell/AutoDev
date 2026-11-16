# Règles de l'Architect

- **Ne genere AUCUN code : seulement la stack, les modules et une justification courte.**
  Pourquoi : le code est écrit plus tard par le Developer, qui doit faire passer les tests du Test Agent.

- **Les modules du frontend commencent par "frontend/" (ex : "frontend/index.html - accueil").**
  Pourquoi : le Frontend Agent ne reprend que les modules qui commencent par « frontend/ » ;
  les autres concernent le backend.

- **Un module par responsabilite (ex : authentification, chaque ressource metier, appel a l'IA, controle des requetes SQL).**
  Pourquoi : chaque règle métier a alors un endroit précis où être codée et testée.
  Origine : GenieLab Hub, le module sql_guard séparé a permis de tester chaque refus de requête.
