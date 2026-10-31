import logging
import os
from pathlib import Path

_DOSSIER_LOGS = Path("logs")
_FICHIER_LOG = _DOSSIER_LOGS / "pipeline.log"


def configurer_logging(nom: str = "autodev") -> logging.Logger:
    """Renvoie un logger pret a l'emploi, configure une seule fois meme si
    cette fonction est appelee plusieurs fois — evite les lignes de log
    dupliquees si plusieurs modules l'appellent.
    """
    logger = logging.getLogger(nom)
    if logger.handlers:
        return logger

    niveau = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(niveau)

    formatteur = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler_console = logging.StreamHandler()
    handler_console.setFormatter(formatteur)
    logger.addHandler(handler_console)

    # LOG_FICHIER vide : console seulement (les tests automatiques n'ecrivent pas dans le vrai journal)
    fichier = Path(os.environ["LOG_FICHIER"]) if "LOG_FICHIER" in os.environ else _FICHIER_LOG
    if str(fichier) not in ("", "."):
        try:
            fichier.parent.mkdir(parents=True, exist_ok=True)
            handler_fichier = logging.FileHandler(fichier, encoding="utf-8")
            handler_fichier.setFormatter(formatteur)
            logger.addHandler(handler_fichier)
        except OSError:
            logger.warning("Impossible d'ecrire dans %s, logs console uniquement.", fichier)

    logger.propagate = False
    return logger
