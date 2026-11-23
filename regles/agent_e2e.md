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
- **Quand une etape prouve un resultat (message, ligne du tableau, classement, erreur), passe cet element en second argument : etape("stock_insuffisant", page.get_by_text("Stock insuffisant")). Il est amene a l'ecran avant la capture : l'image doit montrer ce que le nom annonce, pas le haut de la page.**
  Pourquoi : on suit le scénario image par image, sans regarder la vidéo ; en cas d'échec, on voit
  la dernière étape réussie.
  Origine : GenieLab Hub, une seule capture (la fin) par scénario.

- **N'affiche jamais un mot de passe dans un message d'assertion.**
- **Chaque user story a au moins un scenario d'interface, en plus des scenarios API ; plusieurs user stories peuvent partager une page, pas un scenario.**
  Pourquoi : une règle par page laisse des user stories vérifiées seulement par l'API, sans capture.
  Origine : GenieLab Hub, 9 scénarios d'interface pour 23 user stories.

- **Chaque refus est verifie deux fois : dans l'interface (bouton ou menu absent, page refusee) et par l'API (reponse 403 ou 404). Pour une ressource d'un autre role ou d'un autre perimetre, teste aussi l'ouverture par URL directe.**
  Pourquoi : un menu qui cache un lien ne protège rien si l'API reste ouverte.

- **Pour chaque formulaire, un scenario soumet les champs obligatoires vides et verifie le message d'erreur.**
  Pourquoi : les refus de saisie sont rarement testés et souvent absents.

- **Les donnees de test utilisent des noms accentues (ex : « Élise Marchand », « Anaïs Côté ») ; verifie qu'ils restent intacts apres rechargement de la page, et dans les exports s'il y en a.**
  Pourquoi : les accents cassés ne se voient qu'à l'écran ou dans un fichier exporté.
  Origine : plan manuel, STK-05.

- **Aucun scenario sans assertion sur le resultat attendu ; un scenario qui ne fait que naviguer ne compte pas.**

- **En tete du fichier de scenarios, ecris en commentaire un tableau de couverture : user story → scenarios API et interface.**
  Pourquoi : on voit d'un coup d'œil quelle user story n'est pas couverte.