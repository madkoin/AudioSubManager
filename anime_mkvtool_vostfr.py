"""
MKV Processor - Outil de traitement de fichiers MKV
=================================================

Ce script permet de traiter des fichiers MKV en:
- Conservant uniquement la piste audio japonaise
- Gardant les sous-titres français sélectionnés
- Supprimant les pistes audio françaises

Dépendances: mkvmerge (MKVToolNix), Python 3.6+
"""

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

# Configuration globale
CONFIG = {
    'MIN_PROCESSES': 4,
    'MEMORY_PER_PROCESS': 500 * 1024 * 1024,  # 500 Mo par processus
    'SUPPORTED_LANGUAGES': {
        'audio_source': ['jpn', 'ja'],
        'subtitle_target': ['fre', 'fr']
    }
}

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def choose_subtitle(french_subtitles: List[Dict], first_file: Optional[str] = None) -> Tuple[Optional[Dict], bool]:
    """
    Interface interactive pour choisir les sous-titres.

    Args:
        french_subtitles: Liste des sous-titres français disponibles
        first_file: Nom du premier fichier (optionnel)

    Returns:
        Tuple[Dict, bool]: (Sous-titre sélectionné, Annulation)

    Raises:
        ValueError: Si la liste des sous-titres est vide
    """
    if not french_subtitles:
        raise ValueError("La liste des sous-titres ne peut pas être vide")

    root = Toplevel()
    root.title("Sélection des sous-titres")

    if first_file:
        Label(root, text=f"Choisissez la piste de sous-titres pour {first_file} :").pack()
    else:
        Label(root, text="Choisissez la piste de sous-titres à utiliser :").pack()

    listbox = Listbox(root, selectmode=SINGLE)
    listbox.pack(padx=10, pady=10, fill='both', expand=True)

    for idx, subtitle in enumerate(french_subtitles, 1):
        display_text = (
            f"Piste {subtitle['id']} - "
            f"Langue: {subtitle.get('properties', {}).get('language', 'N/A')} | "
            f"Nom : {subtitle.get('properties', {}).get('track_name', 'N/A')}"
        )
        listbox.insert(END, display_text)

    selected_subtitle = [None]
    canceled = [False]

    def on_select():
        if listbox.curselection():
            selected_idx = listbox.curselection()[0]
            selected_subtitle[0] = french_subtitles[selected_idx]
            root.destroy()

    def on_cancel():
        canceled[0] = True
        root.destroy()

    Button(root, text="Sélectionner", command=on_select).pack(side='left', padx=5, pady=5)
    Button(root, text="Annuler", command=on_cancel).pack(side='right', padx=5, pady=5)

    root.wait_window()

    return selected_subtitle[0], canceled[0]

def choose_subtitles(french_subtitles: List[Dict], first_file: str, selected_main_subtitle: Dict) -> List[Dict]:
    """
    Interface interactive pour choisir plusieurs pistes de sous-titres.

    Args:
        french_subtitles: Liste des sous-titres français disponibles
        first_file: Nom du premier fichier
        selected_main_subtitle: Sous-titre principal déjà sélectionné

    Returns:
        List[Dict]: Liste des sous-titres sélectionnés
    """
    if not french_subtitles:
        raise ValueError("La liste des sous-titres ne peut pas être vide")

    root = Toplevel()
    root.title(f"Sélection des sous-titres pour {first_file}")

    Label(root, text="Sélectionnez les pistes de sous-titres à conserver :").pack()

    subtitle_vars = []
    subtitle_checkboxes = []

    for subtitle in french_subtitles:
        var = tk.BooleanVar(
            value=subtitle.get('properties', {}).get('track_name') == selected_main_subtitle.get('properties', {}).get('track_name')
        )
        subtitle_vars.append((var, subtitle))

        display_text = (
            f"Piste {subtitle['id']} - "
            f"Langue: {subtitle.get('properties', {}).get('language', 'N/A')} | "
            f"Nom : {subtitle.get('properties', {}).get('track_name', 'N/A')}"
        )

        cb = tk.Checkbutton(root, text=display_text, variable=var)
        cb.pack(anchor='w')
        subtitle_checkboxes.append(cb)

    selected_subtitles = [None]

    def on_confirm():
        selected = [subtitle for (var, subtitle) in subtitle_vars if var.get()]
        selected_subtitles[0] = selected
        root.destroy()

    Button(root, text="Confirmer la sélection", command=on_confirm).pack(pady=10)

    root.wait_window()

    return selected_subtitles[0] or []

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

