from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Employee, Process, Order, WorkLog, Payment, OrderStatus, Overage, WorkLogOverage, Setting, AuditLog, Material, InventoryTransaction, BillOfMaterials
from datetime import datetime, timedelta, date
from sqlalchemy import func, extract, and_, inspect, text
import os
import sys
import shutil
import secrets
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from io import BytesIO
import csv
import io
from functools import wraps

# --- Paths -------------------------------------------------------------------
# RESOURCE_DIR: bundled read-only files (templates, static). Inside the PyInstaller build
#   this is the unpacked bundle folder.
# DATA_DIR: the database and backups. The packaged desktop app uses
#   %APPDATA%\Oleema so data survives upgrades and reinstalls; running from source keeps
#   using the project folder. OLEEMA_DATA_DIR overrides both.
def _resource_dir():
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

def _data_dir():
    override = os.environ.get('OLEEMA_DATA_DIR')
    if override:
        return os.path.abspath(override)
    if getattr(sys, 'frozen', False):
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Oleema')
    return os.path.dirname(os.path.abspath(__file__))

RESOURCE_DIR = _resource_dir()
BASE_DIR = _data_dir()
os.makedirs(BASE_DIR, exist_ok=True)
DATABASE_PATH = os.path.join(BASE_DIR, 'oleema.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

def _migrate_portable_data():
    """Older Windows builds kept oleema.db next to Oleema.exe. Carry it over on first run."""
    if not getattr(sys, 'frozen', False) or os.environ.get('OLEEMA_DATA_DIR') or os.path.exists(DATABASE_PATH):
        return
    old_dir = os.path.dirname(sys.executable)
    old_db = os.path.join(old_dir, 'oleema.db')
    if os.path.exists(old_db):
        shutil.copy2(old_db, DATABASE_PATH)
        old_backups = os.path.join(old_dir, 'backups')
        if os.path.isdir(old_backups):
            for name in os.listdir(old_backups):
                if name.startswith('oleema_backup_') and name.endswith('.db'):
                    shutil.copy2(os.path.join(old_backups, name), os.path.join(BACKUP_DIR, name))

_migrate_portable_data()

def _secret_key():
    """Keep the same key across restarts so logins survive an app restart."""
    key_file = os.path.join(BASE_DIR, 'secret.key')
    try:
        with open(key_file) as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(key)
    return key

app = Flask(__name__,
            template_folder=os.path.join(RESOURCE_DIR, 'templates'),
            static_folder=os.path.join(RESOURCE_DIR, 'static'),
            instance_path=BASE_DIR)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or _secret_key()

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function for audit logging
def log_audit(action, entity_type, entity_id, details):
    """Log an audit event"""
    try:
        audit_log = AuditLog(
            user_id=session.get('user_id'),
            action=action,
            target_type=entity_type,  # Using target_type to match model
            target_id=entity_id,       # Using target_id to match model
            details=details
        )
        db.session.add(audit_log)
        db.session.commit()
    except Exception as e:
        print(f"Error logging audit: {e}")
        # Don't fail the main operation if audit logging fails
        db.session.rollback()

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DATABASE_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session timeout configuration (2 hours = 7200 seconds)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Initialize database
db.init_app(app)

DEFAULT_SETTINGS = [
    ('company_name', 'Oleema Industries', 'Company name'),
    ('currency_symbol', 'LKR', 'Currency symbol'),
    ('items_per_page', '10', 'Items per page in lists'),
]

def upgrade_schema():
    """Add columns that exist on the models but not in an older database file.

    db.create_all() creates missing tables but never adds missing columns.
    """
    inspector = inspect(db.engine)
    with db.engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col['name'] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    col_type = column.type.compile(dialect=db.engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))

