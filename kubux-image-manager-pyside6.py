# Copyright 2025 [Kai-Uwe Bux]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import traceback
import types
import shutil
import hashlib
import json
import os
import re
import shlex
import math
import platform
import secrets
import queue
import threading
import subprocess
import time
from collections import OrderedDict
from datetime import datetime

# PySide6 imports
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QTimer, Signal, QObject, QThread
from PySide6.QtCore import QModelIndex, QAbstractListModel, QByteArray, QMimeData
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, 
                              QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, 
                              QPlainTextEdit, QScrollArea, QSlider, QFileDialog,
                              QListView, QAbstractItemView, QMenu, QDialog, QMessageBox,
                              QFrame, QScrollBar, QSizePolicy)
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QFont, QFontMetrics,
                          QTextCursor, QDrag, QTextDocument, QTextCharFormat, 
                          QSyntaxHighlighter, QIcon, QAction, QCursor)

# External library imports
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import requests
from PIL import Image


# --- configuration ---

SUPPORTED_IMAGE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp',
    '.ico', '.icns', '.avif', '.dds', '.msp', '.pcx', '.ppm',
    '.pbm', '.pgm', '.sgi', '.tga', '.xbm', '.xpm'
)

CACHE_SIZE = 10000

HOME_DIR = os.path.expanduser('~')
CONFIG_DIR = os.path.join(HOME_DIR, ".config", "kubux-image-manager")
CACHE_DIR = os.path.join(HOME_DIR, ".cache", "kubux-thumbnail-cache")
THUMBNAIL_CACHE_ROOT = os.path.join(CACHE_DIR, "thumbnails")
PICTURES_DIR = os.path.join(HOME_DIR, "Pictures")
DEFAULT_THUMBNAIL_DIM = 192
APP_SETTINGS_FILE = os.path.join(CONFIG_DIR, "app_settings.json")    

os.makedirs(THUMBNAIL_CACHE_ROOT, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)


# --- logging ---

def log_action(msg):
    print(msg)
    pass

def log_error(msg):
    print(msg)
    pass

def log_debug(msg):
    print(msg)
    pass


# --- probe font ---

def get_gtk_ui_font():
    """
    Queries the system's default UI font and size for GTK-based desktops
    using gsettings.
    """
    try:
        # Check if gsettings is available
        subprocess.run(["which", "gsettings"], check=True, capture_output=True)

        # Get the font name string from GNOME's desktop interface settings
        font_info_str = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "font-name"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip().strip("'") # Remove leading/trailing whitespace and single quotes

        # Example output: 'Noto Sans 10', 'Ubuntu 11', 'Cantarell 11'
        parts = font_info_str.rsplit(' ', 1) # Split only on the last space

        font_name = "Sans" # Default fallback
        font_size = 10     # Default fallback

        if len(parts) == 2 and parts[1].isdigit():
            font_name = parts[0]
            font_size = int(parts[1])
        else:
            # Handle cases like "Font Name" 10 or unexpected formats
            # Attempt to split assuming format "Font Name Size"
            try:
                # Common scenario: "Font Name X" where X is size
                # Sometimes font names have spaces (e.g., "Noto Sans CJK JP")
                # So finding the *last* space before digits is key.
                last_space_idx = font_info_str.rfind(' ')
                if last_space_idx != -1 and font_info_str[last_space_idx+1:].isdigit():
                    font_name = font_info_str[:last_space_idx]
                    font_size = int(font_info_str[last_space_idx+1:])
                else:
                    log_error(f"Warning: Unexpected gsettings font format: '{font_info_str}'")
            except Exception as e:
                log_error(f"Error parsing gsettings font: {e}")

        return font_name, font_size

    except subprocess.CalledProcessError:
        log_error("gsettings command not found or failed. Are you on a GTK-based desktop with dconf/gsettings installed?")
        return "Sans", 10 # Fallback for non-GTK or missing gsettings
    except Exception as e:
        log_error(f"An error occurred while getting GTK font settings: {e}")
        return "Sans", 10 # General fallback

def get_kde_ui_font():
    """
    Queries the system's default UI font and size for KDE Plasma desktops
    using kreadconfig5.
    """
    try:
        # Check if kreadconfig5 is available
        subprocess.run(["which", "kreadconfig5"], check=True, capture_output=True)

        # Get the font string from the kdeglobals file
        # This typically looks like "Font Name,points,weight,slant,underline,strikeout"
        font_string = subprocess.run(
            ["kreadconfig5", "--file", "kdeglobals", "--group", "General", "--key", "font", "--default", "Sans,10,-1,5,50,0,0,0,0,0"],
            capture_output=True,
            text=True,
            check=True
        ).stdout.strip()

        parts = font_string.split(',')
        if len(parts) >= 2:
            font_name = parts[0].strip()
            # Font size is in points. kreadconfig often gives it as an int directly.
            font_size = int(parts[1].strip())
            return font_name, font_size
        else:
            log_error(f"Warning: Unexpected KDE font format: '{font_string}'")
            return "Sans", 10 # Fallback

    except subprocess.CalledProcessError:
        log_error("kreadconfig5 command not found or failed. Are you on KDE Plasma?")
        return "Sans", 10 # Fallback for non-KDE or missing kreadconfig5
    except Exception as e:
        log_error(f"An error occurred while getting KDE font settings: {e}")
        return "Sans", 10 # General fallback

def get_linux_system_ui_font_info():
    """
    Attempts to detect the Linux desktop environment and return its
    configured default UI font family and size.
    Returns (font_family, font_size) or (None, None) if undetectable.
    """
    # Check for common desktop environment indicators
    desktop_session = os.environ.get("XDG_CURRENT_DESKTOP")
    if not desktop_session:
        desktop_session = os.environ.get("DESKTOP_SESSION")

    # log_debug(f"Detected desktop session: {desktop_session}")

    if desktop_session and ("GNOME" in desktop_session.upper() or
                            "CINNAMON" in desktop_session.upper() or
                            "XFCE" in desktop_session.upper() or
                            "MATE" in desktop_session.upper()):
        # log_debug("Attempting to get GTK font...")
        return get_gtk_ui_font()
    elif desktop_session and "KDE" in desktop_session.upper():
        # log_debug("Attempting to get KDE font...")
        return get_kde_ui_font()
    else:
        # Fallback for other desktops or if detection fails
        log_error("Could not reliably detect desktop environment. Trying common defaults or gsettings as fallback.")
        # Try gsettings anyway, as it's common even outside "full" GNOME
        font_name, font_size = get_gtk_ui_font()
        if font_name != "Sans" or font_size != 10: # If gsettings returned something more specific
            return font_name, font_size
        return "Sans", 10 # Final generic fallback