def calculate_optimal_processes():
    """
    Calcule le nombre optimal de processus en fonction des ressources système.
    """
    # Nombre total de cœurs
    total_cores = multiprocessing.cpu_count()

    # Mémoire totale et disponible
    total_memory = psutil.virtual_memory().total
    available_memory = psutil.virtual_memory().available

    # Estimation de la mémoire par processus (approximation)
    estimated_memory_per_process = CONFIG['MEMORY_PER_PROCESS']

    # Calcul du nombre de processus basé sur la mémoire
    memory_based_processes = max(1, int(available_memory / estimated_memory_per_process))

    # Calcul du nombre optimal de processus
    optimal_processes = min(
        total_cores, # Ne pas dépasser le nombre de cœurs
        memory_based_processes, # Limiter par la mémoire disponible
        max(total_cores // 2, CONFIG['MIN_PROCESSES']) # Au moins 4 processus, ou la moitié des cœurs
    )

    return optimal_processes

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

def choose_audio_tracks(audio_tracks: List[Dict], first_file: Optional[str] = None) -> Tuple[List[Dict], bool]:
    """
    Interface interactive pour choisir les pistes audio avec des cases à cocher.

    Args:
        audio_tracks: Liste des pistes audio disponibles
        first_file: Nom du premier fichier (optionnel)

    Returns:
        Tuple[List[Dict], bool]: (Liste des pistes audio sélectionnées, Annulation)
    """
    if not audio_tracks:
        raise ValueError("La liste des pistes audio ne peut pas être vide")

    root = Toplevel()
    root.title("Sélection des pistes audio")

    if first_file:
        Label(root, text=f"Choisissez les pistes audio pour {first_file} :").pack()
    else:
        Label(root, text="Choisissez les pistes audio à conserver :").pack()

    # Frame pour les cases à cocher
    checkbox_frame = tk.Frame(root)
    checkbox_frame.pack(padx=10, pady=10, fill='both', expand=True)

    # Variables pour les cases à cocher
    audio_vars = []
    audio_checkboxes = []

    for audio in audio_tracks:
        var = tk.BooleanVar(value=True)  # Par défaut, toutes les pistes sont sélectionnées
        audio_vars.append((var, audio))

        display_text = (
            f"Piste {audio['id']} - "
            f"Langue: {audio.get('properties', {}).get('language', 'N/A')} | "
            f"Nom : {audio.get('properties', {}).get('track_name', 'N/A')} | "
            f"Codec : {audio.get('codec', 'N/A')}"
        )

        cb = tk.Checkbutton(checkbox_frame, text=display_text, variable=var)
        cb.pack(anchor='w')
        audio_checkboxes.append(cb)

    selected_audio = [None]
    canceled = [False]

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

    # Frame pour les boutons
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    Button(button_frame, text="Confirmer", command=on_confirm).pack(side='left', padx=5)
    Button(button_frame, text="Annuler", command=on_cancel).pack(side='right', padx=5)

    root.wait_window()

    return selected_audio[0], canceled[0]

def process_single_mkv(mkvmerge_path, input_dir, output_dir, filename, selected_audio_tracks, selected_main_subtitle, selected_subtitles):
    """
    Traite un seul fichier MKV.
    """
    input_path = os.path.join(input_dir, filename)
    output_filename = f"{os.path.splitext(filename)[0]}_processed.mkv"
    output_path = os.path.join(output_dir, output_filename)

    # Obtenir les informations des pistes
    track_info = get_mkv_tracks(input_path, mkvmerge_path)
    if not track_info:
        logging.error(f"Impossible de traiter {filename}")
        return False

    # Trouver les pistes correspondantes
    matching_audio_tracks = []
    for selected_audio in selected_audio_tracks:
        matching_audio = find_matching_subtitle(
            [track for track in track_info.get('tracks', []) if track['type'] == 'audio'],
            selected_audio
        )
        if matching_audio:
            matching_audio_tracks.append(matching_audio)
    
    if not matching_audio_tracks:
        logging.error(f"Aucune piste audio correspondante trouvée dans {filename}")
        return False

    # Construire la commande MKVMerge
    cmd = [
        mkvmerge_path,
        '-o', output_path,
        # Ne garder que les pistes audio sélectionnées
        '--audio-tracks', ','.join(map(str, [audio['id'] for audio in matching_audio_tracks])),
        # Définir la première piste audio comme piste audio par défaut
        '--default-track', f"{matching_audio_tracks[0]['id']}:yes"
    ]

    # Gestion des sous-titres
    if selected_main_subtitle:
        french_subtitles = [track for track in track_info.get('tracks', []) 
                          if track['type'] == 'subtitles' and 
                          track.get('properties', {}).get('language') in CONFIG['SUPPORTED_LANGUAGES']['subtitle_target']]
        
        matching_main_subtitle = find_matching_subtitle(french_subtitles, selected_main_subtitle)
        if matching_main_subtitle:
            subtitle_tracks_to_keep = [matching_main_subtitle['id']]
            # Ajouter les autres sous-titres sélectionnés
            for selected_subtitle in selected_subtitles:
                matching_subtitle = find_matching_subtitle(french_subtitles, selected_subtitle)
                if matching_subtitle and matching_subtitle['id'] != matching_main_subtitle['id']:
                    subtitle_tracks_to_keep.append(matching_subtitle['id'])
            
            if subtitle_tracks_to_keep:  # Vérifier qu'il y a des sous-titres à conserver
                cmd.extend([
                    '--subtitle-tracks', ','.join(map(str, subtitle_tracks_to_keep)),
                    '--default-track', f"{matching_main_subtitle['id']}:yes"
                ])
    else:
        # Si aucun sous-titre n'est sélectionné, supprimer tous les sous-titres
        cmd.append('--no-subtitles')

    cmd.append(input_path)

    try:
        # Exécuter la commande
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logging.info(f"Traité : {filename}")
        
        # Informations sur les pistes conservées
        logging.info(f"Pistes audio conservées dans {filename}:")
        for audio in matching_audio_tracks:
            logging.info(f"  - Piste {audio['id']}: {audio.get('properties', {}).get('track_name', 'N/A')}")
        
        if selected_main_subtitle and subtitle_tracks_to_keep:  # N'afficher les infos des sous-titres que s'il y en a
            logging.info(f"Pistes de sous-titres dans {filename}:")
            for subtitle_id in subtitle_tracks_to_keep:
                subtitle = next((s for s in french_subtitles if s['id'] == subtitle_id), None)
                if subtitle:
                    logging.info(f"  - Piste {subtitle['id']}: {subtitle.get('properties', {}).get('track_name', 'N/A')}")

        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Erreur lors du traitement de {filename}: {e}")
        logging.error(f"Sortie standard: {e.stdout}")
        logging.error(f"Erreur standard: {e.stderr}")
        return False

def process_mkv_files(input_dir, output_dir, mkvmerge_path):
    """
    Traite les fichiers MKV en parallèle.
    """
    # Créer le répertoire de sortie
    os.makedirs(output_dir, exist_ok=True)
    # Calculer la taille initiale
    initial_size = calculate_directory_size(input_dir)
    # Filtrer les fichiers MKV
    mkv_files = [f for f in os.listdir(input_dir) if f.endswith('.mkv')]
    
    if not mkv_files:
        messagebox.showerror("Erreur", "Aucun fichier MKV trouvé dans le dossier sélectionné.")
        return
        
    # Prendre le premier fichier pour la sélection des pistes
    first_file = mkv_files[0]
    first_file_path = os.path.join(input_dir, first_file)
    
    # Obtenir les informations des pistes du premier fichier
    track_info = get_mkv_tracks(first_file_path, mkvmerge_path)
    if not track_info:
        messagebox.showerror("Erreur", "Impossible de lire les pistes du premier fichier.")
        return
        
    # Trouver toutes les pistes audio et sous-titres
    all_audio_tracks = [track for track in track_info.get('tracks', []) if track['type'] == 'audio']
    french_subtitles = [track for track in track_info.get('tracks', []) 
                       if track['type'] == 'subtitles' and 
                       track.get('properties', {}).get('language') in CONFIG['SUPPORTED_LANGUAGES']['subtitle_target']]
    
    # Sélection des pistes audio
    selected_audio_tracks, audio_canceled = choose_audio_tracks(all_audio_tracks, first_file)
    if audio_canceled:
        messagebox.showinfo("Information", "Opération annulée.")
        return
    if not selected_audio_tracks:
        messagebox.showerror("Erreur", "Aucune piste audio sélectionnée.")
        return
        
    # Sélection des sous-titres (optionnelle)
    selected_main_subtitle = None
    selected_subtitles = []
    
    if french_subtitles:
        want_subtitles = messagebox.askyesno("Sous-titres", 
                                           "Voulez-vous conserver des sous-titres ?")
        if want_subtitles:
            selected_main_subtitle, subtitle_canceled = choose_subtitle(french_subtitles, first_file)
            if subtitle_canceled:
                messagebox.showinfo("Information", "Opération annulée.")
                return
            if selected_main_subtitle:
                selected_subtitles = choose_subtitles(french_subtitles, first_file, selected_main_subtitle)
    else:
        messagebox.showinfo("Information", "Aucune piste de sous-titres française trouvée.")
    
    # Détecter le GPU
    gpu_type = detect_gpu()
    logging.info(f"GPU détecté : {gpu_type if gpu_type else 'Aucun GPU spécifique'}")
    
    # Calculer le nombre optimal de processus
    num_processes = calculate_optimal_processes()
    logging.info(f"Nombre de processus : {num_processes}")
    
    # Mesurer le temps de début
    start_time = time.time()
    
    # Utiliser un pool de processus
    with multiprocessing.Pool(processes=num_processes) as pool:
        # Fonction partielle avec les arguments fixes
        process_func = partial(
            process_single_mkv,
            mkvmerge_path,
            input_dir,
            output_dir,
            selected_audio_tracks=selected_audio_tracks,
            selected_main_subtitle=selected_main_subtitle,
            selected_subtitles=selected_subtitles
        )
        # Traitement parallèle
        results = pool.map(process_func, mkv_files)
    
    # Calculer et afficher le temps total
    end_time = time.time()
    total_time = end_time - start_time
    
    # Calculer la taille finale
    final_size = calculate_directory_size(output_dir)
    
    # Calculer l'espace économisé
    saved_size = initial_size - final_size
    saved_percentage = (saved_size / initial_size * 100) if initial_size > 0 else 0
    
    # Résumé des résultats
    successful = sum(results)
    failed = len(results) - successful

    logging.info("\n--- Résumé du traitement ---")
    logging.info(f"Fichiers traités : {len(results)}")
    logging.info(f"Succès : {successful}")
    logging.info(f"Échecs : {failed}")
    logging.info(f"Temps total : {total_time:.2f} secondes")
    logging.info(f"Nombre de processus utilisés : {num_processes}")
    logging.info("\n--- Analyse de l'espace disque ---")
    logging.info(f"Taille initiale : {format_size(initial_size)}")
    logging.info(f"Taille finale : {format_size(final_size)}")
    logging.info(f"Espace économisé : {format_size(saved_size)} ({saved_percentage:.2f}%)")
    
    # Message de fin détaillé
    message = (
        f"Traitement terminé.\n\n"
        f"Fichiers traités : {successful}/{len(results)}\n"
        f"Temps total : {total_time:.2f} secondes\n\n"
        f"Espace disque :\n"
        f"- Taille initiale : {format_size(initial_size)}\n"
        f"- Taille finale : {format_size(final_size)}\n"
        f"- Espace économisé : {format_size(saved_size)} ({saved_percentage:.2f}%)"
    )
    messagebox.showinfo("Terminé", message)

def main():
    # Initialiser Tkinter
    root = tk.Tk()
    root.withdraw()  # Cacher la fenêtre principale
    # Trouver mkvmerge
    mkvmerge_path = find_mkvmerge()

    if not mkvmerge_path:
        messagebox.showerror("Erreur", "Impossible de trouver mkvmerge.exe")
        return
    # Sélectionner le dossier d'entrée
    input_dir = filedialog.askdirectory(
        title="Sélectionnez le dossier contenant les fichiers MKV"
    )

    if not input_dir:
        messagebox.showerror("Erreur", "Aucun dossier sélectionné")
        return
    # Définir automatiquement le dossier de sortie comme un sous-dossier 'processed'
    output_dir = os.path.join(input_dir, 'processed')
    # Lancer le traitement
    process_mkv_files(input_dir, output_dir, mkvmerge_path)

if __name__ == '__main__':
    # Vérifier et installer les dépendances
    check_and_install_dependencies()
    # Support de l'exécution sous Windows
    multiprocessing.freeze_support()
    main()
