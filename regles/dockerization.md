# Règles de la Dockerization

- **Aucun volume qui monte un dossier du projet (ex : ./frontend:/usr/share/nginx/html ou ./backend:/app) : le code et les pages sont COPIES dans les images (COPY dans un Dockerfile). Seuls les volumes nommes (ex : db_data) sont autorises.**
  Pourquoi : l'application est aussi lancée par un Docker qui ne voit pas ces dossiers (conteneur
  AutoDev, autre poste) : un dossier monté y serait vide et nginx répondrait 404.
  Origine : Cabinet médical, toutes les pages répondaient 404 pendant les Tests E2E.
  Contrôle : la Validation Docker refuse un dossier monté et exige une page d'accueil en 200.

- **Ecris aussi {dossier_frontend}/.dockerignore (au moins Dockerfile et .dockerignore).**
  Pourquoi : sinon nginx servirait le Dockerfile comme une page du site.

- **Adresses e-mail par defaut (compte administrateur, comptes de demonstration) : un domaine normal (ex : cabinet-medical.fr), jamais .local, .localhost, .test, .invalid ni .example.**
  Pourquoi : la validation des e-mails (EmailStr) les refuse et l'application planterait.
  Origine : Cabinet médical, ADMIN_EMAIL en .local, connexion en 500. Trouvé par l'Agent E2E.

- **Si le backend lance une commande externe (ex : subprocess avec ["claude", ...] ou une variable claude_path), installe-la dans le Dockerfile du backend AVANT l'instruction USER. Pour claude (Claude Code) : apt-get install nodejs npm, puis npm install -g @anthropic-ai/claude-code ; ENV CLAUDE_CONFIG_DIR=/home/app/.claude et DISABLE_AUTOUPDATER=1 ; un volume nomme monte sur /home/app/.claude garde la connexion (faite une fois avec docker compose exec -it app claude, puis /login) ; aucune cle API.**
  Pourquoi : sans la commande dans l'image, chaque question au modèle renvoie une erreur 503.
  Origine : Assistant d'équipe, Claude Code absent de l'image. Trouvé en test manuel.
  Contrôle : la Validation Docker vérifie que la commande existe dans l'image (command -v).

- **L'application tourne avec un utilisateur non-root (instruction USER apres le dernier FROM).**
  Contrôle : la Validation Docker refuse un Dockerfile exécuté en root.