def get_linux_ui_font():
    font_name, font_size = get_linux_system_ui_font_info()
    return QFont(font_name, font_size)


# --- list ops ---

def copy_truish(the_list):
     return [entry for entry in the_list if entry]

def remove_falsy(the_list):
    new_list = copy_truish( the_list )
    the_list.clear()
    the_list.extend( new_list )

    
def copy_uniq(the_list):
    helper = set()
    result = []
    for entry in the_list:
        if not entry in helper:
            helper.add( entry )
            result.append( entry )
    return ( result )

def make_uniq(the_list):
    new_list = copy_uniq(the_list)
    the_list.clear()
    the_list.extend( new_list )


def prepend_or_move_to_front(entry, the_list):
    the_list.insert( 0, entry )
    make_uniq(the_list)
    
        
# --- file ops ---

def is_file_below_dir(file_path, dir_path):
    file_dir_path = os.path.realpath( os.path.dirname(file_path) )
    dir_path = os.path.realpath(dir_path)
    # log_debug(f"{file_path} vs {dir_path}")
    return file_dir_path.startswith(dir_path)

def is_file_in_dir(file_path, dir_path):
    file_dir_path = os.path.realpath( os.path.dirname(file_path) )
    dir_path = os.path.realpath(dir_path)
    # log_debug(f"{file_path} vs {dir_path}")
    return dir_path == file_dir_path
    
def execute_shell_command(command):
    result = subprocess.run(command, shell=True)

def execute_shell_command_with_capture(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    # log_debug(f"return code = {result.returncode}")
    # log_debug(f"stdout = {result.stdout}")
    # log_debug(f"stderr = {result.stderr}")
    return result


def filter_for_files_in_directory(command, directory):
    result = subprocess.run(command, cwd=directory, shell=True, capture_output=True, text=True)
    line_list = result.stdout.splitlines()
    return [file for file in line_list if (os.path.isfile(file) and is_file_in_dir(file, directory))]
        
def filter_for_files(command):
    line_list = execute_shell_command_with_capture(command).stdout.splitlines()
    return [file for file in line_list if os.path.isfile(file)]
        

def list_image_files_by_command(dir, cmd):
    raw_output = subprocess.run(cmd, cwd=dir, shell=True, capture_output=True, text=True).stdout.splitlines()
    listing = []
    for path in raw_output:
        if os.path.isabs(path):
            listing.append( os.path.normpath(path) )
        else:
            listing.append( os.path.normpath( os.path.join(dir, path) ) )
    # log_debug(f"choosing from {listing}")
    return [path for path in listing if is_image_file(path) and is_file_below_dir(path, dir)]
    
    
def move_file_to_directory(file_path, target_dir_path):
    """
    Moves a file or symlink to a new directory, preserving link validity for relative symlinks
    """

    # log_debug("enter:move_file_to_directory")
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file or link not found: '{file_path}'")
        
        if not os.path.isdir(target_dir_path):
            os.makedirs(target_dir_path, exist_ok=True)
        
        item_name = os.path.basename(file_path)
        new_path = os.path.normpath( os.path.join(target_dir_path, item_name) )

        if os.path.islink(file_path):
            link_target = os.readlink(file_path)
            # log_debug(f"{file_path} is a symlink with target {link_target}.")
           
            if os.path.isabs(link_target):
                # If absolute, just move the symlink file itself.
                shutil.move(file_path, new_path)
                # log_debug(f"Moved absolute symlink '{item_name}' to '{target_dir_path}'")
            else:
                # If relative, we must calculate the new relative path.
                original_link_dir = os.path.dirname(os.path.abspath(file_path))
                target_abs_path = os.path.normpath(os.path.join(original_link_dir, link_target))
                new_link_dir = os.path.abspath(target_dir_path)
                new_relative_path = os.path.relpath(target_abs_path, new_link_dir)
                
                # Remove the old link and create a new one with the corrected path.
                os.remove(file_path)
                os.symlink(new_relative_path, new_path)
                # log_debug(f"Moved relative symlink '{item_name}' to '{target_dir_path}' and updated its target.")
        else:
            shutil.move(file_path, new_path)
            # log_debug(f"Moved file '{item_name}' to '{target_dir_path}'")

        return os.path.normpath( new_path )
        
    except FileNotFoundError as e:
        log_error(f"Error: {e}")
        return None
    except PermissionError:
        log_error(f"Error: Permission denied. Cannot move '{file_path}'")
        return None
    except shutil.Error as e:
        log_error(f"Error moving file with shutil: {e}")
        return None
    except Exception as e:
        log_error(f"An unexpected error occurred: {e}")
        return None


# --- watch directory ---

class DirectoryEventHandler(FileSystemEventHandler):
    def __init__(self, directory, image_picker):
        log_debug(f"Initializing event handler for {directory} with picker {image_picker}")
        self.image_picker = image_picker
        self.directory = directory
        
    def on_any_event(self, event):
        log_debug(f"directory {self.directory} has changed.")
        QTimer.singleShot(0, self.image_picker.parent().broadcast_contents_change)


class DirectoryWatcher(QObject):
    def __init__(self, image_picker):
        super().__init__(image_picker)
        self.image_picker = image_picker
        log_debug(f"Initializing watcher for picker {image_picker}")
        
    def start_watching(self, directory):
        log_debug(f"Start watching directory {directory}")
        self.event_handler = DirectoryEventHandler(directory, self.image_picker)
        self.observer = Observer()
        self.observer.daemon = True
        self.observer.schedule(self.event_handler, directory, recursive=False)
        self.observer.start()

    def stop_watching(self):
        log_debug(f"Stop watching directory {self.image_picker.image_dir}")
        self.observer.stop()
        self.observer.join()
        self.observer = None
        
    def change_dir(self, directory):
        self.stop_watching()
        self.start_watching(directory)


# --- image stuff / caching ---

def is_image_file_name(file_name):
    return file_name.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)

def is_image_file(file_path):
    file_name = os.path.basename(file_path)
    # log_debug(f"checking {file_path} / {file_name}")
    return os.path.isfile(file_path) and is_image_file_name(file_name)

def list_image_files(directory_path):
    # log_debug(f"list image files in {directory_path}")
    if not os.path.isdir(directory_path):
        return []
    full_paths = [os.path.join(directory_path, file) for file in os.listdir(directory_path)]
    return [path for path in full_paths if is_image_file(path)]

