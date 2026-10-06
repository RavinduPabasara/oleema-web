"""
Create or upgrade the Oleema database and seed defaults (admin user, settings).

The app does this automatically on every start, so running this is optional.
"""

from app import app, init_database, DATABASE_PATH

if __name__ == '__main__':
    with app.app_context():
        init_database()
    print(f"Database ready: {DATABASE_PATH}")
    print("Default login: admin / admin123 (change it after first login)")
