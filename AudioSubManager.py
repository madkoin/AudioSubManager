"""
MKV Processor - Outil de traitement de fichiers MKV
=================================================

Ce script permet de traiter des fichiers MKV en:
- Conservant uniquement les pistes audio et sous-titres sélectionnés par l'utilisateur
- Supprimant les pistes non désirées
- Fonctionne sur toutes les langues
- Utilise les ressources de la machine de façon sûre et adaptée

Dépendances: mkvmerge (MKVToolNix), Python 3.6+
"""

# Import des modules standards et externes (à ne faire qu'ici, pas dans les fonctions)
import os
import subprocess
import json
import sys
import multiprocessing
from functools import partial
import time
import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel, Listbox, Button, SINGLE, END, Label
import psutil
import platform
from typing import List, Dict, Tuple, Optional
import logging

# Configuration globale du script
CONFIG = {
    'MIN_PROCESSES': 2,  # Nombre minimal de processus pour le traitement parallèle
    'MAX_PROCESSES': 8,  # Nombre maximal de processus (pour éviter de saturer la machine)
    'MEMORY_BUFFER_PERCENTAGE': 0.2,  # Pourcentage de RAM à laisser libre (sécurité)
    'DEFAULT_LANGUAGES': {
        'audio_source': ['jpn', 'ja'],
        'subtitle_target': ['fre', 'fr']
    }
}

# Configuration du logging (journalisation des événements)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mkv_processor.log'),
        logging.StreamHandler(),
        logging.FileHandler('track_names_debug.log')  # Pour debug des noms de pistes
    ]
)

# Classe d'exception personnalisée pour les erreurs de traitement
class ProcessingError(Exception):
    """Exception personnalisée pour les erreurs de traitement"""
    pass

