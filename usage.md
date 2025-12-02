# Kubux Image Manager - User Guide

This guide covers all features of Kubux Image Manager in detail, organized by the three main window types: the Main Window, Image Picker Windows, and Image Viewer Windows.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Main Window](#main-window)
   - [Command Field](#command-field)
   - [Control Buttons](#control-buttons)
   - [Internal Commands](#internal-commands)
   - [Wildcards and Variables](#wildcards-and-variables)
3. [Image Picker Window](#image-picker-window)
   - [Breadcrumb Navigation](#breadcrumb-navigation)
   - [Thumbnail Grid](#thumbnail-grid)
   - [Bottom Control Bar](#bottom-control-bar)
   - [Keyboard Navigation](#keyboard-navigation)
   - [Directory Watching](#directory-watching)
4. [Image Viewer Window](#image-viewer-window)
   - [Viewing and Zooming](#viewing-and-zooming)
   - [Fullscreen Mode](#fullscreen-mode)
   - [Filename Bar](#filename-bar)
5. [Customization Examples](#customization-examples)
6. [Keyboard Shortcuts Reference](#keyboard-shortcuts-reference)
7. [Persistence & Settings](#persistence--settings)
8. [Platform Support](#platform-support)

---

## Getting Started

When you first launch Kubux Image Manager, you'll see the Main Window - a small command center window. To browse images:

1. Add a command like `Open: ${HOME}/Pictures` to the command field
2. Double-click that line to execute it
3. An Image Picker window opens showing thumbnails from that directory

From there, you can:
- Click thumbnails to select them (blue border indicates selection)
- Right-click thumbnails to execute commands
- Drag thumbnails to move files between directories
- Double-click on thumbnails (with `Open: {*}` command) to open them in the viewer

---

## Main Window

The Main Window is your command center for batch operations.

### Command Field

The command field is a multi-line text editor where you store and organize your commands:

- **Current line highlighting**: The active line has a light gray background (#e0e0e0)
- **Double-click to execute**: Double-clicking any line executes that command immediately
- **Standard text editing**: Full cursor navigation with scrollbars
- **Persistent storage**: All commands are automatically saved between sessions

**Tip**: Organize your commands by purpose - keep commonly used ones at the top.

### Control Buttons

| Button | Function |
|--------|----------|
| **Process selected** | Executes the current command on all selected files |
| **Clear selection** | Deselects all files (disabled when nothing is selected) |
| **Quit** | Saves all settings and closes the application |
| **UI slider** | Adjusts font size across the entire application (0.2x to 3.5x) |

### Internal Commands

Kubux Image Manager recognizes several built-in commands that start with special prefixes:

#### Open: \<path\>
Opens an image file in the viewer or a directory in a new picker window.

```
# Open user's Pictures folder
Open: ${HOME}/Pictures

# Open all selected images
Open: {*}

# Open a specific subfolder
Open: /path/to/photos
```

#### Fullscreen: \<path\>
Opens an image file directly in fullscreen mode.

```
# Open current image in fullscreen
Fullscreen: {*}
```

#### SetWP: \<path\>
Sets the specified image as the desktop wallpaper. Supports multiple Linux desktop environments.

```
# Set wallpaper from selected file
SetWP: *
```

#### Select: \<command\>
Runs a shell command and selects all files that appear in its output.

```
# Select all JPG files
Select: find . -name "*.jpg"

# Select files modified in the last week
Select: find . -type f -mtime -7

# Select large files
Select: find . -size +5M
```

#### Deselect: \<command\>
Runs a shell command and deselects all files that appear in its output.

```
# Deselect PNG files
Deselect: find . -name "*.png"

# Deselect files older than 30 days
Deselect: find . -mtime +30
```

### Wildcards and Variables

#### Environment Variables
Use `${VAR_NAME}` syntax to include environment variables:

```
Open: ${HOME}/Pictures
Open: ${XDG_PICTURES_DIR}
cp * ${HOME}/Backup/
```

#### Wildcards

| Wildcard | Meaning | Use Case |
|----------|---------|----------|
| `*` | Expands to all selected files as arguments | Batch operations on all files |
| `{*}` | Creates a separate command for each selected file | Per-file operations |

**Examples:**

```
# Move all selected files to trash (single command with all files)
gio trash *

# Convert each selected file individually
convert {*} -resize 50% ~/resized/$(basename {*})

# Open all selected in viewer
Open: *

# Open each in separate viewer (same result, different mechanism)
Open: {*}
```

---

## Image Picker Window

The Image Picker is your primary interface for browsing and selecting images.

### Breadcrumb Navigation

The breadcrumb bar at the top shows your current path as clickable segments:

| Action | Result |
|--------|--------|
| **Click** a segment | Navigate to that directory |
| **Long-press** a segment | Opens subdirectory selection menu |
| **Right-click** a segment | Opens subdirectory selection menu immediately |
| **Click "//"** (root button) | Always opens directory menu |
| **Clone** button | Opens a duplicate picker with the same settings |
| **Close** button | Closes this picker window |

**Tip**: Use long-press or right-click on parent directories to quickly jump to sibling folders without navigating up and back down.

### Thumbnail Grid

The thumbnail grid displays image files with intelligent caching and responsive layout:

#### Layout
- **Responsive columns**: Columns automatically adjust to window width
- **Thumbnail caching**: Resized thumbnails are cached on disk for fast reloading
- **Background preloading**: Thumbnails for parent and sibling directories are preloaded

#### Mouse Interactions

| Action | Effect |
|--------|--------|
| **Left-click** | Toggles selection (blue border when selected) |
| **Left-drag** | Moves ALL selected files in this directory to drop target |
| **Right-click** | Opens command context menu for that single file |
| **Right-drag** | Moves ONLY that single file to drop target |
| **Shift+Right-click** | Executes current command on that single file |
| **Mouse wheel** | Scrolls the thumbnail grid |

#### Drop Targets

You can drop files (from left-drag or right-drag) onto:
- **Breadcrumb buttons** - moves files to that directory
- **Other picker windows** - moves files to that picker's directory
- **Picker scroll area** - moves files to the current picker's directory

**Example Workflows:**

1. **Quick file sorting**: Left-click to select several images, then left-drag them to a breadcrumb segment of a target folder.

2. **Move a single file without disturbing selection**: Right-drag just that file to the destination.

3. **Execute command on one file**: Shift+Right-click executes the current line's command on just that image.

### Bottom Control Bar

| Control | Function |
|---------|----------|
| **Size slider** | Adjusts thumbnail size (96-1920 pixels) |
| **Show field** | Shell command to list which files appear (default: `ls`) |
| **Des. button** | Deselects all files in current directory only |
| **Sel. button** | Selects all files in current directory |
| **Apply button** | Opens command menu to apply to selected files here |

#### The "Show:" Field

The Show field lets you filter which files appear using any shell command:

```
# Show all files (default)
ls

# Show only JPG files
ls *.jpg

# Show files recursively
find . -type f

# Show files from a specific subdirectory
find ./2024 -maxdepth 1 -type f

# Show files sorted by modification time (newest first)
ls -t

# Show files by size
ls -S
```

- Press **Enter** in the Show field to execute and refresh
- **Right-click** on the Show field to see history of previous commands

### Keyboard Navigation

| Key | Action |
|-----|--------|
| **Up/Down arrows** | Scroll the thumbnail grid |
| **Page Up/Page Down** | Scroll by page |
| **Escape** | Close the picker window |
| **Mouse wheel** | Scroll the thumbnail grid |

### Directory Watching

Image Picker windows automatically refresh when files are added, removed, or renamed in the current directory. This uses the `watchdog` library to monitor filesystem changes.

---

## Image Viewer Window

The Image Viewer provides detailed viewing of individual images.

### Viewing and Zooming

#### Automatic Fit
When you open an image, it automatically scales to fit the window while maintaining aspect ratio.

#### Zoom Controls

| Control | Action |
|---------|--------|
| **+ or =** | Zoom in |
| **- or _** | Zoom out |
| **0** | Reset to fit-to-window |
| **Mouse wheel up** | Zoom in (centered on cursor) |
| **Mouse wheel down** | Zoom out (centered on cursor) |

#### Panning

When zoomed in beyond the window size:
- **Left-click and drag** to pan around the image
- Cursor changes to a move cursor while panning
- Scrollbars appear when the image exceeds the viewport

### Fullscreen Mode

| Control | Action |
|---------|--------|
| **F** or **F11** | Toggle fullscreen on/off |
| **Escape** | Exit fullscreen (or close viewer if not fullscreen) |

### Filename Bar

The bottom bar of the viewer shows file information:

| Element | Description |
|---------|-------------|
| **Dimensions** | Shows image size (e.g., "1920x1080") |
| **Filename field** | Click to edit; press Enter to rename the file |
| **Copy button** | Copies filename to clipboard (green flash confirms) |
| **Title bar** | Shows filename; for symlinks shows link target |

---

## Customization Examples

### Batch Image Operations

```
# Resize images to 50%
convert {*} -resize 50% ~/resized/$(basename {*})

# Convert to PNG
convert {*} ~/converted/$(basename {*} | sed 's/\.[^.]*$/.png/')

# Add watermark
composite -dissolve 30 -gravity southeast watermark.png {*} ~/watermarked/$(basename {*})

# Optimize JPEG quality
jpegoptim --max=85 *
```

### File Organization

```
# Move to dated folder
mkdir -p ~/Pictures/$(date +%Y-%m) && mv * ~/Pictures/$(date +%Y-%m)/

# Move to trash
gio trash *

# Copy to backup location
cp * ~/Backup/Photos/

# Create symbolic links
ln -s {*} ~/Links/
```

### Integration with External Tools

```
# Open in GIMP
gimp *

# Open in Inkscape (for SVG)
inkscape *

# Upload to image hosting (example with curl)
curl -F "image=@{*}" https://api.imgbb.com/1/upload

# Send via email attachment (using mail command)
echo "Photos attached" | mail -s "Photos" -A * recipient@example.com
```

### Smart Selection Examples

```
# Select all screenshots (assuming naming pattern)
Select: find . -name "Screenshot*"

# Select files from today
Select: find . -daystart -mtime 0

# Select small images (under 100KB)
Select: find . -size -100k

# Deselect already backed up files
Deselect: comm -12 <(ls | sort) <(ls ~/Backup | sort)
```

---

## Keyboard Shortcuts Reference

### Main Window

| Key | Action |
|-----|--------|
| Double-click line | Execute that command |

### Image Picker

| Key | Action |
|-----|--------|
| Up/Down | Scroll thumbnail grid |
| Page Up/Page Down | Scroll by page |
| Escape | Close picker |
| Enter (in Show field) | Execute filter and refresh |

### Image Viewer

| Key | Action |
|-----|--------|
| + or = | Zoom in |
| - or _ | Zoom out |
| 0 | Reset zoom (fit to window) |
| F or F11 | Toggle fullscreen |
| Escape | Close viewer (or exit fullscreen first) |
| Left-drag | Pan image |
| Mouse wheel | Zoom in/out at cursor |

---

## Persistence & Settings

Kubux Image Manager automatically saves and restores:

| What | Where |
|------|-------|
| Commands in command field | `~/.config/kubux-image-manager/app_settings.json` |
| Window positions and sizes | Saved per window |
| Thumbnail sizes per picker | Saved per picker |
| "Show:" commands per picker | Saved per picker |
| Selected files | Persists across sessions |
| All open picker and viewer windows | Re-opened on restart |
| "Show:" command history | For dropdown menu |
| UI scale factor | Global setting |

Thumbnail cache is stored in:
```
~/.cache/kubux-thumbnail-cache/thumbnails/
```

The cache is organized by thumbnail size for efficient retrieval.

---

## Platform Support

### Desktop Wallpaper

The `SetWP:` command supports these Linux desktop environments:
- GNOME
- KDE Plasma
- XFCE
- Cinnamon
- MATE
- LXQt/LXDE
- i3
- sway

It automatically detects your desktop environment and uses the appropriate method.

### System Font Integration

Kubux Image Manager reads your system font settings:
- **GTK-based desktops**: Reads from gsettings (GNOME, XFCE, Cinnamon, MATE)
- **KDE**: Reads from kdeglobals configuration

The UI scale slider multiplies this base font size.

---

## Tips & Tricks

1. **Use Clone for side-by-side sorting**: Open two pickers of different folders and drag files between them.

2. **Quick single-file operations**: Shift+Right-click executes the current command on just that file without changing your selection.

3. **Preview before batch**: Use `{*}` with `echo` first to see what commands would run:
   ```
   echo "Would process: {*}"
   ```

4. **Combine Select/Deselect**: Build complex selections:
   ```
   Select: find . -name "*.jpg"
   Deselect: find . -size +10M
   ```

5. **Custom workflows**: Create commands for your regular tasks and keep them in the command field.

6. **Thumbnail size vs. performance**: Larger thumbnails look better but take more memory and disk space.

7. **Use the Show: field creatively**: Filter by any attribute `find` supports - date, size, name, type.