def init_database():
    """Create/upgrade tables and seed defaults. Safe to run on every start."""
    is_new = 'users' not in set(inspect(db.engine).get_table_names())
    db.create_all()
    upgrade_schema()
    if not User.query.first():
        admin_user = User(username='admin', role='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
    if is_new and not Process.query.first():
        db.session.add_all([
            Process(name='Cutting', pay_rate=5.0, description='Fabric cutting process'),
            Process(name='Sewing', pay_rate=8.0, description='Garment sewing process'),
            Process(name='Finishing', pay_rate=3.0, description='Final finishing process'),
            Process(name='Quality Check', pay_rate=4.0, description='Quality control process'),
        ])
    for key, value, description in DEFAULT_SETTINGS:
        if not db.session.get(Setting, key):
            db.session.add(Setting(key=key, value=value, description=description))
    db.session.commit()

with app.app_context():
    init_database()

BACKUPS_TO_KEEP = 30

def _list_backups():
    """Backup files in BACKUP_DIR, newest first, as (created, path)."""
    backups = []
    for filename in os.listdir(BACKUP_DIR):
        if filename.startswith('oleema_backup_') and filename.endswith('.db'):
            file_path = os.path.join(BACKUP_DIR, filename)
            backups.append((datetime.fromtimestamp(os.path.getmtime(file_path)), file_path))
    backups.sort(key=lambda b: b[0], reverse=True)
    return backups

def create_backup():
    """Create a backup of the database (consistent even while the app is running)"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(BACKUP_DIR, f'oleema_backup_{timestamp}.db')
        counter = 1
        while os.path.exists(backup_path):  # never overwrite a backup made in the same second
            backup_path = os.path.join(BACKUP_DIR, f'oleema_backup_{timestamp}_{counter}.db')
            counter += 1
        source = sqlite3.connect(DATABASE_PATH)
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        cleanup_old_backups()
        return True, backup_path
    except Exception as e:
        return False, str(e)

def cleanup_old_backups():
    """Keep the newest BACKUPS_TO_KEEP backups (by count, so old ones are never all lost)"""
    try:
        for _, file_path in _list_backups()[BACKUPS_TO_KEEP:]:
            os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up old backups: {e}")

def get_last_backup_info():
    """Get information about the last backup"""
    try:
        backups = _list_backups()
        if backups:
            return backups[0]
        return None, None
    except Exception as e:
        print(f"Error getting backup info: {e}")
        return None, None

def auto_backup_if_due(max_age=timedelta(hours=24)):
    """Take a backup if the newest one is older than max_age (called at app start)"""
    last_time, _ = get_last_backup_info()
    if os.path.exists(DATABASE_PATH) and (last_time is None or datetime.now() - last_time > max_age):
        return create_backup()
    return None

def restore_backup(filename):
    """Replace the live database with a backup from BACKUP_DIR"""
    filename = os.path.basename(filename or '')
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not (filename.startswith('oleema_backup_') and filename.endswith('.db') and os.path.exists(backup_path)):
        raise ValueError('Invalid backup file selected')
    create_backup()  # safety copy of the current state
    db.session.remove()
    db.engine.dispose()
    source = sqlite3.connect(backup_path)
    target = sqlite3.connect(DATABASE_PATH)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    db.engine.dispose()
    init_database()  # bring an older backup up to the current schema

def check_session_timeout():
    """Check if session has timed out"""
    if 'logged_in' in session:
        last_activity = session.get('last_activity')
        if last_activity:
            last_activity = datetime.fromisoformat(last_activity)
            if datetime.now() - last_activity > timedelta(hours=2):
                session.clear()
                return True
    return False

def update_session_activity():
    """Update session activity timestamp"""
    session['last_activity'] = datetime.now().isoformat()

@app.before_request
def before_request():
    """Check session timeout before each request"""
    if request.endpoint and 'static' not in request.endpoint:
        if check_session_timeout():
            flash('Session expired due to inactivity. Please login again.', 'warning')
            return redirect(url_for('login'))
        elif session.get('logged_in'):
            update_session_activity()

# Context processor to make settings available in all templates
@app.context_processor
def inject_settings():
    """Make settings available in all templates"""
    try:
        settings_dict = {}
        all_settings = Setting.query.all()
        for setting in all_settings:
            settings_dict[setting.key] = setting.value
        return dict(app_settings=settings_dict, settings=settings_dict)
    except Exception:
        # If settings table doesn't exist yet, return empty dict
        return dict(app_settings={}, settings={})

@app.route('/')
def index():
    """Redirect to login page"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['logged_in'] = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # Update last active time
            session['last_active'] = datetime.utcnow().timestamp()
            
            # Assuming log_audit is defined elsewhere or will be added
            # log_audit('Login', 'User', user.id, 'User logged in') 
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get dashboard statistics
    total_employees = Employee.query.filter_by(is_active=True).count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    completed_orders = Order.query.filter_by(status='completed').count()
    
    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Recent work logs
    recent_work_logs = WorkLog.query.order_by(WorkLog.created_at.desc()).limit(5).all()
    
    # Calculate daily production for the last 7 days
    today = date.today()
    dates = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    daily_production = []
    
    for d in dates:
        total = db.session.query(func.sum(WorkLog.quantity)).filter(WorkLog.date == d).scalar() or 0
        daily_production.append(total)
        
    chart_dates = [d.strftime('%b %d') for d in dates]
    
    return render_template('pages/dashboard.html',
                         total_employees=total_employees,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         recent_orders=recent_orders,
                         recent_work_logs=recent_work_logs,
                         chart_dates=chart_dates,
                         daily_production=daily_production)

@app.route('/employees')
def employees():
    """Employee management page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employees = Employee.query.order_by(Employee.is_active.desc(), Employee.name).all()
    return render_template('pages/employees.html', employees=employees)

@app.route('/employees/add', methods=['GET', 'POST'])
def add_employee():
    """Add new employee"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        print("POST request received to /employees/add")
        print("Form data:", request.form)
        
        employee_id = request.form.get('employee_id')
        name = request.form.get('name')
        
        print(f"Parsed data: employee_id={employee_id}, name={name}")
        
        if not all([employee_id, name]):
            print("Validation failed - missing required fields")
            flash('Please fill in all required fields', 'error')
        else:
            # Check if employee ID already exists
            existing = Employee.query.filter_by(employee_id=employee_id).first()
            if existing:
                print(f"Employee ID {employee_id} already exists")
                flash('Employee ID already exists', 'error')
            else:
                employee = Employee(
                    employee_id=employee_id,
                    name=name
                )
                db.session.add(employee)
                db.session.commit()
                print(f"Employee created successfully: {employee.name} ({employee.employee_id})")
                flash('Employee added successfully!', 'success')
                return redirect(url_for('employees'))
    
    return render_template('pages/add_employee.html')

@app.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
def edit_employee(employee_id):
    """Edit employee"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        employee.name = request.form.get('name')
        employee.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('Employee updated successfully!', 'success')
        return redirect(url_for('employees'))
    
    return render_template('pages/edit_employee.html', employee=employee)

@app.route('/new-order', methods=['GET', 'POST'])
def new_order():
    """Add new order page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        order_no = request.form.get('order_no')
        date_str = request.form.get('date')
        color = request.form.get('color')
        size = request.form.get('size')
        try:
            quantity = int(request.form.get('quantity') or 0)
        except ValueError:
            quantity = 0
        notes = request.form.get('notes')
        
        if quantity < 1:
            flash('Quantity must be a whole number of at least 1', 'error')
        elif not all([order_no, date_str, color, size]):
            flash('Please fill in all required fields', 'error')
        else:
            # Check if order number already exists
            existing = Order.query.filter_by(order_no=order_no).first()
            if existing:
                flash('Order number already exists', 'error')
            else:
                order_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                order = Order(
                    order_no=order_no,
                    date=order_date,
                    color=color,
                    size=size,
                    quantity=quantity,
                    notes=notes
                )
                db.session.add(order)
                db.session.commit()
                flash('Order created successfully!', 'success')
                return redirect(url_for('orders'))
    
    return render_template('pages/new_order.html')

@app.route('/orders')
def orders():
    """View all orders"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('pages/orders.html', orders=orders)

@app.route('/orders/<int:order_id>')
def view_order(order_id):
    """View specific order details"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    order = Order.query.get_or_404(order_id)
    work_logs = WorkLog.query.filter_by(order_id=order_id).all()
    
    # Calculate totals
    total_processed = sum(wl.quantity for wl in work_logs)
    total_payment = sum(wl.quantity * wl.process.pay_rate for wl in work_logs)
    
    # Calculate progress per process
    processes = Process.query.filter_by(is_active=True).all()
    process_progress = {}
    
    for process in processes:
        process_work_logs = [wl for wl in work_logs if wl.process_id == process.id]
        process_total = sum(wl.quantity for wl in process_work_logs)
        process_completion = min(process_total / order.quantity * 100, 100) if order.quantity > 0 else 0
        process_progress[process.name] = {
            'total': process_total,
            'completion': process_completion
        }
    
    # Overall progress (average of all processes that have work)
    active_processes = [p for p in process_progress.values() if p['total'] > 0]
    overall_progress = sum(p['completion'] for p in active_processes) / len(active_processes) if active_processes else 0
    
    return render_template('pages/view_order.html', 
                         order=order, 
                         work_logs=work_logs,
                         total_processed=total_processed,
                         total_payment=total_payment,
                         progress_percent=overall_progress,
                         process_progress=process_progress)

@app.route('/orders/<int:order_id>/status', methods=['POST'])
def update_order_status_route(order_id):
    """Manually change an order's status"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    order = Order.query.get_or_404(order_id)
    status = request.form.get('status')
    if status not in ORDER_STATUSES:
        flash('Invalid status.', 'error')
        return redirect(url_for('view_order', order_id=order.id))
    if status != order.status:
        old_status = order.status
        order.status = status
        db.session.add(OrderStatus(order_id=order.id, status=status,
                                   notes=request.form.get('notes') or f'Changed from {old_status} by {session.get("username")}'))
        db.session.commit()
        log_audit('Update Order Status', 'Order', order.id, f'{order.order_no}: {old_status} -> {status}')
        flash(f'Order status changed to {status.replace("_", " ").title()}.', 'success')
    return redirect(url_for('view_order', order_id=order.id))

@app.route('/api/orders')
def api_orders():
    """API endpoint to get orders for dropdown"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    orders = Order.query.filter(Order.status.in_(['pending', 'in_progress'])).all()
    return jsonify([{
        'id': order.id,
        'order_no': order.order_no,
        'color': order.color,
        'size': order.size,
        'quantity': order.quantity
    } for order in orders])

@app.route('/api/check-order-number/<order_no>')
def check_order_number(order_no):
    """API endpoint to check if order number exists"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    existing = Order.query.filter_by(order_no=order_no).first()
    return jsonify({'exists': existing is not None})

def cleanup_overages_for_order(order_id):
    """Clean up overages for a deleted order"""
    try:
        overages = Overage.query.filter_by(order_id=order_id).all()
        for overage in overages:
            db.session.delete(overage)
        print(f"Cleaned up {len(overages)} overages for order {order_id}")
        return True
    except Exception as e:
        print(f"Error cleaning up overages for order {order_id}: {e}")
        return False

def cleanup_payments_for_employee(employee_id):
    """Clean up payments for a deleted employee"""
    try:
        payments = Payment.query.filter_by(employee_id=employee_id).all()
        for payment in payments:
            db.session.delete(payment)
        print(f"Cleaned up {len(payments)} payments for employee {employee_id}")
        return True
    except Exception as e:
        print(f"Error cleaning up payments for employee {employee_id}: {e}")
        return False

def cleanup_overages_for_process(process_id):
    """Clean up overages for a deleted process"""
    try:
        overages = Overage.query.filter_by(process_id=process_id).all()
        for overage in overages:
            db.session.delete(overage)
        print(f"Cleaned up {len(overages)} overages for process {process_id}")
        return True
    except Exception as e:
        print(f"Error cleaning up overages for process {process_id}: {e}")
        return False

ORDER_STATUSES = ['pending', 'in_progress', 'completed', 'cancelled']

class FormError(ValueError):
    """Validation error whose message is safe to show to the user."""

def parse_int(value, label, minimum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise FormError(f'{label} is required and must be a whole number.')
    if minimum is not None and number < minimum:
        raise FormError(f'{label} must be at least {minimum}.')
    return number

def parse_float(value, label, minimum=None, default=None):
    if value in (None, '') and default is not None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise FormError(f'{label} must be a number.')
    if minimum is not None and number < minimum:
        raise FormError(f'{label} cannot be less than {minimum}.')
    return number

def parse_date(value, label='Date'):
    try:
        return datetime.strptime(value or '', '%Y-%m-%d').date()
    except ValueError:
        raise FormError(f'{label} must be a valid date.')

def parse_work_log_form(form):
    """Validate the work log form. Returns a dict of clean values."""
    data = {
        'employee_id': parse_int(form.get('employee_id'), 'Employee'),
        'order_id': parse_int(form.get('order_id'), 'Order'),
        'process_id': parse_int(form.get('process_id'), 'Process'),
        'quantity': parse_int(form.get('quantity'), 'Quantity', minimum=1),
        'date': parse_date(form.get('date')).strftime('%Y-%m-%d'),
        'notes': form.get('notes') or '',
    }
    if not db.session.get(Employee, data['employee_id']):
        raise FormError('Selected employee does not exist.')
    if not db.session.get(Order, data['order_id']):
        raise FormError('Selected order does not exist.')
    if not db.session.get(Process, data['process_id']):
        raise FormError('Selected process does not exist.')
    return data

def process_total(order_id, process_id, exclude_work_log_id=None):
    query = db.session.query(func.coalesce(func.sum(WorkLog.quantity), 0)).filter(
        WorkLog.order_id == order_id, WorkLog.process_id == process_id)
    if exclude_work_log_id is not None:
        query = query.filter(WorkLog.id != exclude_work_log_id)
    return query.scalar()

def detect_overage(order_id, process_id, quantity, exclude_work_log_id=None):
    """Return the number of units over the order quantity this entry would cause (0 if none). No DB writes."""
    order = db.session.get(Order, order_id)
    new_total = process_total(order_id, process_id, exclude_work_log_id) + quantity
    return max(new_total - order.quantity, 0)

def sync_overage(order_id, process_id):
    """Make the pending overage record for an order/process match the work actually logged.

    Creates or updates a pending overage when logged units exceed the order quantity and
    removes it when they no longer do. Resolved overages are kept as history.
    """
    order = db.session.get(Order, order_id)
    if not order:
        return
    total = process_total(order_id, process_id)
    pending = Overage.query.filter_by(order_id=order_id, process_id=process_id, status='pending').first()
    if total > order.quantity:
        resolved = Overage.query.filter_by(order_id=order_id, process_id=process_id, status='resolved')\
            .order_by(Overage.actual_units.desc()).first()
        if pending:
            pending.expected_units = order.quantity
            pending.actual_units = total
            pending.overage_units = total - order.quantity
        elif not resolved or total > resolved.actual_units:
            db.session.add(Overage(order_id=order_id, process_id=process_id, expected_units=order.quantity,
                                   actual_units=total, overage_units=total - order.quantity))
    elif pending:
        WorkLogOverage.query.filter_by(overage_id=pending.id).delete()
        db.session.delete(pending)

def update_order_status(order):
    """Move an order forward automatically: pending -> in_progress when work is logged,
    in_progress -> completed once every active process has logged the full quantity.
    Never moves backwards, so manual changes (e.g. cancelled) are respected."""
    if not order or order.status in ('completed', 'cancelled'):
        return
    has_work = WorkLog.query.filter_by(order_id=order.id).first() is not None
    if order.status == 'pending' and has_work:
        order.status = 'in_progress'
    active_processes = Process.query.filter_by(is_active=True).all()
    if order.status == 'in_progress' and active_processes and all(
            process_total(order.id, p.id) >= order.quantity for p in active_processes):
        order.status = 'completed'
        db.session.add(OrderStatus(order_id=order.id, status='completed',
                                   notes='Automatically completed: all processes reached the order quantity'))

def after_work_log_change(*order_process_pairs):
    """Re-sync overages and order status for each (order_id, process_id) touched."""
    db.session.flush()
    for order_id, process_id in set(order_process_pairs):
        sync_overage(order_id, process_id)
    for order_id in {order_id for order_id, _ in order_process_pairs}:
        update_order_status(db.session.get(Order, order_id))

def save_work_log(data):
    work_log = WorkLog(
        employee_id=data['employee_id'],
        order_id=data['order_id'],
        process_id=data['process_id'],
        quantity=data['quantity'],
        date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        notes=data['notes'],
    )
    db.session.add(work_log)
    after_work_log_change((data['order_id'], data['process_id']))
    db.session.commit()
    return work_log

@app.route('/overages')
def overages():
    """Overage dashboard page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Get all pending overages
    pending_overages = Overage.query.filter_by(status='pending').all()
    
    # Get resolved overages from last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    resolved_overages = Overage.query.filter(
        and_(
            Overage.status == 'resolved',
            Overage.resolved_at >= thirty_days_ago
        )
    ).all()
    
    return render_template('pages/overages.html', 
                         pending_overages=pending_overages,
                         resolved_overages=resolved_overages)

