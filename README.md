# AudioSubManager

## Description

AudioSubManager est un outil graphique pour Windows permettant de traiter automatiquement des fichiers MKV :
- Sélection des pistes audio et sous-titres à conserver (toutes langues supportées)
- Suppression des pistes non désirées
- Création d'une version allégée de vos vidéos dans un sous-dossier `output`
- Utilisation intelligente des ressources de votre PC (CPU, RAM, GPU détecté)
- Interface simple, moderne et adaptée à tous les usages

## Prérequis

- **Python 3.6+** installé sur votre machine
- **MKVToolNix** (notamment l'outil `mkvmerge`) installé ([télécharger ici](https://mkvtoolnix.download/downloads.html#windows))
- Les dépendances Python sont installées automatiquement au premier lancement

## Installation

1. Téléchargez ou clonez ce dépôt dans un dossier de votre choix
2. Placez vos fichiers `.mkv` à traiter dans un dossier dédié
3. Lancez le script avec :
   ```bash
   python AudioSubManager.py
   ```

## Utilisation pas à pas

1. **Sélection du dossier** : Choisissez le dossier contenant vos fichiers MKV
2. **Résumé de la configuration** : Une fenêtre affiche les ressources de votre PC (CPU, RAM, GPU)
3. **Sélection des pistes audio** : Cochez les pistes audio à conserver (toutes langues affichées)
4. **Sélection des sous-titres** : Cochez les sous-titres à conserver (toutes langues affichées)
5. **Traitement** : Le script traite tous les fichiers du dossier, crée les nouveaux fichiers dans le sous-dossier `output`, et affiche un résumé (nombre de fichiers, temps, espace économisé)

## Fonctionnement

- **Traitement par lots** : tous les fichiers `.mkv` du dossier sont traités en une seule fois
- **Aucune modification des fichiers originaux** : les fichiers traités sont placés dans `output`
- **Utilisation des ressources** : le script adapte automatiquement le nombre de processus à la puissance de votre PC, sans le saturer
- **Reprise automatique** : à chaque lancement, tous les fichiers sont retraités (pas de cache bloquant)
- **Interface intuitive** : possibilité de revenir en arrière à chaque étape, annuler à tout moment

## FAQ

**Q : Est-ce que mes fichiers originaux sont modifiés ?**  
R : Non, ils restent intacts. Les fichiers modifiés sont dans le sous-dossier `output`.

**Q : Puis-je traiter des fichiers dans n'importe quelle langue ?**  
R : Oui, toutes les langues audio et sous-titres sont affichées et sélectionnables.

**Q : Le script utilise-t-il mon GPU ?**  
R : Le GPU est détecté et affiché, mais n'est utilisé que si une étape de ré-encodage est ajoutée (non activée par défaut).

**Q : Que faire si un fichier n'est pas traité ?**  
R : Vérifiez qu'il a bien l'extension `.mkv` et qu'il n'est pas corrompu. Tous les fichiers sont retraités à chaque lancement.

**Q : Comment obtenir plus d'informations sur le traitement ?**  
R : Consultez le fichier `mkv_processor.log` généré dans le dossier du script.

## Support

Pour toute question ou suggestion, ouvrez une issue sur le dépôt ou contactez le développeur.
