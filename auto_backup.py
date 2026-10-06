#!/usr/bin/env python3
"""
Automatic backup script for Oleema Production Management System.

The desktop app already takes a backup automatically once a day when it starts.
Run this script (e.g. from Task Scheduler) if you want extra scheduled backups.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_backup, DATABASE_PATH


def main():
    print("Oleema Automatic Backup")
    print("=" * 30)

    if not os.path.exists(DATABASE_PATH):
        print(f"Database file not found: {DATABASE_PATH}")
        return False

    success, result = create_backup()
    if success:
        print(f"Backup created: {result}")
        return True
    print(f"Backup failed: {result}")
    return False


if __name__ == '__main__':
    sys.exit(0 if main() else 1)
