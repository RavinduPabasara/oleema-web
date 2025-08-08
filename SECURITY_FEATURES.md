# Security Features Guide

## Overview
This guide explains the security features implemented in the Oleema Production Management System.

## 🔐 Password Management

### Change Password
- **Location**: Security → Change Password
- **Requirements**: 
  - Current password must be correct
  - New password must be at least 6 characters
  - Passwords must match
- **How to use**:
  1. Go to Security → Change Password
  2. Enter your current password
  3. Enter new password (minimum 6 characters)
  4. Confirm new password
  5. Click "Change Password"

### Default Password
- **Current**: `admin` / `admin123`
- **Recommendation**: Change immediately after first login

## 💾 Backup & Restore

### Manual Backup
- **Location**: Security → Backup & Restore
- **How to use**:
  1. Go to Security → Backup & Restore
  2. Click "Create Backup"
  3. Backup will be saved in `backups/` folder

### Automatic Backup
- **Script**: `auto_backup.py`
- **How to run**: `python auto_backup.py`
- **Schedule**: Run daily for automatic backups

### Restore Backup
- **How to use**:
  1. Go to Security → Backup & Restore
  2. Find the backup you want to restore
  3. Click "Restore" button
  4. Confirm the action

### Backup Information
- **Location**: `backups/` folder
- **Format**: `oleema_backup_YYYYMMDD_HHMMSS.db`
- **Retention**: Last 7 days (automatic cleanup)
- **Size**: Usually 50-200 KB

## ⏰ Session Timeout

### Automatic Logout
- **Timeout**: 2 hours of inactivity
- **Warning**: Shows 5 minutes before timeout
- **Reset**: Any mouse click, keyboard input, or page scroll

### Session Warning
- **Appears**: 5 minutes before timeout
- **Message**: "Your session will expire in X minutes"
- **Action**: Click anywhere to extend session

## 🛡️ Security Tips

### Password Security
- Use a password that's easy to remember but hard to guess
- Don't share your password with anyone
- Change your password regularly
- Use at least 6 characters

### Data Protection
- Create backups regularly (daily recommended)
- Store backups in a safe location
- Test restore functionality occasionally
- Keep your computer secure

### Session Security
- Log out when you're done using the system
- Don't leave the system logged in on shared computers
- The system will automatically log you out after 2 hours

## 📁 File Locations

### Database
- **Main**: `instance/oleema.db`
- **Backups**: `backups/oleema_backup_*.db`

### Scripts
- **Auto backup**: `auto_backup.py`
- **Database init**: `init_db.py`

## 🔧 Troubleshooting

### Can't Login
- Check username and password
- Make sure caps lock is off
- Try changing password if forgotten

### Backup Issues
- Check if `backups/` folder exists
- Ensure you have write permissions
- Check available disk space

### Session Issues
- Clear browser cache and cookies
- Restart the application
- Check system time is correct

## 📞 Support
For technical issues, contact your system administrator or refer to the main README file. 