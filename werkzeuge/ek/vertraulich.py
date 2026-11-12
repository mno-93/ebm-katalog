"""Prüft, ob vertrauliche Inhalte ins Repository geraten sind.

Eingebaute Muster (verraten nichts über das Projekt): lokale Pfade, Ordner außerhalb des Repositorys,
Schlüssel und Token. Projektbezogene Muster gehören selbst nicht ins Repository: Umgebungsvariable
VERTRAULICH_MUSTER (im Workflow aus einer Repository-Variable) oder die von Git ignorierte Datei
`.vertraulich-muster` — ein regulärer Ausdruck je Zeile, ohne Groß-/Kleinschreibung, # für Kommentare.
Geprüft werden alle Dateien, die Git verfolgt oder die zum Commit vorgemerkt sind.
"""
import os
import re
import subprocess

from .grundlagen import WURZEL

EINGEBAUT = [
    ('lokaler Pfad', re.compile(r'/Users/[^/\s]+/|[A-Z]:\\Users\\')),
    ('Ordner außerhalb des Repositorys', re.compile(r'\.\./\.\./\.\./|\b[0-9]_[A-Z][a-z]+(?:_[A-Za-z]+)*/')),
    ('privater Schlüssel', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('Zugangstoken', re.compile(r'\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9]{20,}')),
]
AUSGENOMMEN = [re.compile(r'^werkzeuge/ek/vertraulich\.py$')]
# Abzüge und Quellen sind veröffentlichte Inhalte Dritter: nur eingebaute Muster
NUR_EINGEBAUT = [re.compile(r'^(rohdaten|quellen|tests/fixtures)/')]


def _projektmuster():
    text = os.environ.get('VERTRAULICH_MUSTER')
    if text is None:
        datei = WURZEL / '.vertraulich-muster'
        text = datei.read_text(encoding='utf-8') if datei.exists() else ''
    return [('Projektmuster', re.compile(z.strip(), re.I)) for z in text.splitlines() if z.strip() and not z.strip().startswith('#')]


def pruefen():
    muster = EINGEBAUT + _projektmuster()
    dateien = subprocess.run(['git', 'ls-files', '--cached'], cwd=WURZEL, capture_output=True, text=True,
                             check=True).stdout.split('\n')
    funde = 0
    for d in filter(None, dateien):
        if any(a.search(d) for a in AUSGENOMMEN) or not (WURZEL / d).is_file():
            continue
        try:
            inhalt = (WURZEL / d).read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        geltend = EINGEBAUT if any(a.search(d) for a in NUR_EINGEBAUT) else muster
        for nr, zeile in enumerate(inhalt.splitlines(), 1):
            for art, m in geltend:
                if m.search(zeile):
                    funde += 1
                    print(f'{d}:{nr}: {art}')
    projekt = len(muster) - len(EINGEBAUT)
    print(f'Vertraulichkeit: {len([d for d in dateien if d])} Dateien, {projekt} Projektmuster — '
          + ('keine Funde' if not funde else f'{funde} Funde'))
    return 1 if funde else 0
