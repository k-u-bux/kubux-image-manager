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
import tkinter as tk
import tkinter.font as tkFont
from collections import OrderedDict
from datetime import datetime
from tkinter import TclError
from tkinter import messagebox
from tkinter import ttk

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import requests
from PIL import Image, ImageTk

SUPPORTED_IMAGE_EXTENSIONS = (
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp',
    '.ico', '.icns', '.avif', '.dds', '.msp', '.pcx', '.ppm',
    '.pbm', '.pgm', '.sgi', '.tga', '.xbm', '.xpm'
)

BUTTON_RELIEF="flat"
SCALE_RELIEF="flat"
SCROLLBAR_RELIEF="flat"

HOME_DIR = os.path.expanduser('~')
CONFIG_DIR = os.path.join(HOME_DIR, ".config", "kubux-image-manager")
CACHE_DIR = os.path.join(HOME_DIR, ".cache", "kubux-thumbnail-cache")
THUMBNAIL_CACHE_ROOT = os.path.join(CACHE_DIR, "thumbnails")
PICTURES_DIR = os.path.join(HOME_DIR, "Pictures")
DEFAULT_THUMBNAIL_DIM = 192
APP_SETTINGS_FILE = os.path.join(CONFIG_DIR, "app_settings.json")    

os.makedirs(THUMBNAIL_CACHE_ROOT, exist_ok=True)


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
                    print(f"Warning: Unexpected gsettings font format: '{font_info_str}'")
            except Exception as e:
                print(f"Error parsing gsettings font: {e}")

        return font_name, font_size

    except subprocess.CalledProcessError:
        print("gsettings command not found or failed. Are you on a GTK-based desktop with dconf/gsettings installed?")
        return "Sans", 10 # Fallback for non-GTK or missing gsettings
    except Exception as e:
        print(f"An error occurred while getting GTK font settings: {e}")
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
            print(f"Warning: Unexpected KDE font format: '{font_string}'")
            return "Sans", 10 # Fallback

    except subprocess.CalledProcessError:
        print("kreadconfig5 command not found or failed. Are you on KDE Plasma?")
        return "Sans", 10 # Fallback for non-KDE or missing kreadconfig5
    except Exception as e:
        print(f"An error occurred while getting KDE font settings: {e}")
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

    print(f"Detected desktop session: {desktop_session}")

    if desktop_session and ("GNOME" in desktop_session.upper() or
                            "CINNAMON" in desktop_session.upper() or
                            "XFCE" in desktop_session.upper() or
                            "MATE" in desktop_session.upper()):
        print("Attempting to get GTK font...")
        return get_gtk_ui_font()
    elif desktop_session and "KDE" in desktop_session.upper():
        print("Attempting to get KDE font...")
        return get_kde_ui_font()
    else:
        # Fallback for other desktops or if detection fails
        print("Could not reliably detect desktop environment. Trying common defaults or gsettings as fallback.")
        # Try gsettings anyway, as it's common even outside "full" GNOME
        font_name, font_size = get_gtk_ui_font()
        if font_name != "Sans" or font_size != 10: # If gsettings returned something more specific
            return font_name, font_size
        return "Sans", 10 # Final generic fallback

def get_linux_ui_font():
    font_name, font_size = get_linux_ui_font_info()
    return tkFont.Font(family=font_name, size=font_size)
    

# --- watch directory ---

class DirectoryEventHandler(FileSystemEventHandler):
    def __init__(self, directory, image_picker):
        # super().__init__(directory)
        self.image_picker = image_picker
        self.directory = directory
        
    def on_any_event(self, event):
        # print(f"directory {self.directory} has changed.")
        self.image_picker.after( 0, self.image_picker._repaint )


class DirectoryWatcher():
    def __init__(self, image_picker):
        self.image_picker = image_picker
        
    def start_watching(self, directory):
        self.event_handler = DirectoryEventHandler(directory, self.image_picker)
        self.observer = Observer()
        self.observer.schedule(self.event_handler, directory, recursive=False)
        self.observer.start()

    def stop_watching(self):
        self.observer.stop()
        self.observer.join()

    def change_dir(self, directory):
        self.stop_watching()
        self.start_watching(directory)

# --- image stuff ---

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
        mtime = os.path.getmtime(img_path)
    except FileNotFoundError:
        print(f"Error: Original image file not found for thumbnail generation: {img_path}")
        return None
    except Exception as e:
        print(f"Warning: Could not get modification time for {img_path}: {e}. Using a default value.")
        mtime = 0
    key = f"{img_path}_{width}_{mtime}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

PIL_CACHE = OrderedDict()

def get_full_size_image(img_path):
    cache_key = uniq_file_id(img_path)
    if cache_key in PIL_CACHE:
        PIL_CACHE.move_to_end(cache_key)
        return PIL_CACHE[cache_key]
    try:
        full_image = Image.open(img_path)
        PIL_CACHE[cache_key] = full_image
        if len( PIL_CACHE ) > 2000:
            PIL_CACHE.popitem(last=False)
            assert len( PIL_CACHE ) == 2000
        return full_image
    except Exception as e:
        print(f"Error loading of for {img_path}: {e}")
        return None
        
def get_or_make_thumbnail(img_path, thumbnail_max_size):
    cache_key = uniq_file_id(img_path, thumbnail_max_size)

    if cache_key in PIL_CACHE:
        return PIL_CACHE[cache_key]

    thumbnail_size_str = str(thumbnail_max_size)
    thumbnail_cache_subdir = os.path.join(THUMBNAIL_CACHE_ROOT, thumbnail_size_str)
    os.makedirs(thumbnail_cache_subdir, exist_ok=True)

    cached_thumbnail_path = os.path.join(thumbnail_cache_subdir, f"{cache_key}.png")

    pil_image_thumbnail = None

    # try reading from on-disk cache
    if  os.path.exists(cached_thumbnail_path):
        try:
            pil_image_thumbnail = Image.open(cached_thumbnail_path)
            PIL_CACHE[cache_key] = pil_image_thumbnail
            return pil_image_thumbnail
        except Exception as e:
            print(f"Error loading thumbnail for {img_path}: {e}")

    # if we are here, caching was not successful
    try:
        pil_image_thumbnail = resize_image( get_full_size_image(img_path), thumbnail_max_size, thumbnail_max_size )
        tmp_path = os.path.join(os.path.dirname(cached_thumbnail_path), "tmp-" + os.path.basename(cached_thumbnail_path))
        pil_image_thumbnail.save(tmp_path)
        os.replace(tmp_path, cached_thumbnail_path)
        PIL_CACHE[cache_key] = pil_image_thumbnail
    except Exception as e:
        print(f"Error loading of / creating thumbnail for {img_path}: {e}")

    return pil_image_thumbnail

def make_tk_image( pil_image ):
    if pil_image.mode not in ("RGB", "RGBA", "L", "1"):
        pil_image = pil_image.convert("RGBA")
    return ImageTk.PhotoImage(pil_image)


# --- dialogue box ---
def fallback_show_error(title, message):
    messagebox.showerror(title, message)
    
def custom_message_dialog(parent, title, message, font=("Arial", 12)):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)  # Set to be on top of the parent window
    
    # Calculate position to center the dialog on parent
    x = parent.winfo_rootx() + parent.winfo_width() // 2 - 200
    y = parent.winfo_rooty() + parent.winfo_height() // 2 - 100
    dialog.geometry(f"400x300+{x}+{y}")
    
    # Message area
    msg_frame = ttk.Frame(dialog, padding=20)
    msg_frame.pack(fill=tk.BOTH, expand=True)
    
    # Text widget with scrollbar for the message
    text_widget = tk.Text(msg_frame, wrap=tk.WORD, font=font, 
                          highlightthickness=0, borderwidth=0)
    scrollbar = tk.Scrollbar(msg_frame, orient="vertical", relief=SCROLLBAR_RELIEF,
                              command=text_widget.yview)
    text_widget.configure(yscrollcommand=scrollbar.set)
    
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # Insert the message text
    text_widget.insert(tk.END, message)
    text_widget.configure(state="disabled")  # Make read-only
    
    # OK button
    button_frame = ttk.Frame(dialog, padding=10)
    button_frame.pack(fill=tk.X)
    ok_button = ttk.Button(button_frame, text="OK", 
                          command=dialog.destroy, width=10)
    ok_button.pack(side=tk.RIGHT, padx=5)
    
    # Center dialog on screen
    dialog.update_idletasks()
    dialog.grab_set()  # Modal: user must interact with this window
    
    # Set focus and wait for window to close
    ok_button.focus_set()
    dialog.wait_window()

    
