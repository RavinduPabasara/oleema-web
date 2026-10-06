# desktop.py - Desktop launcher for Oleema
#
# Starts the Flask app on a private local port (127.0.0.1 only) and shows it in a native
# window via pywebview (Microsoft Edge WebView2 on Windows). Falls back to the default
# web browser if a native window can't be created.
#
#   python desktop.py               run the app
#   python desktop.py --smoke-test  exercise the main flows against a temporary database

import os
import sys
import socket
import tempfile
import threading
import time
import urllib.request
import webbrowser

APP_TITLE = 'Oleema - Production Management'


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_server(app, port):
    from waitress import serve
    thread = threading.Thread(
        target=serve, args=(app,),
        kwargs={'host': '127.0.0.1', 'port': port, 'threads': 8, '_quiet': True},
        daemon=True,
    )
    thread.start()
    url = f'http://127.0.0.1:{port}/'
    for _ in range(100):
        try:
            urllib.request.urlopen(url + 'login', timeout=1)
            return thread, url
        except Exception:
            time.sleep(0.1)
    raise RuntimeError('Server did not start')


def _show_window(url):
    """Show the app in a native window. Returns False if no native window is available."""
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.settings['ALLOW_DOWNLOADS'] = True  # PDF/CSV reports, archive export
    except Exception:
        pass
    try:
        webview.create_window(APP_TITLE, url, width=1366, height=860, min_size=(1000, 650))
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None)
        return True
    except Exception:
        return False


def _error_box(message):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)
    else:
        print(message, file=sys.stderr)


def run():
    from app import app, auto_backup_if_due
    auto_backup_if_due()
    server_thread, url = _start_server(app, _free_port())
    if not _show_window(url):
        # No WebView2/pywebview: use the browser and keep serving until the process is killed
        webbrowser.open(url)
        server_thread.join()


