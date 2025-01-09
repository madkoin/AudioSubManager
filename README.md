# MKV Processor

Outil pour traiter les fichiers MKV d'anime en conservant l'audio japonais et les sous-titres français.

## Prérequis

- Python 3.6+
- MKVToolNix (mkvmerge)
- Les dépendances Python seront installées automatiquement

## Installation

1. Clonez le repository
2. Installez MKVToolNix
3. Ouvrez PowerShell et exécutez : `pip install -r requirements.txt`
4. Lancez le script : `python anime_mkvtool_vostfr.py`

## Utilisation et Fonctionnalités

- Traitement par lot : traite tous les fichiers MKV d'un dossier en une fois
- Crée un sous-dossier "processed" pour les fichiers traités
- Conserve les fichiers originaux
- Permet la sélection des sous-titres à conserver
- Traitement multiprocessus pour de meilleures performances
