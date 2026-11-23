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
- **Une cle ou un service externe absent (cle API, connecteur non configure) donne une erreur 503 qui nomme ce qui manque (ex : « Assistant indisponible : clé API non configurée ») ; ne remplace jamais ce message par un message generique.**
  Pourquoi : « réessayez plus tard » cache la cause ; l'administrateur attend au lieu de configurer la clé.
  Origine : GenieLab Hub, E16, le message précis est devenu « réessayez plus tard » pendant la correction.

- **Si un test echoue seulement parce qu'une cle ou un service externe manque dans l'environnement, ne modifie pas le code pour le faire passer : le code est juste, c'est la configuration qui manque.**
  Pourquoi : aucune modification du code ne crée une clé ; chaque essai est payé pour rien.
  Origine : GenieLab Hub, E16 et E29, 6 corrections inutiles sur 3 essais.

- **Les messages affiches a l'utilisateur sont ecrits en francais correct, avec les accents.**
  Origine : GenieLab Hub, « cle non configuree », « Demo : evenement ajoute a Outlook ».
  - **Pendant une correction des Tests E2E, n'ajoute aucune nouvelle dependance externe (commande comme claude, service, paquet systeme).**
  Pourquoi : la Dockerization et la Validation Docker ne sont pas rejouées ; la dépendance manquerait dans l'image.
  Origine : GenieLab Hub, plan B claude -p ajouté pendant la correction d'E16, absent de l'image.