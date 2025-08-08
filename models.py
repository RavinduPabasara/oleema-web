from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Employee(db.Model):
    """Employee model"""
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    pay_rate = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    work_logs = db.relationship('WorkLog', backref='employee', lazy=True)
    
    def __repr__(self):
        return f'<Employee {self.name} ({self.employee_id})>'

class Process(db.Model):
    """Manufacturing process model"""
    __tablename__ = 'processes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pay_rate = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    work_logs = db.relationship('WorkLog', backref='process', lazy=True)
    
    def __repr__(self):
        return f'<Process {self.name}>'

class Order(db.Model):
    """Order model"""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False)
    color = db.Column(db.String(50), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, cancelled
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    work_logs = db.relationship('WorkLog', backref='order', lazy=True)
    
    def __repr__(self):
        return f'<Order {self.order_no}>'

class WorkLog(db.Model):
    """Work log model to track employee work on orders"""
    __tablename__ = 'work_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False)
    hours_worked = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<WorkLog {self.employee.name} - {self.order.order_no} - {self.process.name}>'

class Payment(db.Model):
    """Payment model for calculated payments"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_quantity = db.Column(db.Integer, default=0)
    total_hours = db.Column(db.Float, default=0.0)
    total_payment = db.Column(db.Float, default=0.0)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    employee = db.relationship('Employee', backref='payments')
    
    def __repr__(self):
        return f'<Payment {self.employee.name} - {self.month}/{self.year}>'

class OrderStatus(db.Model):
    """Order status tracking"""
    __tablename__ = 'order_statuses'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref='status_history')
    
    def __repr__(self):
        return f'<OrderStatus {self.order.order_no} - {self.status}>'

class Overage(db.Model):
    """Overage tracking model"""
    __tablename__ = 'overages'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    process_id = db.Column(db.Integer, db.ForeignKey('processes.id'), nullable=False)
    expected_units = db.Column(db.Integer, nullable=False)
    actual_units = db.Column(db.Integer, nullable=False)
    overage_units = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, resolved
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref='overages')
    process = db.relationship('Process', backref='overages')
    resolver = db.relationship('User', backref='resolved_overages')
    
    def __repr__(self):
        return f'<Overage {self.order.order_no} - {self.process.name} (+{self.overage_units})>'

class WorkLogOverage(db.Model):
    """Work log overage tracking - tracks which work logs contributed to overages"""
    __tablename__ = 'work_log_overages'
    
    id = db.Column(db.Integer, primary_key=True)
    overage_id = db.Column(db.Integer, db.ForeignKey('overages.id'), nullable=False)
    work_log_id = db.Column(db.Integer, db.ForeignKey('work_logs.id'), nullable=False)
    overage_units = db.Column(db.Integer, nullable=False)  # How many units from this work log contributed to overage
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    overage = db.relationship('Overage', backref='work_log_overages')
    work_log = db.relationship('WorkLog', backref='overage_contributions')
    
    def __repr__(self):
        return f'<WorkLogOverage {self.work_log.employee.name} - {self.overage_units} units>' 