def smoke_test():
    """Exercise the app end to end against a throwaway database. Returns a process exit code."""
    os.environ['OLEEMA_DATA_DIR'] = tempfile.mkdtemp(prefix='oleema-smoke-')
    from app import app, db, BACKUP_DIR
    from models import Employee, Order, Process, WorkLog, Overage, Material

    failures = []

    def check(label, condition):
        print(('PASS ' if condition else 'FAIL ') + label)
        if not condition:
            failures.append(label)

    # Real HTTP server, as the desktop window uses it
    _, url = _start_server(app, _free_port())
    for path in ['login', 'static/css/main.css', 'static/js/main.js',
                 'static/vendor/fontawesome/css/all.min.css',
                 'static/vendor/fontawesome/webfonts/fa-solid-900.woff2',
                 'static/vendor/chartjs/chart.umd.min.js']:
        try:
            status = urllib.request.urlopen(url + path, timeout=5).status
        except Exception as e:
            status = repr(e)
        check(f'GET /{path} -> {status}', status == 200)

    c = app.test_client()
    r = c.post('/login', data={'username': 'admin', 'password': 'admin123'})
    check('admin login', r.status_code == 302 and '/dashboard' in r.headers.get('Location', ''))

    c.post('/employees/add', data={'employee_id': 'E1', 'name': 'Smoke Tester'})
    c.post('/new-order', data={'order_no': 'SMOKE-1', 'date': '2026-01-05', 'color': 'black', 'size': '34', 'quantity': '10'})
    c.post('/new-order', data={'order_no': 'SMOKE-2', 'date': '2026-01-05', 'color': 'white', 'size': '32', 'quantity': '5'})
    with app.app_context():
        emp = Employee.query.filter_by(employee_id='E1').first()
        o1 = Order.query.filter_by(order_no='SMOKE-1').first()
        o2 = Order.query.filter_by(order_no='SMOKE-2').first()
        processes = Process.query.filter_by(is_active=True).all()
        check('create employee and orders', emp is not None and o1 is not None and o2 is not None)
        emp_id, o1_id, o2_id, p_ids = emp.id, o1.id, o2.id, [p.id for p in processes]

    def log(order_id, process_id, qty):
        return c.post('/work-log', data={'employee_id': emp_id, 'order_id': order_id, 'process_id': process_id,
                                         'quantity': str(qty), 'date': '2026-01-06', 'notes': ''})

    r = log(o1_id, p_ids[0], 10)
    with app.app_context():
        check('first work log moves order to in_progress', db.session.get(Order, o1_id).status == 'in_progress')
    for pid in p_ids[1:]:
        log(o1_id, pid, 10)
    with app.app_context():
        check('order auto-completes when every process reaches quantity', db.session.get(Order, o1_id).status == 'completed')

    r = c.post('/work-log', data={'employee_id': '', 'order_id': o2_id, 'process_id': p_ids[0], 'quantity': '1', 'date': '2026-01-06'})
    check('missing employee shows an error instead of crashing', r.status_code == 200 and b'Employee is required' in r.data)

    r = log(o2_id, p_ids[0], 6)
    with app.app_context():
        check('overage asks for approval and saves nothing yet',
              '/approve-overage' in r.headers.get('Location', '') and Overage.query.count() == 0
              and WorkLog.query.filter_by(order_id=o2_id).count() == 0)
    check('approve page renders', c.get('/approve-overage').status_code == 200)
    c.post('/approve-overage', data={'action': 'cancel'})
    with app.app_context():
        check('cancelled overage leaves no record', Overage.query.count() == 0)

    log(o2_id, p_ids[0], 6)
    c.post('/approve-overage', data={'action': 'approve'})
    with app.app_context():
        wl = WorkLog.query.filter_by(order_id=o2_id).first()
        ov = Overage.query.filter_by(order_id=o2_id, status='pending').first()
        check('approved overage saves log and records 1 unit over', wl is not None and ov is not None and ov.overage_units == 1)
        wl_id, ov_id = (wl.id if wl else 0), (ov.id if ov else 0)

    for path in ['/dashboard', '/employees', '/employees/add', f'/employees/{emp_id}/edit', '/new-order', '/orders',
                 f'/orders/{o1_id}', f'/orders/{o2_id}', '/api/orders', '/overages', f'/overages/{ov_id}', '/work-log',
                 '/work-logs', f'/work-logs/{wl_id}/edit', '/payment-report', '/processes', '/processes/add',
                 f'/processes/{p_ids[0]}/edit', '/change-password', '/backup', '/settings', '/audit-logs', '/users',
                 '/users/add', '/users/1/edit', '/materials', '/materials/add']:
        r = c.get(path)
        check(f'GET {path} -> {r.status_code}', r.status_code == 200)

    c.post('/materials/add', data={'name': 'Elastic', 'unit': 'meters', 'cost_per_unit': '2.5', 'current_stock': '10', 'reorder_level': '2'})
    with app.app_context():
        mat = Material.query.first()
    check('add material', mat is not None)
    if mat:
        check('materials list and edit render', c.get('/materials').status_code == 200
              and c.get(f'/materials/{mat.id}/edit').status_code == 200)

    report = {'employee_id': emp_id, 'month': '1', 'year': '2026'}
    r = c.post('/payment-report', data=report)
    check('payment report', r.status_code == 200)
    r = c.post('/payment-report/pdf', data=report)
    check('payment report PDF', r.status_code == 200 and r.mimetype == 'application/pdf')
    r = c.post('/payment-report/csv', data=report)
    check('payment report CSV', r.status_code == 200 and r.mimetype == 'text/csv')

    c.post(f'/orders/{o2_id}/status', data={'status': 'cancelled'})
    with app.app_context():
        check('manual status change', db.session.get(Order, o2_id).status == 'cancelled')

    c.post(f'/work-logs/{wl_id}/delete')
    with app.app_context():
        check('deleting the over-limit log clears the pending overage',
              Overage.query.filter_by(order_id=o2_id, status='pending').count() == 0)

    c.post('/backup', data={'action': 'create_backup'})
    backups = sorted(os.listdir(BACKUP_DIR))
    check('create backup', len(backups) >= 1)
    if backups:
        r = c.post('/backup', data={'action': 'restore_backup', 'backup_file': backups[-1]}, follow_redirects=True)
        check('restore backup', b'restored successfully' in r.data)
        r = c.post('/backup', data={'action': 'restore_backup', 'backup_file': '../oleema.db'}, follow_redirects=True)
        check('restore rejects files outside the backup folder', b'Invalid backup file' in r.data)

    before = len(os.listdir(BACKUP_DIR))
    r = c.post('/work-logs/archive')
    with app.app_context():
        check('archive exports CSV, backs up first, clears logs',
              r.status_code == 200 and r.mimetype == 'text/csv' and WorkLog.query.count() == 0
              and len(os.listdir(BACKUP_DIR)) > before)

    print('SMOKE TEST ' + ('FAILED: ' + ', '.join(failures) if failures else 'PASSED'))
    return 1 if failures else 0


def main():
    if '--smoke-test' in sys.argv:
        # Windowed builds have no console; mirror output to a file CI can read
        log_path = os.environ.get('OLEEMA_SMOKE_LOG')
        if log_path:
            sys.stdout = sys.stderr = open(log_path, 'w', encoding='utf-8', buffering=1)
        code = smoke_test()
        sys.stdout.flush()
        os._exit(code)  # don't wait for the waitress thread
    try:
        run()
    except Exception as e:
        _error_box(f'{APP_TITLE} failed to start:\n\n{e}')
        raise


if __name__ == '__main__':
    main()
