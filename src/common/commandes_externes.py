"""Commandes externes appelees par le backend genere (ex : claude) et regles de securite.

Trouve sur le chatbot Assistant equipe : le backend appelait `claude -p`, mais
1. l'image Docker n'installait pas Claude Code (commande absente : toute question en 503) ;
2. `--tools ""` seul laissait les connecteurs du compte Claude (ex : Claude Docs)
   accessibles a tous les utilisateurs du chatbot ; il faut aussi `--strict-mcp-config`.
Ni les tests unitaires (appel simule) ni les scenarios E2E ne l'avaient vu.
"""
import re
from pathlib import Path

# Commandes que le backend peut lancer et qu'il faut alors installer dans son image
COMMANDES_CONNUES = {"claude", "git", "ffmpeg", "pandoc", "tesseract", "libreoffice", "soffice", "node", "npx"}
# Une liste qui commence par le nom de la commande : ["claude", "-p", ...] ou ("git", ...)
_MOTIF_COMMANDE = re.compile(r"""[\[(]\s*["']([a-z][\w.-]*)["']\s*[,\])]""")
OPTIONS_INTERDITES = ("--allowedTools", "--allowed-tools", "--dangerously-skip-permissions")


def _fichiers_du_backend(dossier_backend) -> list[Path]:
    dossier = Path(dossier_backend)
    if not dossier.is_dir():
        return []
    return [f for f in dossier.rglob("*.py")
            if "tests" not in f.relative_to(dossier).parts and ".venv" not in f.parts]


def commandes_utilisees(dossier_backend) -> set[str]:
    """Commandes connues lancees par le code du backend (hors tests)."""
    trouvees = set()
    for fichier in _fichiers_du_backend(dossier_backend):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        trouvees |= {nom for nom in _MOTIF_COMMANDE.findall(texte) if nom in COMMANDES_CONNUES}
    return trouvees


def problemes_securite_claude(dossier_backend) -> list[str]:
    """Le backend appelle claude : il ne doit donner a l'IA ni outil ni connecteur du compte."""
    problemes = []
    for fichier in _fichiers_du_backend(dossier_backend):
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        if "claude" not in _MOTIF_COMMANDE.findall(texte):
            continue
        manque = [o for o in ("--tools", "--strict-mcp-config") if o not in texte]
        interdites = [o for o in OPTIONS_INTERDITES if o in texte]
        if manque or interdites:
            problemes.append(
                f"Securite : {fichier.as_posix()} appelle claude sans bloquer outils et connecteurs"
                + (f" (manque : {', '.join(manque)})" if manque else "")
                + (f" (interdit : {', '.join(interdites)})" if interdites else "")
                + ". Appeler claude -p avec --tools \"\" et --strict-mcp-config, sans --allowedTools ni "
                "--dangerously-skip-permissions : sinon un utilisateur peut faire lire des fichiers (.env) "
                "ou utiliser les connecteurs du compte Claude.")
    return problemes