def resize_image(image, target_width, target_height):
    original_width, original_height = image.size

    if target_width <= 0 or target_height <= 0:
        return image.copy() # Return a copy of the original or a small placeholder

    target_aspect = target_width / target_height
    image_aspect = original_width / original_height

    if image_aspect > target_aspect:
        new_width = target_width
        new_height = int(target_width / image_aspect)
    else:
        new_height = target_height
        new_width = int(target_height * image_aspect)

    new_width = max(1, new_width)
    new_height = max(1, new_height)

    return image.resize((new_width, new_height), resample=Image.LANCZOS)

def uniq_file_id(img_path, width=-1):
    try:
        real_path = os.path.realpath(img_path)
        mtime = os.path.getmtime(real_path)
    except FileNotFoundError:
        log_error(f"Error: Original image file not found for thumbnail generation: {img_path} resolves to {real_path}")
        return None
    except Exception as e:
        log_error(f"Warning: Could not get modification time for {real_path} (from {img_path}): {e}. Using a default value.")
        mtime = 0
    key = f"{real_path}_{width}_{mtime}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

PIL_CACHE = OrderedDict() # cache for full size pictures
QT_CACHE = OrderedDict()  # cache for QPixmap thumbnails, the pil is cached on disk

def get_full_size_image(img_path):
    cache_key = uniq_file_id(img_path)
    if cache_key in PIL_CACHE:
        PIL_CACHE.move_to_end(cache_key)
        return PIL_CACHE[cache_key]
    try:
        full_image = Image.open(img_path)
        PIL_CACHE[cache_key] = full_image
        if len(PIL_CACHE) > CACHE_SIZE:
            PIL_CACHE.popitem(last=False)
            assert len(PIL_CACHE) == CACHE_SIZE
        return full_image
    except Exception as e:
        log_error(f"Error loading image for {img_path}: {e}")
        return None
        
def get_or_make_pil_by_key(cache_key, img_path, thumbnail_max_size):
    thumbnail_size_str = str(thumbnail_max_size)
    thumbnail_cache_subdir = os.path.join(THUMBNAIL_CACHE_ROOT, thumbnail_size_str)
    os.makedirs(thumbnail_cache_subdir, exist_ok=True)
    cached_thumbnail_path = os.path.join(thumbnail_cache_subdir, f"{cache_key}.png")

    pil_image_thumbnail = None

    # try reading from on-disk cache
    if os.path.exists(cached_thumbnail_path):
        try:
            pil_image_thumbnail = Image.open(cached_thumbnail_path)
            # log_debug(f"found {img_path} at size {thumbnail_max_size} on disk.")
        except Exception as e:
            log_error(f"Error loading thumbnail for {img_path}: {e}")

    if pil_image_thumbnail is None:
        try:
            pil_image_thumbnail = resize_image(get_full_size_image(img_path), thumbnail_max_size, thumbnail_max_size)
            tmp_path = os.path.join(os.path.dirname(cached_thumbnail_path), "tmp-" + os.path.basename(cached_thumbnail_path))
            pil_image_thumbnail.save(tmp_path)
            os.replace(tmp_path, cached_thumbnail_path)
        except Exception as e:
            log_error(f"Error creating thumbnail for {img_path}: {e}")

    return pil_image_thumbnail

def get_or_make_pil(img_path, thumbnail_max_size):
    cache_key = uniq_file_id(img_path, thumbnail_max_size)
    # log_debug(f"cache_key for {img_path} @ {thumbnail_max_size} is {cache_key}")
    return get_or_make_pil_by_key(cache_key, img_path, thumbnail_max_size)

def make_qpixmap(pil_image):
    if pil_image is None:
        return QPixmap()
        
    if pil_image.mode not in ("RGB", "RGBA", "L", "1"):
        pil_image = pil_image.convert("RGBA")
    
    img_data = pil_image.tobytes("raw", "RGBA")
    qimage = QImage(img_data, pil_image.size[0], pil_image.size[1], QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)

def get_or_make_qpixmap_by_key(cache_key, img_path, thumbnail_max_size):
    if cache_key in QT_CACHE:
        QT_CACHE.move_to_end(cache_key)
        return QT_CACHE[cache_key]
    
    pil_image = get_or_make_pil_by_key(cache_key, img_path, thumbnail_max_size)
    if pil_image is None:
        return QPixmap()
        
    qpixmap = make_qpixmap(pil_image)
    QT_CACHE[cache_key] = qpixmap
    
    if len(QT_CACHE) > CACHE_SIZE:
        QT_CACHE.popitem(last=False)
        assert len(QT_CACHE) == CACHE_SIZE
    
    return qpixmap
     
def get_or_make_qpixmap(img_path, thumbnail_max_size):
    cache_key = uniq_file_id(img_path, thumbnail_max_size)
    return get_or_make_qpixmap_by_key(cache_key, img_path, thumbnail_max_size)


# --- dialogue box ---

def fallback_show_error(title, message):
    QMessageBox.critical(None, title, message)
    
def custom_message_dialog(parent, title, message, font=None):
    if font is None:
        font = QFont("Sans", 12)
    
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(title)
    dialog.setText(message)
    dialog.setFont(font)
    dialog.setStandardButtons(QMessageBox.Ok)
    dialog.exec()

    
# --- Wallpaper Setting Functions (Platform-Specific) ---

