# Kubux Image Manager

![Kubux Image Manager](screenshots/all-windows.png)

## Overview

Kubux Image Manager is a powerful yet simple image management application for Linux desktop environments. Built with PySide6, it provides an intuitive interface for browsing, viewing, organizing, and manipulating image files with support for batch operations through customizable commands.

## Features

- **Flexible Image Browsing**: Navigate your file system with an intuitive breadcrumb interface
- **Thumbnail Gallery**: View image thumbnails with adjustable size (96-1920px)
- **Advanced Image Viewer**: Built-in viewer with zoom, pan, and fullscreen capabilities
- **Multi-Selection Operations**: Select multiple files for batch operations
- **Drag and Drop File Management**: Move files between directories with intuitive mouse operations
- **Command System**: Execute custom commands on selected files with wildcards and environment variables
- **Multi-window Interface**: Open multiple browser windows simultaneously for different folders
- **Persistent Settings**: Application remembers window positions, open directories, and selections
- **Desktop Integration**: Set wallpaper directly from the application on supported Linux DEs
- **Directory Watching**: Auto-refresh when files change
- **Background Thumbnail Preloading**: Predictively caches thumbnails for smooth navigation

For detailed usage instructions, see [usage.md](usage.md).

## Installation

### From Source (Nix)

Kubux Image Manager includes a `flake.nix` for easy installation on NixOS and other systems with Nix package manager:

```bash
nix profile install github:k-u-bux/kubux-image-manager
```

Alternatively, you can test drive the app:

```bash
nix run github:k-u-bux/kubux-image-manager
```

### Dependencies

- Python 3.x
- PySide6
- Pillow (PIL)
- watchdog
- requests

## Quick Start

1. Launch the application
2. Add a command like `Open: ${HOME}/Pictures` to the command field
3. Double-click that line to open an Image Picker
4. Left-click thumbnails to select, right-click for context menu
5. Drag selected files to breadcrumb segments to move them

## Mouse Operations Summary

| Action | Effect |
|--------|--------|
| Left-click | Toggle selection |
| Left-drag | Move all selected files |
| Right-click | Context menu for single file |
| Right-drag | Move single file |
| Shift+Right-click | Execute current command on single file |

## Internal Commands

| Command | Description |
|---------|-------------|
| `Open: <path>` | Open image or directory |
| `Fullscreen: <path>` | Open image in fullscreen |
| `SetWP: <path>` | Set as wallpaper |
| `Select: <cmd>` | Select files from command output |
| `Deselect: <cmd>` | Deselect files from command output |

Use `*` for all selected files, `{*}` for per-file expansion.

## Documentation

- **[usage.md](usage.md)** - Complete user guide with all features and examples

## Configuration

Settings are stored in:
- `~/.config/kubux-image-manager/app_settings.json`

Thumbnail cache is stored in:
- `~/.cache/kubux-thumbnail-cache/thumbnails/`

## Supported Desktop Environments

Wallpaper setting works on: GNOME, KDE, XFCE, Cinnamon, MATE, LXQt, LXDE, i3, sway

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) file for details.

## Author

Copyright 2025 Kai-Uwe Bux
