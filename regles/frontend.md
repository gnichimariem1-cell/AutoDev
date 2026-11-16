# Règles du Frontend

- **Chaque champ de formulaire a un <label for="..."> relie a son id, et chaque bouton un texte visible.**
  Pourquoi : les utilisateurs (et les scénarios de l'Agent E2E, qui cherchent les champs par leur libellé)
  doivent pouvoir trouver chaque élément.

- **Les messages d'erreur et de succes sont visibles dans la page (role="alert" pour une erreur, role="status" pour un succes), jamais seulement dans la console.**
  Pourquoi : un refus de l'API doit être compris par l'utilisateur.

- **Le texte venant de l'API ou d'une IA est affiche comme du texte (textContent), jamais interprete comme du HTML ; pas de Markdown brut affiche.**
  Pourquoi : sécurité (injection de HTML) et lisibilité.
  Origine : Assistant AutoDev, les réponses s'affichaient en Markdown brut.

- **L'adresse de l'API est definie a un seul endroit du JavaScript.**
  Pourquoi : elle change selon l'endroit où l'application est lancée.

- **Ne cree ni Dockerfile ni configuration de serveur : c'est le travail de la Dockerization.**