def set_wallpaper(image_path, error_callback=fallback_show_error):
    # returns True if the WP was set and False if not

    if platform.system() != "Linux":
        error_callback("Unsupported OS", f"Wallpaper setting not supported on {platform.system()}.")
        return False
        
    try:
        abs_path = os.path.abspath(image_path)
        file_uri = f"file://{abs_path}"
        
        # Detect desktop environment
        desktop_env = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        if not desktop_env and os.environ.get('DESKTOP_SESSION'):
            desktop_env = os.environ.get('DESKTOP_SESSION').lower()
            
        success = False
        
        # GNOME, Unity, Pantheon, Budgie
        if any(de in desktop_env for de in ['gnome', 'unity', 'pantheon', 'budgie']):
            # Try GNOME 3 approach first (newer versions)
            subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', file_uri])
            # For GNOME 40+ with dark mode support
            subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', file_uri])
            success = True
            
        # KDE Plasma
        elif 'kde' in desktop_env:
            # For KDE Plasma 5
            script = f"""
            var allDesktops = desktops();
            for (var i=0; i < allDesktops.length; i++) {{
                d = allDesktops[i];
                d.wallpaperPlugin = "org.kde.image";
                d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
                d.writeConfig("Image", "{abs_path}");
            }}
            """
            subprocess.run([ "qdbus", "org.kde.plasmashell", "/PlasmaShell",  "org.kde.PlasmaShell.evaluateScript", script])
            success = True
            
        # XFCE
        elif 'xfce' in desktop_env:
            # Get the current monitor
            try:
                props = subprocess.check_output(['xfconf-query', '-c', 'xfce4-desktop', '-p', '/backdrop', '-l']).decode('utf-8')
                monitors = set([p.split('/')[2] for p in props.splitlines() if p.endswith('last-image')])
                
                for monitor in monitors:
                    # Find all properties for this monitor
                    monitor_props = [p for p in props.splitlines() if f'/backdrop/screen0/{monitor}/' in p and p.endswith('last-image')]
                    for prop in monitor_props:
                        subprocess.run([ "xfconf-query", "-c", "xfce4-desktop",  "-p", f"{prop}",  "-s", f"{abs_path}" ])
                success = True
            except:
                # Fallback for older XFCE
                subprocess.run([ "xfconf-query", "-c", "xfce4-desktop", "-p", "/backdrop/screen0/monitor0/workspace0/last-image", "-s", f"{abs_path}" ])
                success = True
                
        # Cinnamon
        elif 'cinnamon' in desktop_env:
            subprocess.run([ "gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", f"{file_uri}" ])
            success = True
            
        # MATE
        elif 'mate' in desktop_env:
            subprocess.run([ "gsettings", "set", "org.mate.background", "picture-filename", f"{abs_path}" ])
            success = True
            
        # LXQt, LXDE
        elif 'lxqt' in desktop_env or 'lxde' in desktop_env:
            # For PCManFM-Qt
            subprocess.run([ "pcmanfm-qt", f"--set-wallpaper={abs_path}" ])
            # For PCManFM
            subprocess.run([ "pcmanfm", f"--set-wallpaper={abs_path}" ])
            success = True
            
        # i3wm, sway and other tiling window managers often use feh
        elif any(de in desktop_env for de in ['i3', 'sway']):
            subprocess.run([ "feh", "--bg-fill", f"{abs_path}" ])
            success = True
            
        # Fallback method using feh (works for many minimal window managers)
        elif not success:
            # Try generic methods
            methods = [
                [ "feh", "--bg-fill", f"{abs_path}" ],
                [ "nitrogen", "--set-scaled", f"{abs_path}" ],
                [ "gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"{file_uri}" ]
            ]
            
            for method in methods:
                exit_code = subprocess.run(method)
                if exit_code == 0:
                    success = True
                    break
                    
        if success:
            return True
        else:
            error_callback("Desktop Environment Not Detected", 
                           f"Couldn't detect your desktop environment ({desktop_env}). Try installing 'feh' package and retry.")
            return False
            
    except Exception as e:
        error_callback("Wallpaper Error", f"Failed to set wallpaper: {e}")
        return False


# --- predictive preloading of thumbnails ---
    
def get_parent_directory(path):
    return os.path.dirname(path)

def list_subdirectories(parent_directory_path):
    if not os.path.isdir(parent_directory_path):
        return []

    subdirectories = []
    for item_name in os.listdir(parent_directory_path):
        item_path = os.path.join(parent_directory_path, item_name)
        if os.path.isdir(item_path):
            subdirectories.append(item_path)
    
    subdirectories.sort() # Optional: keep the list sorted
    return subdirectories

def list_relevant_files(dir_path):
    # log_debug(f"list relevant files for {dir_path}")
    file_list = list_image_files(dir_path)
    file_list.extend(list_image_files(get_parent_directory(dir_path)))
    for subdir in list_subdirectories(dir_path):
        file_list.extend(list_image_files(subdir))
    return file_list


class BackgroundWorker(QObject):
    finished = Signal()
    
    def __init__(self, path, width):
        super().__init__()
        self.keep_running = True
        self.current_size = width
        self.current_dir = path
        self.path_name_queue = queue.Queue()
        self.block = threading.Event()
        
        self.worker_thread = QThread()
        self.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.process)
        self.worker_thread.start()
    
    def process(self):
        while self.keep_running:
            old_size = self.current_size
            old_directory = self.current_dir
            to_do_list = list_relevant_files(old_directory)
            for path_name in to_do_list:
                if not self.keep_running:
                    return
                self.barrier()
                if self.keep_running and (old_size == self.current_size) and (old_directory == self.current_dir):
                    # log_debug(f"background: {path_name}")
                    self.path_name_queue.put(path_name)
                else:
                    break
            while self.keep_running and (old_size == self.current_size) and (old_directory == self.current_dir):
                time.sleep(2)

    def pause(self):
        self.block.clear()

    def resume(self):
        self.block.set()

    def barrier(self):
        self.block.wait()

    def run(self, dir_path, size):
        self.pause()
        self.current_size = size
        self.current_dir = dir_path
        self.resume()
        
    def stop(self):
        self.keep_running = False
        self.resume()
        if self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()


# --- drag and drop support ---

