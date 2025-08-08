#!/usr/bin/env python3
"""
Automatic backup script for Oleema Production Management System
Run this script daily to create automatic backups
"""

import os
import shutil
from datetime import datetime
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_backup, get_last_backup_info

def main():
    """Create automatic daily backup"""
    print("Oleema Automatic Backup")
    print("=" * 30)
    
    # Check if database exists
    db_path = 'instance/oleema.db'
    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        print(f"Expected location: {db_path}")
        return False
    
    # Create backup
    print("📦 Creating backup...")
    success, result = create_backup()
    
    if success:
        print(f"✅ Backup created successfully!")
        print(f"📁 File: {os.path.basename(result)}")
        
        # Get backup info
        last_backup_time, last_backup_path = get_last_backup_info()
        if last_backup_time:
            print(f"🕒 Created: {last_backup_time.strftime('%B %d, %Y at %I:%M %p')}")
        
        return True
    else:
        print(f"❌ Backup failed: {result}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1) 