# Classe pour gérer l'état du traitement (fichiers déjà traités, échecs, etc.)
class ProcessingState:
    """Classe pour gérer l'état du traitement et permettre la reprise"""
    def __init__(self, state_file: str = "processing_state.json"):
        self.state_file = state_file
        self.processed_files = set()
        self.failed_files = {}
        self.load_state()

    def load_state(self):
        """Charge l'état précédent du traitement depuis un fichier JSON"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.processed_files = set(state.get('processed_files', []))
                    self.failed_files = state.get('failed_files', {})
        except Exception as e:
            logging.warning(f"Impossible de charger l'état précédent : {e}")

    def save_state(self):
        """Sauvegarde l'état actuel du traitement dans un fichier JSON"""
        try:
            state = {
                'processed_files': list(self.processed_files),
                'failed_files': self.failed_files
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde de l'état : {e}")

    def mark_as_processed(self, filename: str):
        """Marque un fichier comme traité avec succès"""
        self.processed_files.add(filename)
        if filename in self.failed_files:
            del self.failed_files[filename]
        self.save_state()

    def mark_as_failed(self, filename: str, error: str):
        """Marque un fichier comme échoué avec la raison"""
        self.failed_files[filename] = error
        self.save_state()

    def is_processed(self, filename: str) -> bool:
        """Vérifie si un fichier a déjà été traité"""
        return filename in self.processed_files

    def get_failed_files(self) -> Dict[str, str]:
        """Retourne la liste des fichiers échoués"""
        return self.failed_files

def check_and_install_dependencies():
    """
    Vérifie et installe les dépendances requises.
    """
    required = {
        'psutil': 'psutil>=5.9.0',  # Version minimale recommandée
        'tkinter': 'tk'
    }

    missing = []
    for package, pip_name in required.items():
        try:
            __import__(package)
        except ImportError:
            missing.append(pip_name)

    if missing:
        logging.info("Installation des dépendances manquantes...")
        try:
            # Installation avec --user pour éviter les problèmes de permissions
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", *missing])
            logging.info("Dépendances installées avec succès.")
            
            # Vérification après installation
            for package in required.keys():
                try:
                    __import__(package)
                except ImportError:
                    logging.error(f"Échec de l'installation de {package}")
                    sys.exit(1)
                    
        except subprocess.CalledProcessError as e:
            logging.error(f"Erreur lors de l'installation des dépendances : {e}")
            sys.exit(1)

def find_mkvmerge() -> Optional[str]:
    """
    Trouve le chemin de l'exécutable mkvmerge.

    Returns:
        str|None: Chemin vers mkvmerge.exe ou None si non trouvé
    """
    default_paths = [
        os.path.join(os.environ.get('PROGRAMFILES', ''), 'MKVToolNix', 'mkvmerge.exe'),
        os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'MKVToolNix', 'mkvmerge.exe')
    ]

    for path in default_paths:
        if os.path.exists(path):
            return path

    # Ajout de la détection pour Linux/MacOS
    if platform.system() == "Linux":
        try:
            result = subprocess.run(['which', 'mkvmerge'], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            pass
    elif platform.system() == "Darwin":  # macOS
        try:
            result = subprocess.run(['brew', 'list', 'mkvtoolnix', '--prefix'], capture_output=True, text=True, check=True)
            mkvmerge_path = os.path.join(result.stdout.strip(), 'bin', 'mkvmerge')
            if os.path.exists(mkvmerge_path):
                return mkvmerge_path
        except subprocess.CalledProcessError:
            pass

    # Interface de sélection si non trouvé
    root = tk.Tk()
    root.withdraw()

    return filedialog.askopenfilename(
        title="Sélectionnez l'exécutable mkvmerge.exe",
        filetypes=[("Exécutable", "mkvmerge.exe")]
    )

def get_mkv_tracks(input_path: str, mkvmerge_path: str) -> Optional[Dict]:
    """
    Analyse un fichier MKV pour extraire les informations sur ses pistes.

    Args:
        input_path: Chemin du fichier MKV
        mkvmerge_path: Chemin vers mkvmerge

    Returns:
        dict|None: Informations des pistes ou None si erreur
    """
    try:
        result = subprocess.run(
            [mkvmerge_path, '-J', input_path],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors de l'analyse du fichier : {e}")
        return None

def get_mkv_tracks(input_path, mkvmerge_path):
    """
    Récupère les informations sur les pistes du fichier MKV
    """
    try:
        # Utiliser mkvmerge pour obtenir les informations des pistes
        result = subprocess.run([
            mkvmerge_path, '-J', input_path
        ], capture_output=True, text=True, check=True)
        
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors de l'analyse du fichier : {e}")
        return None

def get_track_language(track: Dict) -> str:
    """
    Récupère la langue d'une piste de manière standardisée.
    
    Args:
        track: Informations de la piste
        
    Returns:
        str: Code de langue standardisé ou 'N/A'
    """
    language = track.get('properties', {}).get('language', 'N/A')
    # Conversion des codes de langue courants
    language_map = {
        'jpn': 'Japonais',
        'ja': 'Japonais',
        'fre': 'Français',
        'fr': 'Français',
        'eng': 'Anglais',
        'en': 'Anglais',
        'ger': 'Allemand',
        'de': 'Allemand',
        'spa': 'Espagnol',
        'es': 'Espagnol',
        'ita': 'Italien',
        'it': 'Italien',
        'por': 'Portugais',
        'pt': 'Portugais',
        'rus': 'Russe',
        'ru': 'Russe',
        'chi': 'Chinois',
        'zh': 'Chinois',
        'kor': 'Coréen',
        'ko': 'Coréen'
    }
    return language_map.get(language.lower(), language.upper())

def safe_track_name(track):
    """
    Corrige l'affichage des noms de pistes audio/sous-titres pour gérer les encodages exotiques.
    Log aussi le nom brut pour debug.
    """
    name = track.get('properties', {}).get('track_name', '')
    if not name:
        return 'Nom non lisible'
    try:
        # Log du nom brut pour debug
        logging.info(f"Nom brut: {repr(name)}")
        if isinstance(name, bytes):
            return name.decode('utf-8')
        try:
            return name.encode('latin1').decode('utf-8')
        except Exception:
            return name
    except Exception:
        return 'Nom non lisible'

def choose_audio_tracks(audio_tracks: List[Dict], first_file: Optional[str] = None) -> Tuple[List[Dict], bool, bool]:
    """
    Interface interactive pour choisir les pistes audio avec des cases à cocher.

    Args:
        audio_tracks: Liste des pistes audio disponibles
        first_file: Nom du premier fichier (optionnel)

    Returns:
        Tuple[List[Dict], bool, bool]: (Liste des pistes audio sélectionnées, Annulation, Retour)
    """
    if not audio_tracks:
        raise ValueError("La liste des pistes audio ne peut pas être vide")

    root = Toplevel()
    root.title("Sélection des pistes audio")
    root.geometry("600x400")
    root.deiconify()
    root.lift()
    root.focus_force()

    if first_file:
        Label(root, text=f"Choisissez les pistes audio pour {first_file} :", font=UNICODE_FONT).pack()
    else:
        Label(root, text="Choisissez les pistes audio à conserver :", font=UNICODE_FONT).pack()

    main_frame = tk.Frame(root)
    main_frame.pack(fill='both', expand=True, padx=10, pady=5)

    canvas = tk.Canvas(main_frame)
    scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    audio_vars = []
    audio_checkboxes = []
    audio_tracks.sort(key=lambda x: get_track_language(x))

    for audio in audio_tracks:
        var = tk.BooleanVar(value=False)
        audio_vars.append((var, audio))
        language = get_track_language(audio)
        display_text = (
            f"Piste {audio['id']} - "
            f"Langue: {language} | "
            f"Codec : {audio.get('codec', 'N/A')}"
        )
        cb = tk.Checkbutton(scrollable_frame, text=display_text, variable=var, font=UNICODE_FONT)
        cb.pack(anchor='w', pady=2)
        audio_checkboxes.append(cb)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    selected_audio = [None]
    canceled = [False]
    back = [False]

    def on_confirm():
        selected = [audio for (var, audio) in audio_vars if var.get()]
        if not selected:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins une piste audio.")
            return
        selected_audio[0] = selected
        root.destroy()

    def on_cancel():
        canceled[0] = True
        root.destroy()

    def on_back():
        back[0] = True
        root.destroy()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    Button(button_frame, text="Confirmer", command=on_confirm, font=UNICODE_FONT).pack(side='left', padx=5)
    Button(button_frame, text="Annuler", command=on_cancel, font=UNICODE_FONT).pack(side='right', padx=5)
    Button(button_frame, text="Retour", command=on_back, font=UNICODE_FONT).pack(side='left', padx=5)

    root.wait_window()

    return selected_audio[0], canceled[0], back[0]

def choose_subtitle(french_subtitles: List[Dict], first_file: Optional[str] = None) -> Tuple[Optional[Dict], bool, bool]:
    """
    Interface interactive pour choisir les sous-titres.

    Args:
        french_subtitles: Liste des sous-titres disponibles
        first_file: Nom du premier fichier (optionnel)

    Returns:
        Tuple[Dict, bool, bool]: (Sous-titre sélectionné, Annulation, Retour)
    """
    if not french_subtitles:
        raise ValueError("La liste des sous-titres ne peut pas être vide")

    root = Toplevel()
    root.title("Sélection des sous-titres")
    root.geometry("600x400")
    root.deiconify()
    root.lift()
    root.focus_force()

    if first_file:
        Label(root, text=f"Choisissez la piste de sous-titres pour {first_file} :", font=UNICODE_FONT).pack()
    else:
        Label(root, text="Choisissez la piste de sous-titres à utiliser :", font=UNICODE_FONT).pack()

    # Frame pour la liste avec scrollbar
    main_frame = tk.Frame(root)
    main_frame.pack(fill='both', expand=True, padx=10, pady=5)

    canvas = tk.Canvas(main_frame)
    scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    # Trier les sous-titres par langue
    french_subtitles.sort(key=lambda x: get_track_language(x))

    # Remplace la Listbox par une version plus large et avec padding
    listbox = Listbox(scrollable_frame, selectmode=SINGLE, font=UNICODE_FONT, width=60, height=15)
    listbox.pack(fill='both', expand=True, padx=20, pady=10)
    for subtitle in french_subtitles:
        language = get_track_language(subtitle)
        display_text = (
            f"Piste {subtitle['id']} - "
            f"Langue: {language}"
        )
        listbox.insert(END, display_text)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    selected_subtitle = [None]
    canceled = [False]
    back = [False]

    def on_select():
        if listbox.curselection():
            selected_idx = listbox.curselection()[0]
            selected_subtitle[0] = french_subtitles[selected_idx]
            root.destroy()

    def on_cancel():
        canceled[0] = True
        root.destroy()

    def on_back():
        back[0] = True
        root.destroy()

    Button(root, text="Sélectionner", command=on_select, font=UNICODE_FONT).pack(side='left', padx=5, pady=5)
    Button(root, text="Annuler", command=on_cancel, font=UNICODE_FONT).pack(side='right', padx=5, pady=5)
    Button(root, text="Retour", command=on_back, font=UNICODE_FONT).pack(side='left', padx=5, pady=5)

    root.wait_window()

    return selected_subtitle[0], canceled[0], back[0]

def choose_subtitles(french_subtitles: List[Dict], first_file: str, selected_main_subtitle: Dict) -> Tuple[List[Dict], bool, bool]:
    """
    Interface interactive pour choisir plusieurs pistes de sous-titres.

    Args:
        french_subtitles: Liste des sous-titres disponibles
        first_file: Nom du premier fichier
        selected_main_subtitle: Sous-titre principal déjà sélectionné

    Returns:
        List[Dict]: Liste des sous-titres sélectionnés
    """
    if not french_subtitles:
        raise ValueError("La liste des sous-titres ne peut pas être vide")

    root = Toplevel()
    root.title(f"Sélection des sous-titres pour {first_file}")
    root.geometry("600x400")
    root.deiconify()
    root.lift()
    root.focus_force()

    Label(root, text="Sélectionnez les pistes de sous-titres à conserver :", font=UNICODE_FONT).pack()

    # Frame pour les cases à cocher avec scrollbar
    main_frame = tk.Frame(root)
    main_frame.pack(fill='both', expand=True, padx=10, pady=5)

    canvas = tk.Canvas(main_frame)
    scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    subtitle_vars = []
    subtitle_checkboxes = []

    # Trier les sous-titres par langue
    french_subtitles.sort(key=lambda x: get_track_language(x))

    for subtitle in french_subtitles:
        if selected_main_subtitle is not None:
            value = subtitle.get('properties', {}).get('track_name') == selected_main_subtitle.get('properties', {}).get('track_name')
        else:
            value = False
        var = tk.BooleanVar(value=value)
        subtitle_vars.append((var, subtitle))
        language = get_track_language(subtitle)
        display_text = (
            f"Piste {subtitle['id']} - "
            f"Langue: {language}"
        )
        cb = tk.Checkbutton(scrollable_frame, text=display_text, variable=var, font=UNICODE_FONT)
        cb.pack(anchor='w', pady=2)
        subtitle_checkboxes.append(cb)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    selected_subtitles = [None]
    canceled = [False]
    back = [False]

    def on_confirm():
        selected = [subtitle for (var, subtitle) in subtitle_vars if var.get()]
        selected_subtitles[0] = selected
        root.destroy()

    def on_cancel():
        canceled[0] = True
        root.destroy()

    def on_back():
        back[0] = True
        root.destroy()

    Button(root, text="Confirmer la sélection", command=on_confirm, font=UNICODE_FONT).pack(pady=10, side='left')
    Button(root, text="Annuler", command=on_cancel, font=UNICODE_FONT).pack(pady=10, side='left')
    Button(root, text="Retour", command=on_back, font=UNICODE_FONT).pack(pady=10, side='left')

    root.wait_window()

    return (selected_subtitles[0] or [], canceled[0], back[0])

def calculate_directory_size(directory):
    """
    Calcule la taille totale d'un répertoire en octets.
    """
    total_size = 0
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size

def format_size(size_bytes):
    """
    Convertit la taille en octets en une chaîne lisible.
    """
    for unit in ['octets', 'Ko', 'Mo', 'Go', 'To']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

def detect_gpu():
    """
    Détecte le type de GPU disponible.
    """
    try:
        if platform.system() == "Windows":
            result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                                    capture_output=True, text=True)
            gpu_info = result.stdout
        elif platform.system() == "Linux":
            result = subprocess.run(['lspci', '|', 'grep', 'VGA'],
                                    shell=True, capture_output=True, text=True)
            gpu_info = result.stdout
        else:  # macOS
            result = subprocess.run(['system_profiler', 'SPDisplaysDataType'],
                                    capture_output=True, text=True)
            gpu_info = result.stdout
        # Vérification des GPU
        if 'NVIDIA' in gpu_info.upper():
            return 'nvidia'
        elif 'AMD' in gpu_info.upper() or 'RADEON' in gpu_info.upper():
            return 'amd'
        elif 'INTEL' in gpu_info.upper():
            return 'intel'
        return None
    except Exception as e:
        logging.error(f"Erreur lors de la détection du GPU : {e}")
        return None

def get_system_resources() -> Dict[str, float]:
    """
    Récupère les informations sur les ressources système disponibles.
    
    Returns:
        Dict[str, float]: Dictionnaire contenant les informations sur la mémoire et le CPU
    """
    memory = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=1)
    
    return {
        'total_memory': memory.total,
        'available_memory': memory.available,
        'memory_percent': memory.percent,
        'cpu_percent': cpu_percent
    }

