# MKV Processor

Outil polyvalent pour le traitement de fichiers MKV permettant de :
- Sélectionner et conserver les pistes audio de votre choix
- Gérer les sous-titres (conservation ou suppression)
- Optimiser la taille des fichiers

## Fonctionnalités

- Sélection multiple des pistes audio via cases à cocher
- Option pour conserver ou exclure les sous-titres
- Traitement parallèle optimisé selon les ressources système
- Affichage détaillé de l'espace disque économisé
- Interface graphique intuitive
- Gestion des erreurs robuste

## Prérequis

- Python 3.6+
- MKVToolNix (mkvmerge)
- Les dépendances Python seront installées automatiquement

## Utilisation

1. Ouvrez PowerShell
2. Naviguez vers le dossier du script
3. Installez les dépendances : `pip install -r requirements.txt`
4. Lancez le script : `AudioSubManager.py`
5. Sélectionnez le dossier contenant vos fichiers MKV
6. Choisissez les pistes audio à conserver (plusieurs sélections possibles)
7. Décidez si vous souhaitez conserver des sous-titres

Note : Les fichiers traités seront placés dans un sous-dossier "processed", les originaux sont conservés.

## Résultats

À la fin du traitement, un résumé détaillé affiche :
- Le nombre de fichiers traités avec succès
- Le temps total de traitement
- L'espace disque économisé
