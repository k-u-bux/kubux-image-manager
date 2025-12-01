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
import sys
from collections import OrderedDict
from datetime import datetime

# PySide6 imports
from PySide6.QtCore import (Qt, QSize, QPoint, QRect, QTimer, Signal, QObject, 
                            QEvent, QMimeData, QByteArray)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, 
                              QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, 
                              QTextEdit, QScrollArea, QSlider, QFileDialog,
                              QDialog, QMessageBox, QFrame, QScrollBar, QSizePolicy,
                              QListWidget, QListWidgetItem, QSplitter, QSpacerItem)
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QFont, QFontMetrics,
                          QTextCursor, QDrag, QTextCharFormat, QIcon, QAction, 
                          QCursor, QKeySequence, QPalette, QTextBlockFormat)

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
    try:
        subprocess.run(["which", "gsettings"], check=True, capture_output=True)
        font_info_str = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "font-name"],
            capture_output=True, text=True, check=True
        ).stdout.strip().strip("'")
        parts = font_info_str.rsplit(' ', 1)
        font_name = "Sans"
        font_size = 10
        if len(parts) == 2 and parts[1].isdigit():
            font_name = parts[0]
            font_size = int(parts[1])
        else:
            try:
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
        log_error("gsettings command not found or failed.")
        return "Sans", 10
    except Exception as e:
        log_error(f"An error occurred while getting GTK font settings: {e}")
        return "Sans", 10

def get_kde_ui_font():
    try:
        subprocess.run(["which", "kreadconfig5"], check=True, capture_output=True)
        font_string = subprocess.run(
            ["kreadconfig5", "--file", "kdeglobals", "--group", "General", "--key", "font", 
             "--default", "Sans,10,-1,5,50,0,0,0,0,0"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        parts = font_string.split(',')
        if len(parts) >= 2:
            font_name = parts[0].strip()
            font_size = int(parts[1].strip())
            return font_name, font_size
        else:
            log_error(f"Warning: Unexpected KDE font format: '{font_string}'")
            return "Sans", 10
    except subprocess.CalledProcessError:
        log_error("kreadconfig5 command not found or failed.")
        return "Sans", 10
    except Exception as e:
        log_error(f"An error occurred while getting KDE font settings: {e}")
        return "Sans", 10

def get_linux_system_ui_font_info():
    desktop_session = os.environ.get("XDG_CURRENT_DESKTOP")
    if not desktop_session:
        desktop_session = os.environ.get("DESKTOP_SESSION")
    if desktop_session and ("GNOME" in desktop_session.upper() or
                            "CINNAMON" in desktop_session.upper() or
                            "XFCE" in desktop_session.upper() or
                            "MATE" in desktop_session.upper()):
        return get_gtk_ui_font()
    elif desktop_session and "KDE" in desktop_session.upper():
        return get_kde_ui_font()
    else:
        log_error("Could not reliably detect desktop environment.")
        font_name, font_size = get_gtk_ui_font()
        if font_name != "Sans" or font_size != 10:
            return font_name, font_size
        return "Sans", 10

def get_linux_ui_font_info():
    return get_linux_system_ui_font_info()

def get_linux_ui_font():
    font_name, font_size = get_linux_ui_font_info()
    return QFont(font_name, font_size)

    
# --- list ops ---

def copy_truish(the_list):
     return [entry for entry in the_list if entry]

def remove_falsy(the_list):
    new_list = copy_truish(the_list)
    the_list.clear()
    the_list.extend(new_list)

def copy_uniq(the_list):
    helper = set()
    result = []
    for entry in the_list:
        if not entry in helper:
            helper.add(entry)
            result.append(entry)
    return result

def make_uniq(the_list):
    new_list = copy_uniq(the_list)
    the_list.clear()
    the_list.extend(new_list)

def prepend_or_move_to_front(entry, the_list):
    the_list.insert(0, entry)
    make_uniq(the_list)
    
        
# --- file ops ---

def is_file_below_dir(file_path, dir_path):
    file_dir_path = os.path.realpath(os.path.dirname(file_path))
    dir_path = os.path.realpath(dir_path)
    return file_dir_path.startswith(dir_path)

def is_file_in_dir(file_path, dir_path):
    file_dir_path = os.path.realpath(os.path.dirname(file_path))
    dir_path = os.path.realpath(dir_path)
    return dir_path == file_dir_path
    
def execute_shell_command(command):
    result = subprocess.run(command, shell=True)

def execute_shell_command_with_capture(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
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
            listing.append(os.path.normpath(path))
        else:
            listing.append(os.path.normpath(os.path.join(dir, path)))
    return [path for path in listing if is_image_file(path) and is_file_below_dir(path, dir)]
    
def move_file_to_directory(file_path, target_dir_path):
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file or link not found: '{file_path}'")
        if not os.path.isdir(target_dir_path):
            os.makedirs(target_dir_path, exist_ok=True)
        item_name = os.path.basename(file_path)
        new_path = os.path.normpath(os.path.join(target_dir_path, item_name))
        if os.path.islink(file_path):
            link_target = os.readlink(file_path)
            if os.path.isabs(link_target):
                shutil.move(file_path, new_path)
            else:
                original_link_dir = os.path.dirname(os.path.abspath(file_path))
                target_abs_path = os.path.normpath(os.path.join(original_link_dir, link_target))
                new_link_dir = os.path.abspath(target_dir_path)
                new_relative_path = os.path.relpath(target_abs_path, new_link_dir)
                os.remove(file_path)
                os.symlink(new_relative_path, new_path)
        else:
            shutil.move(file_path, new_path)
        return os.path.normpath(new_path)
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
        QTimer.singleShot(0, self.image_picker.master.broadcast_contents_change)


class DirectoryWatcher():
    def __init__(self, image_picker):
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

def resize_image(image, target_width, target_height):
    original_width, original_height = image.size
    if target_width <= 0 or target_height <= 0:
        return image.copy()
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
        log_error(f"Error: Original image file not found: {img_path}")
        return None
    except Exception as e:
        log_error(f"Warning: Could not get modification time for {img_path}: {e}")
        mtime = 0
    key = f"{real_path}_{width}_{mtime}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

PIL_CACHE = OrderedDict()
QT_CACHE = OrderedDict()

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
    if os.path.exists(cached_thumbnail_path):
        try:
            pil_image_thumbnail = Image.open(cached_thumbnail_path)
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
    return get_or_make_pil_by_key(cache_key, img_path, thumbnail_max_size)

def pil_to_qpixmap(pil_image):
    if pil_image is None:
        return QPixmap()
    # Convert all non-RGB/RGBA modes to RGBA for consistent handling
    if pil_image.mode not in ("RGB", "RGBA"):
        pil_image = pil_image.convert("RGBA")
    if pil_image.mode == "RGB":
        data = pil_image.tobytes("raw", "RGB")
        qimage = QImage(data, pil_image.width, pil_image.height, 3 * pil_image.width, QImage.Format_RGB888)
    else:
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height, 4 * pil_image.width, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())

def get_or_make_qt_by_key(cache_key, img_path, thumbnail_max_size):
    if cache_key in QT_CACHE:
        QT_CACHE.move_to_end(cache_key)
        return QT_CACHE[cache_key]
    pil_image = get_or_make_pil_by_key(cache_key, img_path, thumbnail_max_size)
    qt_pixmap = pil_to_qpixmap(pil_image)
    QT_CACHE[cache_key] = qt_pixmap
    if len(QT_CACHE) > CACHE_SIZE:
        QT_CACHE.popitem(last=False)
    return qt_pixmap
     
def get_or_make_qt(img_path, thumbnail_max_size):
    cache_key = uniq_file_id(img_path, thumbnail_max_size)
    return get_or_make_qt_by_key(cache_key, img_path, thumbnail_max_size)


# --- dialogue box ---

def fallback_show_error(title, message):
    QMessageBox.critical(None, title, message)
    
def custom_message_dialog(parent, title, message, font=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    x = parent.x() + parent.width() // 2 - 200
    y = parent.y() + parent.height() // 2 - 100
    dialog.setGeometry(x, y, 400, 300)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    text_widget = QTextEdit()
    text_widget.setReadOnly(True)
    text_widget.setPlainText(message)
    if font:
        text_widget.setFont(font)
    layout.addWidget(text_widget)
    button_layout = QHBoxLayout()
    button_layout.addStretch()
    ok_button = QPushButton("OK")
    ok_button.clicked.connect(dialog.accept)
    ok_button.setFixedWidth(80)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)
    ok_button.setFocus()
    dialog.exec()

    
# --- Wallpaper Setting Functions (Platform-Specific) ---

def set_wallpaper(image_path, error_callback=fallback_show_error):
    if platform.system() != "Linux":
        error_callback("Unsupported OS", f"Wallpaper setting not supported on {platform.system()}.")
        return False
    try:
        abs_path = os.path.abspath(image_path)
        file_uri = f"file://{abs_path}"
        desktop_env = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        if not desktop_env and os.environ.get('DESKTOP_SESSION'):
            desktop_env = os.environ.get('DESKTOP_SESSION').lower()
        success = False
        if any(de in desktop_env for de in ['gnome', 'unity', 'pantheon', 'budgie']):
            subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', file_uri])
            subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', file_uri])
            success = True
        elif 'kde' in desktop_env:
            script = f"""
            var allDesktops = desktops();
            for (var i=0; i < allDesktops.length; i++) {{
                d = allDesktops[i];
                d.wallpaperPlugin = "org.kde.image";
                d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
                d.writeConfig("Image", "{abs_path}");
            }}
            """
            subprocess.run(["qdbus", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script])
            success = True
        elif 'xfce' in desktop_env:
            try:
                props = subprocess.check_output(['xfconf-query', '-c', 'xfce4-desktop', '-p', '/backdrop', '-l']).decode('utf-8')
                monitors = set([p.split('/')[2] for p in props.splitlines() if p.endswith('last-image')])
                for monitor in monitors:
                    monitor_props = [p for p in props.splitlines() if f'/backdrop/screen0/{monitor}/' in p and p.endswith('last-image')]
                    for prop in monitor_props:
                        subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-p", f"{prop}", "-s", f"{abs_path}"])
                success = True
            except:
                subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-p", "/backdrop/screen0/monitor0/workspace0/last-image", "-s", f"{abs_path}"])
                success = True
        elif 'cinnamon' in desktop_env:
            subprocess.run(["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", f"{file_uri}"])
            success = True
        elif 'mate' in desktop_env:
            subprocess.run(["gsettings", "set", "org.mate.background", "picture-filename", f"{abs_path}"])
            success = True
        elif 'lxqt' in desktop_env or 'lxde' in desktop_env:
            subprocess.run(["pcmanfm-qt", f"--set-wallpaper={abs_path}"])
            subprocess.run(["pcmanfm", f"--set-wallpaper={abs_path}"])
            success = True
        elif any(de in desktop_env for de in ['i3', 'sway']):
            subprocess.run(["feh", "--bg-fill", f"{abs_path}"])
            success = True
        elif not success:
            methods = [
                ["feh", "--bg-fill", f"{abs_path}"],
                ["nitrogen", "--set-scaled", f"{abs_path}"],
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"{file_uri}"]
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
                           f"Couldn't detect your desktop environment ({desktop_env}).")
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
    subdirectories.sort()
    return subdirectories

def list_relevant_files(dir_path):
    file_list = list_image_files(dir_path)
    file_list.extend(list_image_files(get_parent_directory(dir_path)))
    for subdir in list_subdirectories(dir_path):
        file_list.extend(list_image_files(subdir))
    return file_list


class BackgroundWorker:
    def background(self):
        while self.keep_running:
            old_size = self.current_size
            old_directory = self.current_dir
            to_do_list = list_relevant_files(old_directory)
            for path_name in to_do_list:
                if not self.keep_running:
                    return
                self.barrier()
                if self.keep_running and (old_size == self.current_size) and (old_directory == self.current_dir):
                    self.path_name_queue.put(path_name)
                else:
                    break
            while self.keep_running and (old_size == self.current_size) and (old_directory == self.current_dir):
                time.sleep(2)

    def __init__(self, path, width):
        self.keep_running = True
        self.current_size = width
        self.current_dir = path
        self.path_name_queue = queue.Queue()
        self.worker = threading.Thread(target=self.background)
        self.block = threading.Event()
        self.worker.daemon = True
        self.worker.start()
        self.pause()
        
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
        

def is_image_file_name(file_name):
    return file_name.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)
        
