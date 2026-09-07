# ArchVM Installables & Release Artifacts

This directory contains the ready-to-run executables and installers for **ArchVM Manager**.

---

## Formats Available

### 1. `portable/ArchVM.exe` (Single-File Standalone)
- **Size**: ~47 MB
- **How it works**: A single self-contained `.exe` containing the embedded Python runtime, PySide6, and all dependencies. Unpacks into a temporary directory on start.
- **Use case**: Put it on a USB drive or anywhere on your PC and run it directly without installing anything.

### 2. `onedir/ArchVM/` (Folder Package)
- **Files**: `ArchVM.exe` (~2.5 MB launcher) + `_internal/` dependency folder.
- **How it works**: Pre-extracted Python runtime and libraries. Launches noticeably faster than the single-file executable because no unpacking is required.
- **Use case**: Recommended for daily local execution. You can create a desktop shortcut to `ArchVM.exe`.

### 3. `setup/` (Windows Inno Setup Installer)
- **Output**: `ArchVM-2.3.0-windows-x64-setup.exe`
- **How it works**: Standard Windows setup wizard with Start Menu shortcuts, optional desktop shortcut, and clean Windows Add/Remove Programs uninstaller.
- **How to compile**:
  ```powershell
  # Compile the onedir build first
  python app/build.py

  # Compile the Inno Setup installer
  iscc /DAppVersion=2.3.0 app/installer/archvm.iss
  ```

---

## How to Build New Installables

From the repository root (`Archie`):

```powershell
# Fast-starting onedir build (placed in app/dist/ArchVM, can be copied to installables/onedir/)
python app/build.py

# Single-file portable build (placed in app/dist/ArchVM.exe, can be copied to installables/portable/)
python app/build.py --onefile

# Full clean rebuild
python app/build.py --clean
```

> **Note**: Binary files (`*.exe`, `*.zip`) inside `installables/` are git-ignored by default to keep the Git repository lightweight, fast, and within GitHub's 100MB file size limit. Only source code and documentation are committed to Git.