@app.route('/overages/<int:overage_id>')
def overage_detail(overage_id):
    """Overage detail page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    overage = Overage.query.get_or_404(overage_id)
    
    # Get all work logs for this order/process with employee and process info
    work_logs = WorkLog.query.filter_by(
        order_id=overage.order_id,
        process_id=overage.process_id
    ).join(Employee).join(Process).order_by(WorkLog.date.desc()).all()
    
    # Debug: Print work logs info
    print(f"Overage Detail - Order: {overage.order_id}, Process: {overage.process_id}")
    print(f"Found {len(work_logs)} work logs:")
    for wl in work_logs:
        print(f"  - {wl.employee.name}: {wl.quantity} units on {wl.date}")
    
    return render_template('pages/overage_detail.html', 
                         overage=overage,
                         work_logs=work_logs)

@app.route('/overages/<int:overage_id>/resolve', methods=['POST'])
def resolve_overage(overage_id):
    """Resolve an overage"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        overage = Overage.query.get_or_404(overage_id)
        
        # Validate overage has required fields
        if not overage.order_id or not overage.process_id:
            flash('Invalid overage record. Please contact administrator.', 'error')
            return redirect(url_for('overages'))
        
        resolution_notes = request.form.get('resolution_notes', '')
        
        overage.status = 'resolved'
        overage.resolved_by = session.get('user_id')
        overage.resolved_at = datetime.utcnow()
        overage.resolution_notes = resolution_notes
        
        db.session.commit()
        
        flash('Overage marked as resolved!', 'success')
        return redirect(url_for('overages'))
        
    except Exception as e:
        print(f"Error resolving overage {overage_id}: {e}")
        db.session.rollback()
        flash('Error resolving overage. Please try again.', 'error')
        return redirect(url_for('overages'))

