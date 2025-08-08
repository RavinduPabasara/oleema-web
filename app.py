from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Employee, Process, Order, WorkLog, Payment, OrderStatus, Overage, WorkLogOverage
import os
import shutil
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///oleema.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session timeout configuration (2 hours = 7200 seconds)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Initialize database
db.init_app(app)

# Create backup directory if it doesn't exist
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

def create_backup():
    """Create a backup of the database"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'oleema_backup_{timestamp}.db'
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Copy the database file
        shutil.copy2('instance/oleema.db', backup_path)
        
        # Keep only last 7 days of backups
        cleanup_old_backups()
        
        return True, backup_path
    except Exception as e:
        return False, str(e)

def cleanup_old_backups():
    """Remove backups older than 7 days"""
    try:
        current_time = datetime.now()
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('oleema_backup_') and filename.endswith('.db'):
                file_path = os.path.join(BACKUP_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                if (current_time - file_time).days > 7:
                    os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up old backups: {e}")

def get_last_backup_info():
    """Get information about the last backup"""
    try:
        backups = []
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('oleema_backup_') and filename.endswith('.db'):
                file_path = os.path.join(BACKUP_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                backups.append((file_time, file_path))
        
        if backups:
            latest_backup = max(backups, key=lambda x: x[0])
            return latest_backup[0], latest_backup[1]
        return None, None
    except Exception as e:
        print(f"Error getting backup info: {e}")
        return None, None

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
            session['username'] = username
            session['user_id'] = user.id
            flash('Login successful!', 'success')
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
    
    return render_template('pages/dashboard.html',
                         total_employees=total_employees,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         completed_orders=completed_orders,
                         recent_orders=recent_orders,
                         recent_work_logs=recent_work_logs)

@app.route('/employees')
def employees():
    """Employee management page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employees = Employee.query.filter_by(is_active=True).all()
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
        quantity = int(request.form.get('quantity', 0))
        notes = request.form.get('notes')
        
        if not all([order_no, date_str, color, size, quantity]):
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

def check_and_create_overage(order_id, process_id, new_quantity):
    """Check if adding new work log creates an overage and handle it"""
    try:
        # Validate inputs
        if not order_id or not process_id or not new_quantity:
            return False, "Invalid input parameters"
        
        order = Order.query.get(order_id)
        process = Process.query.get(process_id)
        
        if not order or not process:
            return False, "Order or process not found"
        
        # Calculate current total for this process
        existing_work_logs = WorkLog.query.filter_by(
            order_id=order_id, 
            process_id=process_id
        ).all()
        
        current_total = sum(wl.quantity for wl in existing_work_logs)
        new_total = current_total + new_quantity
        
        # Check if this creates an overage
        if new_total > order.quantity:
            overage_units = new_total - order.quantity
            
            # Check if overage already exists for this order/process
            existing_overage = Overage.query.filter_by(
                order_id=order_id,
                process_id=process_id,
                status='pending'
            ).first()
            
            if existing_overage:
                # Update existing overage
                existing_overage.actual_units = new_total
                existing_overage.overage_units = overage_units
            else:
                # Create new overage
                overage = Overage(
                    order_id=order_id,
                    process_id=process_id,
                    expected_units=order.quantity,
                    actual_units=new_total,
                    overage_units=overage_units
                )
                db.session.add(overage)
            
            db.session.commit()
            return True, f"Overage detected: {overage_units} units over limit"
        
        return False, "No overage"
        
    except Exception as e:
        print(f"Error in check_and_create_overage: {e}")
        db.session.rollback()
        return False, f"Error creating overage: {str(e)}"

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
    
    if request.method == 'POST':
        print("POST request received to /work-log")
        print("Form data:", request.form)
        
        employee_id = int(request.form.get('employee_id'))
        order_id = int(request.form.get('order_id'))
        process_id = int(request.form.get('process_id'))
        quantity = int(request.form.get('quantity', 0))
        date_str = request.form.get('date')
        notes = request.form.get('notes')
        
        print(f"Parsed data: employee_id={employee_id}, order_id={order_id}, process_id={process_id}, quantity={quantity}, date={date_str}")
        
        if not all([employee_id, order_id, process_id, quantity, date_str]):
            print("Validation failed - missing required fields")
            flash('Please fill in all required fields', 'error')
        else:
            # Check for overage before creating work log
            has_overage, overage_message = check_and_create_overage(order_id, process_id, quantity)
            
            if has_overage:
                # Store work log data in session for approval
                session['pending_work_log'] = {
                    'employee_id': employee_id,
                    'order_id': order_id,
                    'process_id': process_id,
                    'quantity': quantity,
                    'date': date_str,
                    'notes': notes,
                    'overage_message': overage_message
                }
                flash(f'Overage detected! {overage_message} Please review and approve.', 'warning')
                return redirect(url_for('approve_overage'))
            
            # No overage, proceed normally
            work_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            work_log = WorkLog(
                employee_id=employee_id,
                order_id=order_id,
                process_id=process_id,
                quantity=quantity,
                date=work_date,
                notes=notes
            )
            db.session.add(work_log)
            
            # Update order status to 'in_progress' if this is the first work log
            order = Order.query.get(order_id)
            if order and order.status == 'pending':
                order.status = 'in_progress'
                print(f"Updated order {order.order_no} status to in_progress")
            
            db.session.commit()
            print(f"Work log created successfully for employee {employee_id}, order {order_id}, process {process_id}")
            flash('Work log added successfully!', 'success')
            return redirect(url_for('work_log'))
    
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
            # Create the work log with overage
            work_date = datetime.strptime(pending_work_log['date'], '%Y-%m-%d').date()
            work_log = WorkLog(
                employee_id=pending_work_log['employee_id'],
                order_id=pending_work_log['order_id'],
                process_id=pending_work_log['process_id'],
                quantity=pending_work_log['quantity'],
                date=work_date,
                notes=pending_work_log['notes']
            )
            db.session.add(work_log)
            
            # Update order status
            order = Order.query.get(pending_work_log['order_id'])
            if order and order.status == 'pending':
                order.status = 'in_progress'
            
            db.session.commit()
            
            # Clear session
            session.pop('pending_work_log', None)
            
            flash('Work log approved and created with overage!', 'success')
            return redirect(url_for('work_log'))
        
        elif action == 'edit':
            # Return to work log form with pre-filled data
            return redirect(url_for('work_log'))
        
        elif action == 'cancel':
            # Clear session and return to work log
            session.pop('pending_work_log', None)
            flash('Work log creation cancelled', 'info')
            return redirect(url_for('work_log'))
    
    # Get order and process details for display
    order = Order.query.get(pending_work_log['order_id'])
    process = Process.query.get(pending_work_log['process_id'])
    employee = Employee.query.get(pending_work_log['employee_id'])
    
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