def show_system_config():
    """
    Affiche une fenêtre résumant la configuration système (CPU, RAM, GPU) à l'utilisateur.
    Cette fenêtre est purement informative et permet de vérifier que le script s'adapte à la machine.
    """
    cpu_count = multiprocessing.cpu_count()
    ram_gb = psutil.virtual_memory().total / (1024**3)
    try:
        gpu = detect_gpu() or 'Aucun GPU détecté'
    except Exception:
        gpu = 'Non détecté'
    # Création de la fenêtre Tkinter
    root = tk.Toplevel()
    root.title("Configuration système")
    root.geometry("500x260")
    root.resizable(False, False)
    Label = tk.Label
    # Explication utilisateur
    Label(root, text="Résumé de la configuration de votre PC :", font=UNICODE_FONT).pack(pady=(10,0))
    Label(root, text="Cette fenêtre s'affiche pour vous informer des ressources qui seront utilisées pour le traitement automatique.\nAucune action n'est requise de votre part.", font=UNICODE_FONT, wraplength=480, justify='left').pack(pady=(0,10))
    # Résumé technique
    Label(root, text=f"- CPU : {cpu_count} cœurs", font=UNICODE_FONT).pack()
    Label(root, text=f"- RAM : {ram_gb:.1f} Go", font=UNICODE_FONT).pack()
    Label(root, text=f"- GPU : {gpu}", font=UNICODE_FONT).pack()
    # Bouton pour fermer la fenêtre
    def close_popup():
        root.destroy()
    btn = tk.Button(root, text="OK", command=close_popup, font=UNICODE_FONT, width=12)
    btn.pack(pady=15)
    root.deiconify(); root.lift(); root.focus_force()
    root.wait_window()
    # Log de la configuration pour le suivi
    resume = (
        f"Configuration détectée :\n"
        f"- CPU : {cpu_count} cœurs\n"
        f"- RAM : {ram_gb:.1f} Go\n"
        f"- GPU : {gpu}"
    )
    logging.info(resume)