def is_image_file(file_path):
    file_name = os.path.basename(file_path)
    return os.path.isfile(file_path) and is_image_file_name(file_name)
        
def list_image_files(directory_path):
    if not os.path.isdir(directory_path):
        return []
    full_paths = [os.path.join(directory_path, file) for file in os.listdir(directory_path)]
    return [path for path in full_paths if is_image_file(path)]


# --- drag and drop support ---

DRAG_DELAY_MS = 250
DRAG_THRESHOLD = 5

def _bind_drop_generic(target_widget, handle_drop, attribute_name):
    def wrapper(source_widget):
        handle_drop(source_widget, target_widget)
    setattr(target_widget, attribute_name, wrapper)

def bind_drop(target_widget, handle_drop):
    _bind_drop_generic(target_widget, handle_drop, 'handle_drop')

def bind_right_drop(target_widget, handle_right_drop):
    _bind_drop_generic(target_widget, handle_right_drop, 'handle_right_drop')


class DragController(QObject):
    """Manages drag-and-drop state for a source widget."""
    
    def __init__(self, source_widget, make_ghost, click_handler, button, attribute_name, picker):
        super().__init__()
        self.source_widget = source_widget
        self.make_ghost = make_ghost
        self.click_handler = click_handler
        self.button = button  # 1 = left, 3 = right
        self.attribute_name = attribute_name
        self.picker = picker
        
        self.drag_start_timer = None
        self.ghost = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.dragging = False
        self.dragging_widget = None
        
    def on_press(self):
        self.drag_start_x = QCursor.pos().x()
        self.drag_start_y = QCursor.pos().y()
        self.dragging_widget = self.source_widget
        self.dragging = False
        self.drag_start_timer = QTimer()
        self.drag_start_timer.setSingleShot(True)
        self.drag_start_timer.timeout.connect(self.start_drag)
        self.drag_start_timer.start(DRAG_DELAY_MS)
        
    def on_motion(self):
        if self.drag_start_timer and self.drag_start_timer.isActive() and self.dragging_widget:
            current_pos = QCursor.pos()
            distance_moved = math.sqrt((current_pos.x() - self.drag_start_x)**2 + 
                                       (current_pos.y() - self.drag_start_y)**2)
            if distance_moved > DRAG_THRESHOLD:
                self.drag_start_timer.stop()
                self.start_drag()
                
    def on_release(self):
        if self.drag_start_timer and self.drag_start_timer.isActive():
            self.drag_start_timer.stop()
            self.drag_start_timer = None
            # It was a click, not a drag
            self.click_handler(self.source_widget)
            self.dragging_widget = None
        elif self.dragging and self.ghost:
            self.end_drag()
        
    def start_drag(self):
        self.drag_start_timer = None
        self.dragging = True
        self.ghost = self.make_ghost(self.dragging_widget, self.drag_start_x, self.drag_start_y)
        self.ghost.show()
        # Take over mouse tracking
        QApplication.instance().installEventFilter(self)
        
    def eventFilter(self, obj, event):
        if self.dragging and self.ghost:
            if event.type() == QEvent.MouseMove:
                pos = QCursor.pos()
                self.ghost.move(pos.x() - 10, pos.y() - 10)
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self.end_drag()
                return True
        return False
        
    def end_drag(self):
        QApplication.instance().removeEventFilter(self)
        x, y = QCursor.pos().x(), QCursor.pos().y()
        if self.ghost:
            self.ghost.close()
            self.ghost = None
        
        # Find the widget under the cursor
        target_widget = QApplication.widgetAt(x, y)
        while target_widget:
            if hasattr(target_widget, self.attribute_name):
                getattr(target_widget, self.attribute_name)(self.dragging_widget)
                break
            target_widget = target_widget.parent()
        
        self.dragging = False
        self.dragging_widget = None