# --- Wallpaper Setting Functions (Platform-Specific) ---

def set_wallpaper(image_path, error_callback=fallback_show_error):
    """
    Set the wallpaper on Linux systems with support for multiple desktop environments.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        bool: True if wallpaper was successfully set, False otherwise
    """
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
            os.system(f"gsettings set org.gnome.desktop.background picture-uri '{file_uri}'")
            # For GNOME 40+ with dark mode support
            os.system(f"gsettings set org.gnome.desktop.background picture-uri-dark '{file_uri}'")
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
            os.system(f"qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '{script}'")
            success = True
            
        # XFCE
        elif 'xfce' in desktop_env:
            # Get the current monitor
            try:
                import subprocess
                props = subprocess.check_output(['xfconf-query', '-c', 'xfce4-desktop', '-p', '/backdrop', '-l']).decode('utf-8')
                monitors = set([p.split('/')[2] for p in props.splitlines() if p.endswith('last-image')])
                
                for monitor in monitors:
                    # Find all properties for this monitor
                    monitor_props = [p for p in props.splitlines() if f'/backdrop/screen0/{monitor}/' in p and p.endswith('last-image')]
                    for prop in monitor_props:
                        os.system(f"xfconf-query -c xfce4-desktop -p {prop} -s {abs_path}")
                success = True
            except:
                # Fallback for older XFCE
                os.system(f"xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/workspace0/last-image -s {abs_path}")
                success = True
                
        # Cinnamon
        elif 'cinnamon' in desktop_env:
            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri '{file_uri}'")
            success = True
            
        # MATE
        elif 'mate' in desktop_env:
            os.system(f"gsettings set org.mate.background picture-filename '{abs_path}'")
            success = True
            
        # LXQt, LXDE
        elif 'lxqt' in desktop_env or 'lxde' in desktop_env:
            # For PCManFM-Qt
            os.system(f"pcmanfm-qt --set-wallpaper={abs_path}")
            # For PCManFM
            os.system(f"pcmanfm --set-wallpaper={abs_path}")
            success = True
            
        # i3wm, sway and other tiling window managers often use feh
        elif any(de in desktop_env for de in ['i3', 'sway']):
            os.system(f"feh --bg-fill '{abs_path}'")
            success = True
            
        # Fallback method using feh (works for many minimal window managers)
        elif not success:
            # Try generic methods
            methods = [
                f"feh --bg-fill '{abs_path}'",
                f"nitrogen --set-scaled '{abs_path}'",
                f"gsettings set org.gnome.desktop.background picture-uri '{file_uri}'"
            ]
            
            for method in methods:
                exit_code = os.system(method)
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
    file_list = list_image_files(dir_path)
    file_list.extend( list_image_files( get_parent_directory( dir_path ) ) )
    for subdir in list_subdirectories( dir_path ):
        file_list.extend( list_image_files( subdir ) )
    return file_list


class BackgroundWorker:
    def background(self):
        while self.keep_running:
            old_size = self.current_size
            old_directory = self.current_dir
            to_do_list = list_relevant_files( old_directory )
            for path_name in to_do_list:
                if not self.keep_running:
                    return
                self.barrier()
                if self.keep_running and ( old_size == self.current_size ) and ( old_directory == self.current_dir ):
                    # print(f"background: {path_name}")
                    get_or_make_thumbnail(path_name, old_size)
                    self.path_name_queue.put(path_name)
                else:
                    break
            while self.keep_running and ( old_size == self.current_size ) and ( old_directory == self.current_dir ):
                time.sleep(2)

    def __init__(self, path, width):
        self.keep_running = True
        self.current_size = width
        self.current_dir = path
        
        self.path_name_queue = queue.Queue()

        self.worker = threading.Thread( target=self.background )
        self.block = threading.Event()
        self.worker.start()
        
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
        

def list_image_files(directory_path):
    if not os.path.isdir(directory_path):
        return []

    image_files = []

    for filename in os.listdir(directory_path):
        f_path = os.path.join(directory_path, filename)
        # Check if it's a file and its lowercase extension is in our supported list
        if os.path.isfile(f_path) and filename.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
            image_files.append(f_path)

    image_files.sort()
    return image_files

def settle_geometry(widget):
    while widget.master:
        widget = widget.master
    widget.update_idletasks()


# --- widgets ---

class EditableLabelWithCopy(tk.Frame):
    def __init__(self, master, initial_text="", on_rename_callback=None, font=None, **kwargs):
        """
        A widget with editable text field and a copy button using tk widgets.
        
        Args:
            master: Parent widget
            initial_text: Initial text in the field
            on_rename_callback: Function to call when text is changed and widget loses focus
                                Function should take (old_text, new_text) as parameters
            font: Font to use for the entry and button
            **kwargs: Additional arguments to pass to the Frame
        """
        super().__init__(master, **kwargs)
        
        self.original_text = initial_text
        self.on_rename_callback = on_rename_callback
        
        # Create a variable to store the current text
        self.text_var = tk.StringVar(value=initial_text)
        
        # Create the entry widget
        self.entry = tk.Entry(self, textvariable=self.text_var, relief="flat", borderwidth=2)
        if font:
            self.entry.configure(font=font)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Create the copy button
        self.copy_button = tk.Button(
            self, 
            text="Copy", 
            command=self._copy_to_clipboard,
            relief=BUTTON_RELIEF,
            borderwidth=2
        )
        if font:
            self.copy_button.configure(font=font)
        self.copy_button.pack(side="right")
        
        # Bind events
        self.bind("<Enter>", self._on_enter)
        self.entry.bind("<Enter>", self._on_enter)
        self.copy_button.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.entry.bind("<Return>", self._on_enter_pressed)
        
    def set_text(self, text):
        """Update the text in the entry field and reset the original text"""
        self.text_var.set(text)
        self.original_text = text
        
    def get_text(self):
        """Get the current text in the entry field"""
        return self.text_var.get()
    
    def _copy_to_clipboard(self):
        """Copy the current text to clipboard"""
        text = self.text_var.get()
        self.clipboard_clear()
        self.clipboard_append(text)
        
        # Visual feedback that copy succeeded
        current_bg = self.entry.cget("background")
        current_fg = self.entry.cget("foreground")
        self.entry.config(background="#90EE90", foreground="#000000")  # light green background
        self.after(200, lambda: self.entry.config(background=current_bg, foreground=current_fg))
    
    def _on_enter(self, event=None):
        self.entry.config(takefocus=1, state=tk.NORMAL)
        self.entry.focus_set()
        
    def _on_leave(self, event=None):
        self.entry.config(takefocus=0, state=tk.DISABLED)
        
    def _on_enter_pressed(self, event=None):
        self._rename()
        
    def _rename(self):
        new_text = self.text_var.get()
        if new_text != self.original_text and self.on_rename_callback:
            self.on_rename_callback(self.original_text, new_text)
            self.original_text = new_text