@app.route('/work-logs/<int:work_log_id>/edit', methods=['GET', 'POST'])
def edit_work_log(work_log_id):
    """Edit work log with overage detection"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    work_log = WorkLog.query.get_or_404(work_log_id)
    
    if request.method == 'POST':
        print("POST request received to /work-logs/edit")
        print("Form data:", request.form)
        
        employee_id = int(request.form.get('employee_id'))
        order_id = int(request.form.get('order_id'))
        process_id = int(request.form.get('process_id'))
        quantity = int(request.form.get('quantity', 0))
        date_str = request.form.get('date')
        notes = request.form.get('notes')
        
        print(f"Parsed data: employee_id={employee_id}, order_id={order_id}, process_id={process_id}, quantity={quantity}, date={date_str}")
        
        if not all([employee_id, order_id, process_id, quantity, date_str]):
            print("Validation failed - missing required fields")
            flash('Please fill in all required fields', 'error')
        else:
            # Calculate current total excluding this work log
            current_total = db.session.query(func.sum(WorkLog.quantity)).filter(
                and_(
                    WorkLog.order_id == order_id,
                    WorkLog.process_id == process_id,
                    WorkLog.id != work_log_id
                )
            ).scalar() or 0
            
            new_total = current_total + quantity
            order = Order.query.get(order_id)
            
            # Check for overage
            if new_total > order.quantity:
                overage_units = new_total - order.quantity
                flash(f'Warning: This will create an overage of {overage_units} units. The work log will still be updated.', 'warning')
            
            work_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Update work log
            work_log.employee_id = employee_id
            work_log.order_id = order_id
            work_log.process_id = process_id
            work_log.quantity = quantity
            work_log.date = work_date
            work_log.notes = notes
            
            db.session.commit()
            print(f"Work log updated successfully: {work_log.id}")
            flash('Work log updated successfully!', 'success')
            return redirect(url_for('work_logs'))
    
    # Get data for dropdowns
    employees = Employee.query.filter_by(is_active=True).all()
    orders = Order.query.filter(Order.status.in_(['pending', 'in_progress'])).all()
    processes = Process.query.filter_by(is_active=True).all()
    
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
    
    print(f"Deleting work log {work_log_id}: {work_log.employee.name} - {work_log.order.order_no} - {work_log.process.name}")
    
    db.session.delete(work_log)
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
    """Delete employee"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Check if employee has work logs
        work_logs = WorkLog.query.filter_by(employee_id=employee_id).all()
        if work_logs:
            flash('Cannot delete employee with existing work logs. Please delete work logs first.', 'error')
            return redirect(url_for('employees'))
        
        # Check if employee has payments
        payments = Payment.query.filter_by(employee_id=employee_id).all()
        if payments:
            # Clean up payments first
            cleanup_payments_for_employee(employee_id)
        
        print(f"Deleting employee {employee_id}: {employee.name}")
        
        db.session.delete(employee)
        db.session.commit()
        
        flash('Employee deleted successfully!', 'success')
        return redirect(url_for('employees'))
        
    except Exception as e:
        print(f"Error deleting employee {employee_id}: {e}")
        db.session.rollback()
        flash('Error deleting employee. Please try again.', 'error')
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
        employee_id = int(request.form.get('employee_id'))
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        
        # Validate inputs
        if not all([employee_id, month, year]):
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

@app.route('/processes')
def processes():
    """View all processes"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    processes = Process.query.filter_by(is_active=True).all()
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
        pay_rate = float(request.form.get('pay_rate', 0))
        description = request.form.get('description')
        
        print(f"Parsed data: name={name}, pay_rate={pay_rate}, description={description}")
        
        if not all([name, pay_rate]):
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
        process.name = request.form.get('name')
        process.pay_rate = float(request.form.get('pay_rate', 0))
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
            backup_file = request.form.get('backup_file')
            if backup_file and os.path.exists(backup_file):
                try:
                    # Create a backup before restoring
                    create_backup()
                    
                    # Restore the selected backup
                    shutil.copy2(backup_file, 'instance/oleema.db')
                    flash('Database restored successfully!', 'success')
                except Exception as e:
                    flash(f'Restore failed: {str(e)}', 'error')
            else:
                flash('Invalid backup file selected', 'error')
    
    # Get backup information
    last_backup_time, last_backup_path = get_last_backup_info()
    
    # Get list of available backups
    available_backups = []
    if os.path.exists(BACKUP_DIR):
        for filename in os.listdir(BACKUP_DIR):
            if filename.startswith('oleema_backup_') and filename.endswith('.db'):
                file_path = os.path.join(BACKUP_DIR, filename)
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
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

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