def calculate_optimal_processes() -> int:
    """
    Calcule le nombre optimal de processus en fonction des ressources système (mode sûr mais adapté à la config).
    """
    resources = get_system_resources()
    cpu_count = multiprocessing.cpu_count()
    available_memory = resources['available_memory']
    memory_per_process = 500 * 1024 * 1024  # 500 Mo par processus
    # Mode sûr mais dynamique :
    # - Ne dépasse pas la moitié des cœurs CPU si >4, sinon tous les cœurs
    # - Ne dépasse pas la RAM disponible avec tampon
    # - Prend en compte la charge CPU actuelle
    max_cpu = cpu_count // 2 if cpu_count > 4 else cpu_count
    memory_based_processes = int(available_memory * (1 - CONFIG['MEMORY_BUFFER_PERCENTAGE']) / memory_per_process)
    cpu_load = resources['cpu_percent']
    cpu_based_processes = int(max_cpu * (1 - cpu_load/100))
    optimal_processes = min(memory_based_processes, cpu_based_processes, max_cpu)
    return max(CONFIG['MIN_PROCESSES'], min(optimal_processes, CONFIG['MAX_PROCESSES']))

def find_tracks(track_info):
    """
    Trouve les pistes japonaises (audio) et françaises (sous-titres).
    Retourne les informations détaillées des pistes.
    """
    japanese_audio = None
    french_subtitles = []
    french_audio_tracks = []

    for track in track_info.get('tracks', []):
        # Recherche de la piste audio japonaise
        if (track['type'] == 'audio' and
            track.get('properties', {}).get('language') in CONFIG['SUPPORTED_LANGUAGES']['audio_source']):
            if japanese_audio is None:
                japanese_audio = track

        # Recherche des pistes de sous-titres françaises
        if (track['type'] == 'subtitles' and
            track.get('properties', {}).get('language') in CONFIG['SUPPORTED_LANGUAGES']['subtitle_target']):
            french_subtitles.append(track)
        # Recherche des pistes audio françaises à supprimer
        if (track['type'] == 'audio' and
            track.get('properties', {}).get('language') in CONFIG['SUPPORTED_LANGUAGES']['subtitle_target']):
            french_audio_tracks.append(str(track['id']))

    return japanese_audio, french_subtitles, french_audio_tracks

