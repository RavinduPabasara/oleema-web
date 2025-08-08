#!/usr/bin/env python3
"""
Fix overage database integrity issues
This script will clean up invalid overage records
"""

import os
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Overage, Order, Process

def fix_overages():
    """Fix overage database integrity issues"""
    with app.app_context():
        print("🔧 Fixing overage database integrity issues...")
        
        # Check for overages with NULL order_id
        null_order_overages = Overage.query.filter(Overage.order_id.is_(None)).all()
        print(f"Found {len(null_order_overages)} overages with NULL order_id")
        
        for overage in null_order_overages:
            print(f"  - Deleting overage ID {overage.id} (NULL order_id)")
            db.session.delete(overage)
        
        # Check for overages with NULL process_id
        null_process_overages = Overage.query.filter(Overage.process_id.is_(None)).all()
        print(f"Found {len(null_process_overages)} overages with NULL process_id")
        
        for overage in null_process_overages:
            print(f"  - Deleting overage ID {overage.id} (NULL process_id)")
            db.session.delete(overage)
        
        # Check for overages with invalid order_id (order doesn't exist)
        all_overages = Overage.query.all()
        invalid_order_overages = []
        
        for overage in all_overages:
            if overage.order_id:
                order = Order.query.get(overage.order_id)
                if not order:
                    invalid_order_overages.append(overage)
        
        print(f"Found {len(invalid_order_overages)} overages with invalid order_id")
        for overage in invalid_order_overages:
            print(f"  - Deleting overage ID {overage.id} (invalid order_id: {overage.order_id})")
            db.session.delete(overage)
        
        # Check for overages with invalid process_id (process doesn't exist)
        invalid_process_overages = []
        
        for overage in all_overages:
            if overage.process_id:
                process = Process.query.get(overage.process_id)
                if not process:
                    invalid_process_overages.append(overage)
        
        print(f"Found {len(invalid_process_overages)} overages with invalid process_id")
        for overage in invalid_process_overages:
            print(f"  - Deleting overage ID {overage.id} (invalid process_id: {overage.process_id})")
            db.session.delete(overage)
        
        # Commit all changes
        try:
            db.session.commit()
            print("✅ Successfully fixed overage database integrity issues!")
            
            # Show remaining overages
            remaining_overages = Overage.query.count()
            print(f"📊 Remaining valid overages: {remaining_overages}")
            
        except Exception as e:
            print(f"❌ Error fixing overages: {e}")
            db.session.rollback()
            return False
        
        return True

def show_overage_stats():
    """Show current overage statistics"""
    with app.app_context():
        print("\n📊 Current Overage Statistics:")
        print("=" * 40)
        
        total_overages = Overage.query.count()
        pending_overages = Overage.query.filter_by(status='pending').count()
        resolved_overages = Overage.query.filter_by(status='resolved').count()
        
        print(f"Total overages: {total_overages}")
        print(f"Pending overages: {pending_overages}")
        print(f"Resolved overages: {resolved_overages}")
        
        if total_overages > 0:
            print("\nRecent overages:")
            recent_overages = Overage.query.order_by(Overage.created_at.desc()).limit(5).all()
            for overage in recent_overages:
                order = Order.query.get(overage.order_id) if overage.order_id else None
                process = Process.query.get(overage.process_id) if overage.process_id else None
                
                order_name = order.order_no if order else "Unknown"
                process_name = process.name if process else "Unknown"
                
                print(f"  - ID {overage.id}: {order_name} / {process_name} (+{overage.overage_units}) - {overage.status}")

if __name__ == '__main__':
    print("Oleema Overage Database Fix")
    print("=" * 30)
    
    # Show current stats
    show_overage_stats()
    
    # Fix issues
    success = fix_overages()
    
    if success:
        print("\n✅ Database fix completed successfully!")
        show_overage_stats()
    else:
        print("\n❌ Database fix failed!")
        sys.exit(1) 