# Oleema – Production Management System

Offline desktop app for tracking garment production: orders, employee work logs by process,
piece-rate payment reports (PDF/CSV), overages, materials, users, audit log, and backups.

## Windows app

Built automatically by GitHub Actions (`.github/workflows/windows-build.yml`) on every push to
`main`, pull request, and `v*` tag.

- **Download:** the workflow run on GitHub → *Artifacts* → `Oleema-Windows-*`. Tagged builds
  (`git tag v1.0.0 && git push --tags`) are also attached to a GitHub Release.
- **Install:** run `Oleema-Setup-<version>.exe` (no admin rights needed), or unzip the portable zip
  and run `Oleema.exe`.
- The app opens in its own window (Microsoft Edge WebView2, built into Windows 10/11) and only
  listens on `127.0.0.1`.
- **Data:** `%APPDATA%\Oleema\oleema.db`, with automatic daily backups in `%APPDATA%\Oleema\backups`.
  Data from older portable builds (`oleema.db` next to `Oleema.exe`) is copied over on first start.
- First login: `admin` / `admin123` – change it under *Change Password*.

## Running from source

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python desktop.py                  # desktop window (Windows) / browser (macOS, Linux)
# or: python app.py                # dev server on http://127.0.0.1:5001 (FLASK_DEBUG=1 for debug)
python desktop.py --smoke-test     # end-to-end self test against a temporary database
```

From source the database is `oleema.db` in the project folder (`OLEEMA_DATA_DIR` overrides it).
It is created and upgraded automatically on start.

Build the Windows app yourself (on Windows): `pip install pyinstaller && python build.py`.