def find_matching_subtitle(french_subtitles, selected_subtitle):
    """
    Trouve une piste de sous-titres correspondante de manière optimisée.
    
    Args:
        french_subtitles: Liste des sous-titres français disponibles
        selected_subtitle: Sous-titre sélectionné comme référence
        
    Returns:
        Dict: Sous-titre correspondant ou None si non trouvé
    """
    if not french_subtitles or not selected_subtitle:
        return None
        
    # Créer un dictionnaire indexé par nom de piste pour une recherche plus rapide
    subtitle_dict = {
        subtitle.get('properties', {}).get('track_name', '').lower(): subtitle 
        for subtitle in french_subtitles
    }
    
    selected_name = selected_subtitle.get('properties', {}).get('track_name', '').lower()
    selected_codec = selected_subtitle.get('codec')
    
    # 1. Recherche exacte (nom + codec)
    if selected_name in subtitle_dict:
        exact_match = subtitle_dict[selected_name]
        if exact_match.get('codec') == selected_codec:
            return exact_match
            
    # 2. Recherche partielle (le nom sélectionné est contenu dans un autre nom)
    for name, subtitle in subtitle_dict.items():
        if selected_name and selected_name in name:
            return subtitle
            
    # 3. Recherche par similarité (si les deux premières méthodes échouent)
    best_match = None
    highest_similarity = 0
    
    for subtitle in french_subtitles:
        current_name = subtitle.get('properties', {}).get('track_name', '').lower()
        # Calcul de similarité simple basé sur les mots communs
        selected_words = set(selected_name.split())
        current_words = set(current_name.split())
        common_words = selected_words.intersection(current_words)
        similarity = len(common_words) / max(len(selected_words), len(current_words))
        
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match = subtitle
            
    # Retourner le meilleur match si la similarité est suffisante
    if highest_similarity > 0.5:  # Seuil de similarité à 50%
        return best_match
        
    # 4. Fallback : premier sous-titre français
    return french_subtitles[0] if french_subtitles else None

