from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Employee, Process, Order, WorkLog, Payment, OrderStatus
import os
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///oleema.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

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
    progress_percent = (total_processed / order.quantity * 100) if order.quantity > 0 else 0
    
    return render_template('pages/view_order.html', 
                         order=order, 
                         work_logs=work_logs,
                         total_processed=total_processed,
                         total_payment=total_payment,
                         progress_percent=progress_percent)

@app.route('/work-log', methods=['GET', 'POST'])
def work_log():
    """Add work log page"""
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
    
    return render_template('pages/work_log.html',
                         employees=employees,
                         orders=orders,
                         processes=processes,
                         recent_work_logs=recent_work_logs,
                         today=date.today().strftime('%Y-%m-%d'))

@app.route('/work-logs')
def work_logs():
    """View all work logs"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    work_logs = WorkLog.query.order_by(WorkLog.date.desc()).all()
    return render_template('pages/work_logs.html', work_logs=work_logs)

@app.route('/work-logs/<int:work_log_id>/edit', methods=['GET', 'POST'])
def edit_work_log(work_log_id):
    """Edit work log"""
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
    
    return render_template('pages/edit_work_log.html', 
                         work_log=work_log,
                         employees=employees,
                         orders=orders,
                         processes=processes)

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
    
    order = Order.query.get_or_404(order_id)
    
    # Check if order has work logs
    work_logs = WorkLog.query.filter_by(order_id=order_id).all()
    if work_logs:
        flash('Cannot delete order with existing work logs. Please delete work logs first.', 'error')
        return redirect(url_for('orders'))
    
    print(f"Deleting order {order_id}: {order.order_no}")
    
    db.session.delete(order)
    db.session.commit()
    
    flash('Order deleted successfully!', 'success')
    return redirect(url_for('orders'))

@app.route('/employees/<int:employee_id>/delete', methods=['POST'])
def delete_employee(employee_id):
    """Delete employee"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employee = Employee.query.get_or_404(employee_id)
    
    # Check if employee has work logs
    work_logs = WorkLog.query.filter_by(employee_id=employee_id).all()
    if work_logs:
        flash('Cannot delete employee with existing work logs. Please delete work logs first.', 'error')
        return redirect(url_for('employees'))
    
    print(f"Deleting employee {employee_id}: {employee.name}")
    
    db.session.delete(employee)
    db.session.commit()
    
    flash('Employee deleted successfully!', 'success')
    return redirect(url_for('employees'))

@app.route('/processes/<int:process_id>/delete', methods=['POST'])
def delete_process(process_id):
    """Delete process"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    process = Process.query.get_or_404(process_id)
    
    # Check if process has work logs
    work_logs = WorkLog.query.filter_by(process_id=process_id).all()
    if work_logs:
        flash('Cannot delete process with existing work logs. Please delete work logs first.', 'error')
        return redirect(url_for('processes'))
    
    print(f"Deleting process {process_id}: {process.name}")
    
    db.session.delete(process)
    db.session.commit()
    
    flash('Process deleted successfully!', 'success')
    return redirect(url_for('processes'))

@app.route('/payment-report', methods=['GET', 'POST'])
def payment_report():
    """Generate payment report page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    employees = Employee.query.filter_by(is_active=True).all()
    report_data = None
    
    if request.method == 'POST':
        print("POST request received to /payment-report")
        print("Form data:", request.form)
        
        employee_id = int(request.form.get('employee_id'))
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        
        print(f"Parsed data: employee_id={employee_id}, month={month}, year={year}")
        
        if not all([employee_id, month, year]):
            print("Validation failed - missing required fields")
            flash('Please fill in all fields', 'error')
        else:
            # Calculate payment report
            work_logs = WorkLog.query.filter(
                and_(
                    WorkLog.employee_id == employee_id,
                    func.extract('month', WorkLog.date) == month,
                    func.extract('year', WorkLog.date) == year
                )
            ).all()
            
            employee = Employee.query.get(employee_id)
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

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