@app.route('/work-log', methods=['GET', 'POST'])
def work_log():
    """Add work log page with overage detection"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    prefill = session.pop('work_log_prefill', None)

    if request.method == 'POST':
        try:
            data = parse_work_log_form(request.form)
            overage_units = detect_overage(data['order_id'], data['process_id'], data['quantity'])
            if overage_units:
                # Nothing is saved until the overage is approved
                data['overage_message'] = f"Overage detected: {overage_units} units over limit"
                session['pending_work_log'] = data
                flash(f"Overage detected! {data['overage_message']} Please review and approve.", 'warning')
                return redirect(url_for('approve_overage'))
            save_work_log(data)
            flash('Work log added successfully!', 'success')
            return redirect(url_for('work_log'))
        except FormError as e:
            db.session.rollback()
            flash(str(e), 'error')
            prefill = request.form.to_dict()

    # Get data for dropdowns
    employees = Employee.query.filter_by(is_active=True).all()
    orders = Order.query.filter(Order.status.in_(['pending', 'in_progress'])).all()
    processes = Process.query.filter_by(is_active=True).all()
    
    # Get recent work logs for display
    recent_work_logs = WorkLog.query.order_by(WorkLog.date.desc()).limit(10).all()
    
    # Calculate current totals for each order/process combination
    order_process_totals = {}
    for order in orders:
        for process in processes:
            total = db.session.query(func.sum(WorkLog.quantity)).filter_by(
                order_id=order.id, 
                process_id=process.id
            ).scalar() or 0
            order_process_totals[f"{order.id}-{process.id}"] = total
    
    return render_template('pages/work_log.html',
                         prefill=prefill or {},
                         employees=employees,
                         orders=orders,
                         processes=processes,
                         recent_work_logs=recent_work_logs,
                         order_process_totals=order_process_totals,
                         today=date.today().strftime('%Y-%m-%d'))

@app.route('/approve-overage', methods=['GET', 'POST'])
def approve_overage():
    """Approve overage work log page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    pending_work_log = session.get('pending_work_log')
    if not pending_work_log:
        flash('No pending work log found', 'error')
        return redirect(url_for('work_log'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'approve':
            save_work_log(pending_work_log)
            session.pop('pending_work_log', None)
            flash('Work log approved and created with overage!', 'success')
            return redirect(url_for('work_log'))
        
        elif action == 'edit':
            # Return to the work log form with the entered values filled in
            session['work_log_prefill'] = session.pop('pending_work_log', None)
            return redirect(url_for('work_log'))
        
        elif action == 'cancel':
            # Clear session and return to work log
            session.pop('pending_work_log', None)
            flash('Work log creation cancelled', 'info')
            return redirect(url_for('work_log'))
    
    # Get order and process details for display
    order = db.session.get(Order, pending_work_log['order_id'])
    process = db.session.get(Process, pending_work_log['process_id'])
    employee = db.session.get(Employee, pending_work_log['employee_id'])
    
    return render_template('pages/approve_overage.html',
                         pending_work_log=pending_work_log,
                         order=order,
                         process=process,
                         employee=employee)

@app.route('/work-logs')
def work_logs():
    """View all work logs"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    work_logs = WorkLog.query.order_by(WorkLog.date.desc()).all()
    return render_template('pages/work_logs.html', work_logs=work_logs)

@app.route('/work-logs/archive', methods=['POST'])
@admin_required
def archive_work_logs():
    """Archive all work logs to CSV and clear table"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        work_logs = WorkLog.query.all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Employee ID', 'Employee Name', 'Order No', 'Process', 'Quantity', 'Rate/Piece', 'Date', 'Notes'])
        
        for wl in work_logs:
            writer.writerow([
                wl.id,
                wl.employee.employee_id if wl.employee else '',
                wl.employee.name if wl.employee else '',
                wl.order.order_no if wl.order else '',
                wl.process.name if wl.process else '',
                wl.quantity,
                wl.process.pay_rate if wl.process else 0,
                wl.date.strftime('%Y-%m-%d') if wl.date else '',
                wl.notes or ''
            ])
            
        csv_data = output.getvalue()
        
        # Safety net: keep a full database backup from just before the clear
        ok, backup_result = create_backup()
        if not ok:
            flash(f'Archive cancelled: could not create a backup first ({backup_result}).', 'error')
            return redirect(url_for('work_logs'))
        
        archived_count = len(work_logs)
        # Clear child tables first
        WorkLogOverage.query.delete()
        # Pending overages refer to the cleared work; resolved ones stay as history
        Overage.query.filter_by(status='pending').delete()
        # Clear main table
        WorkLog.query.delete()
        db.session.commit()
        log_audit('Archive Work Logs', 'WorkLog', None,
                  f'Archived {archived_count} work logs; backup {os.path.basename(backup_result)}')
        
        # Send file directly
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return send_file(
            io.BytesIO(csv_data.encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'work_logs_archive_{timestamp}.csv'
        )
        
    except Exception as e:
        print(f"Error archiving work logs: {e}")
        db.session.rollback()
        flash('Error archiving work logs. Please try again.', 'error')
        return redirect(url_for('work_logs'))

@app.route('/work-logs/<int:work_log_id>/edit', methods=['GET', 'POST'])
def edit_work_log(work_log_id):
    """Edit work log with overage detection"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    work_log = WorkLog.query.get_or_404(work_log_id)
    
    if request.method == 'POST':
        try:
            data = parse_work_log_form(request.form)
            overage_units = detect_overage(data['order_id'], data['process_id'], data['quantity'],
                                           exclude_work_log_id=work_log.id)
            if overage_units:
                flash(f'Warning: This creates an overage of {overage_units} units. It has been recorded for review.', 'warning')
            previous = (work_log.order_id, work_log.process_id)
            work_log.employee_id = data['employee_id']
            work_log.order_id = data['order_id']
            work_log.process_id = data['process_id']
            work_log.quantity = data['quantity']
            work_log.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
            work_log.notes = data['notes']
            after_work_log_change(previous, (data['order_id'], data['process_id']))
            db.session.commit()
            flash('Work log updated successfully!', 'success')
            return redirect(url_for('work_logs'))
        except FormError as e:
            db.session.rollback()
            flash(str(e), 'error')
    
    # Get data for dropdowns (always include the entry's current employee/order/process)
    employees = Employee.query.filter((Employee.is_active == True) | (Employee.id == work_log.employee_id)).all()
    orders = Order.query.filter(Order.status.in_(['pending', 'in_progress']) | (Order.id == work_log.order_id)).all()
    processes = Process.query.filter((Process.is_active == True) | (Process.id == work_log.process_id)).all()
    
    # Calculate current total excluding this work log
    current_total = db.session.query(func.sum(WorkLog.quantity)).filter(
        and_(
            WorkLog.order_id == work_log.order_id,
            WorkLog.process_id == work_log.process_id,
            WorkLog.id != work_log_id
        )
    ).scalar() or 0
    
    return render_template('pages/edit_work_log.html', 
                         work_log=work_log,
                         employees=employees,
                         orders=orders,
                         processes=processes,
                         current_total=current_total)

@app.route('/work-logs/<int:work_log_id>/delete', methods=['POST'])
def delete_work_log(work_log_id):
    """Delete work log"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    work_log = WorkLog.query.get_or_404(work_log_id)
    
    affected = (work_log.order_id, work_log.process_id)
    WorkLogOverage.query.filter_by(work_log_id=work_log.id).delete()
    db.session.delete(work_log)
    after_work_log_change(affected)
    db.session.commit()
    
    flash('Work log deleted successfully!', 'success')
    return redirect(url_for('work_logs'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
def delete_order(order_id):
    """Delete order"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        order = Order.query.get_or_404(order_id)
        
        # Check if order has work logs
        work_logs = WorkLog.query.filter_by(order_id=order_id).all()
        if work_logs:
            flash('Cannot delete order with existing work logs. Please delete work logs first.', 'error')
            return redirect(url_for('orders'))
        
        # Check if order has overages
        overages = Overage.query.filter_by(order_id=order_id).all()
        if overages:
            # Clean up overages first
            cleanup_overages_for_order(order_id)
        
        print(f"Deleting order {order_id}: {order.order_no}")
        
        db.session.delete(order)
        db.session.commit()
        
        flash('Order deleted successfully!', 'success')
        return redirect(url_for('orders'))
        
    except Exception as e:
        print(f"Error deleting order {order_id}: {e}")
        db.session.rollback()
        flash('Error deleting order. Please try again.', 'error')
        return redirect(url_for('orders'))

@app.route('/employees/<int:employee_id>/delete', methods=['POST'])
def delete_employee(employee_id):
    """Delete employee (kept for backward compatibility, redirects to deactivate)"""
    return deactivate_employee(employee_id)

@app.route('/employees/<int:employee_id>/deactivate', methods=['POST'])
def deactivate_employee(employee_id):
    """Deactivate employee (soft delete)"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        employee = Employee.query.get_or_404(employee_id)
        employee.is_active = False
        db.session.commit()
        
        log_audit('Deactivate Employee', 'Employee', employee.id, f'Deactivated employee {employee.name}')
        flash(f'Employee {employee.name} has been deactivated.', 'success')
        
    except Exception as e:
        print(f"Error deactivating employee {employee_id}: {e}")
        db.session.rollback()
        flash('Error deactivating employee. Please try again.', 'error')
        
    return redirect(url_for('employees'))

@app.route('/employees/<int:employee_id>/activate', methods=['POST'])
def activate_employee(employee_id):
    """Activate employee"""
    print(f"=== ACTIVATE ROUTE CALLED for employee_id: {employee_id} ===")
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        employee = Employee.query.get_or_404(employee_id)
        print(f"Activating employee {employee_id}: {employee.name}, current status: {employee.is_active}")
        employee.is_active = True
        db.session.commit()
        print(f"Employee {employee_id} activated successfully, new status: {employee.is_active}")
        
        log_audit('Activate Employee', 'Employee', employee.id, f'Activated employee {employee.name}')
        flash(f'Employee {employee.name} has been activated.', 'success')
        
    except Exception as e:
        print(f"Error activating employee {employee_id}: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        flash('Error activating employee. Please try again.', 'error')
        
    return redirect(url_for('employees'))

@app.route('/processes/<int:process_id>/delete', methods=['POST'])
def delete_process(process_id):
    """Delete process"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        process = Process.query.get_or_404(process_id)
        
        # Check if process has work logs
        work_logs = WorkLog.query.filter_by(process_id=process_id).all()
        if work_logs:
            flash('Cannot delete process with existing work logs. Please delete work logs first.', 'error')
            return redirect(url_for('processes'))
        
        # Check if process has overages
        overages = Overage.query.filter_by(process_id=process_id).all()
        if overages:
            # Clean up overages first
            cleanup_overages_for_process(process_id)
        
        print(f"Deleting process {process_id}: {process.name}")
        
        db.session.delete(process)
        db.session.commit()
        
        flash('Process deleted successfully!', 'success')
        return redirect(url_for('processes'))
        
    except Exception as e:
        print(f"Error deleting process {process_id}: {e}")
        db.session.rollback()
        flash('Error deleting process. Please try again.', 'error')
        return redirect(url_for('processes'))

@app.route('/payment-report', methods=['GET', 'POST'])
def payment_report():
    """Generate payment report page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employees = Employee.query.filter_by(is_active=True).all()
    report_data = None
    
    # Check if there are any employees
    if not employees:
        flash('No employees found. Please add employees before generating payment reports.', 'warning')
    
    if request.method == 'POST':
        print("POST request received to /payment-report")
        print("Form data:", request.form)
        
        # Get form data with proper validation
        employee_id_str = request.form.get('employee_id')
        month_str = request.form.get('month')
        year_str = request.form.get('year')
        
        # Check if any required field is missing
        if not all([employee_id_str, month_str, year_str]):
            print("Validation failed - missing required fields")
            flash('Please fill in all fields', 'error')
        else:
            try:
                employee_id = int(employee_id_str)
                month = int(month_str)
                year = int(year_str)
                
                print(f"Parsed data: employee_id={employee_id}, month={month}, year={year}")
                
                # Additional validation
                if month < 1 or month > 12:
                    flash('Invalid month. Please select a month between 1 and 12.', 'error')
                    return render_template('pages/payment_report.html',
                                         employees=employees,
                                         report_data=report_data)
                
                if year < 2020 or year > 2030:
                    flash('Invalid year. Please select a year between 2020 and 2030.', 'error')
                    return render_template('pages/payment_report.html',
                                         employees=employees,
                                         report_data=report_data)
                
            except (ValueError, TypeError) as e:
                print(f"Error parsing form data: {e}")
                flash('Invalid form data. Please check your inputs.', 'error')
                return render_template('pages/payment_report.html',
                                     employees=employees,
                                     report_data=report_data)
            # Calculate payment report
            work_logs = WorkLog.query.filter(
                and_(
                    WorkLog.employee_id == employee_id,
                    func.extract('month', WorkLog.date) == month,
                    func.extract('year', WorkLog.date) == year
                )
            ).all()
            
            # Check if employee exists
            employee = Employee.query.get(employee_id)
            if not employee:
                flash(f'Employee with ID {employee_id} not found.', 'error')
                return render_template('pages/payment_report.html',
                                     employees=employees,
                                     report_data=report_data)
            
            total_quantity = sum(wl.quantity for wl in work_logs)
            
            # Calculate total payment based on process pay rates (piece rate)
            total_payment = 0
            for wl in work_logs:
                process = Process.query.get(wl.process_id)
                if process:
                    total_payment += wl.quantity * process.pay_rate
            
            report_data = {
                'employee': employee,
                'month': month,
                'year': year,
                'work_logs': work_logs,
                'total_quantity': total_quantity,
                'total_payment': total_payment
            }
            
            print(f"Payment report generated for {employee.name}: {total_quantity} pieces, LKR {total_payment:.2f}")
    
    return render_template('pages/payment_report.html',
                         employees=employees,
                         report_data=report_data)

@app.route('/payment-report/pdf', methods=['POST'])
def download_payment_report_pdf():
    """Generate and download payment report as PDF"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        # Get form data
        try:
            employee_id = int(request.form.get('employee_id'))
            month = int(request.form.get('month'))
            year = int(request.form.get('year'))
        except (TypeError, ValueError):
            flash('Please fill in all fields', 'error')
            return redirect(url_for('payment_report'))
        
        if month < 1 or month > 12:
            flash('Invalid month', 'error')
            return redirect(url_for('payment_report'))
        
        if year < 2020 or year > 2030:
            flash('Invalid year', 'error')
            return redirect(url_for('payment_report'))
        
        # Get employee
        employee = Employee.query.get(employee_id)
        if not employee:
            flash('Employee not found', 'error')
            return redirect(url_for('payment_report'))
        
        # Get work logs
        work_logs = WorkLog.query.filter(
            and_(
                WorkLog.employee_id == employee_id,
                func.extract('month', WorkLog.date) == month,
                func.extract('year', WorkLog.date) == year
            )
        ).all()
        
        # Calculate totals
        total_quantity = sum(wl.quantity for wl in work_logs)
        total_payment = 0
        for wl in work_logs:
            process = Process.query.get(wl.process_id)
            if process:
                total_payment += wl.quantity * process.pay_rate
        
        # Generate PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=20
        )
        normal_style = styles['Normal']
        
        # Add title
        story.append(Paragraph("OLEEMA - Payment Report", title_style))
        story.append(Spacer(1, 20))
        
        # Add employee info
        story.append(Paragraph(f"Employee: {employee.name} ({employee.employee_id})", heading_style))
        story.append(Paragraph(f"Period: {month}/{year}", normal_style))
        story.append(Spacer(1, 20))
        
        # Add summary
        summary_data = [
            ['Total Pieces', str(total_quantity)],
            ['Total Payment', f"LKR {total_payment:.2f}"]
        ]
        summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightblue),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))
        
        # Add work logs table if any
        if work_logs:
            story.append(Paragraph("Work Log Details", heading_style))
            
            # Table headers
            table_data = [['Date', 'Order', 'Process', 'Pieces', 'Rate/Piece', 'Payment']]
            
            # Add work log data
            for wl in work_logs:
                process = Process.query.get(wl.process_id)
                order = Order.query.get(wl.order_id)
                rate = process.pay_rate if process else 0
                payment = wl.quantity * rate
                
                table_data.append([
                    wl.date.strftime('%Y-%m-%d'),
                    order.order_no if order else 'N/A',
                    process.name if process else 'N/A',
                    str(wl.quantity),
                    f"LKR {rate:.2f}",
                    f"LKR {payment:.2f}"
                ])
            
            # Create table
            work_log_table = Table(table_data, colWidths=[1*inch, 1.2*inch, 1.2*inch, 0.8*inch, 1*inch, 1*inch])
            work_log_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(work_log_table)
        else:
            story.append(Paragraph("No work logs found for the selected period.", normal_style))
        
        # Add footer
        story.append(Spacer(1, 30))
        story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        # Generate filename
        filename = f"payment_report_{employee.employee_id}_{year}_{month:02d}.pdf"
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        flash('Error generating PDF report', 'error')
        return redirect(url_for('payment_report'))

@app.route('/payment-report/csv', methods=['POST'])
def download_payment_report_csv():
    """Generate CSV payment report"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        employee_id = request.form.get('employee_id')
        year = int(request.form.get('year'))
        month = int(request.form.get('month'))
        
        employee = Employee.query.get_or_404(employee_id)
        work_logs = WorkLog.query.filter(
            WorkLog.employee_id == employee_id,
            extract('year', WorkLog.date) == year,
            extract('month', WorkLog.date) == month
        ).order_by(WorkLog.date.asc()).all()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Payment Report'])
        writer.writerow([f'Employee: {employee.name} ({employee.employee_id})'])
        writer.writerow([f'Period: {year}-{month:02d}'])
        writer.writerow([])
        
        # Column headers
        writer.writerow(['Date', 'Order ID', 'Process', 'Quantity', 'Rate', 'Amount'])
        
        # Data rows
        total_payment = 0
        for wl in work_logs:
            process = Process.query.get(wl.process_id)
            if process:
                amount = wl.quantity * process.pay_rate
                total_payment += amount
                writer.writerow([
                    wl.date.strftime('%Y-%m-%d'),
                    wl.order_id,
                    process.name,
                    wl.quantity,
                    f'{process.pay_rate:.2f}',
                    f'{amount:.2f}'
                ])
        
        # Total
        writer.writerow([])
        writer.writerow(['', '', '', '', 'Total:', f'{total_payment:.2f}'])
        
        # Convert to bytes
        output.seek(0)
        
        filename = f"payment_report_{employee.employee_id}_{year}_{month:02d}.csv"
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
        
    except Exception as e:
        print(f"Error generating CSV: {e}")
        flash('Error generating CSV report', 'error')
        return redirect(url_for('payment_report'))


@app.route('/processes')
def processes():
    """View all processes"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    processes = Process.query.order_by(Process.is_active.desc(), Process.name).all()
    return render_template('pages/processes.html', processes=processes)

@app.route('/processes/add', methods=['GET', 'POST'])
def add_process():
    """Add new process"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        print("POST request received to /processes/add")
        print("Form data:", request.form)
        
        name = request.form.get('name')
        try:
            pay_rate = parse_float(request.form.get('pay_rate'), 'Pay rate', minimum=0)
        except FormError:
            pay_rate = None
        description = request.form.get('description')
        
        if not name or not pay_rate:
            print("Validation failed - missing required fields")
            flash('Please fill in all required fields', 'error')
        else:
            process = Process(
                name=name,
                pay_rate=pay_rate,
                description=description
            )
            db.session.add(process)
            db.session.commit()
            print(f"Process created successfully: {process.name} (LKR {process.pay_rate}/piece)")
            flash('Process added successfully!', 'success')
            return redirect(url_for('processes'))
    
    return render_template('pages/add_process.html')

@app.route('/processes/<int:process_id>/edit', methods=['GET', 'POST'])
def edit_process(process_id):
    """Edit process"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    process = Process.query.get_or_404(process_id)
    
    if request.method == 'POST':
        try:
            pay_rate = parse_float(request.form.get('pay_rate'), 'Pay rate', minimum=0)
        except FormError as e:
            flash(str(e), 'error')
            return render_template('pages/edit_process.html', process=process)
        if not request.form.get('name'):
            flash('Process name is required', 'error')
            return render_template('pages/edit_process.html', process=process)
        process.name = request.form.get('name')
        process.pay_rate = pay_rate
        process.description = request.form.get('description')
        process.is_active = 'is_active' in request.form
        
        db.session.commit()
        flash('Process updated successfully!', 'success')
        return redirect(url_for('processes'))
    
    return render_template('pages/edit_process.html', process=process)

@app.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Change password page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Get current user
        user = User.query.filter_by(username=session.get('username')).first()
        
        if not user or not user.check_password(current_password):
            flash('Current password is incorrect', 'error')
        elif len(new_password) < 6:
            flash('New password must be at least 6 characters long', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match', 'error')
        else:
            user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template('pages/change_password.html')

@app.route('/backup', methods=['GET', 'POST'])
@admin_required
def backup():
    """Backup management page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_backup':
            success, result = create_backup()
            if success:
                flash(f'Backup created successfully! File: {os.path.basename(result)}', 'success')
            else:
                flash(f'Backup failed: {result}', 'error')
        elif action == 'restore_backup':
            try:
                restore_backup(request.form.get('backup_file'))
                flash('Database restored successfully! A backup of the previous data was taken first.', 'success')
            except Exception as e:
                flash(f'Restore failed: {str(e)}', 'error')
    
    # Get backup information
    last_backup_time, last_backup_path = get_last_backup_info()
    
    # Get list of available backups
    available_backups = []
    if os.path.exists(BACKUP_DIR):
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('oleema_backup_') and filename.endswith('.db'):
                file_path = os.path.join(BACKUP_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                available_backups.append({
                    'filename': filename,
                    'path': file_path,
                    'created': file_time,
                    'size': os.path.getsize(file_path)
                })
        available_backups.sort(key=lambda x: x['created'], reverse=True)
    
    return render_template('pages/backup.html',
                         last_backup_time=last_backup_time,
                         last_backup_path=last_backup_path,
                         available_backups=available_backups)

@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    """System settings page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Update settings
            settings_data = {
                'company_name': request.form.get('company_name'),
                'currency_symbol': request.form.get('currency_symbol'),
                'items_per_page': request.form.get('items_per_page')
            }
            
            for key, value in settings_data.items():
                setting = Setting.query.get(key)
                if not setting:
                    setting = Setting(key=key, description=key.replace('_', ' ').title())
                    db.session.add(setting)
                setting.value = value
            
            db.session.commit()
            log_audit('Update Settings', 'System', None, 'Updated system settings')
            flash('Settings updated successfully!', 'success')
            
        except Exception as e:
            print(f"Error updating settings: {e}")
            db.session.rollback()
            flash('Error updating settings', 'error')
            
        return redirect(url_for('settings'))
    
    # Fetch current settings
    settings_dict = {}
    try:
        all_settings = Setting.query.all()
        for setting in all_settings:
            settings_dict[setting.key] = setting.value
    except Exception as e:
        print(f"Error fetching settings: {e}")
        # Provide defaults if tables don't exist yet
        settings_dict = {
            'company_name': 'Oleema Industries',
            'currency_symbol': 'LKR',
            'items_per_page': '10'
        }
    
    return render_template('pages/settings.html', settings=settings_dict)

@app.route('/audit-logs')
@admin_required
def audit_logs():
    """View audit logs"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('pages/audit_logs.html', logs=logs)

@app.route('/users')
@admin_required
def users():
    """User management page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    users = User.query.all()
    return render_template('pages/users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Add new user"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not all([username, password, role]):
            flash('Please fill in all required fields', 'error')
        else:
            existing = User.query.filter_by(username=username).first()
            if existing:
                flash('Username already exists', 'error')
            else:
                user = User(username=username, role=role)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                log_audit('Create User', 'User', user.id, f'Created user {username}')
                flash('User created successfully!', 'success')
                return redirect(url_for('users'))
    
    return render_template('pages/add_user.html')

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit user"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.role = request.form.get('role')
        
        password = request.form.get('password')
        if password:
            user.set_password(password)
            
        db.session.commit()
        log_audit('Update User', 'User', user.id, f'Updated user {user.username}')
        flash('User updated successfully!', 'success')
        return redirect(url_for('users'))
    
    return render_template('pages/edit_user.html', user=user)

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete user"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account', 'error')
        return redirect(url_for('users'))
    
    user = User.query.get_or_404(user_id)
    username = user.username
    
    try:
        db.session.delete(user)
        db.session.commit()
        log_audit('Delete User', 'User', user_id, f'Deleted user {username}')
        flash('User deleted successfully!', 'success')
    except Exception as e:
        print(f"Error deleting user: {e}")
        db.session.rollback()
        flash('Error deleting user', 'error')
        
    return redirect(url_for('users'))

@app.route('/logout')
def logout():
    """Logout user"""
    if session.get('logged_in'):
        log_audit('Logout', 'User', session.get('user_id'), 'User logged out')
        
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

# Material Management Routes
@app.route('/materials')
def materials():
    """Material management page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    materials = Material.query.filter_by(is_active=True).all()
    return render_template('pages/materials.html', materials=materials)

@app.route('/materials/add', methods=['GET', 'POST'])
def add_material():
    """Add new material"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        unit = request.form.get('unit')
        description = request.form.get('description')
        try:
            cost = parse_float(request.form.get('cost_per_unit'), 'Cost per unit', minimum=0, default=0)
            stock = parse_float(request.form.get('current_stock'), 'Current stock', minimum=0, default=0)
            reorder = parse_float(request.form.get('reorder_level'), 'Reorder level', minimum=0, default=0)
        except FormError as e:
            flash(str(e), 'error')
            return render_template('pages/add_material.html')
        
        if not all([name, unit]):
            flash('Please fill in all required fields', 'error')
        else:
            material = Material(
                name=name,
                unit=unit,
                cost_per_unit=cost,
                current_stock=stock,
                reorder_level=reorder,
                description=description
            )
            db.session.add(material)
            db.session.commit()
            
            # Log initial stock transaction if > 0
            if stock > 0:
                transaction = InventoryTransaction(
                    material_id=material.id,
                    quantity_change=stock,
                    transaction_type='adjustment',
                    notes='Initial stock',
                    user_id=session.get('user_id')
                )
                db.session.add(transaction)
                db.session.commit()
            
            log_audit('Create Material', 'Material', material.id, f'Created material {name}')
            flash('Material added successfully!', 'success')
            return redirect(url_for('materials'))
            
    return render_template('pages/add_material.html')

@app.route('/materials/<int:material_id>/edit', methods=['GET', 'POST'])
def edit_material(material_id):
    """Edit material"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    material = Material.query.get_or_404(material_id)
    
    if request.method == 'POST':
        try:
            cost = parse_float(request.form.get('cost_per_unit'), 'Cost per unit', minimum=0, default=0)
            reorder = parse_float(request.form.get('reorder_level'), 'Reorder level', minimum=0, default=0)
            new_stock = parse_float(request.form.get('current_stock'), 'Current stock', minimum=0, default=0)
        except FormError as e:
            flash(str(e), 'error')
            return render_template('pages/edit_material.html', material=material)
        if not request.form.get('name') or not request.form.get('unit'):
            flash('Please fill in all required fields', 'error')
            return render_template('pages/edit_material.html', material=material)
        material.name = request.form.get('name')
        material.unit = request.form.get('unit')
        material.cost_per_unit = cost
        material.reorder_level = reorder
        material.description = request.form.get('description')
        
        # Handle stock adjustment
        stock_diff = new_stock - material.current_stock
        
        if abs(stock_diff) > 0.001:
            transaction = InventoryTransaction(
                material_id=material.id,
                quantity_change=stock_diff,
                transaction_type='adjustment',
                notes='Manual adjustment',
                user_id=session.get('user_id')
            )
            db.session.add(transaction)
            material.current_stock = new_stock
            
        db.session.commit()
        log_audit('Update Material', 'Material', material.id, f'Updated material {material.name}')
        flash('Material updated successfully!', 'success')
        return redirect(url_for('materials'))
        
    return render_template('pages/edit_material.html', material=material)

@app.route('/materials/<int:material_id>/delete', methods=['POST'])
def delete_material(material_id):
    """Soft delete material"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    material = Material.query.get_or_404(material_id)
    material.is_active = False
    db.session.commit()
    
    log_audit('Delete Material', 'Material', material.id, f'Deactivated material {material.name}')
    flash('Material deactivated successfully!', 'success')
    return redirect(url_for('materials'))

if __name__ == '__main__':
    # Local only: never expose the debugger to other machines on the network
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1', host='127.0.0.1', port=5001)
