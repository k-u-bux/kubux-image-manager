# README.md for Kubux Image Manager

## Overview

Kubux Image Manager is a powerful yet simple Tkinter-based image management application for Linux desktop environments. It provides an intuitive interface for browsing, viewing, organizing, and manipulating image files with support for batch operations through customizable commands.

## Features

- **Flexible Image Browsing**: Navigate your file system with an intuitive breadcrumb interface
- **Thumbnail Gallery**: View image thumbnails with adjustable size
- **Advanced Image Viewer**: Built-in viewer with zoom, pan, and fullscreen capabilities
- **Multiple Selection**: Select multiple files for batch operations
- **Command System**: Execute custom commands on selected files with support for wildcards and environment variables
- **Multi-window Interface**: Open multiple browser windows simultaneously for different folders
- **Persistent Settings**: Application remembers window positions, open directories, and selected files
- **Desktop Integration**: Set wallpaper directly from the application (on supported Linux Desktop Environments)

## Installation

### Prerequisites

- Python 3.6+
- Tkinter
- Pillow (PIL fork)
- Requests
- python-dotenv

### Dependencies Installation

```bash
pip install pillow requests python-dotenv
```

If you wish to use the optional AI image generation features, also install:
```bash
pip install together
```

### Run the Application

```bash
python kubux-image-manager.py
```

## Usage

### Basic Navigation

- **Browse Images**: Use the breadcrumb navigation to move between directories
- **View Images**: Double-click or right-click on a thumbnail to open it in the viewer
- **Select Images**: Left-click on thumbnails to select them for batch operations
- **Clear Selection**: Use the "Clear selection" button to deselect all images

### Commands

The application uses a command system to operate on selected files. Commands are entered in the text field at the top of the main window.

#### Wildcards

- `*` - Expands to all selected files as separate arguments
- `{*}` - Creates a separate command for each selected file

#### Built-in Commands

- `open {path}` - Open a file or directory
- `SetWP {path}` - Set the specified image as wallpaper

#### Examples

```
# Open all selected files in the viewer
open *

# Move selected files to trash
gio trash *

# Copy selected files to a directory
cp * ~/Pictures/Saved/

# Process each file individually
convert {*} -resize 800x600 ~/Pictures/Resized/$(basename {*})

# Open a specific directory
open ${HOME}/Pictures
```

### Keyboard Shortcuts

#### Main Window
- **Enter**: Execute the current command
- **Escape**: Close a dialog or window

#### Image Viewer
- **+/=**: Zoom in
- **-/_**: Zoom out
- **0**: Reset zoom to fit window
- **F11**: Toggle fullscreen
- **Escape**: Close viewer
- **Mouse wheel**: Zoom in/out
- **Mouse drag**: Pan when zoomed

## Configuration

The application stores configuration in:
- `~/.config/kubux-image-manager/app_settings.json`
- `~/.cache/kubux-thumbnail-cache/` for thumbnail cache

## AI Image Generation (Optional)

If you have a Together.ai API key, you can enable AI image generation features by creating a `.env` file with:

```
TOGETHER_API_KEY=your_api_key
```

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details.

## Author

Copyright 2025 Kai-Uwe Bux

## Tips

1. **Batch Processing**: Create custom commands for common operations like resizing, converting, or uploading.
2. **Multiple Browsers**: Use the "Clone" button to open multiple browser windows for easier file management.
3. **Thumbnail Size**: Adjust the thumbnail size slider for better visibility of your images.
4. **Command History**: Commands are saved between sessions for easy reuse.
5. **Quick Navigation**: Long-press on any breadcrumb segment to reveal a directory selection menu.
