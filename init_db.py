"""
Database initialization script for Oleema Web Application
This script will create all necessary tables including the new ones:
- settings
- audit_logs  
- materials
- inventory_transactions
- bill_of_materials
"""

from app import app, db
from models import User, Employee, Process, Order, WorkLog, Payment, OrderStatus, Overage, WorkLogOverage, Setting, AuditLog, Material, InventoryTransaction, BillOfMaterials
from werkzeug.security import generate_password_hash

def init_database():
    """Initialize the database with all tables"""
    with app.app_context():
        print("Creating all database tables...")
        
        # Create all tables
        db.create_all()
        
        print("✓ All tables created successfully!")
        
        # Check if admin user exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("\nCreating default admin user...")
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✓ Default admin user created (username: admin, password: admin123)")
            print("  ⚠️  Please change the password after first login!")
        else:
            print("\nAdmin user already exists.")
        
        # Initialize default settings
        default_settings = [
            ('company_name', 'Oleema Industries', 'Company name'),
            ('currency_symbol', 'LKR', 'Currency symbol'),
            ('items_per_page', '10', 'Items per page in lists')
        ]
        
        print("\nInitializing default settings...")
        for key, value, description in default_settings:
            setting = Setting.query.get(key)
            if not setting:
                setting = Setting(key=key, value=value, description=description)
                db.session.add(setting)
                print(f"  ✓ Added setting: {key} = {value}")
        
        db.session.commit()
        
        print("\n" + "="*50)
        print("Database initialization complete!")
        print("="*50)
        print("\nYou can now run the application with: python app.py")
        print("\nDefault login credentials:")
        print("  Username: admin")
        print("  Password: admin123")
        print("\n⚠️  IMPORTANT: Change the default password after first login!")

if __name__ == '__main__':
    init_database()