def bind_click_or_drag(source_widget, make_ghost, click_handler, picker):
    """Sets up left-click-or-drag on a widget. Click toggles selection, drag moves selected files."""
    controller = DragController(source_widget, make_ghost, click_handler, 1, 'handle_drop', picker)
    source_widget._left_drag_controller = controller
    # Override mouse events
    original_press = source_widget.mousePressEvent
    original_move = source_widget.mouseMoveEvent
    original_release = source_widget.mouseReleaseEvent
    
    def new_press(event):
        if event.button() == Qt.LeftButton:
            controller.on_press()
        else:
            original_press(event)
    
    def new_move(event):
        if controller.dragging_widget:
            controller.on_motion()
        else:
            original_move(event)
    
    def new_release(event):
        if event.button() == Qt.LeftButton and controller.dragging_widget:
            controller.on_release()
        else:
            original_release(event)
    
    source_widget.mousePressEvent = new_press
    source_widget.mouseMoveEvent = new_move
    source_widget.mouseReleaseEvent = new_release


def bind_right_click_or_drag(source_widget, make_ghost, right_click_handler, picker):
    """Sets up right-click-or-drag on a widget. Right-click opens context menu, drag moves single file."""
    controller = DragController(source_widget, make_ghost, right_click_handler, 3, 'handle_right_drop', picker)
    source_widget._right_drag_controller = controller
    # We need to handle right button separately
    original_press = source_widget.mousePressEvent
    original_move = source_widget.mouseMoveEvent
    original_release = source_widget.mouseReleaseEvent
    
    def new_press(event):
        if event.button() == Qt.RightButton:
            controller.on_press()
        else:
            if hasattr(source_widget, '_left_drag_controller'):
                # Let left controller handle it
                if event.button() == Qt.LeftButton:
                    source_widget._left_drag_controller.on_press()
                    return
            original_press(event)
    
    def new_move(event):
        if controller.dragging_widget:
            controller.on_motion()
        elif hasattr(source_widget, '_left_drag_controller') and source_widget._left_drag_controller.dragging_widget:
            source_widget._left_drag_controller.on_motion()
        else:
            original_move(event)
    
    def new_release(event):
        if event.button() == Qt.RightButton and controller.dragging_widget:
            controller.on_release()
        elif event.button() == Qt.LeftButton and hasattr(source_widget, '_left_drag_controller') and source_widget._left_drag_controller.dragging_widget:
            source_widget._left_drag_controller.on_release()
        else:
            original_release(event)
    
    source_widget.mousePressEvent = new_press
    source_widget.mouseMoveEvent = new_move
    source_widget.mouseReleaseEvent = new_release


# --- helper to get font from widget hierarchy ---

def get_font(widget):
    while widget.parent() is not None:
        widget = widget.parent()
    if hasattr(widget, 'main_font'):
        return widget.main_font
    return get_linux_ui_font()


# --- widgets ---

class EditableLabelWithCopy(QWidget):
    def __init__(self, master, initial_text="", info="", on_rename_callback=None, font=None, **kwargs):
        super().__init__(master)
        
        self.original_text = initial_text
        self.info = info
        self.on_rename_callback = on_rename_callback

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.label = QLabel(info)
        if font:
            self.label.setFont(font)
        layout.addWidget(self.label)
        
        self.entry = QLineEdit(initial_text)
        if font:
            self.entry.setFont(font)
        layout.addWidget(self.entry, 1)
        
        self.copy_button = QPushButton("Copy")
        if font:
            self.copy_button.setFont(font)
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(self.copy_button)
        
        self.entry.returnPressed.connect(self._on_enter_pressed)

    def set_info(self, text):
        self.info = text
        self.label.setText(text)
        
    def set_text(self, text):
        self.entry.setText(text)
        self.original_text = text
        
    def get_text(self):
        return self.entry.text()
    
    def _copy_to_clipboard(self):
        text = self.entry.text()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        original_style = self.entry.styleSheet()
        self.entry.setStyleSheet("background-color: #90EE90; color: #000000;")
        QTimer.singleShot(200, lambda: self.entry.setStyleSheet(original_style))

    def _on_enter_pressed(self):
        self._rename()
        
    def _rename(self):
        new_text = self.entry.text()
        if new_text != self.original_text and self.on_rename_callback:
            self.on_rename_callback(self.original_text, new_text)
            self.original_text = new_text


class ImageViewer(QMainWindow):
    def __init__(self, master, image_info):
        super().__init__(master)
        self.master = master
        self.setWindowTitle("kubux image manager")
        self.image_path = image_info[0]
        self.file_name = os.path.basename(self.image_path)
        self.dir_name = os.path.dirname(self.image_path)
        self.window_geometry = image_info[1]
        self.is_fullscreen = image_info[2]
        self.original_image = get_full_size_image(self.image_path)
        self.display_image = None
        self.photo_image = None

        if self.window_geometry is not None:
            self.restoreGeometry(QByteArray.fromBase64(self.window_geometry.encode()))

        w, h = self.original_image.size
        x = w
        y = h
        while x < 1000 and y < 600:
            x = 1.1 * x
            y = 1.1 * y
        while 1300 < x or 900 < y:
            x = x / 1.1
            y = y / 1.1

        canvas_width = int(x)
        canvas_height = int(y)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.filename_widget = EditableLabelWithCopy(
            central_widget,
            initial_text=self.file_name,
            info=f"{w}x{h}",
            on_rename_callback=self._rename_current_image,
            font=get_font(self)
        )

        self.image_frame = QWidget(central_widget)
        image_layout = QGridLayout(self.image_frame)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: black;")
        
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setStyleSheet("background-color: black;")
        self.scroll_area.setWidget(self.canvas)

        image_layout.addWidget(self.scroll_area, 0, 0)
        image_layout.setRowStretch(0, 1)
        image_layout.setColumnStretch(0, 1)

        main_layout.addWidget(self.image_frame, 1)
        main_layout.addWidget(self.filename_widget)

        self.zoom_factor = x / w
        self.fit_to_window = True
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.panning = False

        self.resize(canvas_width, canvas_height + 40)
        self._update_title()
        self._update_image()

        self.scroll_area.setMouseTracking(True)
        self.canvas.setMouseTracking(True)
        self.canvas.mousePressEvent = self._on_mouse_down
        self.canvas.mouseMoveEvent = self._on_mouse_drag
        self.canvas.mouseReleaseEvent = self._on_mouse_up
        self.canvas.wheelEvent = self._on_mouse_wheel

        self.set_screen_mode(self.is_fullscreen)
        self.show()
        self.activateWindow()
        self.canvas.setFocus()

    def get_image_info(self):
        geom = self.saveGeometry().toBase64().data().decode()
        return self.image_path, geom, self.is_fullscreen

    def set_screen_mode(self, is_fullscreen):
        if is_fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()
        self.is_fullscreen = is_fullscreen
        QTimer.singleShot(100, self._update_image)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.set_screen_mode(self.is_fullscreen)

    def _update_title(self):
        title = f"{self.file_name} (file)"
        try:
            if os.path.islink(self.image_path):
                title = f"{self.file_name} (symlink to {os.path.realpath(self.image_path)})"
        except Exception as e:
            title = "oops"
        self.setWindowTitle(title)

    def _update_image(self):
        if not self.original_image:
            return
        canvas_width = self.scroll_area.viewport().width()
        canvas_height = self.scroll_area.viewport().height()
        if canvas_width <= 1:
            canvas_width = 800
        if canvas_height <= 1:
            canvas_height = 600
        orig_width, orig_height = self.original_image.size
        if self.fit_to_window:
            scale_width = canvas_width / orig_width
            scale_height = canvas_height / orig_height
            scale = min(scale_width, scale_height)
            self.zoom_factor = scale
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
        else:
            new_width = int(orig_width * self.zoom_factor)
            new_height = int(orig_height * self.zoom_factor)

        self.display_image = resize_image(self.original_image, new_width, new_height)
        pixmap = pil_to_qpixmap(self.display_image)
        self.canvas.setPixmap(pixmap)
        self.canvas.resize(pixmap.size())

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Plus or key == Qt.Key_Equal:
            self._zoom_in()
        elif key == Qt.Key_Minus or key == Qt.Key_Underscore:
            self._zoom_out()
        elif key == Qt.Key_0:
            self.fit_to_window = True
            self._update_image()
        elif key == Qt.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key_F11:
            self.toggle_fullscreen()
        elif key == Qt.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(event)

    def _on_mouse_down(self, event):
        if event.button() == Qt.LeftButton:
            self.panning = True
            self.pan_start_x = event.globalX()
            self.pan_start_y = event.globalY()
            self.canvas.setCursor(Qt.ClosedHandCursor)

    def _on_mouse_drag(self, event):
        if not self.panning:
            return
        dx = self.pan_start_x - event.globalX()
        dy = self.pan_start_y - event.globalY()
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() + dx)
        v_bar.setValue(v_bar.value() + dy)
        self.pan_start_x = event.globalX()
        self.pan_start_y = event.globalY()

    def _on_mouse_up(self, event):
        if event.button() == Qt.LeftButton:
            self.panning = False
            self.canvas.setCursor(Qt.ArrowCursor)

    def _on_mouse_wheel(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._zoom_in(event.position().x(), event.position().y())
        else:
            self._zoom_out(event.position().x(), event.position().y())

    def resizeEvent(self, event):
        if self.fit_to_window:
            self._update_image()
        super().resizeEvent(event)

    def _zoom_in(self, x=None, y=None):
        self.fit_to_window = False
        self.zoom_factor *= 1.25
        self._update_image()

    def _zoom_out(self, x=None, y=None):
        self.fit_to_window = False
        self.zoom_factor /= 1.25
        min_zoom = 0.1
        if self.zoom_factor < min_zoom:
            self.fit_to_window = True
        self._update_image()

    def _rename_current_image(self, old_name, new_name):
        try:
            new_path = os.path.join(self.dir_name, new_name)
            if os.path.exists(new_path):
                return
            os.rename(self.image_path, new_path)
            self.image_path = new_path
            self.file_name = os.path.basename(self.image_path)
        except Exception as e:
            log_error(f"renaming file {old_name} to {new_name} failed, error: {e}")
        self._update_title()

    def _close(self):
        if self.is_fullscreen:
            self.toggle_fullscreen()
        self.master.open_images.remove(self)
        self.close()

    def closeEvent(self, event):
        if self in self.master.open_images:
            self.master.open_images.remove(self)
        event.accept()


class ThumbnailButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.img_path = None
        self.cache_key = None
        self.qt_image = None
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)


