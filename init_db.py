from app import app, db
from models import User, Employee, Process, Order, WorkLog, Payment, OrderStatus, Overage, WorkLogOverage
from datetime import datetime, date
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create default user if not exists
        if not User.query.first():
            admin_user = User(username='admin', role='admin')
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created (username: admin, password: admin123)")
        
        # Create some sample processes if not exists
        if not Process.query.first():
            processes = [
                Process(name='Cutting', pay_rate=5.0, description='Fabric cutting process'),
                Process(name='Sewing', pay_rate=8.0, description='Garment sewing process'),
                Process(name='Finishing', pay_rate=3.0, description='Final finishing process'),
                Process(name='Quality Check', pay_rate=4.0, description='Quality control process')
            ]
            db.session.add_all(processes)
            db.session.commit()
            print("Sample processes created")
        
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_db() 