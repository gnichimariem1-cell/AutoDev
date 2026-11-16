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

- **Chaque user story a exactement les 5 champs "id", "titre", "description", "criteres_acceptation" et "priorite" ; "priorite" vaut "haute", "moyenne" ou "basse" (pas « Must », pas « moscow »).**
  Pourquoi : une user story sans priorité est refusée, et tout le run s'arrête au Product Owner.
  Origine : Stock du labo, les 12 user stories sans champ « priorite » (deux runs arrêtés).
  Contrôle : AutoDev comprend les synonymes (priority, moscow, Must, High…) et redemande une fois
  une réponse incomplète en disant ce qui manque.