class DirectoryThumbnailGrid(QWidget):
    def __init__(self, master, directory_path="", list_cmd="ls", item_width=None, item_border_width=None,
                 static_button_config_callback=None, dynamic_button_config_callback=None, **kwargs):
        super().__init__(master)
        self._item_border_width = item_border_width
        self._directory_path = directory_path
        self._list_cmd = list_cmd
        self._item_width = item_width
        self._static_button_config_callback = static_button_config_callback
        self._dynamic_button_config_callback = dynamic_button_config_callback
        self._widget_cache = OrderedDict()
        self._cache_size = 2000
        self._active_widgets = {}
        self._last_known_width = -1
        self._files = []

        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def get_width_and_height(self):
        self.updateGeometry()
        return self.sizeHint().width(), self.sizeHint().height()

    def set_size_path_and_command(self, width, path, list_cmd):
        self._directory_path = path
        self._item_width = width
        self._list_cmd = list_cmd
        return self.regrid()

    def _get_button(self, img_path, width, pre_cache=True):
        cache_key = uniq_file_id(img_path, width)
        btn = self._widget_cache.get(cache_key, None)
        if btn is None:
            qt_image = get_or_make_qt_by_key(cache_key, img_path, width)
            btn = ThumbnailButton(self)
            btn.cache_key = cache_key
            btn.qt_image = qt_image
            btn.setIcon(QIcon(qt_image))
            btn.setIconSize(qt_image.size())
            self._widget_cache[cache_key] = btn
            if self._static_button_config_callback:
                self._static_button_config_callback(btn, img_path)
        else:
            self._widget_cache.move_to_end(cache_key)
        return btn

    def refresh(self):
        for img_path, btn in self._active_widgets.items():
            if self._dynamic_button_config_callback:
                self._dynamic_button_config_callback(btn, img_path)
        return self.get_width_and_height()

    def regrid(self):
        old_files = self._files
        self._files = list_image_files_by_command(self._directory_path, self._list_cmd)
        if self._files == old_files:
            return self.refresh()
        return self.redraw()

    def redraw(self):
        for btn in self._active_widgets.values():
            if btn is not None:
                self._layout.removeWidget(btn)
                btn.hide()
        self._active_widgets = {}
        for img_path in self._files:
            btn = self._get_button(img_path, self._item_width, pre_cache=False)
            if self._dynamic_button_config_callback:
                self._dynamic_button_config_callback(btn, img_path)
            self._active_widgets[img_path] = btn
        return self._layout_the_grid()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        current_width = event.size().width()
        if current_width <= 0 or current_width == self._last_known_width:
            return
        self._last_known_width = current_width
        self._layout_the_grid()

    def _calculate_columns(self, frame_width):
        if frame_width <= 0:
            return 1
        item_total_occupancy_width = self._item_width + (2 * self._item_border_width)
        buffer_for_gutters_and_edges = 10
        available_width_for_items = frame_width - buffer_for_gutters_and_edges
        if available_width_for_items <= 0:
            return 1
        calculated_cols = max(1, available_width_for_items // item_total_occupancy_width)
        return calculated_cols

    def _layout_the_grid(self):
        parent_width = self.parent().width() if self.parent() else self.width()
        desired_content_cols = self._calculate_columns(parent_width)
        if desired_content_cols == 0:
            desired_content_cols = 1

        for i, img_path in enumerate(self._active_widgets.keys()):
            widget = self._active_widgets.get(img_path)
            if widget is None:
                continue
            row, col_idx = divmod(i, desired_content_cols)
            widget.show()
            self._layout.addWidget(widget, row, col_idx)

        while len(self._widget_cache) > self._cache_size:
            self._widget_cache.popitem(last=False)

        return self.get_width_and_height()


class LongMenu(QDialog):
    def __init__(self, master, default_option, other_options, font=None, x_pos=None, y_pos=None,
                 pos="bottom", n_lines=12):
        super().__init__(master, Qt.Popup | Qt.FramelessWindowHint)
        self.result = default_option
        self._options = other_options
        self._main_font = font if font else get_font(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        max_length = max((len(line) for line in self._options), default=10) + 5

        self._listbox = QListWidget()
        self._listbox.setFont(self._main_font)
        fm = QFontMetrics(self._main_font)
        char_width = fm.averageCharWidth()
        self._listbox.setMinimumWidth(char_width * max_length)
        self._listbox.setMinimumHeight(fm.height() * min(n_lines, len(self._options)))

        for option_name in other_options:
            self._listbox.addItem(option_name)

        layout.addWidget(self._listbox)

        self._listbox.itemClicked.connect(self._on_listbox_select)
        self._listbox.itemDoubleClicked.connect(self._on_double_click)

        self.adjustSize()

        if x_pos is None or y_pos is None:
            master_pos = master.mapToGlobal(QPoint(0, 0))
            x_pos = master_pos.x()
            y_pos = master_pos.y() + master.height()

        if pos == "top":
            y_pos = y_pos - self.height()
        elif pos == "center":
            y_pos = y_pos - int(0.5 * self.height())
        if y_pos < 0:
            y_pos = 0

        screen = QApplication.primaryScreen().geometry()
        if x_pos + self.width() > screen.width():
            x_pos = screen.width() - self.width() - 5
        if y_pos + self.height() > screen.height():
            y_pos = screen.height() - self.height() - 5

        self.move(int(x_pos), int(y_pos))
        self._listbox.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self._exit_ok()
        elif event.key() == Qt.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(event)

    def _on_listbox_select(self, item):
        self._exit_ok()

    def _on_double_click(self, item):
        self._exit_ok()

    def _exit_ok(self):
        current_item = self._listbox.currentItem()
        if current_item:
            self.result = current_item.text()
        else:
            row = self._listbox.currentRow()
            if row >= 0 and row < len(self._options):
                self.result = self._options[row]
        self.accept()

    def _cancel(self):
        self.result = None
        self.reject()


class BreadCrumNavigator(QWidget):
    def __init__(self, master, on_navigate_callback=None, font=None,
                 long_press_threshold_ms=400, drag_threshold_pixels=5):
        super().__init__(master)
        self._on_navigate_callback = on_navigate_callback
        self._current_path = ""
        self._LONG_PRESS_THRESHOLD_MS = long_press_threshold_ms
        self._DRAG_THRESHOLD_PIXELS = drag_threshold_pixels
        self._long_press_timer = None
        self._press_start_time = 0
        self._press_x = 0
        self._press_y = 0
        self._active_button = None

        if font is None:
            self.font = get_font(self)
        else:
            self.font = font

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def set_path(self, path):
        if not os.path.isdir(path):
            return
        self._current_path = os.path.normpath(path)
        self._update_breadcrumbs()

    def _update_breadcrumbs(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        btn_list = []
        current_display_path = self._current_path
        while len(current_display_path) > 1:
            path = current_display_path
            current_display_path = os.path.dirname(path)
            btn_text = os.path.basename(path)
            if btn_text == '':
                btn_text = os.path.sep
            btn = QPushButton(btn_text)
            btn.setFlat(True)
            btn.setFont(self.font)
            btn.setStyleSheet("padding: 0px; margin: 0px;")
            btn.path = path
            btn.pressed.connect(lambda b=btn: self._on_button_press(b))
            btn.released.connect(lambda b=btn: self._on_button_release(b))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, b=btn: self._on_button_press_menu(b))
            btn_list.insert(0, btn)

        btn_text = "//"
        btn = QPushButton(btn_text)
        btn.setFlat(True)
        btn.setFont(self.font)
        btn.setStyleSheet("padding: 0px; margin: 0px;")
        btn.path = current_display_path
        btn.pressed.connect(lambda b=btn: self._on_button_press(b))
        btn.released.connect(lambda b=btn: self._on_button_release(b))
        btn_list.insert(0, btn)

        for i, btn in enumerate(btn_list):
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            bind_drop(btn, self._handle_drop)
            bind_right_drop(btn, self._handle_right_drop)
            self._layout.addWidget(btn)
            if i + 1 < len(btn_list):
                sep = QLabel("/")
                sep.setFont(self.font)
                sep.setContentsMargins(0, 0, 0, 0)
                sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                self._layout.addWidget(sep)
            if i == 0:
                btn.pressed.disconnect()
                btn.pressed.connect(lambda b=btn: self._on_button_press_menu(b))
        self._layout.addStretch(1)

    def _handle_drop(self, source_button, target_button):
        # Get the picker (go up hierarchy: BreadCrumNavigator -> _top_frame -> central_widget -> ImagePicker)
        picker = self.parent().parent().parent()
        picker.master.move_selected_files_to_directory(source_button.img_path, target_button.path)
        
    def _handle_right_drop(self, source_button, target_button):
        picker = self.parent().parent().parent()
        picker.master.move_file_to_directory(source_button.img_path, target_button.path)

    def _trigger_navigate(self, path):
        if self._on_navigate_callback:
            self._on_navigate_callback(path)

    def _on_button_press_menu(self, button):
        self._show_subdirectory_menu(button)

    def _on_button_press(self, button):
        self._press_start_time = time.time()
        self._press_x = QCursor.pos().x()
        self._press_y = QCursor.pos().y()
        self._active_button = button
        self._long_press_timer = QTimer()
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.timeout.connect(lambda: self._on_long_press_timeout(button))
        self._long_press_timer.start(self._LONG_PRESS_THRESHOLD_MS)

    def _on_button_release(self, button):
        if self._long_press_timer and self._long_press_timer.isActive():
            self._long_press_timer.stop()
        if self._active_button:
            current_pos = QCursor.pos()
            dist = math.sqrt((current_pos.x() - self._press_x)**2 + (current_pos.y() - self._press_y)**2)
            if dist < self._DRAG_THRESHOLD_PIXELS:
                if (time.time() - self._press_start_time) * 1000 < self._LONG_PRESS_THRESHOLD_MS:
                    path = self._active_button.path
                    if path and self._on_navigate_callback:
                        self._on_navigate_callback(path)
            self._active_button = None

    def _on_long_press_timeout(self, button):
        if self._active_button is button:
            self._show_subdirectory_menu(button)
            self._long_press_timer = None

    def _show_subdirectory_menu(self, button):
        path = button.path
        selected_path = path

        all_entries = os.listdir(path)
        subdirs = []
        hidden_subdirs = []
        for entry in all_entries:
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                if entry.startswith('.'):
                    hidden_subdirs.append(entry)
                else:
                    subdirs.append(entry)
        subdirs.sort()
        hidden_subdirs.sort()
        sorted_subdirs = subdirs + hidden_subdirs

        if sorted_subdirs:
            button_pos = button.mapToGlobal(QPoint(0, button.height()))
            menu_x = button_pos.x()
            menu_y = button_pos.y()
            selector_dialog = LongMenu(
                button,
                None,
                sorted_subdirs,
                font=self.font,
                x_pos=menu_x,
                y_pos=menu_y,
                n_lines=15
            )
            selector_dialog.exec()
            selected_name = selector_dialog.result
            if selected_name:
                selected_path = os.path.join(path, selected_name)

        self._trigger_navigate(selected_path)


class ImagePicker(QMainWindow):
    def __init__(self, master, picker_info=None):
        super().__init__(master)
        self.master = master
        self.setWindowTitle("kubux image manager")
        self.thumbnail_width = picker_info[0]
        self.image_dir = picker_info[1]
        self.list_cmd = picker_info[2]
        self.window_geometry = picker_info[3]
        self.background_worker = BackgroundWorker(self.image_dir, self.thumbnail_width)
        self.update_thumbnail_job_id = None
        self.watcher = DirectoryWatcher(self)
        
        if self.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.window_geometry.encode()))
        else:
            self.resize(1000, 600)
        
        self._create_widgets()
        self._cache_timer = QTimer(self)
        self._cache_timer.timeout.connect(self._cache_widget)
        self._cache_timer.start(50)

    def _cache_widget(self):
        try:
            path_name = self.background_worker.path_name_queue.get_nowait()
            self._gallery_grid._get_button(path_name, self.thumbnail_width)
        except queue.Empty:
            pass

    def get_picker_info(self):
        geom = self.saveGeometry().toBase64().data().decode()
        return self.thumbnail_width, self.image_dir, self.list_cmd, geom

    def _on_clone(self):
        self.master.open_picker_dialog(self.get_picker_info())

    def _update_list_cmd(self):
        self.list_cmd = self.list_cmd_entry.text()
        prepend_or_move_to_front(self.list_cmd, self.master.list_commands)
        QTimer.singleShot(0, self._regrid)

    def _show_list_cmd_menu(self, pos):
        current_cmd = self.list_cmd_entry.text().strip()
        prepend_or_move_to_front(current_cmd, self.master.list_commands)
        widget_pos = self.list_cmd_entry.mapToGlobal(QPoint(0, 0))
        menu_x = widget_pos.x()
        menu_y = widget_pos.y()
        selector_dialog = LongMenu(
            self,
            None,
            self.master.list_commands,
            font=get_font(self),
            x_pos=menu_x,
            y_pos=menu_y,
            pos="top"
        )
        selector_dialog.exec()
        selected_cmd = selector_dialog.result
        if selected_cmd:
            self.list_cmd_entry.setText(selected_cmd)
            self._update_list_cmd()

    def _regrid(self):
        self._gallery_grid.set_size_path_and_command(self.thumbnail_width, self.image_dir, self.list_cmd)

    def _redraw(self):
        self._gallery_grid.redraw()

    def _refresh(self):
        self._gallery_grid.refresh()

    def _create_widgets(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Top bar
        self._top_frame = QWidget()
        top_layout = QHBoxLayout(self._top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        self.breadcrumb_nav = BreadCrumNavigator(
            self._top_frame,
            on_navigate_callback=self._browse_directory,
            font=get_font(self)
        )
        top_layout.addWidget(self.breadcrumb_nav, 1)
        
        clone_btn = QPushButton("Clone")
        clone_btn.setFont(get_font(self))
        clone_btn.clicked.connect(self._on_clone)
        top_layout.addWidget(clone_btn)
        
        close_btn = QPushButton("Close")
        close_btn.setFont(get_font(self))
        close_btn.clicked.connect(self._on_close)
        top_layout.addWidget(close_btn)
        
        main_layout.addWidget(self._top_frame)

        # Gallery area
        self._canvas_frame = QWidget()
        canvas_layout = QHBoxLayout(self._canvas_frame)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        
        self._gallery_scroll = QScrollArea()
        self._gallery_scroll.setWidgetResizable(True)
        self._gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self._gallery_grid = DirectoryThumbnailGrid(
            self._gallery_scroll,
            directory_path=self.image_dir,
            list_cmd=self.list_cmd,
            item_width=self.thumbnail_width,
            item_border_width=6,
            static_button_config_callback=self._static_configure_picker_button,
            dynamic_button_config_callback=self._dynamic_configure_picker_button
        )
        self._gallery_scroll.setWidget(self._gallery_grid)
        canvas_layout.addWidget(self._gallery_scroll)
        
        main_layout.addWidget(self._canvas_frame, 1)

        # Bottom bar
        self._bot_frame = QWidget()
        bot_layout = QHBoxLayout(self._bot_frame)
        bot_layout.setContentsMargins(0, 0, 0, 0)
        
        size_label = QLabel("Size:")
        size_label.setFont(get_font(self))
        bot_layout.addWidget(size_label)
        
        self.thumbnail_slider = QSlider(Qt.Horizontal)
        self.thumbnail_slider.setMinimum(96)
        self.thumbnail_slider.setMaximum(1920)
        self.thumbnail_slider.setSingleStep(20)
        self.thumbnail_slider.setValue(self.thumbnail_width)
        self.thumbnail_slider.valueChanged.connect(self._update_thumbnail_width)
        self.thumbnail_slider.setFixedWidth(150)
        bot_layout.addWidget(self.thumbnail_slider)
        
        show_label = QLabel("Show:")
        show_label.setFont(get_font(self))
        bot_layout.addWidget(show_label)
        
        self.list_cmd_entry = QLineEdit(self.list_cmd)
        self.list_cmd_entry.setFont(get_font(self))
        self.list_cmd_entry.returnPressed.connect(self._update_list_cmd)
        self.list_cmd_entry.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_cmd_entry.customContextMenuRequested.connect(self._show_list_cmd_menu)
        bot_layout.addWidget(self.list_cmd_entry, 1)
        
        desel_btn = QPushButton("Des.")
        desel_btn.setFont(get_font(self))
        desel_btn.clicked.connect(self._on_deselect)
        bot_layout.addWidget(desel_btn)
        
        sel_btn = QPushButton("Sel.")
        sel_btn.setFont(get_font(self))
        sel_btn.clicked.connect(self._on_select)
        bot_layout.addWidget(sel_btn)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setFont(get_font(self))
        self.apply_btn.clicked.connect(self._on_apply)
        bot_layout.addWidget(self.apply_btn)
        
        main_layout.addWidget(self._bot_frame)

        self.watcher.start_watching(self.image_dir)
        self._gallery_scroll.verticalScrollBar().setValue(0)
        self.background_worker.run(self.image_dir, self.thumbnail_width)
        self.breadcrumb_nav.set_path(self.image_dir)
        self._gallery_grid.regrid()
        
        # Bind drop handlers for drag-and-drop to this picker
        bind_drop(self._gallery_scroll, self._handle_drop)
        bind_right_drop(self._gallery_scroll, self._handle_right_drop)
        bind_drop(self._gallery_grid, self._handle_drop)
        bind_right_drop(self._gallery_grid, self._handle_right_drop)
        
        QTimer.singleShot(100, self.activateWindow)
        self.show()

    def _make_ghost(self, button, x, y):
        dir_path = os.path.dirname(button.img_path)
        files = self.master.selected_files_in_directory(dir_path)
        base = os.path.basename(dir_path)
        
        ghost = QDialog(self.master, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        ghost.setAttribute(Qt.WA_TranslucentBackground)
        ghost.setWindowOpacity(0.7)
        
        layout = QVBoxLayout(ghost)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if files:
            label = QLabel(f"move {len(files)} files from directory {base} selected")
            label.setStyleSheet("background-color: lightgreen; padding: 10px;")
        else:
            label = QLabel(f"NO FILES SELECTED in {base}")
            label.setStyleSheet("background-color: red; padding: 10px;")
        label.setWordWrap(True)
        label.setMaximumWidth(300)
        label.setFont(get_font(self))
        layout.addWidget(label)
        
        ghost.adjustSize()
        ghost.move(x - 10, y - 10)
        return ghost

    def _make_right_ghost(self, button, x, y):
        ghost = QDialog(self.master, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        ghost.setAttribute(Qt.WA_TranslucentBackground)
        ghost.setWindowOpacity(0.7)
        
        layout = QVBoxLayout(ghost)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel()
        label.setPixmap(button.qt_image)
        layout.addWidget(label)
        
        ghost.adjustSize()
        ghost.move(x - 10, y - 10)
        return ghost

    def _handle_drop(self, source_button, target_picker):
        self.master.move_selected_files_to_directory(source_button.img_path, target_picker.image_dir)
        
    def _handle_right_drop(self, source_button, target_picker):
        self.master.move_file_to_directory(source_button.img_path, target_picker.image_dir)

    def _exec_cmd_for_image(self, button):
        args = [button.img_path]
        self.master.execute_current_command_with_args(args)

    def _static_configure_picker_button(self, btn, img_path):
        pass

    def _toggle_selection(self, btn):
        self.master.toggle_selection(btn.img_path)

    def _open_right_click_context_menu(self, btn):
        options = self.master.command_field.current_cmd_list()
        global_pos = QCursor.pos()
        context_menu = LongMenu(
            self,
            default_option=None,
            other_options=options,
            font=self.master.main_font,
            x_pos=global_pos.x() - 30,
            y_pos=global_pos.y() - 30,
            pos="bottom"
        )
        context_menu.exec()
        command = context_menu.result
        if command:
            args = [btn.img_path]
            self.master.execute_command_with_args(command, args)

    def _dynamic_configure_picker_button(self, btn, img_path):
        cache_key = uniq_file_id(img_path, self.thumbnail_width)
        btn.img_path = img_path
        if btn.cache_key != cache_key:
            btn.cache_key = cache_key
            qt_image = get_or_make_qt_by_key(cache_key, img_path, self.thumbnail_width)
            btn.qt_image = qt_image
            btn.setIcon(QIcon(qt_image))
            btn.setIconSize(qt_image.size())
        
        # Only setup drag handlers once (check if already connected via attribute)
        if not hasattr(btn, '_drag_connected'):
            bind_click_or_drag(btn, self._make_ghost, self._toggle_selection, self)
            bind_right_click_or_drag(btn, self._make_right_ghost, self._open_right_click_context_menu, self)
            btn._drag_connected = True
        
        if img_path in self.master.selected_files:
            btn.setStyleSheet("border: 3px solid blue;")
        else:
            btn.setStyleSheet("")

    def _toggle_selection_btn(self, btn):
        self.master.toggle_selection(btn.img_path)

    def _on_close(self):
        self.background_worker.stop()
        self.watcher.stop_watching()
        self._cache_timer.stop()
        self.master.open_picker_dialogs.remove(self)
        self.close()

    def _on_select(self):
        all_files = list_image_files_by_command(self.image_dir, self.list_cmd)
        for file in all_files:
            self.master.select_file(file)

    def _on_deselect(self):
        all_files = list_image_files_by_command(self.image_dir, self.list_cmd)
        for file in all_files:
            self.master.unselect_file(file)

    def _on_apply(self):
        files = self.master.selected_files_in_directory(self.image_dir)
        options = self.master.command_field.current_cmd_list()
        btn_pos = self.apply_btn.mapToGlobal(QPoint(0, 0))
        context_menu = LongMenu(
            self,
            default_option=None,
            other_options=options,
            font=self.master.main_font,
            x_pos=btn_pos.x() - 30,
            y_pos=btn_pos.y() - 30,
            pos="center"
        )
        context_menu.exec()
        command = context_menu.result
        if command:
            self.master.execute_command_with_args(command, files)

    def _open_context_menu(self, btn, pos):
        options = self.master.command_field.current_cmd_list()
        global_pos = btn.mapToGlobal(pos)
        context_menu = LongMenu(
            self,
            default_option=None,
            other_options=options,
            font=self.master.main_font,
            x_pos=global_pos.x() - 30,
            y_pos=global_pos.y() - 30,
            pos="bottom"
        )
        context_menu.exec()
        command = context_menu.result
        if command:
            args = [btn.img_path]
            self.master.execute_command_with_args(command, args)

    def _browse_directory(self, path):
        if not os.path.isdir(path):
            custom_message_dialog(parent=self, title="Error", message=f"Invalid directory: {path}",
                                  font=get_font(self))
            return
        self.image_dir = path
        self.watcher.change_dir(path)
        self.background_worker.run(path, self.thumbnail_width)
        self.breadcrumb_nav.set_path(path)
        self._regrid()
        self._gallery_scroll.verticalScrollBar().setValue(0)

    def _update_thumbnail_width(self, value):
        if self.update_thumbnail_job_id:
            self.update_thumbnail_job_id.stop()
        self.update_thumbnail_job_id = QTimer()
        self.update_thumbnail_job_id.setSingleShot(True)
        self.update_thumbnail_job_id.timeout.connect(lambda: self._do_update_thumbnail_width(value))
        self.update_thumbnail_job_id.start(400)

    def _do_update_thumbnail_width(self, value):
        self.thumbnail_width = value
        self._regrid()

    def closeEvent(self, event):
        if self in self.master.open_picker_dialogs:
            self.background_worker.stop()
            self.watcher.stop_watching()
            self._cache_timer.stop()
            self.master.open_picker_dialogs.remove(self)
        event.accept()


class FlexibleTextField(QWidget):
    def __init__(self, parent, command_callback, commands="", font=None):
        super().__init__(parent)
        self.command_callback = command_callback
        self.previous_index = None
        if font is None:
            self.font = get_font(self)
        else:
            self.font = font
        self._create_widgets()
        self._set_commands(commands)

    def _create_widgets(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.text_area = QTextEdit()
        self.text_area.setFont(self.font)
        self.text_area.setLineWrapMode(QTextEdit.NoWrap)
        self.text_area.cursorPositionChanged.connect(self._on_cursor_move)
        self.text_area.mouseDoubleClickEvent = self._on_double_click_select
        
        layout.addWidget(self.text_area)
        self.text_area.setFocus()

    def _set_index(self, index):
        cursor = self.text_area.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(index - 1):
            cursor.movePosition(QTextCursor.Down)
        self.text_area.setTextCursor(cursor)
        self._on_cursor_move()

    def _set_commands(self, commands):
        self.commands = commands
        self.text_area.setPlainText(commands)
        self._set_index(1)

    def _current_index(self):
        cursor = self.text_area.textCursor()
        return cursor.blockNumber() + 1

    def _current_length(self):
        return self.text_area.document().blockCount()

    def _on_cursor_move(self):
        current_index = self._current_index()
        if current_index != self.previous_index:
            self._highlight_current_line()
            self.previous_index = current_index

    def _highlight_current_line(self):
        extra_selections = []
        selection = QTextEdit.ExtraSelection()
        line_color = QColor("#e0e0e0")
        selection.format.setBackground(line_color)
        selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        selection.cursor = self.text_area.textCursor()
        selection.cursor.clearSelection()
        extra_selections.append(selection)
        self.text_area.setExtraSelections(extra_selections)

    def _on_double_click_select(self, event):
        cursor = self.text_area.cursorForPosition(event.pos())
        index = cursor.blockNumber() + 1
        command = self.get_command(index)
        if command:
            self.command_callback(command)
        self._on_cursor_move()
        QTextEdit.mouseDoubleClickEvent(self.text_area, event)

    def get_command(self, index):
        doc = self.text_area.document()
        block = doc.findBlockByNumber(index - 1)
        return block.text().strip() if block.isValid() else ""

    def current_command(self):
        index = self._current_index()
        return self.get_command(index)

    def current_text(self):
        return self.text_area.toPlainText()

    def current_cmd_list(self):
        return [self.get_command(index) for index in range(1, self._current_length() + 1)]

    def call_current_command(self):
        command = self.current_command()
        if command:
            self.command_callback(command)


# --- string ops ---

def strip_prefix(prefix, string):
    if string.startswith(prefix):
        return string[len(prefix):].strip()
    return None

def expand_env_vars(input_string):
    env_var_pattern = r'\${([A-Za-z_][A-Za-z0-9_]*)}'
    def replacer(match):
        var_name = match.group(1)
        value = os.getenv(var_name, "")
        return value
    return re.sub(env_var_pattern, replacer, input_string)

def expand_wildcards(command_line, selected_files):
    try:
        raw_tokens = shlex.split(command_line)
    except ValueError as e:
        log_error(f"Error parsing command line '{command_line}': {e}")
        return [command_line]

    if not raw_tokens:
        return []

    has_single_wildcard = '*' in raw_tokens
    has_list_wildcard = '{*}' in raw_tokens

    if (has_single_wildcard or has_list_wildcard) and not selected_files:
        return []

    keep_fingers_crossed = "dasdklasdashdaisdhiunerwehuacnkajdasudhuiewrnksvjiurkanr"
    quoted_args = shlex.join(selected_files)
    outputs = []
    for file in selected_files:
        quoted_file = shlex.quote(file)
        cmd = command_line.replace("{*}", keep_fingers_crossed).replace("*", quoted_args).replace(keep_fingers_crossed, quoted_file)
        outputs.append(cmd)
    if outputs:
        return outputs

    return [command_line.replace("*", quoted_args)]


# --- main ---

class ImageManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kubux image manager")
        self._load_app_settings()
        font_name, font_size = get_linux_system_ui_font_info()
        self.regrid_job = None
        self.redraw_job = None
        self.refresh_job = None
        self._ui_scale_job = None
        self.base_font_size = font_size
        self.main_font = QFont(font_name, int(self.base_font_size * self.ui_scale))
        
        if self.main_win_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.main_win_geometry.encode()))
        else:
            self.resize(300, 400)
        
        self._create_widgets()
        self.open_picker_dialogs = []
        self.open_picker_dialogs_from_info()
        self.open_images = []
        self.open_images_from_info()
        self.command_field._set_index(self.current_index)
        self.show()

    def collect_open_picker_info(self):
        self.open_picker_info = []
        for picker in self.open_picker_dialogs:
            self.open_picker_info.append(picker.get_picker_info())
        return self.open_picker_info

    def open_picker_dialogs_from_info(self):
        for picker_info in self.open_picker_info:
            self.open_picker_dialog(picker_info)

    def open_picker_dialog(self, picker_info):
        dummy = ImagePicker(self, picker_info)
        self.open_picker_dialogs.append(dummy)

    def collect_open_image_info(self):
        self.open_image_info = []
        for image in self.open_images:
            self.open_image_info.append(image.get_image_info())
        return self.open_image_info

    def open_images_from_info(self):
        for image_info in self.open_image_info:
            self.open_image(image_info)

    def open_image(self, image_info):
        dummy = ImageViewer(self, image_info)
        self.open_images.append(dummy)

    def _load_app_settings(self):
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r') as f:
                    self.app_settings = json.load(f)
            else:
                self.app_settings = {}
        except (json.JSONDecodeError, Exception) as e:
            log_error(f"Error loading app settings, initializing defaults: {e}")
            self.app_settings = {}

        self.ui_scale = self.app_settings.get("ui_scale", 1.0)
        self.main_win_geometry = self.app_settings.get("main_win_geometry", None)
        self.commands = self.app_settings.get("commands", "Open: {*}\nSetWP: *\nOpen: ${HOME}/Pictures")
        self.current_index = int(self.app_settings.get("current_index", 1))
        self.selected_files = self.app_settings.get("selected_files", [])
        self.new_picker_info = self.app_settings.get("new_picker_info", [192, PICTURES_DIR, "ls", None])
        self.open_picker_info = self.app_settings.get("open_picker_info", [])
        self.open_image_info = self.app_settings.get("open_image_info", [])
        self.list_commands = self.app_settings.get("list_commands", ["ls", "find . -maxdepth 1 -type f"])

    def _save_app_settings(self):
        try:
            if not hasattr(self, 'app_settings'):
                self.app_settings = {}
            self.app_settings["ui_scale"] = self.ui_scale
            self.app_settings["main_win_geometry"] = self.saveGeometry().toBase64().data().decode()
            self.app_settings["commands"] = self.command_field.current_text().rstrip('\n')
            self.app_settings["current_index"] = self.command_field._current_index()
            self.app_settings["selected_files"] = self.selected_files
            self.app_settings["new_picker_info"] = self.new_picker_info
            self.app_settings["open_picker_info"] = self.collect_open_picker_info()
            self.app_settings["open_image_info"] = self.collect_open_image_info()
            self.app_settings["list_commands"] = self.list_commands

            with open(APP_SETTINGS_FILE, 'w') as f:
                json.dump(self.app_settings, f, indent=4)
        except Exception as e:
            log_error(f"Error saving app settings: {e}")

    def _create_widgets(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        self.command_field = FlexibleTextField(
            central_widget,
            commands=self.commands,
            command_callback=self.execute_command,
            font=self.main_font
        )
        main_layout.addWidget(self.command_field, 1)
        
        control_frame = QWidget()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.exec_button = QPushButton("Process selected")
        self.exec_button.setFont(self.main_font)
        self.exec_button.clicked.connect(self.execute_current_command)
        control_layout.addWidget(self.exec_button)
        
        self.deselect_button = QPushButton("Clear selection")
        self.deselect_button.setFont(self.main_font)
        self.deselect_button.clicked.connect(self.clear_selection)
        control_layout.addWidget(self.deselect_button)
        
        control_layout.addStretch()
        
        ui_label = QLabel("UI:")
        ui_label.setFont(self.main_font)
        control_layout.addWidget(ui_label)
        
        self.ui_slider = QSlider(Qt.Horizontal)
        self.ui_slider.setMinimum(2)
        self.ui_slider.setMaximum(35)
        self.ui_slider.setValue(int(self.ui_scale * 10))
        self.ui_slider.valueChanged.connect(self._update_ui_scale)
        self.ui_slider.setFixedWidth(100)
        control_layout.addWidget(self.ui_slider)
        
        self.quit_button = QPushButton("Quit")
        self.quit_button.setFont(self.main_font)
        self.quit_button.clicked.connect(self.close_app)
        control_layout.addWidget(self.quit_button)
        
        main_layout.addWidget(control_frame)
        self.update_button_status()

    def move_file_to_directory(self, file_path, target_dir):
        new_path = move_file_to_directory(file_path, target_dir)
        if file_path in self.selected_files:
            self.unselect_file(file_path)
            self.select_file(new_path)
        self.broadcast_contents_change()

    def selected_files_in_directory(self, directory):
        return [file for file in self.selected_files if is_file_in_dir(file, directory)]

    def move_selected_files_to_directory(self, file_path, target_dir):
        source_dir = os.path.realpath(os.path.dirname(file_path))
        old_selected = self.selected_files
        self.selected_files = []
        for file in old_selected:
            if is_file_in_dir(file, source_dir):
                new_path = move_file_to_directory(file, target_dir)
                self.selected_files.append(new_path)
            else:
                self.selected_files.append(file)
        self.broadcast_contents_change()

    def sanitize_selected_files(self):
        self.selected_files[:] = [path for path in self.selected_files if os.path.exists(path)]

    def execute_command_with_args(self, command, args):
        command = expand_env_vars(command)
        to_do = expand_wildcards(command, args)
        status_change = False
        for cmd in to_do:
            if (files := strip_prefix("Open:", cmd)) is not None:
                log_action(f"execute as an internal command: Open: {files}")
                path_list = shlex.split(files)
                for path in path_list:
                    self.open_path(path)
            elif (files := strip_prefix("Fullscreen:", cmd)) is not None:
                log_action(f"execute as an internal command: Fullscreen: {files}")
                path_list = shlex.split(files)
                for path in path_list:
                    self.fullscreen_path(path)
            elif (files := strip_prefix("SetWP:", cmd)) is not None:
                log_action(f"execute as an internal command: SetWP: {files}")
                path_list = shlex.split(files)
                if path_list:
                    self.set_wp(path_list[-1])
            elif (list_cmd := strip_prefix("Select:", cmd)) is not None:
                log_action(f"execute as an internal command: Select: {list_cmd}")
                status_change = True
                file_list = filter_for_files(list_cmd)
                for file in file_list:
                    self.select_file(file)
            elif (list_cmd := strip_prefix("Deselect:", cmd)) is not None:
                log_action(f"execute as an internal command: Deselect: {list_cmd}")
                status_change = True
                file_list = filter_for_files(list_cmd)
                for file in file_list:
                    self.unselect_file(file)
            else:
                log_action(f"execute as a shell command: {cmd}")
                execute_shell_command(cmd)
        if status_change:
            self.broadcast_selection_change()

    def execute_command(self, command):
        self.execute_command_with_args(command, self.selected_files)

    def execute_current_command(self):
        self.sanitize_selected_files()
        self.execute_command(self.command_field.current_command())

    def execute_current_command_with_args(self, args):
        self.execute_command_with_args(self.command_field.current_command(), args)

    def broadcast_selection_change(self):
        self.sanitize_selected_files()
        if self.refresh_job:
            self.refresh_job.stop()
        self.refresh_job = QTimer()
        self.refresh_job.setSingleShot(True)
        self.refresh_job.timeout.connect(self.refresh_open_pickers)
        self.refresh_job.start(50)

    def broadcast_contents_change(self):
        self.sanitize_selected_files()
        if self.regrid_job:
            self.regrid_job.stop()
        self.regrid_job = QTimer()
        self.regrid_job.setSingleShot(True)
        self.regrid_job.timeout.connect(self.regrid_open_pickers)
        self.regrid_job.start(50)

    def refresh_open_pickers(self):
        self.refresh_job = None
        for picker in self.open_picker_dialogs:
            picker._refresh()
        self.update_button_status()

    def redraw_open_pickers(self):
        self.redraw_job = None
        for picker in self.open_picker_dialogs:
            picker._redraw()
        self.update_button_status()

    def regrid_open_pickers(self):
        log_debug(f"regridding all open pickers.")
        self.regrid_job = None
        for picker in self.open_picker_dialogs:
            log_debug(f"rigridding picker {picker}")
            picker._regrid()
        self.update_button_status()

    def select_file(self, path):
        self.selected_files.append(path)
        self.broadcast_selection_change()

    def unselect_file(self, path):
        try:
            self.selected_files.remove(path)
        except Exception:
            pass
        self.broadcast_selection_change()

    def _do_update_ui_scale(self, scale_factor):
        self.ui_scale = scale_factor
        new_size = int(self.base_font_size * scale_factor)
        self.main_font.setPointSize(new_size)
        self._update_widget_fonts(self, self.main_font)

    def _update_widget_fonts(self, widget, font):
        try:
            widget.setFont(font)
        except:
            pass
        for child in widget.findChildren(QWidget):
            try:
                child.setFont(font)
            except:
                pass

    def _update_ui_scale(self, value):
        if self._ui_scale_job:
            self._ui_scale_job.stop()
        self._ui_scale_job = QTimer()
        self._ui_scale_job.setSingleShot(True)
        self._ui_scale_job.timeout.connect(lambda: self._do_update_ui_scale(value / 10.0))
        self._ui_scale_job.start(400)

    def clear_selection(self):
        self.selected_files = []
        self.broadcast_selection_change()

    def toggle_selection(self, file):
        if file in self.selected_files:
            self.unselect_file(file)
        else:
            self.select_file(file)
        self.update_button_status()

    def update_button_status(self):
        if not self.selected_files:
            self.deselect_button.setEnabled(False)
        else:
            self.deselect_button.setEnabled(True)

    def close_app(self):
        self.close()

    def fullscreen_path(self, path):
        try:
            if os.path.isfile(path):
                self.fullscreen_image_file(path)
                return
        except Exception as e:
            log_error(f"path {path} has problems, message: {e}")
            traceback.print_exc()

    def open_path(self, path):
        try:
            if os.path.isdir(path):
                self.open_image_directory(path)
                return
            if os.path.isfile(path):
                self.open_image_file(path)
                return
        except Exception as e:
            log_error(f"path {path} has problems, message: {e}")
            traceback.print_exc()

    def open_image_file(self, file_path):
        self.open_image([file_path, None, False])

    def fullscreen_image_file(self, file_path):
        self.open_image([file_path, None, True])

    def open_image_directory(self, directory_path):
        if self.open_picker_dialogs:
            self.new_picker_info = list(self.open_picker_dialogs[-1].get_picker_info())
        self.open_picker_dialog([self.new_picker_info[0],
                                  directory_path,
                                  self.new_picker_info[2],
                                  self.new_picker_info[3]])

    def set_wp(self, path):
        try:
            if os.path.isfile(path):
                set_wallpaper(path)
        except Exception as e:
            log_error(f"path {path} has problems, message: {e}")

    def closeEvent(self, event):
        self._save_app_settings()
        for picker in list(self.open_picker_dialogs):
            picker._on_close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("kubux image manager")
    manager = ImageManager()
    sys.exit(app.exec())