def process_single_mkv(mkvmerge_path: str, input_dir: str, output_dir: str, filename: str,
                      selected_audio_tracks: List[Dict], selected_main_subtitle: Dict,
                      selected_subtitles: List[Dict], state: ProcessingState) -> bool:
    """
    Traite un seul fichier MKV avec gestion des erreurs et reprise.
    
    Args:
        mkvmerge_path: Chemin vers mkvmerge
        input_dir: Répertoire d'entrée
        output_dir: Répertoire de sortie
        filename: Nom du fichier à traiter
        selected_audio_tracks: Liste des pistes audio sélectionnées
        selected_main_subtitle: Sous-titre principal sélectionné
        selected_subtitles: Liste des sous-titres sélectionnés
        state: État du traitement pour la reprise
        
    Returns:
        bool: True si le traitement a réussi, False sinon
    """
    if state.is_processed(filename):
        logging.info(f"Fichier {filename} déjà traité, passage au suivant")
        return True

    input_path = os.path.join(input_dir, filename)
    output_path = os.path.join(output_dir, f"processed_{filename}")

    try:
        # Vérification de l'espace disque disponible
        free_space = psutil.disk_usage(output_dir).free
        file_size = os.path.getsize(input_path)
        if free_space < file_size * 1.5:  # 50% de marge
            raise ProcessingError(f"Espace disque insuffisant pour traiter {filename}")

        # Construction de la commande mkvmerge
        command = [mkvmerge_path, '-o', output_path]
        
        # Ajout des pistes audio sélectionnées
        for track in selected_audio_tracks:
            command.extend(['--audio-tracks', str(track['id'])])
        
        # Ajout des sous-titres sélectionnés
        for subtitle in selected_subtitles:
            command.extend(['--subtitle-tracks', str(subtitle['id'])])
        
        command.append(input_path)

        # Exécution de la commande
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Vérification du fichier de sortie
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ProcessingError(f"Le fichier de sortie {output_path} est vide ou n'existe pas")

        state.mark_as_processed(filename)
        logging.info(f"Traitement réussi pour {filename}")
        return True

    except subprocess.CalledProcessError as e:
        error_msg = f"Erreur lors du traitement de {filename}: {e.stderr}"
        logging.error(error_msg)
        state.mark_as_failed(filename, error_msg)
        return False
    except ProcessingError as e:
        logging.error(str(e))
        state.mark_as_failed(filename, str(e))
        return False
    except Exception as e:
        error_msg = f"Erreur inattendue lors du traitement de {filename}: {str(e)}"
        logging.error(error_msg)
        state.mark_as_failed(filename, error_msg)
        return False

