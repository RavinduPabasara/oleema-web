#!/usr/bin/env python3
"""
Build the Oleema desktop app with PyInstaller into dist/Oleema/ (Oleema.exe on Windows).
The GitHub Actions workflow wraps that folder in an installer and a portable zip.

PyInstaller cannot cross-compile: run this on Windows to get a Windows .exe.

    pip install -r requirements.txt pyinstaller
    python build.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def build():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--name', 'Oleema',
        '--windowed',  # no console window
        '--add-data', f'templates{os.pathsep}templates',
        '--add-data', f'static{os.pathsep}static',
        '--exclude-module', 'tkinter',
    ]
    icon = os.path.join(ROOT, 'packaging', 'icon.ico')
    if sys.platform == 'win32' and os.path.exists(icon):  # macOS would need an .icns
        cmd += ['--icon', icon]
    cmd.append('desktop.py')

    print('Running: ' + ' '.join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)
    print('Built dist/Oleema/')


if __name__ == '__main__':
    build()