class ImageViewer(tk.Toplevel):
    """
    A widget for displaying an image with zooming and panning capabilities.
    """

    def __init__(self, master, image_info ):
        super().__init__(master, class_="kubux-image-manager")
        
        self.image_path = image_info[0]
        self.file_name = os.path.basename( self.image_path )
        self.dir_name = os.path.dirname( self.image_path )
        self._geometry = image_info[1]
        self.original_image = get_full_size_image(self.image_path)
        self.display_image = None
        self.photo_image = None
        self.is_fullscreen = False
        
        # Set window properties
        try:
            if os.path.islink(self.image_path):
                title = f"{self.file_name} (symlink to {os.path.realpath(self.image_path)})"
            else:
                title = self.file_name
        except Exception:
            title = self.file_name 
        self.title(title or "oops")
        
        if self._geometry is not None:
            self.geometry(self._geometry)            

        w, h = self.original_image.size
        x = w
        y = h
        while x < 120 and y < 120 :
            x = 2*x
            y = 2*y
        while 1300 < x or 900 < y:
            x = x / 1.1
            y = y / 1.1

        canvas_width = int(x)
        canvas_height = int(y)
            
        self.filename_widget = EditableLabelWithCopy(
            self,
            initial_text=self.file_name,
            on_rename_callback=self._rename_current_image,
            font=self.master.main_font
        )
        self.filename_widget.pack(side="bottom", fill="x", padx=5, pady=(0, 5))


        self.image_frame = tk.Frame(self)
        self.image_frame.pack(side="top", fill=tk.BOTH, expand=True)
            
        # Create a frame to hold the canvas and scrollbars
        if True:
            self.h_scrollbar = tk.Scrollbar(self.image_frame, orient=tk.HORIZONTAL, relief=SCROLLBAR_RELIEF)
            self.v_scrollbar = tk.Scrollbar(self.image_frame, orient=tk.VERTICAL, relief=SCROLLBAR_RELIEF)
            self.canvas = tk.Canvas(
                self.image_frame, 
                xscrollcommand=self.h_scrollbar.set,
                yscrollcommand=self.v_scrollbar.set,
                bg="black",
                width=canvas_width,
                height=canvas_height
            )
            self.h_scrollbar.config(command=self.canvas.xview)
            self.v_scrollbar.config(command=self.canvas.yview)
            self.canvas.grid(row=0, column=0, sticky="nsew")        
            self.h_scrollbar.grid(row=1, column=0, sticky="ew")
            self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.image_frame.columnconfigure(0, weight=1)
        self.image_frame.rowconfigure(0, weight=1)

        
        # Image display state
        self.zoom_factor = x / w
        self.fit_to_window = True  # Start in "fit to window" mode
        
        # Pan control variables
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.panning = False
        
        self.bind("<Configure>", self._on_configure)
        self._bind_canvas_events()
        self.focus_set()
        self.canvas.focus_set()
        
        self.update_idletasks()
        self._update_image()
        self.update_idletasks()
        
        self.resizable(True, True)
        self.wm_attributes("-type", "normal")
        self.wm_attributes('-fullscreen', False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._geometry=self.geometry()
    def get_image_info(self):
        self._geometry = self.geometry()
        return self.image_path, self._geometry
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        self.is_fullscreen = not self.is_fullscreen
        self.attributes('-fullscreen', self.is_fullscreen)
        self.update_idletasks()
        self._update_image()
    
    def _update_image(self):
        """Update the displayed image based on current zoom and size."""
        if not self.original_image:
            return
                
        # Get current canvas size
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # Use default size if canvas size not available yet
        if canvas_width <= 1:
            canvas_width = 800
        if canvas_height <= 1:
            canvas_height = 600
                
        # Get original image dimensions
        orig_width, orig_height = self.original_image.size
        
        # Calculate dimensions based on fit mode or zoom
        if self.fit_to_window:
            # Calculate scale to fit the window
            scale_width = canvas_width / orig_width
            scale_height = canvas_height / orig_height
            scale = min(scale_width, scale_height)
            self.zoom_factor = scale
            
            # Apply the scale
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
        else:
            # Apply the current zoom factor
            new_width = int(orig_width * self.zoom_factor)
            new_height = int(orig_height * self.zoom_factor)
        
        # Resize image
        self.display_image = self.original_image.resize(
            (new_width, new_height), 
            Image.LANCZOS
        )
        self.photo_image = ImageTk.PhotoImage(self.display_image)
        
        # Calculate the offset to center the image
        x_offset = max(0, (canvas_width - new_width) // 2)
        y_offset = max(0, (canvas_height - new_height) // 2)
        
        # Update canvas with new image
        self.canvas.delete("all")
        self.image_id = self.canvas.create_image(
            x_offset, y_offset, 
            anchor=tk.NW, 
            image=self.photo_image
        )
        
        # Set the scroll region - determine if scrolling is needed
        if new_width > canvas_width or new_height > canvas_height:
            # Image is larger than canvas, set scroll region to image size
            self.canvas.config(scrollregion=(0, 0, new_width, new_height))
            
            # When image is larger than canvas, we don't need the offset
            # We'll reposition the image at the origin for proper scrolling
            self.canvas.coords(self.image_id, 0, 0)
        else:
            # Image fits within canvas, include the offset in the scroll region
            self.canvas.config(scrollregion=(0, 0, 
                                            max(canvas_width, x_offset + new_width), 
                                            max(canvas_height, y_offset + new_height)))
        
        # Update scrollbars visibility based on image vs canvas size
        self._update_scrollbars()
        
        # If in fit mode or image is smaller than canvas, center the view
        if self.fit_to_window or (new_width <= canvas_width and new_height <= canvas_height):
            # Reset scroll position to start
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)

    def _update_scrollbars(self):
        """Show or hide scrollbars based on the image size compared to canvas."""
        # Get image and canvas dimensions
        img_width = self.display_image.width
        img_height = self.display_image.height
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # Show/hide horizontal scrollbar
        if img_width <= canvas_width:
            self.h_scrollbar.grid_remove()
            self.canvas.xview_moveto(0)  # Reset horizontal scroll position
        else:
            self.h_scrollbar.grid()
            
        # Show/hide vertical scrollbar
        if img_height <= canvas_height:
            self.v_scrollbar.grid_remove()
            self.canvas.yview_moveto(0)  # Reset vertical scroll position
        else:
            self.v_scrollbar.grid()

    def _canvas_focus(self, event):
        self.canvas.focus_set()
            
    def _bind_canvas_events(self):
        self.canvas.bind("<Enter>", self._canvas_focus)

        self.canvas.bind("<Key>", self._on_key)
        self.canvas.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.canvas.bind("<Escape>", self._on_escape)

        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        if platform.system() == "Windows":
            self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        else:
            self.canvas.bind("<Button-4>", self._on_mouse_wheel)
            self.canvas.bind("<Button-5>", self._on_mouse_wheel)
            
    def _on_escape(self, event):
        self._close()
    
    def _close(self):
        if self.is_fullscreen:
            self.toggle_fullscreen()
        self.master.open_images.remove(self)
        self.destroy()
        
    def _on_key(self, event):
        """Handle keyboard events."""
        key = event.char
        
        if key == '+' or key == '=':  # Zoom in
            self._zoom_in()
        elif key == '-' or key == '_':  # Zoom out
            self._zoom_out()
        elif key == '0':  # Reset zoom
            self.fit_to_window = True
            self._update_image()
    
    def _on_mouse_down(self, event):
        """Handle mouse button press."""
        self.panning = True
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        self.canvas.config(cursor="fleur")  # Change cursor to indicate panning
        
    def _on_mouse_drag(self, event):
        """Handle mouse drag for panning."""
        if not self.panning:
            return
            
        # Calculate the distance moved
        dx = self.pan_start_x - event.x
        dy = self.pan_start_y - event.y
        
        # Move the canvas view
        self.canvas.xview_scroll(dx, "units")
        self.canvas.yview_scroll(dy, "units")
        
        # Update the starting position
        self.pan_start_x = event.x
        self.pan_start_y = event.y
    
    def _on_mouse_up(self, event):
        """Handle mouse button release."""
        self.panning = False
        self.canvas.config(cursor="")  # Reset cursor
    
    def _on_mouse_wheel(self, event):
        """Handle mouse wheel events for zooming."""
        if platform.system() == "Windows":
            delta = event.delta
            if delta > 0:
                self._zoom_in(event.x, event.y)
            else:
                self._zoom_out(event.x, event.y)
        else:
            # For Linux/Unix/Mac
            if event.num == 4:  # Scroll up
                self._zoom_in(event.x, event.y)
            elif event.num == 5:  # Scroll down
                self._zoom_out(event.x, event.y)
                
    def _on_configure(self, event):
        """Handle window resize events."""
        # Only process events for the main window, not child widgets
        if event.widget == self and self.fit_to_window:
            # Delay update to avoid excessive redraws during resize
            self.after_cancel(getattr(self, '_resize_job', 'break'))
            self._resize_job = self.after(100, self._update_image)
    
    def _zoom_in(self, x=None, y=None):
        """Zoom in on the image."""
        self.fit_to_window = False
        self.zoom_factor *= 1.25
        
        # Save current view fractions before zooming
        if x is not None and y is not None:
            # Calculate the fractions to maintain zoom point
            x_fraction = self.canvas.canvasx(x) / (self.display_image.width)
            y_fraction = self.canvas.canvasy(y) / (self.display_image.height)
            
        # Update the image with new zoom
        self._update_image()
        
        # After zoom, scroll to maintain focus point
        if x is not None and y is not None:
            # Calculate new position in the zoomed image
            new_x = x_fraction * self.display_image.width
            new_y = y_fraction * self.display_image.height
            
            # Calculate canvas center
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            # Calculate scroll fractions
            x_view_fraction = (new_x - canvas_width / 2) / self.display_image.width
            y_view_fraction = (new_y - canvas_height / 2) / self.display_image.height
            
            # Apply the scroll
            self.canvas.xview_moveto(max(0, min(1, x_view_fraction)))
            self.canvas.yview_moveto(max(0, min(1, y_view_fraction)))
    
    def _zoom_out(self, x=None, y=None):
        """Zoom out from the image."""
        self.fit_to_window = False
        self.zoom_factor /= 1.25
        
        # Minimum zoom factor - if we go below this, switch to fit mode
        min_zoom = 0.1
        if self.zoom_factor < min_zoom:
            self.fit_to_window = True
            self._update_image()
            return
            
        # Same logic as zoom in for maintaining focus point
        if x is not None and y is not None:
            x_fraction = self.canvas.canvasx(x) / (self.display_image.width)
            y_fraction = self.canvas.canvasy(y) / (self.display_image.height)
            
        self._update_image()
        
        if x is not None and y is not None:
            new_x = x_fraction * self.display_image.width
            new_y = y_fraction * self.display_image.height
            
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            x_view_fraction = (new_x - canvas_width / 2) / self.display_image.width
            y_view_fraction = (new_y - canvas_height / 2) / self.display_image.height
            
            self.canvas.xview_moveto(max(0, min(1, x_view_fraction)))
            self.canvas.yview_moveto(max(0, min(1, y_view_fraction)))

    def _rename_current_image(self, old_name, new_name):
        print(f"renaming from {old_name} to {new_name}")
        try:
            new_path = os.path.join(self.dir_name, new_name)
            if os.path.exists(new_path):
                print(f"there already is a file {new_path}. Not overwriting.")
                return
            os.rename( self.image_path, new_path )
            self.image_path = new_path
            self.title( new_name )
        except Exception as e:
            print(f"renaming file {old_name} to {new_name} failed, error: {e}")    

            
class DirectoryThumbnailGrid(tk.Frame):
    def __init__(self, master=None, directory_path="", item_width=None, item_border_width=None,
                 button_config_callback=None, **kwargs):
        super().__init__(master, class_="kubux-image-manager", **kwargs)

        self._item_border_width = item_border_width
        self._directory_path = directory_path
        self._item_width = item_width
        self._button_config_callback = button_config_callback 
        self._widget_cache = OrderedDict() # This is a dict: hash_str -> (tk.Button, ImageTk.PhotoImage)
        self._cache_size = 2000
        self._active_widgets = {} # This is a dict: img_path -> (tk.Button, ImageTk.PhotoImage)
        self._last_known_width = -1
        self.pack_propagate(True)
        self.grid_propagate(True)    
        self.bind("<Configure>", self._on_resize)

    def get_width_and_height(self):
        self.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        return width, height
        
    def set_size_and_path(self, width, path):
        self._directory_path = path
        self._item_width = width
        return self.regrid()

    def _get_button(self, img_path, width):
        cache_key = uniq_file_id(img_path, width)
        target_btn, tk_image = self._widget_cache.get(cache_key, (None, None))
        
        if target_btn is None:
            target_btn = tk.Button(self, relief=BUTTON_RELIEF)
            tk_image_ref = self._configure_button(target_btn, img_path)
            assert not tk_image_ref is None
            self._widget_cache[cache_key] = (target_btn, tk_image_ref)
        else:
            assert not tk_image is None
            self._button_config_callback(target_btn, img_path, tk_image)
            self._widget_cache.move_to_end(cache_key)
            
        return target_btn, tk_image
            
    def regrid(self):
        new_image_paths_from_disk = list_image_files(self._directory_path)
        # Note: Since the helper returns sorted (oldest first), we need to reverse it
        # to match the existing behavior of showing newest first
        new_image_paths_from_disk.reverse()

        for btn, _ in self._active_widgets.values():
            assert btn is not None
            assert btn.winfo_exists()
            btn.grid_forget()

        self._active_widgets = {}

        # Create/reuse and configure buttons for the new set of image paths
        for img_path in new_image_paths_from_disk:
            target_btn, tk_image = self._get_button(img_path, self._item_width)
            self._active_widgets[img_path] = (target_btn, tk_image)
            
        return self._layout_the_grid()

    def _on_resize(self, event=None):
        self.update_idletasks()
        current_width = self.winfo_width() 
        current_height = self.winfo_height()

        if event is not None and event.width > 0:
            current_width = event.width
            
        if current_width <= 0 or current_width == self._last_known_width:
            return current_width, current_height

        # print(f"current_width = {current_width}, last known width = {self._last_known_width}")
            
        self._last_known_width = current_width

        desired_content_cols_for_width = self._calculate_columns(current_width)
        if desired_content_cols_for_width == 0:
            desired_content_cols_for_width = 1 

        actual_tk_total_cols = 0
        try:
            actual_tk_total_cols = self.grid_size()[0]
        except TclError:
            pass 

        actual_tk_content_cols = 0
        if actual_tk_total_cols >= 2: 
            actual_tk_content_cols = actual_tk_total_cols - 2
        elif actual_tk_total_cols > 0:
            actual_tk_content_cols = actual_tk_total_cols

        if desired_content_cols_for_width != actual_tk_content_cols:
            return self._layout_the_grid()
        
        return self.get_width_and_height()

    def _calculate_columns(self, frame_width):
        if frame_width <= 0: return 1
        item_total_occupancy_width = self._item_width + (2 * self._item_border_width)
        buffer_for_gutters_and_edges = 10 
        available_width_for_items = frame_width - buffer_for_gutters_and_edges
        if available_width_for_items <= 0: return 1
        calculated_cols = max(1, available_width_for_items // item_total_occupancy_width)
        return calculated_cols

    def _layout_the_grid(self):
        desired_content_cols_for_this_pass = self._calculate_columns(self.master.winfo_width())
        if desired_content_cols_for_this_pass == 0:
            desired_content_cols_for_this_pass = 1 

        current_configured_cols = 0
        try:
            current_configured_cols = self.grid_size()[0]
        except TclError:
            pass
        for i in range(current_configured_cols):
            self.grid_columnconfigure(i, weight=0)
            
        self.grid_columnconfigure(0, weight=1)  
        self.grid_columnconfigure(desired_content_cols_for_this_pass + 1, weight=1) 

        # Widget Placement Loop
        for i, img_path in enumerate(self._active_widgets.keys()):
            widget, _ = self._active_widgets.get(img_path) 
            
            if widget is None or not widget.winfo_exists():
                print(f"Warning: Attempted to layout a non-existent widget for path '{img_path}'. Skipping.")
                continue
            row, col_idx = divmod(i, desired_content_cols_for_this_pass)
            grid_column = col_idx + 1 
            widget.grid(row=row, column=grid_column, padx=2, pady=2) 
        
        while len(self._widget_cache) > self._cache_size:
            self._widget_cache.popitem(last=False)

        return self.get_width_and_height()
    
    def _configure_button(self, btn, img_path):
        thumbnail_pil = get_or_make_thumbnail(img_path, self._item_width)
        tk_thumbnail = None
        if thumbnail_pil:
            try:
                tk_thumbnail = make_tk_image(thumbnail_pil)
            except Exception as e:
                print(f"Error converting PIL image to ImageTk.PhotoImage for {img_path}: {e}")
        
        if tk_thumbnail is not None:
            btn.config(image=tk_thumbnail)
        elif tk_thumbnail is None: 
            btn.config(image=None)
            
        if self._button_config_callback:
            self._button_config_callback(btn, img_path, tk_thumbnail)
        else:
            btn.config(relief="flat", borderwidth=0, cursor="arrow", command=None)
            
        return tk_thumbnail

    def destroy(self):
        for btn, _ in self._active_widgets.values(): 
            if btn is not None and btn.winfo_exists():
                btn.image = None
                btn.destroy() 
        self._active_widgets.clear()
        for btn, _ in self._widget_cache.values():
            if btn is not None and btn.winfo_exists():
                btn.image = None
                btn.destroy() 
        self._widget_cache.clear()
        super().destroy()


class LongMenu(tk.Toplevel):
    def __init__(self, master, default_option, other_options, font=None, x_pos=None, y_pos=None):
        super().__init__(master)
        self.overrideredirect(True) # Remove window decorations (title bar, borders)
        self.transient(master)      # Tie to master window
        # self.grab_set()             # Make it modal, redirect all input here

        self.result = default_option
        self._options = other_options

        self._main_font = font if font else ("TkDefaultFont", 12, "normal")

        self._listbox_frame = ttk.Frame(self)
        self._listbox_frame.pack(padx=10, pady=10, fill="both", expand=True)

        self._listbox = tk.Listbox(
            self._listbox_frame,
            selectmode=tk.SINGLE,
            font=self._main_font,
            height=15
        )
        self._listbox.pack(side="left", fill="both", expand=True)

        self._scrollbar = tk.Scrollbar(self._listbox_frame, relief=SCROLLBAR_RELIEF, orient="vertical", command=self._listbox.yview)
        self._scrollbar.pack(side="right", fill="y")
        self._listbox.config(yscrollcommand=self._scrollbar.set)

        # Populate the _listbox
        for option_name in other_options:
            self._listbox.insert(tk.END, option_name)

        # --- Bindings ---
        self._listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        self._listbox.bind("<Double-Button-1>", self._on_double_click) # Double-click to select and close
        self.bind("<Return>", self._on_return_key) # Enter key to select and close
        self.bind("<Escape>", self._cancel) # Close on Escape key
        self.bind("<FocusOut>", self._on_focus_out)
        
        # --- Positioning and Focus ---
        self.update_idletasks()
        self.grab_set() 

        if x_pos is None or y_pos is None:
            master_x = master.winfo_x()
            master_y = master.winfo_y()
            master_h = master.winfo_height()
            x_pos = master_x
            y_pos = master_y + master_h

        screen_width = self.winfo_screenwidth()
        popup_w = self.winfo_width()
        if x_pos + popup_w > screen_width:
            x_pos = screen_width - popup_w - 5 # 5 pixels margin
            
        # Adjust if menu would go off-screen downwards (or upwards if preferred)
        screen_height = self.winfo_screenheight()
        popup_h = self.winfo_height()
        if y_pos + popup_h > screen_height:
            y_pos = screen_height - popup_h - 5 # 5 pixels margin
            
        self.geometry(f"+{int(x_pos)}+{int(y_pos)}")        # Center the window relative to its master

        self._listbox.focus_set() # Set focus to the _listbox for immediate keyboard navigation
        self.wait_window(self) # Make the dialog modal until it's destroyed

    def _on_listbox_select(self, event):
        self._exit_ok()

    def _on_double_click(self, event):
        self._exit_ok()

    def _on_return_key(self, event):
        self._exit_ok()

    def _exit_ok(self):
        selected_indices = self._listbox.curselection()
        if selected_indices:
            # Store the selected directory name, not the full path yet
            self.result = self._options[selected_indices[0]]
        self.destroy()

    def _cancel(self, event=None):
        self.result = None
        self.destroy()

    def _on_focus_out(self, event):
        # If the widget losing focus is not a child of this menu (e.g., clicking outside)
        # then close the menu.
        if self.winfo_exists() and not self.focus_get() in self.winfo_children():
            self._cancel()

        
class BreadCrumNavigator(ttk.Frame):
    def __init__(self, master, on_navigate_callback=None, font=None,
                 long_press_threshold_ms=400, drag_threshold_pixels=5):
        
        super().__init__(master)
        self._on_navigate_callback = on_navigate_callback
        self._current_path = ""

        self._LONG_PRESS_THRESHOLD_MS = long_press_threshold_ms
        self._DRAG_THRESHOLD_PIXELS = drag_threshold_pixels

        self._long_press_timer_id = None
        self._press_start_time = 0
        self._press_x = 0
        self._press_y = 0
        self._active_button = None 

        if isinstance(font, tkFont.Font):
            self.btn_font = (
                font.actual('family'),
                font.actual('size'),
                font.actual('weight') 
            )
        elif isinstance(font, (tuple, str)):
            self.btn_font = font
        else:
            self.btn_font = ("TkDefaultFont", 10, "normal") 

    def set_path(self, path):
        if not os.path.isdir(path):
            print(f"Warning: Path '{path}' is not a directory. Cannot set breadcrumbs.")
            return

        self._current_path = os.path.normpath(path)
        self._update_breadcrumbs()

    def _update_breadcrumbs(self):
        for widget in self.winfo_children():
            widget.destroy()

        btn_list = []
        current_display_path = self._current_path
        while len(current_display_path) > 1: 
            path = current_display_path
            current_display_path = os.path.dirname(path)
            btn_text = os.path.basename(path)
            if btn_text == '': 
                btn_text = os.path.sep
            btn = tk.Button(self, text=btn_text, relief=BUTTON_RELIEF, font=self.btn_font)
            btn.path = path
            btn.bind("<ButtonPress-1>", self._on_button_press)
            btn.bind("<ButtonRelease-1>", self._on_button_release)
            btn.bind("<Motion>", self._on_button_motion)
            btn_list.insert( 0, btn )

        btn_text="//"
        btn = tk.Button(self, text=btn_text, relief=BUTTON_RELIEF, font=self.btn_font)
        btn.path = current_display_path
        btn.bind("<ButtonPress-1>", self._on_button_press)
        btn.bind("<ButtonRelease-1>", self._on_button_release)
        btn.bind("<Motion>", self._on_button_motion)
        btn_list.insert( 0, btn )

        dummy_frame = tk.Frame(self)
        dummy_frame.pack(side="right", fill="x", expand=True)
        for i, btn in enumerate( reversed(btn_list) ):
            btn.pack(side="right")
            if i + 1< len(btn_list):
                ttk.Label(self, text="/").pack(side="right")
            if i == 0:
                btn.bind("<ButtonPress-1>", self._on_button_press_menu)

    def _trigger_navigate(self, path):
        if self._on_navigate_callback:
            self._on_navigate_callback(path)

    def _on_button_press_menu(self, event):
        self._show_subdirectory_menu( event.widget )
            
    def _on_button_press(self, event):
        self._press_start_time = time.time()
        self._press_x, self._press_y = event.x_root, event.y_root
        self._active_button = event.widget
        self._long_press_timer_id = self.after(self._LONG_PRESS_THRESHOLD_MS,
                                               lambda: self._on_long_press_timeout(self._active_button))

    def _on_button_release(self, event):
        if self._long_press_timer_id:
            self.after_cancel(self._long_press_timer_id)
            self._long_press_timer_id = None

        if self._active_button:
            dist = (abs(event.x_root - self._press_x)**2 + abs(event.y_root - self._press_y)**2)**0.5
            if dist < self._DRAG_THRESHOLD_PIXELS:
                if (time.time() - self._press_start_time) * 1000 < self._LONG_PRESS_THRESHOLD_MS:
                    path = self._active_button.path
                    if path and self._on_navigate_callback:
                        self._on_navigate_callback(path)
            self._active_button = None

    def _on_button_motion(self, event):
        if self._active_button and self._long_press_timer_id:
            dist = (abs(event.x_root - self._press_x)**2 + abs(event.y_root - self._press_y)**2)**0.5
            if dist > self._DRAG_THRESHOLD_PIXELS:
                self.after_cancel(self._long_press_timer_id)
                self._long_press_timer_id = None
                self._active_button = None

    def _on_long_press_timeout(self, button):
        if self._active_button is button:
            self._show_subdirectory_menu(button)
            self._long_press_timer_id = None

    def _show_subdirectory_menu(self, button):
        path = button.path
        selected_path = path

        all_entries = os.listdir(path)
        subdirs = []
        hidden_subdirs = []
        for entry in all_entries:
            full_path = os.path.join( path, entry )
            if os.path.isdir( full_path ):
                if entry.startswith('.'):
                    hidden_subdirs.append(entry)
                else:
                    subdirs.append(entry)
        subdirs.sort()
        hidden_subdirs.sort()
        sorted_subdirs = subdirs + hidden_subdirs
        
        if sorted_subdirs:
            button_x = button.winfo_rootx()
            button_y = button.winfo_rooty()
            button_height = button.winfo_height()
            menu_x = button_x
            menu_y = button_y + button_height
            selector_dialog = LongMenu(
                button,
                None,
                sorted_subdirs,
                font=self.btn_font,
                x_pos=menu_x,
                y_pos=menu_y
            )
            selected_name = selector_dialog.result
            if selected_name:
                selected_path = os.path.join(path, selected_name)
                
        self._trigger_navigate(selected_path)

        
class ImagePicker(tk.Toplevel):
    def __init__(self, master, picker_info = None):
        super().__init__(master, class_="kubux-image-manager")

        self._master = master
        self._thumbnail_width = picker_info[0]
        self._image_dir = picker_info[1]
        self.background_worker = BackgroundWorker( self._image_dir, self._thumbnail_width )
        self._geometry = picker_info[2]
        self._update_thumbnail_job = None
        self.watcher = DirectoryWatcher(self)
        self.geometry(self._geometry)
        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._cache_widget)

    def _cache_widget(self):
        try:
            path_name = self.background_worker.path_name_queue.get_nowait()
            self._gallery_grid._get_button(path_name, self._thumbnail_width)
            # print(f"created button for {path_name} at size {self._thumbnail_max_size}")
        except queue.Empty:
            pass
        self.after(50, self._cache_widget)

    def get_picker_info(self):
        self._geometry = self.geometry()
        return self._thumbnail_width, self._image_dir, self._geometry
        
    def _on_clone(self):
        self.master.open_picker_dialog( self.get_picker_info() )
        
    def _repaint(self):
        self._gallery_grid.set_size_and_path(self._thumbnail_width, self._image_dir)
        self.update_idletasks()

    def _create_widgets(self):
        # Thumbnail Display Area (Canvas and Scrollbar)
        self._canvas_frame = ttk.Frame(self)
        self._canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._gallery_canvas = tk.Canvas(self._canvas_frame, bg=self.cget("background"))
        self._gallery_scrollbar = tk.Scrollbar(self._canvas_frame, relief=SCROLLBAR_RELIEF, orient="vertical", command=self._gallery_canvas.yview)
        self._gallery_canvas.config(yscrollcommand=self._gallery_scrollbar.set)
        
        self._gallery_scrollbar.pack(side="right", fill="y")
        self._gallery_canvas.pack(side="left", fill="both", expand=True)
        
        self._gallery_grid = DirectoryThumbnailGrid(
            self._gallery_canvas,
            directory_path=self._image_dir,
            item_width=self._thumbnail_width,
            item_border_width=6,
            button_config_callback=self._configure_picker_button,
            bg=self.cget("background")
        )
        self._gallery_canvas.create_window((0, 0), window=self._gallery_grid, anchor="nw")

        self._gallery_canvas.bind("<Configure>", self._on_canvas_configure)
        self._gallery_grid.bind("<Configure>", lambda e: self._gallery_canvas.configure(scrollregion=self._gallery_canvas.bbox("all")))
        
        self._bind_mousewheel(self)

        self.bind("<Up>", lambda e: self._gallery_canvas.yview_scroll(-1, "units"))
        self.bind("<Down>", lambda e: self._gallery_canvas.yview_scroll(1, "units"))
        self.bind("<Prior>", lambda e: self._gallery_canvas.yview_scroll(-1, "pages"))
        self.bind("<Next>", lambda e: self._gallery_canvas.yview_scroll(1, "pages"))
        self.bind("<Escape>", lambda e: self._on_close())

        # Control Frame (at the bottom)
        self._control_frame = ttk.Frame(self)
        self._control_frame.pack(fill="x", padx=5, pady=5)

        # Breadcrumb Frame
        self.breadcrumb_nav = BreadCrumNavigator(
            self._control_frame, # Parent is the _control_frame
            on_navigate_callback=self._browse_directory, # This callback will update the grid and breadcrumbs
            font=self._master.main_font, # Use the app's font
        )
        self.breadcrumb_nav.pack(side="left", fill="x", expand=True, padx=5)


        # Right side: Clone and Close buttons, thumnail slider
        tk.Button(self._control_frame, font=self._master.main_font, text="Close", relief=BUTTON_RELIEF, command=self._on_close).pack(side="right", padx=(24, 2))
        tk.Button(self._control_frame, font=self._master.main_font, text="Clone", relief=BUTTON_RELIEF, command=self._on_clone).pack(side="right", padx=(24, 2))

        dummy_C_frame = tk.Frame(self._control_frame)
        dummy_C_frame.pack(side="right", expand=False, fill="x")
        self.thumbnail_slider = tk.Scale(
            dummy_C_frame, from_=96, to=480, orient="horizontal", relief=SCALE_RELIEF,
            resolution=20, showvalue=False
        )
        self.thumbnail_slider.set(self._thumbnail_width)
        self.thumbnail_slider.config(command=self._update_thumbnail_width)
        self.thumbnail_slider.pack(anchor="e")
        dummy_C_label = tk.Label(self._control_frame, text="Size:", font=self.master.main_font)
        dummy_C_label.pack(side="right", padx=(12,0))

        self.watcher.start_watching(self._image_dir)
        self._browse_directory(self._image_dir)
        self._gallery_canvas.yview_moveto(0.0)
        self.after(100, self.focus_set)

    def _adjust_gallery_scroll_position(self, old_scroll_fraction=0.0):
        bbox = self._gallery_canvas.bbox("all")

        if not bbox:
            self._gallery_canvas.yview_moveto(0.0)
            return
    
        total_content_height = bbox[3] - bbox[1] # y2 - y1
        visible_canvas_height = self._gallery_canvas.winfo_height()
        if total_content_height <= visible_canvas_height:
            self._gallery_canvas.yview_moveto(0.0)
            return

        old_abs_scroll_pos = old_scroll_fraction * total_content_height
        max_scroll_abs_pos = total_content_height - visible_canvas_height
        if max_scroll_abs_pos < 0: # Should not happen if previous check passed, but for safety
            max_scroll_abs_pos = 0

        new_abs_scroll_pos = min(old_abs_scroll_pos, max_scroll_abs_pos)
        new_scroll_fraction = new_abs_scroll_pos / total_content_height

        self._gallery_canvas.yview_moveto(new_scroll_fraction)
        
    def _show_full_image(self, img_path):
        args = [ img_path ]
        self.master.execute_current_command_with_args( args )
        
    def _configure_picker_button(self, btn, img_path, tk_thumbnail):
         btn.config(
            cursor="hand2", 
            relief="flat", 
            borderwidth=0,
            highlightthickness=3,
            bg=self.cget("background"),
            command=lambda dummy=None: self._toggle_selection(img_path, btn)
         )
         btn.bind("<Button-3>", lambda dummy: self._show_full_image(img_path))
        
         if img_path in self.master.selected_files:
             btn.config(highlightbackground="blue")
         else:
             btn.config(highlightbackground=self.cget("background"))

    def _on_close(self):
        self.background_worker.stop()
        self.watcher.stop_watching()
        self.master.open_picker_dialogs.remove(self)
        self.destroy()

    def _browse_directory(self, path):
        if not os.path.isdir(path):
            custom_message_dialog(parent=self, title="Error", message=f"Invalid directory: {path}", font=self._master.main_font)
            return
        
        self._image_dir = path
        self.watcher.change_dir( path )
        self.background_worker.run( path, self._thumbnail_width )
            
        self.breadcrumb_nav.set_path(path)
        self.update_idletasks()
        self._repaint()
        self._adjust_gallery_scroll_position()

    def _toggle_selection(self, img_path, button_widget):
        self.master.toggle_selection(img_path)

    def _on_canvas_configure(self, event):
        self._gallery_canvas.itemconfig(self._gallery_canvas.find_all()[0], width=event.width)
        old_scroll_fraction = self._gallery_canvas.yview()[0]
        width, height = self._gallery_grid._on_resize()
        # print(f"widht = {width}, height = {height}")
        self._gallery_canvas.configure(scrollregion=(0, 0, width, height))
        self._adjust_gallery_scroll_position(old_scroll_fraction)

    def _update_thumbnail_width(self, value):
        if self._update_thumbnail_job: self.after_cancel(self._update_thumbnail_job)
        self._update_thumbnail_job = self.after(400, lambda: self._do_update_thumbnail_width(int(value)))
        
    def _do_update_thumbnail_width(self, value):
        self._thumbnail_width = value
        self._repaint()
        
    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", lambda e: self._on_mousewheel(e), add="+")
        widget.bind("<Button-5>", lambda e: self._on_mousewheel(e), add="+")

    def _on_mousewheel(self, event):
        if platform.system() == "Windows": self._gallery_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif event.num == 4: self._gallery_canvas.yview_scroll(-1, "units")
        elif event.num == 5: self._gallery_canvas.yview_scroll(1, "units")


class FlexibleTextField(tk.Frame):
    def __init__(self, parent, command_callback, commands="", font=None):
        super().__init__(parent)
        self.command_callback = command_callback
        self._previous_index = None
        self._font = font
        self._create_widgets()
        self._set_commands(commands)

    def _create_widgets(self):
        self.text_area = tk.Text(self, wrap=tk.NONE, font=self._font, height=1, width=1)
        self.text_scroll = tk.Scrollbar(self, relief=SCROLLBAR_RELIEF, orient=tk.VERTICAL, command=self.text_area.yview)
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text_area.config(yscrollcommand=self.text_scroll.set)
        self.text_area.tag_configure('current_line_highlight', background='#e0e0e0', selectbackground='#d0d0d0')
        self.text_area.bind("<Double-Button-1>", self._on_double_click_select)
        self.text_area.bind("<<CursorMoved>>", self._on_cursor_move)
        self.text_area.bind("<KeyRelease>", self._on_cursor_move)
        self.text_area.bind("<ButtonRelease-1>", self._on_cursor_move)
        self.text_area.focus_set()

    def _set_index(self, index):
        self.text_area.mark_set(tk.INSERT, f"{index}.0")
        self.text_area.see(tk.INSERT)
        self._on_cursor_move(None)
        
    def _set_commands(self, commands):
        self.commands = commands
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", commands)
        self._set_index(1)
        
    def _current_index(self):
        return self.text_area.index(tk.INSERT).split('.')[0]

    def _on_cursor_move(self, event):
        current_index = self._current_index()
        # print(f"move from {self._previous_index} to {current_index}")
        if current_index != self._previous_index:
            if self._previous_index:
                self.text_area.tag_remove('current_line_highlight', "1.0", tk.END)
            self.text_area.tag_add('current_line_highlight', f"{current_index}.0", f"{current_index}.end")
            self._previous_index = current_index

    def _on_double_click_select(self, event):
        index = self.text_area.index(f"@{event.x},{event.y}").split('.')[0]
        command = self.text_area.get(f"{index}.0", f"{index}.end").strip()
        if command:
            self.command_callback(command)
            # print(f"Double-clicked and selected line: '{command}'")
        else:
            # print("Double-clicked on an empty line.")
            pass
        self._on_cursor_move(None)

    def current_command(self):
        index = self._current_index()
        start = f"{index}.0"
        end = f"{index}.end"
        return self.text_area.get(start, end).strip()

    def current_text(self):
        return self.text_area.get("1.0", tk.END)

    def call_current_command(self):
        command = self.current_command()
        if command:
            self.command_callback(command)

            
def expand_env_vars(input_string: str) -> str:
    # Regex to find patterns like ${VAR_NAME}.
    # [A-Za-z_] for start, [A-Za-z0-9_]* for subsequent chars in var name.
    env_var_pattern = r'\${([A-Za-z_][A-Za-z0-9_]*)}'

    def replacer(match):
        var_name = match.group(1) # Get the variable name (e.g., "HOME", "USER")
        value = os.getenv(var_name, "")
        if not value:
            # You might want to use a logging system in a larger application.
            print(f"Warning: Environment variable '{var_name}' not found. Replacing with empty string.")
        return value

    # Use re.sub to find all matches of the pattern and replace them
    # using the 'replacer' function.
    return re.sub(env_var_pattern, replacer, input_string)

def expand_wildcards(command_line: str, selected_files: list[str]) -> list[str]:
    try:
        raw_tokens = shlex.split(command_line)
    except ValueError as e:
        print(f"Error parsing command line '{command_line}': {e}")
        return [command_line]

    if not raw_tokens:
        return []

    has_single_wildcard = '*' in raw_tokens
    has_list_wildcard = '{*}' in raw_tokens

    # --- Initial Error/Warning Handling ---
    if (has_single_wildcard or has_list_wildcard) and not selected_files:
        return []
    
    keep_fingers_crossed = "dasdklasdashdaisdhiunerwehuacnkajdasudhuiewrnksvjiurkanr"
    quoted_args = shlex.join(selected_files)
    outputs = []
    for file in selected_files:
        quoted_file = shlex.quote(file)
        cmd = command_line.replace("{*}", keep_fingers_crossed).replace("*", quoted_args).replace(keep_fingers_crossed, quoted_file)
        outputs.append( cmd )
    if outputs:
        return outputs

    return [ command_line.replace("*", quoted_args) ]

        
class ImageManager(tk.Tk):
    def __init__(self):
        super().__init__(className="kubux-image-manager")
        self._load_app_settings()
        self.title("kubux image manager")
        self.configure(background=self.cget("background"))
        font_name, font_size = get_linux_system_ui_font_info()
        self.ui_scale = 1.0
        self._ui_scale_job = None
        self.base_font_size = font_size
        self.main_font = tkFont.Font(family=font_name, size=int(self.base_font_size * self.ui_scale))
        self.geometry(self.main_win_geometry)
        self._create_widgets()
        self.open_picker_dialogs = [] # list of ( thmbn_width, path, geometry )
        self.open_picker_dialogs_from_info()
        self.open_images = [] # list of (path, geometry)
        self.open_images_from_info()
        self.command_field._set_index( self.current_index )
        
    def collect_open_picker_info(self):
        self.open_picker_info = []
        for picker in self.open_picker_dialogs:
            self.open_picker_info.append( picker.get_picker_info() )
        return self.open_picker_info

    def open_picker_dialogs_from_info(self):
        for picker_info in self.open_picker_info:
            self.open_picker_dialog( picker_info )

    def open_picker_dialog(self, picker_info):
        dummy = ImagePicker(self, picker_info)
        self.open_picker_dialogs.append( dummy )        
        
    def collect_open_image_info(self):
        self.open_image_info = []
        for image in self.open_images:
            self.open_image_info.append( image.get_image_info() )
        return self.open_image_info
    
    def open_images_from_info(self):
        for image_info in self.open_image_info:
            self.open_image( image_info )
            
    def open_image(self, image_info):
        dummy = ImageViewer(self, image_info)
        self.open_images.append( dummy )
        
    def _load_app_settings(self):
        try:
            if os.path.exists(APP_SETTINGS_FILE):
                with open(APP_SETTINGS_FILE, 'r') as f:
                    self.app_settings = json.load(f)
            else:
                self.app_settings = {}
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error loading app settings, initializing defaults: {e}")
            self.app_settings = {}

        self.ui_scale = self.app_settings.get("ui_scale", 1.0)
        self.main_win_geometry = self.app_settings.get("main_win_geometry", "300x400")
        self.commands = self.app_settings.get("commands", "Open {*}\nSetWP *\nOpen ${HOME}/Pictures\necho {*} >> /tmp/files")
        self.current_index = self.app_settings.get("current_index", 1)
        self.selected_files = self.app_settings.get("selected_files", [])
        self.new_picker_info = self.app_settings.get("new_picker_info", [ 192, PICTURES_DIR, "1000x600" ])
        self.open_picker_info = self.app_settings.get("open_picker_info", [])
        self.open_image_info = self.app_settings.get("open_image_info", [])
        
    def _save_app_settings(self):
        try:
            if not hasattr(self, 'app_settings'):
                self.app_settings = {}

            self.app_settings["ui_scale"] = self.ui_scale
            self.app_settings["main_win_geometry"] = self.geometry()
            self.app_settings["commands"] = self.command_field.current_text().rstrip('\n')
            self.app_settings["current_index"] = self.command_field._current_index()
            self.app_settings["selected_files"] = self.selected_files
            self.app_settings["new_picker_info"] = self.new_picker_info
            self.app_settings["open_picker_info"] = self.collect_open_picker_info()
            self.app_settings["open_image_info"] = self.collect_open_image_info()

            with open(APP_SETTINGS_FILE, 'w') as f:
                json.dump(self.app_settings, f, indent=4)
        except Exception as e:
            print(f"Error saving app settings: {e}")
            
    def _create_widgets(self):
        self.style = ttk.Style()
        self.style.configure('.', font=self.main_font)
        self.main_container = tk.Frame(self)
        self.main_container.pack(side="top", fill="both", expand=True, padx=5, pady=(5, 0))
        if True:
            self.command_field = FlexibleTextField( self.main_container, commands=self.commands,
                                                    command_callback=self.execute_command,
                                                    font = self.main_font )
            self.command_field.pack(side="top", fill="both", expand=True, padx=5, pady=5 )

            self.controll_frame = tk.Frame( self.main_container )
            self.controll_frame.pack( side="bottom", fill="x", expand=False, padx=5, pady=5 )
            if True:
                self.exec_button = tk.Button( self.controll_frame, relief=BUTTON_RELIEF, text="Process selected", font = self.main_font, command = self.execute_current_command )
                self.exec_button.pack(side="left", padx=5)
                self.deselect_button = tk.Button( self.controll_frame, relief=BUTTON_RELIEF, text="Clear selection", font = self.main_font, command = self.clear_selection)
                self.deselect_button.pack(side="left", padx=5)

                self.quit_button = tk.Button( self.controll_frame, relief=BUTTON_RELIEF, text="Quit", font = self.main_font, command = self.close)
                self.quit_button.pack(side="right", padx=5)

                dummy_C_frame = tk.Frame(self.controll_frame)
                dummy_C_frame.pack(side="right", expand=False, fill="x")
                self.ui_slider = tk.Scale(
                    dummy_C_frame, from_=0.5, to=3.5, orient="horizontal", relief=SCALE_RELIEF,
                    resolution=0.1, showvalue=False
                )
                self.ui_slider.set(self.ui_scale)
                self.ui_slider.config(command=self._update_ui_scale)
                self.ui_slider.pack(anchor="e")
                dummy_C_label = tk.Label(self.controll_frame, text="UI:", font=self.main_font)
                dummy_C_label.pack(side="right", padx=(12,0))

        self.update_button_status()
                
    def execute_command_with_args(self, command, args):
        print(f"execute: {command} with args = {args}")
        command = expand_env_vars(command)
        print(f"command after expansion of environment variables = {command}")
        to_do = expand_wildcards( command, args )
        for cmd in to_do:
            print(f"executing {cmd}")
            if cmd.startswith("Open"):
                print(f"execute as an internal command: {cmd}")
                path_list = shlex.split( cmd )
                del path_list[0]
                for path in path_list:
                    self.open_path(path)
            elif cmd.startswith("SetWP"):
                print(f"execute as an internal command: {cmd}")
                path_list = shlex.split( cmd )
                del path_list[0]
                if path_list:
                    self.set_wp(path_list[-1])
            else:
                print(f"execute as a shell command: {cmd}")
                self.execute_shell_command(cmd)
                self.broadcast_contents_change()

    def execute_command(self, command):
        self.execute_command_with_args( command, self.selected_files)
                
    def execute_current_command(self):
        self.execute_command(self.command_field.current_command())

    def execute_current_command_with_args(self, args):
        self.execute_command_with_args(self.command_field.current_command(), args)
        
    def broadcast_selection_change(self):
        for picker in self.open_picker_dialogs:
            picker._repaint()

    def broadcast_contents_change(self):
        for picker in self.open_picker_dialogs:
            # print(f"alerting image picker for directory {picker.get_picker_info()[1]}")
            picker._repaint()
        
    def select_file(self, path):
        print(f"selecting {path}")
        self.selected_files.append(path)
        self.broadcast_selection_change()
        
    def unselect_file(self, path):
        print(f"unselecting {path}")
        self.selected_files.remove(path)
        self.broadcast_selection_change()
        
    def _do_update_ui_scale(self, scale_factor):
        self.ui_scale = scale_factor
        new_size = int(self.base_font_size * scale_factor)
        self.main_font.config(size=new_size)
        def update_widget_fonts(widget, font):
            try:
                if 'font' in widget.config(): widget.config(font=font)
            except tk.TclError: pass
            for child in widget.winfo_children(): update_widget_fonts(child, font)
        update_widget_fonts(self, self.main_font)

    def _update_ui_scale(self, value):
        if self._ui_scale_job: self.after_cancel(self._ui_scale_job)
        self._ui_scale_job = self.after(400, lambda: self._do_update_ui_scale(float(value)))

    def clear_selection(self):
        print(f"clearing selection")
        self.selected_files = []
        self.broadcast_selection_change()
        self.update_button_status()
        
    def toggle_selection(self, file):
        if file in self.selected_files:
            self.unselect_file(file)
        else:
            self.select_file(file)
        self.update_button_status()

    def update_button_status(self):
        if not self.selected_files:
            self.deselect_button.config(state="disabled")
        else:
            self.deselect_button.config(state="normal")
        
    def close(self):
        self._save_app_settings()
        for picker in self.open_picker_dialogs:
            picker._on_close()
        self.destroy()

    def open_path(self, path):
        try:
            if os.path.isdir(path):
                self.open_image_directory(path)
                return
            if os.path.isfile(path):
                self.open_image_file(path)
                return
        except Exception as e:
            print(f"path {path} has problems, message: {e}")
            traceback.print_exc()
        
    def open_image_file(self, file_path):
        print(f"opening file {file_path}")
        self.open_image([ file_path, None ])
        
    def open_image_directory(self, directory_path):
        print(f"opening directory {directory_path}")
        if self.open_picker_dialogs:
            self.new_picker_info = self.open_picker_dialogs[-1].get_picker_info()
        self.open_picker_dialog([ self.new_picker_info[0], directory_path, self.new_picker_info[2] ])

    def set_wp(self, path):
        try:
            if os.path.isfile(path):
                set_wallpaper(path)
        except Exception as e:
            print(f"path {path} has problems, message: {e}")
                
    def execute_shell_command(self, command):
        result = subprocess.run(command, shell=True)
        print(f"return code = {result.returncode}")
        print(f"stdout = {result.stdout}")
        print(f"stderr = {result.stderr}")
        
        
if __name__ == "__main__":
    app = ImageManager()
    app.mainloop()
