from app import app, db
from models import User, Employee, Process, Order, WorkLog, Payment, OrderStatus
from datetime import datetime, date
from werkzeug.security import generate_password_hash

def init_database():
    """Initialize the database with tables and sample data"""
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if we already have orders data
        if Order.query.first():
            print("Database already has data. Skipping initialization.")
            return
        
        print("Initializing database with sample data...")
        
        # Create admin user
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin 123'),
            role='admin'
        )
        db.session.add(admin_user)
        
        # Create sample employees
        employees = [
            Employee(employee_id='EMP001', name='John Doe', pay_rate=15.00),
            Employee(employee_id='EMP002', name='Jane Smith', pay_rate=16.50),
            Employee(employee_id='EMP003', name='Mike Johnson', pay_rate=14.00),
            Employee(employee_id='EMP004', name='Sarah Wilson', pay_rate=17.00),
        ]
        
        for emp in employees:
            db.session.add(emp)
        
        # Create sample processes
        processes = [
            Process(name='Cutting', pay_rate=2.50, description='Fabric cutting process'),
            Process(name='Sewing', pay_rate=3.00, description='Garment sewing process'),
            Process(name='Finishing', pay_rate=2.00, description='Final finishing process'),
            Process(name='Quality Check', pay_rate=2.75, description='Quality control process'),
        ]
        
        for proc in processes:
            db.session.add(proc)
        
        # Create sample orders
        orders = [
            Order(
                order_no='ORD001',
                date=date(2024, 1, 15),
                color='black',
                size='36',
                quantity=100,
                status='pending'
            ),
            Order(
                order_no='ORD002',
                date=date(2024, 1, 16),
                color='dark-blue',
                size='38',
                quantity=150,
                status='in_progress'
            ),
            Order(
                order_no='ORD003',
                date=date(2024, 1, 17),
                color='maroon',
                size='34',
                quantity=75,
                status='completed'
            ),
            Order(
                order_no='ORD004',
                date=date(2024, 1, 18),
                color='beige',
                size='40',
                quantity=200,
                status='pending'
            ),
            Order(
                order_no='ORD005',
                date=date(2024, 1, 19),
                color='ash',
                size='42',
                quantity=120,
                status='in_progress'
            ),
        ]
        
        for order in orders:
            db.session.add(order)
        
        # Commit to get IDs
        db.session.commit()
        
        # Create sample work logs
        work_logs = [
            WorkLog(
                employee_id=employees[0].id,
                order_id=orders[0].id,
                process_id=processes[0].id,
                quantity=50,
                date=date(2024, 1, 15)
            ),
            WorkLog(
                employee_id=employees[1].id,
                order_id=orders[0].id,
                process_id=processes[1].id,
                quantity=50,
                date=date(2024, 1, 15)
            ),
            WorkLog(
                employee_id=employees[2].id,
                order_id=orders[1].id,
                process_id=processes[0].id,
                quantity=75,
                date=date(2024, 1, 16)
            ),
        ]
        
        for work_log in work_logs:
            db.session.add(work_log)
        
        # Create sample payments
        payments = [
            Payment(
                employee_id=employees[0].id,
                month=1,
                year=2024,
                total_quantity=50,
                total_payment=125.00
            ),
            Payment(
                employee_id=employees[1].id,
                month=1,
                year=2024,
                total_quantity=50,
                total_payment=180.00
            ),
        ]
        
        for payment in payments:
            db.session.add(payment)
        
        # Commit all changes
        db.session.commit()
        
        print("Database initialized successfully!")
        print(f"Created {len(employees)} employees")
        print(f"Created {len(processes)} processes")
        print(f"Created {len(orders)} orders")
        print(f"Created {len(work_logs)} work logs")
        print(f"Created {len(payments)} payments")

if __name__ == '__main__':
    init_database() 