class DragHelper(QObject):
    """Helper class to manage drag and drop functionality"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_timer = None
        self.drag_start_pos = None
        self.dragging_widget = None
        self.drag_object = None
        self.drag_threshold = 5
        self.drag_delay_ms = 250
        
    def start_tracking(self, widget, event, make_ghost, click_handler, button=Qt.LeftButton,
                      drop_handler='handle_drop', right_drop_handler=None):
        """Begin tracking a potential drag operation"""
        if self.drag_timer and self.drag_timer.isActive():
            self.drag_timer.stop()
            
        self.drag_start_pos = event.globalPos()
        self.dragging_widget = widget
        self.make_ghost = make_ghost
        self.click_handler = click_handler
        self.drop_handler = drop_handler
        self.right_drop_handler = right_drop_handler
        self.button = button
        
        # Set up the timer for delayed drag start
        self.drag_timer = QTimer()
        self.drag_timer.setSingleShot(True)
        self.drag_timer.timeout.connect(self.start_drag)
        self.drag_timer.start(self.drag_delay_ms)
        
    def process_motion(self, event):
        """Handle mouse motion during potential drag operation"""
        if not self.drag_timer or not self.drag_start_pos:
            return False
            
        # Calculate distance moved
        delta = (event.globalPos() - self.drag_start_pos)
        distance = math.sqrt(delta.x()**2 + delta.y()**2)
        
        # If moved beyond threshold, start drag
        if distance > self.drag_threshold:
            self.drag_timer.stop()
            self.start_drag()
            return True
            
        return False
    
    def process_release(self, event):
        """Handle button release event"""
        if not self.drag_timer:
            return False
            
        if self.drag_timer.isActive():
            # If timer is still active, it's a click not a drag
            self.drag_timer.stop()
            if self.click_handler:
                self.click_handler(event)
            result = True
        else:
            # Drag was in progress, handle drop
            result = False
            
        self.reset()
        return result
    
    def start_drag(self):
        """Start the actual dragging operation"""
        if not self.dragging_widget or not self.make_ghost:
            return
        
        self.drag_object = QDrag(self.dragging_widget)
        
        # Create ghost/preview image for dragging
        ghost_pixmap = self.make_ghost(self.dragging_widget, 
                                   self.drag_start_pos.x(), 
                                   self.drag_start_pos.y())
        
        if isinstance(ghost_pixmap, QPixmap):
            self.drag_object.setPixmap(ghost_pixmap)
            # Set hotspot to center of pixmap
            self.drag_object.setHotSpot(QPoint(ghost_pixmap.width()//2, ghost_pixmap.height()//2))
        
        # Set up MIME data with custom format
        mime_data = QMimeData()
        mime_data.setData("application/x-kubux-image-item", QByteArray())
        self.drag_object.setMimeData(mime_data)
        
        # Execute the drag operation
        drop_action = self.drag_object.exec_(Qt.CopyAction | Qt.MoveAction)
        
        # Clean up
        self.reset()
    
    def find_drop_target(self, position):
        """Find suitable drop target widget at given position"""
        app = QApplication.instance()
        widget = app.widgetAt(position)
        
        if not widget:
            return None
            
        # Try to find a parent that can handle our drop
        while widget:
            if hasattr(widget, self.drop_handler):
                return widget
            
            if self.right_drop_handler and hasattr(widget, self.right_drop_handler):
                return widget
                
            widget = widget.parent()
            
        return None
    
    def reset(self):
        """Reset all drag tracking state"""
        self.drag_timer = None
        self.drag_start_pos = None
        self.dragging_widget = None
        self.drag_object = None


# --- UI components ---

class ImageViewer(QMainWindow):
    """Image viewer window - displays a single image with zoom and pan capabilities"""
    
    def __init__(self, parent, image_info):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Image Viewer")
        
        # Extract image info
        self.image_path = image_info[0]
        self.window_geometry = image_info[1]
        self.is_fullscreen = image_info[2]
        
        self.file_name = os.path.basename(self.image_path)
        self.dir_name = os.path.dirname(self.image_path)
        
        # Image state
        self.original_image = get_full_size_image(self.image_path)
        self.display_pixmap = QPixmap()
        self.fit_to_window = True
        self.zoom_factor = 1.0
        
        # Pan state
        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        
        # Set up UI
        self._create_ui()
        self._setup_shortcuts()
        
        # Apply stored geometry if available
        if self.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(self.window_geometry.encode()))
        else:
            # Default size if no geometry is provided
            self.resize(1024, 768)
            
        # Update initial image
        self._update_display_image()
        
        # Apply fullscreen mode
        self.set_screen_mode(self.is_fullscreen)
        
        # Show the window
        self.show()
        self.activateWindow()
        self.raise_()
    
    def _create_ui(self):
        """Create the UI components for the viewer"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setBackgroundRole(QPalette.Dark)
        
        # Create image label
        self.image_label = QLabel()
        self.image_label.setBackgroundRole(QPalette.Base)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setScaledContents(False)
        self.image_label.setAlignment(Qt.AlignCenter)
        
        # Set up mouse tracking for panning
        self.image_label.setMouseTracking(True)
        
        # Set up mouse events
        self.image_label.mousePressEvent = self._on_mouse_press
        self.image_label.mouseMoveEvent = self._on_mouse_move
        self.image_label.mouseReleaseEvent = self._on_mouse_release
        self.image_label.wheelEvent = self._on_mouse_wheel
        
        # Add label to scroll area
        self.scroll_area.setWidget(self.image_label)
        
        # Add scroll area to main layout
        main_layout.addWidget(self.scroll_area)
        
        # Create filename widget at the bottom
        self.filename_widget = EditableLabelWithCopy(
            central_widget,
            initial_text=self.file_name,
            info="",
            font=get_linux_ui_font()
        )
        self.filename_widget.rename_requested.connect(self._rename_current_image)
        
        # Add filename widget to main layout
        main_layout.addWidget(self.filename_widget)
        
        # Set image dimensions in info label
        if self.original_image:
            w, h = self.original_image.size
            self.filename_widget.set_info(f"{w}x{h}")
        
        # Set focus
        self.setFocus()
        
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Zoom in/out shortcuts
        zoom_in_action = QAction(self)
        zoom_in_action.setShortcut(Qt.Key_Plus)
        zoom_in_action.triggered.connect(self._zoom_in)
        self.addAction(zoom_in_action)
        
        zoom_out_action = QAction(self)
        zoom_out_action.setShortcut(Qt.Key_Minus)
        zoom_out_action.triggered.connect(self._zoom_out)
        self.addAction(zoom_out_action)
        
        # Reset zoom
        reset_zoom_action = QAction(self)
        reset_zoom_action.setShortcut(Qt.Key_0)
        reset_zoom_action.triggered.connect(self._reset_zoom)
        self.addAction(reset_zoom_action)
        
        # Fullscreen
        fullscreen_action = QAction(self)
        fullscreen_action.setShortcut(Qt.Key_F)
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(fullscreen_action)
        
        # F11 also toggles fullscreen
        f11_action = QAction(self)
        f11_action.setShortcut(Qt.Key_F11)
        f11_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(f11_action)
        
        # Escape to close if fullscreen, otherwise just close on Escape
        escape_action = QAction(self)
        escape_action.setShortcut(Qt.Key_Escape)
        escape_action.triggered.connect(self._on_escape)
        self.addAction(escape_action)
    
    def _update_display_image(self):
        """Update the displayed image based on current zoom settings"""
        if not self.original_image:
            return
            
        # Get the original image dimensions
        orig_width, orig_height = self.original_image.size
        
        # Calculate target dimensions based on fit mode and zoom factor
        if self.fit_to_window:
            # Calculate available space
            view_width = self.scroll_area.viewport().width()
            view_height = self.scroll_area.viewport().height()
            
            if view_width <= 1 or view_height <= 1:
                view_width = 800
                view_height = 600
            
            # Calculate scale to fit
            scale_width = view_width / orig_width
            scale_height = view_height / orig_height
            scale = min(scale_width, scale_height)
            
            # Update zoom factor based on fit
            self.zoom_factor = scale
            
            # Calculate new dimensions
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
        else:
            # Use current zoom factor
            new_width = int(orig_width * self.zoom_factor)
            new_height = int(orig_height * self.zoom_factor)
        
        # Create the resized pixmap
        pil_image = resize_image(self.original_image, new_width, new_height)
        self.display_pixmap = make_qpixmap(pil_image)
        
        # Update the label with new pixmap
        self.image_label.setPixmap(self.display_pixmap)
        self.image_label.resize(self.display_pixmap.size())
        
        # Update scroll area if needed
        if self.fit_to_window:
            # Center the image when it fits the view
            self.scroll_area.horizontalScrollBar().setValue(0)
            self.scroll_area.verticalScrollBar().setValue(0)
    
    def set_screen_mode(self, is_fullscreen):
        """Set fullscreen mode on or off"""
        self.is_fullscreen = is_fullscreen
        if is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
        
        # Update image after screen mode change
        self._update_display_image()
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        self.set_screen_mode(not self.is_fullscreen)
    
    def _zoom_in(self):
        """Zoom in the image"""
        self.fit_to_window = False
        self.zoom_factor *= 1.25
        self._update_display_image()
        
    def _zoom_out(self):
        """Zoom out the image"""
        self.fit_to_window = False
        self.zoom_factor /= 1.25
        
        # Limit minimum zoom
        min_zoom = 0.1
        if self.zoom_factor < min_zoom:
            self.fit_to_window = True
            
        self._update_display_image()
    
    def _reset_zoom(self):
        """Reset zoom to fit the window"""
        self.fit_to_window = True
        self._update_display_image()
    
    def _on_mouse_press(self, event):
        """Handle mouse button press"""
        if event.button() == Qt.LeftButton:
            # Start panning
            self.panning = True
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
            self.setCursor(Qt.ClosedHandCursor)
    
    def _on_mouse_move(self, event):
        """Handle mouse movement"""
        if self.panning:
            # Calculate the distance moved
            dx = self.pan_start_x - event.x()
            dy = self.pan_start_y - event.y()
            
            # Update scrollbars
            hbar = self.scroll_area.horizontalScrollBar()
            vbar = self.scroll_area.verticalScrollBar()
            hbar.setValue(hbar.value() + dx)
            vbar.setValue(vbar.value() + dy)
            
            # Update starting point for next movement
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
    
    def _on_mouse_release(self, event):
        """Handle mouse button release"""
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
    
    def _on_mouse_wheel(self, event):
        """Handle mouse wheel for zooming"""
        delta = event.angleDelta().y()
        
        if delta > 0:
            # Zoom in
            self._zoom_in()
        else:
            # Zoom out
            self._zoom_out()
    
    def _on_escape(self):
        """Handle Escape key press"""
        if self.is_fullscreen:
            # Exit fullscreen mode
            self.toggle_fullscreen()
        else:
            # Close the window
            self.close()
    
    def _rename_current_image(self, old_name, new_name):
        """Rename the current image file"""
        try:
            new_path = os.path.join(self.dir_name, new_name)
            if os.path.exists(new_path):
                return
                
            os.rename(self.image_path, new_path)
            self.image_path = new_path
            self.file_name = os.path.basename(self.image_path)
            self.setWindowTitle(f"{self.file_name}")
        except Exception as e:
            log_error(f"Error renaming file from {old_name} to {new_name}: {e}")
    
    def get_image_info(self):
        """Return information about the current image view"""
        # Convert geometry to hex string for storage
        geometry_hex = self.saveGeometry().toHex().data().decode()
        return self.image_path, geometry_hex, self.is_fullscreen
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.parent():
            # Notify parent that we're closing
            self.parent().remove_image_viewer(self)
        event.accept()


