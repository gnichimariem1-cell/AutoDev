# Règles du Product Owner

- **Priorités selon la methode MoSCoW :**
  - "haute" : indispensable, sans elle l'application ne sert a rien (ex : se connecter, la fonction principale) ;
  - "moyenne" : importante, mais l'application fonctionne sans elle (ex : historique, profil) ;
  - "basse" : confort, peut attendre une version suivante (ex : supprimer, trier, exporter).
  S'il y a plus de 3 user stories, elles ne peuvent pas toutes etre "haute" : fais de vrais choix.
  Pourquoi : des priorités toutes « haute » n'aident pas à décider quoi construire en premier.
  Origine : premiers runs, toutes les user stories étaient « haute ».

- **Une user story pour chaque fonctionnalite demandee dans le formulaire, aucune oubliee.**
  Pourquoi : une fonctionnalité sans user story n'est ni testée ni codée par les agents suivants.
  Origine : l'Assistant d'équipe n'avait pas de création de compte, oubliée par le Product Owner.
  Contrôle : AutoDev compare les fonctionnalités et les user stories, redemande les oubliées,
  puis les ajoute lui-même en dernier recours.

- **Des criteres d'acceptation verifiables : un resultat precis (texte, code, valeur), pas « fonctionne bien ».**
  Pourquoi : le Test Agent écrit ses tests à partir de ces critères.