def process_mkv_files(input_dir: str, output_dir: str, mkvmerge_path: str):
    # Reset automatique de l'état à chaque lancement
    state_file = 'processing_state.json'
    if os.path.exists(state_file):
        os.remove(state_file)
        logging.info('Fichier d\'état supprimé, tous les fichiers seront retraités.')
    state = ProcessingState()
    failed_files = state.get_failed_files()
    if failed_files:
        retry = messagebox.askyesno(
            "Fichiers échoués",
            f"{len(failed_files)} fichiers ont échoué lors du dernier traitement.\n"
            f"Voulez-vous réessayer de les traiter ?"
        )
        if not retry:
            state = ProcessingState()  # Réinitialiser l'état
    mkv_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.mkv')]
    if not mkv_files:
        messagebox.showwarning("Aucun fichier", "Aucun fichier MKV trouvé dans le répertoire sélectionné.")
        return
    first_file = next((f for f in mkv_files if not state.is_processed(f)), mkv_files[0])
    track_info = get_mkv_tracks(os.path.join(input_dir, first_file), mkvmerge_path)
    if not track_info:
        messagebox.showerror("Erreur", f"Impossible d'analyser le fichier {first_file}")
        return
    audio_tracks = [track for track in track_info.get('tracks', []) if track['type'] == 'audio']
    if not audio_tracks:
        messagebox.showerror("Erreur", f"Aucune piste audio trouvée dans {first_file}")
        return
    # Affiche la config système au début
    show_system_config()
    initial_size = calculate_directory_size(input_dir)
    while True:
        # Sélection des pistes audio
        selected_audio_tracks, canceled, back = choose_audio_tracks(audio_tracks, first_file)
        if canceled:
            return
        if back:
            continue  # Revenir à l'étape précédente (ici, il n'y en a pas, donc recommence)
        # Sélection multiple des sous-titres directement
        all_subtitles = [track for track in track_info.get('tracks', []) if track['type'] == 'subtitles']
        if not all_subtitles:
            selected_subtitles = []
        else:
            selected_subtitles, canceled, back = choose_subtitles(all_subtitles, first_file, None)
            if canceled:
                return
            if back:
                continue  # Revenir à la sélection audio
        break  # Sortir de la boucle principale
    os.makedirs(output_dir, exist_ok=True)
    num_processes = calculate_optimal_processes()  # Toujours mode défaut
    logging.info(f"Utilisation de {num_processes} processus pour le traitement (mode : défaut)")
    start_time = time.time()
    with multiprocessing.Pool(processes=num_processes) as pool:
        process_args = [
            (mkvmerge_path, input_dir, output_dir, filename, 
             selected_audio_tracks, None, selected_subtitles, state)
            for filename in mkv_files if not state.is_processed(filename)
        ]
        results = pool.starmap(process_single_mkv, process_args)
    failed_files = state.get_failed_files()
    # Calcul du résumé
    end_time = time.time()
    total_time = end_time - start_time
    final_size = calculate_directory_size(output_dir)
    saved_size = initial_size - final_size
    saved_percentage = (saved_size / initial_size * 100) if initial_size > 0 else 0
    successful = sum(results)
    failed = len(results) - successful
    resume = (
        f"Traitement terminé.\n\n"
        f"Fichiers traités : {successful}/{len(results)}\n"
        f"Temps total : {total_time:.2f} secondes\n\n"
        f"Espace disque :\n"
        f"- Taille initiale : {format_size(initial_size)}\n"
        f"- Taille finale : {format_size(final_size)}\n"
        f"- Espace économisé : {format_size(saved_size)} ({saved_percentage:.2f}%)"
    )
    logging.info("\n--- Résumé du traitement ---\n" + resume)
    if failed_files:
        error_message = "Les fichiers suivants n'ont pas pu être traités :\n\n"
        for filename, error in failed_files.items():
            error_message += f"{filename}: {error}\n"
        messagebox.showerror("Erreurs de traitement", error_message + "\n" + resume)
    else:
        messagebox.showinfo("Succès", resume)

def main():
    """
    Fonction principale du programme.
    """
    # Initialiser Tkinter et masquer la fenêtre principale
    root = tk.Tk()
    root.withdraw()

    # Vérification des dépendances
    check_and_install_dependencies()
    
    # Recherche de mkvmerge
    mkvmerge_path = find_mkvmerge()
    if not mkvmerge_path:
        messagebox.showerror("Erreur", "mkvmerge n'a pas été trouvé. Veuillez installer MKVToolNix.")
        return
    
    # Sélection du dossier à traiter
    input_dir = filedialog.askdirectory(title="Sélectionnez le répertoire contenant les fichiers MKV")
    if not input_dir:
        return
    
    # Traitement des fichiers
    process_mkv_files(input_dir, os.path.join(input_dir, 'output'), mkvmerge_path)

# Teste plusieurs polices Unicode pour maximiser la compatibilité des caractères spéciaux
try:
    UNICODE_FONT = ("Arial Unicode MS", 10)
except:
    try:
        UNICODE_FONT = ("Noto Sans", 10)
    except:
        UNICODE_FONT = ("MS Gothic", 10)

if __name__ == "__main__":
    main()