class ImagePicker(QMainWindow):
    """A window for displaying image thumbnails in a directory"""
    
    directory_changed = Signal(str)
    
    def __init__(self, parent=None, initial_dir=None, picker_id=0):
        super().__init__(parent)
        self.picker_id = picker_id
        self.image_dir = initial_dir if initial_dir else PICTURES_DIR
        self.image_path = None
        self.selected_thumbnails = set()
        self.viewer_windows = []
        self.list_cmd = "ls"
        self.thumbnail_dim = DEFAULT_THUMBNAIL_DIM
        
        # UI setup
        self._create_ui()
        
        # Directory watcher
        self.watcher = DirectoryWatcher(self)
        self.watcher.start_watching(self.image_dir)
        
        # Background preloading
        self.background_worker = BackgroundWorker(self.image_dir, self.thumbnail_dim)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._check_queue)
        self.update_timer.start(50)  # 50ms interval
        
        self.setWindowTitle(f"Image Picker {self.picker_id}")
        self.resize(800, 600)
        self.show()
    
    def _create_ui(self):
        """Create the UI components"""
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)
        
        # Create bread crumb navigator for directory navigation
        self.breadcrumbs = BreadCrumbNavigator(self)
        self.breadcrumbs.navigate_requested.connect(self.change_directory)
        self.breadcrumbs.set_path(self.image_dir)
        
        # Create thumbnail grid for images
        self.thumbnail_grid = DirectoryThumbnailGrid(
            self,
            self.image_dir,
            self.list_cmd,
            self.thumbnail_dim,
            static_button_config_callback=self._static_button_config,
            dynamic_button_config_callback=self._dynamic_button_config
        )
        
        # Create directory path editable label
        self.path_label = EditableLabelWithCopy(
            self, 
            initial_text=self.image_dir,
            info="Dir: ",
            font=get_linux_ui_font()
        )
        self.path_label.rename_requested.connect(self._on_path_edit)
        
        # Create thumbnail size slider
        size_layout = QHBoxLayout()
        size_label = QLabel("Size:")
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setMinimum(50)
        self.size_slider.setMaximum(400)
        self.size_slider.setValue(self.thumbnail_dim)
        self.size_slider.setTickPosition(QSlider.TicksBelow)
        self.size_slider.setTickInterval(50)
        self.size_slider.valueChanged.connect(self._on_size_change)
        
        size_layout.addWidget(size_label)
        size_layout.addWidget(self.size_slider)
        
        # Add all components to main layout
        main_layout.addWidget(self.breadcrumbs)
        main_layout.addWidget(self.path_label)
        main_layout.addLayout(size_layout)
        main_layout.addWidget(self.thumbnail_grid, 1)  # Give stretch factor to grid
        
        # Create context menu
        self.thumbnail_context_menu = QMenu(self)
        self.open_action = QAction("Open", self)
        self.open_action.triggered.connect(self._open_context_menu_image)
        self.wallpaper_action = QAction("Set as Wallpaper", self)
        self.wallpaper_action.triggered.connect(self._set_wallpaper)
        self.thumbnail_context_menu.addAction(self.open_action)
        self.thumbnail_context_menu.addAction(self.wallpaper_action)
        
        # Set up keyboard shortcuts
        self._setup_shortcuts()
    
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        # Escape to clear selection
        escape_action = QAction(self)
        escape_action.setShortcut(Qt.Key_Escape)
        escape_action.triggered.connect(self.clear_selection)
        self.addAction(escape_action)
        
        # Ctrl+A to select all
        select_all_action = QAction(self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self.select_all)
        self.addAction(select_all_action)
    
    def _static_button_config(self, button, img_path):
        """Configure static properties of thumbnail buttons"""
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, b=button: self._show_context_menu(b, pos))
        button.clicked.connect(lambda checked=False, b=button: self._on_thumbnail_click(b))
        button.mouseDoubleClickEvent = lambda event, b=button: self._on_thumbnail_double_click(b, event)
        button.mousePressEvent = lambda event, b=button: self._on_thumbnail_press(b, event)
        button.mouseMoveEvent = lambda event, b=button: self._on_thumbnail_move(b, event)
        button.mouseReleaseEvent = lambda event, b=button: self._on_thumbnail_release(b, event)
        
    def _dynamic_button_config(self, button, img_path):
        """Configure dynamic properties of thumbnail buttons"""
        is_selected = img_path in self.selected_thumbnails
        button.setProperty("selected", is_selected)
        
    def _on_thumbnail_click(self, button):
        """Handle thumbnail button click"""
        img_path = button.property("img_path")
        if not img_path:
            return
        
        self.image_path = img_path
        
        # Update selection state
        if img_path in self.selected_thumbnails:
            self.selected_thumbnails.remove(img_path)
        else:
            self.selected_thumbnails.add(img_path)
        
        # Refresh UI to show selection changes
        self.thumbnail_grid.refresh()
    
    def _on_thumbnail_double_click(self, button, event):
        """Handle thumbnail double click to open image"""
        img_path = button.property("img_path")
        if img_path:
            self.open_image(img_path)
    
    def _on_thumbnail_press(self, button, event):
        """Handle mouse press on thumbnail (for drag and drop)"""
        if not hasattr(self, 'drag_helper'):
            self.drag_helper = DragHelper(self)
        
        # Start tracking for potential drag operation
        self.drag_helper.start_tracking(
            button, 
            event, 
            lambda widget, x, y: self._make_drag_ghost(widget), 
            lambda event: self._on_thumbnail_click(button),
            Qt.LeftButton,
            'handle_drop',
            'handle_right_drop'
        )
        return True
    
    def _on_thumbnail_move(self, button, event):
        """Handle mouse movement for drag and drop"""
        if hasattr(self, 'drag_helper'):
            return self.drag_helper.process_motion(event)
        return False
    
    def _on_thumbnail_release(self, button, event):
        """Handle mouse button release for drag and drop"""
        if hasattr(self, 'drag_helper'):
            return self.drag_helper.process_release(event)
        return False
    
    def _make_drag_ghost(self, button):
        """Create ghost image for drag and drop"""
        img_path = button.property("img_path")
        pixmap = button.property("pixmap")
        
        if pixmap and not pixmap.isNull():
            # Create a semi-transparent version of the pixmap
            ghost_pixmap = QPixmap(pixmap.size())
            ghost_pixmap.fill(Qt.transparent)
            
            painter = QPainter(ghost_pixmap)
            painter.setOpacity(0.7)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()
            
            return ghost_pixmap
        
        # Fallback: Create a simple colored rectangle
        ghost_pixmap = QPixmap(100, 100)
        ghost_pixmap.fill(QColor(0, 0, 255, 128))
        return ghost_pixmap
    
    def _show_context_menu(self, button, pos):
        """Show context menu for thumbnail"""
        img_path = button.property("img_path")
        if not img_path:
            return
        
        # Set current image path
        self.image_path = img_path
        
        # Show menu at cursor position
        global_pos = button.mapToGlobal(pos)
        self.thumbnail_context_menu.exec_(global_pos)
    
    def _open_context_menu_image(self):
        """Open the image from context menu"""
        if self.image_path:
            self.open_image(self.image_path)
    
    def _set_wallpaper(self):
        """Set the selected image as wallpaper"""
        if not self.image_path:
            return
        
        if not set_wallpaper(self.image_path, lambda title, msg: custom_message_dialog(self, title, msg)):
            custom_message_dialog(self, "Error", "Failed to set wallpaper")
    
    def open_image(self, img_path=None):
        """Open an image in the viewer window"""
        if not img_path and self.image_path:
            img_path = self.image_path
        elif not img_path:
            return
        
        # Check if image already open in a viewer
        for viewer in self.viewer_windows:
            if viewer.image_path == img_path:
                # Already open, just activate it
                viewer.activateWindow()
                viewer.raise_()
                return
        
        # Create a new viewer
        viewer_info = (img_path, None, False)  # (path, geometry, fullscreen)
        viewer = ImageViewer(self, viewer_info)
        self.viewer_windows.append(viewer)
    
    def _on_path_edit(self, old_path, new_path):
        """Handle directory path edit"""
        if not new_path:
            return
        
        # Try to change to the new directory
        if os.path.isdir(new_path):
            self.change_directory(new_path)
        elif os.path.isdir(os.path.dirname(new_path)):
            # If user entered a subdirectory that doesn't exist yet, create it
            try:
                os.makedirs(new_path, exist_ok=True)
                self.change_directory(new_path)
            except Exception as e:
                log_error(f"Error creating directory '{new_path}': {e}")
                # Reset to old path
                self.path_label.set_text(old_path)
        else:
            # Reset to old path
            self.path_label.set_text(old_path)
    
    def _on_size_change(self, value):
        """Handle thumbnail size slider change"""
        self.thumbnail_dim = value
        
        # Update background worker
        self.background_worker.run(self.image_dir, self.thumbnail_dim)
        
        # Update thumbnail grid
        self.thumbnail_grid.set_size_path_and_command(self.thumbnail_dim, self.image_dir, self.list_cmd)
    
    def change_directory(self, new_dir):
        """Change the current directory"""
        if not os.path.isdir(new_dir):
            return
        
        # Update directory
        self.image_dir = os.path.normpath(new_dir)
        
        # Update UI
        self.path_label.set_text(self.image_dir)
        self.breadcrumbs.set_path(self.image_dir)
        
        # Clear selection
        self.selected_thumbnails.clear()
        
        # Update watcher
        self.watcher.change_dir(self.image_dir)
        
        # Update background worker
        self.background_worker.run(self.image_dir, self.thumbnail_dim)
        
        # Update thumbnail grid
        self.thumbnail_grid.set_size_path_and_command(self.thumbnail_dim, self.image_dir, self.list_cmd)
        
        # Emit signal
        self.directory_changed.emit(self.image_dir)
    
    def select_all(self):
        """Select all images in the current directory"""
        # Get all image files in the directory
        all_images = self.thumbnail_grid._files
        
        # Add all to selection
        self.selected_thumbnails.update(all_images)
        
        # Refresh UI
        self.thumbnail_grid.refresh()
    
    def clear_selection(self):
        """Clear the current selection"""
        self.selected_thumbnails.clear()
        
        # Refresh UI
        self.thumbnail_grid.refresh()
    
    def move_selected_files_to_directory(self, source_path, target_dir_path):
        """Move all selected files to the target directory"""
        if not self.selected_thumbnails:
            # If no selection, move the source file if provided
            if source_path:
                self._move_file_to_dir(source_path, target_dir_path)
        else:
            # Move all selected files
            for img_path in list(self.selected_thumbnails):
                self._move_file_to_dir(img_path, target_dir_path)
            
            # Clear selection after move
            self.selected_thumbnails.clear()
        
        # Refresh the view
        self.thumbnail_grid.regrid()
    
    def move_file_to_directory(self, source_path, target_dir_path):
        """Move a single file to the target directory"""
        if not source_path or source_path.lower() == 'none':
            return
        
        self._move_file_to_dir(source_path, target_dir_path)
        
        # Remove from selection if it was selected
        if source_path in self.selected_thumbnails:
            self.selected_thumbnails.remove(source_path)
        
        # Refresh the view
        self.thumbnail_grid.regrid()
    
    def _move_file_to_dir(self, source_path, target_dir_path):
        """Helper to move a file and update UI accordingly"""
        # Check source and target
        if not os.path.exists(source_path):
            return
            
        if not os.path.isdir(target_dir_path):
            try:
                os.makedirs(target_dir_path, exist_ok=True)
            except Exception as e:
                log_error(f"Error creating directory '{target_dir_path}': {e}")
                return
        
        # Move the file
        new_path = move_file_to_directory(source_path, target_dir_path)
        
        if new_path:
            log_action(f"Moved '{os.path.basename(source_path)}' to '{target_dir_path}'")
            
            # If target dir is the same as our current dir, we need to update selection
            if os.path.realpath(target_dir_path) == os.path.realpath(self.image_dir):
                # Update selection with new path
                if source_path in self.selected_thumbnails:
                    self.selected_thumbnails.remove(source_path)
                    self.selected_thumbnails.add(new_path)
    
    def remove_image_viewer(self, viewer):
        """Remove a viewer window from our tracking list"""
        if viewer in self.viewer_windows:
            self.viewer_windows.remove(viewer)
    
    def _check_queue(self):
        """Check the background worker queue for new images to preload"""
        try:
            while not self.background_worker.path_name_queue.empty():
                path = self.background_worker.path_name_queue.get_nowait()
                # Silently preload the image
                get_or_make_qpixmap(path, self.thumbnail_dim)
        except Exception as e:
            log_error(f"Error in background worker: {e}")
    
    def broadcast_contents_change(self):
        """Handle directory contents change event"""
        self.thumbnail_grid.regrid()
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop background worker and watcher
        if hasattr(self, 'background_worker'):
            self.background_worker.stop()
        
        if hasattr(self, 'watcher'):
            self.watcher.stop_watching()
        
        # Close all viewer windows
        for viewer in self.viewer_windows:
            viewer.close()
        
        # Accept the close event
        event.accept()


