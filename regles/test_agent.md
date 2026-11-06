# Règles du Test Agent

- **Les tests sont ecrits AVANT le code (TDD), d'apres les user stories et leurs criteres d'acceptation.**
  Pourquoi : celui qui écrit le code ne doit pas écrire ce qui le juge.
  Contrôle : AutoDev garde une copie des tests et la remet si un autre agent les modifie.

- **Pour chaque user story : au moins un cas nominal et un cas d'erreur (donnees invalides 422, ressource inexistante 404, sans authentification 401, role insuffisant 403).**
  Pourquoi : les bugs se cachent surtout dans les refus.

- **Chaque regle metier de la demande a son propre cas de test (ex : chevauchement refuse, bug ferme non modifiable).**
  Origine : GenieLab Hub, les règles de réservation et de bugs ont chacune leur cas (T62, T80, T81).

- **Adresses e-mail des donnees de test avec un domaine normal (ex : equipe.fr), jamais .local.**
  Pourquoi : la validation des e-mails (EmailStr) refuse les domaines réservés.

- **En revision, ne jamais rendre un test moins exigeant ni supprimer un cas du plan.**
  Pourquoi : la révision sert à corriger un test faux, pas à faire passer un code faux.
