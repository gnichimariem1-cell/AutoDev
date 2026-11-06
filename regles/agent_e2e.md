# Règles de l'Agent E2E

- **`pytest.skip` interdit (une variable manquante est une erreur, pas une raison d'ignorer), sauf si une regle depend vraiment de l'heure ou du jour (ex : moins de 24 h avant un rendez-vous) et qu'aucune donnee ne permet de la tester maintenant : donne alors la raison exacte.**
  Pourquoi : un scénario ignoré n'a rien vérifié ; il est affiché « non vérifié ».
  Origine : Cabinet médical, E15 (règle des 24 h) s'ignorait le vendredi après-midi.

- **httpx : un client deja utilise ne peut pas etre rouvert avec `with` (RuntimeError) ; une fonction utilitaire qui connecte un compte renvoie un client deja ouvert, utilise-le sans `with` puis ferme-le avec `.close()`.**
  Origine : Cabinet médical, le scénario E23 plantait sur cette erreur.

- **Utilise les libelles, roles et textes reellement presents dans les pages (get_by_label, get_by_role, get_by_text), apres avoir lu les fichiers HTML du frontend.**
  Pourquoi : un scénario qui devine un libellé échoue alors que l'application est juste.

- **Chaque regle metier de la demande a au moins un scenario qui verifie le refus (ex : chevauchement, role insuffisant).**
  Pourquoi : c'est là que les applications générées se trompent le plus.

- **Chaque page principale de l'application (connexion, tableau de bord, chaque liste ou formulaire, assistant...) a au moins un scenario d'interface.**
  Pourquoi : seuls les scénarios d'interface donnent une capture et une vidéo ; avec 3 à 6 parcours,
  la plupart des pages n'étaient jamais vues.
  Origine : GenieLab Hub, seulement 5 captures pour toute l'application.

- **Dans chaque scenario d'interface, appelle etape("nom_court") apres chaque action importante : page ouverte, formulaire rempli, apres le clic, resultat affiche (2 a 5 etapes par scenario). Ajoute la fixture etape aux parametres du test : def test_E21_connexion(page: Page, front_url, etape).**
  Pourquoi : on suit le scénario image par image, sans regarder la vidéo ; en cas d'échec, on voit
  la dernière étape réussie.
  Origine : GenieLab Hub, une seule capture (la fin) par scénario.

- **N'affiche jamais un mot de passe dans un message d'assertion.**