class ImageBrowser(QMainWindow):
    """Main application window that manages multiple image pickers"""
    
    def __init__(self):
        super().__init__()
        
        # App settings
        self.app_settings = self._load_app_settings()
        self.current_picker_id = 0
        self.pickers = {}
        
        # Set up UI
        self._create_ui()
        
        # Create initial picker
        self._create_picker()
        
        self.setWindowTitle("Image Browser")
        self.resize(1200, 800)
        self.show()
    
    def _create_ui(self):
        """Set up the user interface"""
        # Create central widget
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        
        # Create main layout
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create toolbar
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        
        # Add toolbar actions
        new_picker_action = QAction("New Picker", self)
        new_picker_action.triggered.connect(self._create_picker)
        toolbar.addAction(new_picker_action)
        
        open_dir_action = QAction("Open Directory", self)
        open_dir_action.triggered.connect(self._open_directory)
        toolbar.addAction(open_dir_action)
        
        # Create status bar
        self.statusBar()
    
    def _create_picker(self, initial_dir=None):
        """Create a new image picker window"""
        picker_id = self.current_picker_id
        self.current_picker_id += 1
        
        # Create the picker
        picker = ImagePicker(None, initial_dir, picker_id)  # Create as independent window
        picker.directory_changed.connect(lambda path: self._update_recent_dirs(path))
        
        # Track the picker
        self.pickers[picker_id] = picker
        
        return picker
    
    def _open_directory(self):
        """Open a directory browser dialog"""
        dir_dialog = QFileDialog(self)
        dir_dialog.setFileMode(QFileDialog.Directory)
        dir_dialog.setOption(QFileDialog.ShowDirsOnly, True)
        
        # Start in recent directory if available
        if self.app_settings.get('recent_dirs'):
            dir_dialog.setDirectory(self.app_settings['recent_dirs'][0])
        
        if dir_dialog.exec_():
            selected_dirs = dir_dialog.selectedFiles()
            if selected_dirs:
                # Create a new picker for the selected directory
                self._create_picker(selected_dirs[0])
    
    def _update_recent_dirs(self, directory):
        """Update the list of recently used directories"""
        # Make sure we have a list for recent directories
        if 'recent_dirs' not in self.app_settings:
            self.app_settings['recent_dirs'] = []
        
        # Update the list - move to front or add
        prepend_or_move_to_front(directory, self.app_settings['recent_dirs'])
        
        # Limit the list size
        if len(self.app_settings['recent_dirs']) > 10:
            self.app_settings['recent_dirs'] = self.app_settings['recent_dirs'][:10]
        
        # Save the settings
        self._save_app_settings()
    
    def _load_app_settings(self):
        """Load application settings from file"""
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                log_error(f"Error loading app settings: {e}")
        
        # Default settings
        return {
            'recent_dirs': [PICTURES_DIR],
            'thumbnail_size': DEFAULT_THUMBNAIL_DIM
        }
    
    def _save_app_settings(self):
        """Save application settings to file"""
        try:
            with open(APP_SETTINGS_FILE, 'w') as f:
                json.dump(self.app_settings, f, indent=2)
        except Exception as e:
            log_error(f"Error saving app settings: {e}")
    
    def closeEvent(self, event):
        """Handle main window close event"""
        # Close all picker windows
        for picker in list(self.pickers.values()):
            picker.close()
        
        # Save settings
        self._save_app_settings()
        
        # Accept the close event
        event.accept()


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("KuBux Image Manager")
    
    # Set application icon
    icon_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "app-icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    main_window = ImageBrowser()
    app.exec_()
