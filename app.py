from flask import Flask, render_template, request, redirect, url_for, flash, session
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

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
        
        print(f"Login attempt - Username: {username}, Password: {password}")  # Debug
        
        # Simple authentication (replace with proper auth later)
        if username == 'admin' and password == 'admin 123':
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            print("Login successful!")  # Debug
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')
            print("Login failed!")  # Debug
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    return render_template('pages/dashboard.html')

@app.route('/new-order', methods=['GET', 'POST'])
def new_order():
    """Add new order page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Handle form submission
        order_no = request.form.get('order_no')
        date = request.form.get('date')
        color = request.form.get('color')
        size = request.form.get('size')
        quantity = request.form.get('quantity')
        
        # Simple validation
        if not all([order_no, date, color, size, quantity]):
            flash('Please fill in all fields', 'error')
        else:
            # Here you would save to database
            flash('Order created successfully!', 'success')
            return redirect(url_for('dashboard'))
    
    return render_template('pages/new_order.html')

@app.route('/work-log', methods=['GET', 'POST'])
def work_log():
    """Add work log page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Handle form submission
        order_no = request.form.get('order_no')
        employee = request.form.get('employee')
        process = request.form.get('process')
        quantity = request.form.get('quantity')
        
        # Simple validation
        if not all([order_no, employee, process, quantity]):
            flash('Please fill in all fields', 'error')
        else:
            # Here you would save to database
            flash('Work log added successfully!', 'success')
            return redirect(url_for('work_log'))
    
    return render_template('pages/work_log.html')

@app.route('/payment-report', methods=['GET', 'POST'])
def payment_report():
    """Generate payment report page"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Handle form submission
        employee = request.form.get('employee')
        month = request.form.get('month')
        year = request.form.get('year')
        
        # Simple validation
        if not all([employee, month, year]):
            flash('Please fill in all fields', 'error')
        else:
            # Here you would:
            # 1. Fetch work logs for this employee in the selected month
            # 2. Calculate daily payments
            # 3. Generate report data
            flash('Report generated successfully!', 'success')
    
    return render_template('pages/payment_report.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
