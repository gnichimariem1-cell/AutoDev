# Règles du Developer

- **Ne modifie PAS, ne supprime PAS et n'ajoute PAS de fichiers dans le dossier tests/.**
  Pourquoi : les tests appartiennent au Test Agent (TDD).
  Contrôle : AutoDev remet les tests d'origine avant chaque QA et signale toute modification.

- **Adresses e-mail par defaut (compte administrateur, comptes de demonstration) : un domaine normal (ex : cabinet-medical.fr), jamais .local, .localhost, .test, .invalid ni .example.**
  Pourquoi : la validation des e-mails (EmailStr) les refuse et l'application planterait.
  Origine : Cabinet médical, la connexion de la secrétaire répondait 500. Trouvé par l'Agent E2E.

- **Si l'application appelle Claude par la commande claude -p : options --tools "" et --strict-mcp-config (aucun outil ni connecteur du compte), question envoyee sur l'entree standard, delai maximal, erreur 503 claire si la commande echoue ; jamais --allowedTools ni --dangerously-skip-permissions.**
  Pourquoi : sinon un utilisateur peut faire lire des fichiers (.env) au chatbot, ou utiliser les
  connecteurs du compte Claude (ex : Claude Docs).
  Origine : Assistant d'équipe, Claude Docs restait accessible au chatbot. Trouvé en test manuel.
  Contrôle : le QA Backend vérifie l'appel et renvoie l'erreur au Developer.

- **Aucun secret en dur dans le code : mots de passe, cles et adresses de base lus dans les variables d'environnement.**
  Pourquoi : le code part sur GitHub, le .env jamais.
