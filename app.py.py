import csv
import io
import os
import sqlite3
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date
from flask import Flask, render_template_string, request, jsonify, Response, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'attendease_secure_production_key_123'
DB_NAME = 'attendance.db'

# ==========================================
# 📧 SMTP EMAIL CONFIGURATION
# ==========================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")          
SMTP_PASSWORD = os.environ.get("SMTP_PASS", "")      
SENDER_EMAIL = SMTP_USER or "alerts@attendease.edu"

def send_warning_email_async(student_name, student_email, roll_number, course_name, course_code, percentage, present, total):
    def _send():
        subject = f"⚠️ Low Attendance Warning: {student_name} ({course_code} - {percentage}%)"
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <div style="max-width: 550px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background: #ef4444; color: white; padding: 20px; text-align: center;">
                    <h2 style="margin: 0;">Attendance Alert</h2>
                </div>
                <div style="padding: 24px;">
                    <p>Dear <strong>{student_name}</strong> (Roll No: <strong>{roll_number}</strong>),</p>
                    <p>Your attendance in <strong>{course_name} ({course_code})</strong> has dropped below the mandatory <strong>75% threshold</strong>.</p>
                    <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
                        <p style="margin: 0; font-size: 16px; color: #991b1b;"><strong>Subject Attendance: {percentage}%</strong></p>
                        <p style="margin: 4px 0 0 0; font-size: 13px; color: #7f1d1d;">Classes Attended: {present} / {total}</p>
                    </div>
                    <p>Please meet your subject instructor immediately to address this shortage.</p>
                </div>
            </div>
        </body>
        </html>
        """
        if not SMTP_USER or not SMTP_PASSWORD:
            print(f"\n[EMAIL SIMULATION] Low Attendance -> {student_name} ({student_email}) | {course_code}: {percentage}% ({present}/{total})")
            return

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"AttendEase Academic System <{SENDER_EMAIL}>"
            msg["To"] = student_email
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SENDER_EMAIL, student_email, msg.as_string())
            print(f"[EMAIL SENT] Successfully dispatched course alert to {student_email}")
        except Exception as e:
            print(f"[EMAIL ERROR] Failed sending to {student_email}: {e}")

    threading.Thread(target=_send, daemon=True).start()

# ==========================================
# 🗄️ DATABASE INITIALIZATION
# ==========================================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # 1. Faculty / Admin Users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS faculty_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'faculty'
            )
        ''')

        # 2. Courses / Subjects Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_name TEXT NOT NULL,
                course_code TEXT UNIQUE NOT NULL,
                department TEXT DEFAULT 'Computer Science'
            )
        ''')

        # 3. Students Directory
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                roll_number TEXT UNIQUE NOT NULL,
                department TEXT DEFAULT 'Computer Science',
                email TEXT NOT NULL
            )
        ''')

        # 4. Attendance Records linked to Course & Student
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students (id),
                FOREIGN KEY (course_id) REFERENCES courses (id)
            )
        ''')

        # Seed Faculty
        cursor.execute('SELECT COUNT(*) FROM faculty_users')
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                'INSERT INTO faculty_users (username, password_hash, name, role) VALUES (?, ?, ?, ?)',
                [
                    ('admin', generate_password_hash('admin123'), 'System Administrator', 'admin'),
                    ('faculty', generate_password_hash('admin123'), 'Dr. Robert Smith', 'faculty')
                ]
            )

        # Seed Courses
        cursor.execute('SELECT COUNT(*) FROM courses')
        if cursor.fetchone()[0] == 0:
            demo_courses = [
                ('Data Structures & Algorithms', 'CS101', 'Computer Science'),
                ('Database Management Systems', 'CS102', 'Computer Science'),
                ('Computer Networks', 'CS103', 'Computer Science'),
                ('Operating Systems', 'CS104', 'Computer Science')
            ]
            cursor.executemany(
                'INSERT INTO courses (course_name, course_code, department) VALUES (?, ?, ?)',
                demo_courses
            )

        # Seed Students
        cursor.execute('SELECT COUNT(*) FROM students')
        if cursor.fetchone()[0] == 0:
            demo_students = [
                ('Aarav Sharma', 'STU001', 'Computer Science', 'aarav.sharma@example.com'),
                ('Ananya Verma', 'STU002', 'Information Tech', 'ananya.verma@example.com'),
                ('Rohan Patel', 'STU003', 'Computer Science', 'rohan.patel@example.com'),
                ('Sneha Iyer', 'STU004', 'Electronics', 'sneha.iyer@example.com'),
                ('Vikram Malhotra', 'STU005', 'Data Science', 'vikram.malhotra@example.com'),
                ('Priya Nair', 'STU006', 'Information Tech', 'priya.nair@example.com')
            ]
            cursor.executemany(
                'INSERT INTO students (name, roll_number, department, email) VALUES (?, ?, ?, ?)',
                demo_students
            )
            conn.commit()

# ==========================================
# 🌐 AUTH & NAVIGATION APIS
# ==========================================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    role = data.get('role')
    
    if role == 'faculty':
        username = data.get('username', '').strip().lower()
        password = data.get('password', '').strip()
        
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute('SELECT * FROM faculty_users WHERE LOWER(username) = ?', (username,)).fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                session['user'] = {'role': user['role'], 'name': user['name'], 'id': user['id']}
                return jsonify({'success': True, 'role': user['role'], 'name': user['name']})
                
        return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
        
    elif role == 'student':
        roll = data.get('roll_number', '').strip().upper()
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            student = conn.execute('SELECT * FROM students WHERE roll_number = ?', (roll,)).fetchone()
            if student:
                session['user'] = {'role': 'student', 'roll_number': roll, 'name': student['name']}
                return jsonify({'success': True, 'role': 'student', 'roll_number': roll, 'name': student['name']})
            return jsonify({'success': False, 'message': 'Roll Number not found in directory'}), 404
            
    return jsonify({'success': False, 'message': 'Invalid login request'}), 400

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# ==========================================
# 📚 COURSE MANAGEMENT APIS
# ==========================================
@app.route('/api/courses', methods=['GET'])
def get_courses():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        courses = conn.execute('SELECT * FROM courses ORDER BY course_code ASC').fetchall()
        return jsonify([dict(c) for c in courses])

@app.route('/api/register/course', methods=['POST'])
def register_course():
    data = request.json or {}
    course_name = data.get('course_name', '').strip()
    course_code = data.get('course_code', '').strip().upper()
    department = data.get('department', 'Computer Science').strip()

    if not course_name or not course_code:
        return jsonify({'success': False, 'message': 'Course Name and Code are required.'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO courses (course_name, course_code, department) VALUES (?, ?, ?)',
                (course_name, course_code, department)
            )
            conn.commit()
        return jsonify({'success': True, 'message': f'Course {course_code} ({course_name}) created successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': f'Course Code "{course_code}" already exists.'}), 409

@app.route('/api/admin/course/<int:course_id>', methods=['PUT'])
def update_course(course_id):
    data = request.json or {}
    course_name = data.get('course_name', '').strip()
    course_code = data.get('course_code', '').strip().upper()
    department = data.get('department', '').strip()

    if not course_name or not course_code:
        return jsonify({'success': False, 'message': 'Course Name and Code are required.'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE courses 
                SET course_name = ?, course_code = ?, department = ? 
                WHERE id = ?
            ''', (course_name, course_code, department, course_id))
            conn.commit()
        return jsonify({'success': True, 'message': f'Course "{course_code}" updated successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': f'Course Code "{course_code}" is already in use.'}), 409

@app.route('/api/admin/course/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM attendance WHERE course_id = ?', (course_id,))
        cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        conn.commit()
    return jsonify({'success': True, 'message': 'Course and all linked attendance logs deleted.'})

# ==========================================
# 🛠️ ADMIN STAFF & STUDENT CRUD
# ==========================================
@app.route('/api/admin/faculty', methods=['GET'])
def get_all_faculty():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        users = conn.execute('SELECT id, username, name, role FROM faculty_users ORDER BY id ASC').fetchall()
        return jsonify([dict(u) for u in users])

@app.route('/api/register/faculty', methods=['POST'])
def register_faculty():
    data = request.json or {}
    name = data.get('name', '').strip()
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    role = data.get('role', 'faculty').strip().lower()

    if not all([name, username, password]):
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    hashed_pw = generate_password_hash(password)
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO faculty_users (name, username, password_hash, role) VALUES (?, ?, ?, ?)',
                (name, username, hashed_pw, role)
            )
            conn.commit()
        return jsonify({'success': True, 'message': f'Staff account "{username}" created successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': f'Username "{username}" is already taken.'}), 409

@app.route('/api/admin/faculty/<int:user_id>', methods=['PUT'])
def update_faculty(user_id):
    data = request.json or {}
    name = data.get('name', '').strip()
    username = data.get('username', '').strip().lower()
    role = data.get('role', 'faculty').strip().lower()
    password = data.get('password', '').strip()

    if not name or not username:
        return jsonify({'success': False, 'message': 'Name and Username are required.'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            if password:
                hashed_pw = generate_password_hash(password)
                cursor.execute(
                    'UPDATE faculty_users SET name = ?, username = ?, role = ?, password_hash = ? WHERE id = ?',
                    (name, username, role, hashed_pw, user_id)
                )
            else:
                cursor.execute(
                    'UPDATE faculty_users SET name = ?, username = ?, role = ? WHERE id = ?',
                    (name, username, role, user_id)
                )
            conn.commit()
        return jsonify({'success': True, 'message': f'Faculty account "{username}" updated successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Username is already taken.'}), 409

@app.route('/api/admin/faculty/<int:user_id>', methods=['DELETE'])
def delete_faculty(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM faculty_users WHERE id = ?', (user_id,))
        conn.commit()
    return jsonify({'success': True, 'message': 'Staff account removed successfully.'})

@app.route('/api/students', methods=['GET'])
def get_students():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        students = conn.execute('SELECT * FROM students ORDER BY roll_number ASC').fetchall()
        return jsonify([dict(row) for row in students])

@app.route('/api/register/student', methods=['POST'])
def register_student():
    data = request.json or {}
    name = data.get('name', '').strip()
    roll_number = data.get('roll_number', '').strip().upper()
    department = data.get('department', 'Computer Science').strip()
    email = data.get('email', '').strip().lower()

    if not all([name, roll_number, email]):
        return jsonify({'success': False, 'message': 'Name, Roll Number, and Email are required.'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO students (name, roll_number, department, email) VALUES (?, ?, ?, ?)',
                (name, roll_number, department, email)
            )
            conn.commit()
        return jsonify({'success': True, 'message': f'Student {name} ({roll_number}) enrolled successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': f'Roll number "{roll_number}" is already registered.'}), 409

@app.route('/api/admin/student/<int:student_id>', methods=['PUT'])
def update_student(student_id):
    data = request.json or {}
    name = data.get('name', '').strip()
    roll_number = data.get('roll_number', '').strip().upper()
    department = data.get('department', '').strip()
    email = data.get('email', '').strip().lower()

    if not all([name, roll_number, email]):
        return jsonify({'success': False, 'message': 'Name, Roll Number, and Email are required.'}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE students 
                SET name = ?, roll_number = ?, department = ?, email = ?
                WHERE id = ?
            ''', (name, roll_number, department, email, student_id))
            conn.commit()
        return jsonify({'success': True, 'message': f'Student record for "{name}" updated successfully!'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Roll Number is already registered for another student.'}), 409

@app.route('/api/admin/student/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM attendance WHERE student_id = ?', (student_id,))
        cursor.execute('DELETE FROM students WHERE id = ?', (student_id,))
        conn.commit()
    return jsonify({'success': True, 'message': 'Student and all associated attendance logs deleted.'})

# ==========================================
# 📊 COURSE-WISE ATTENDANCE & STATS
# ==========================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    today = date.today().strftime('%Y-%m-%d')
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        total_students = conn.execute('SELECT COUNT(*) as count FROM students').fetchone()['count']
        total_courses = conn.execute('SELECT COUNT(*) as count FROM courses').fetchone()['count']
        today_present = conn.execute('SELECT COUNT(*) as count FROM attendance WHERE date = ? AND status = "Present"', (today,)).fetchone()['count']
        today_absent = conn.execute('SELECT COUNT(*) as count FROM attendance WHERE date = ? AND status = "Absent"', (today,)).fetchone()['count']
        
        return jsonify({
            'total_students': total_students,
            'total_courses': total_courses,
            'today_present': today_present,
            'today_absent': today_absent
        })

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    payload = request.json or {}
    record_date = payload.get('attendance_date') or date.today().strftime('%Y-%m-%d')
    course_id = payload.get('course_id')
    records = payload.get('records', {})
    warned_students = []

    if not course_id:
        return jsonify({'error': 'Course selection is required'}), 400

    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
        if not course:
            return jsonify({'error': 'Invalid course selected'}), 400

        # 1. Insert logs
        for student_id, status in records.items():
            cursor.execute(
                'INSERT INTO attendance (student_id, course_id, date, status) VALUES (?, ?, ?, ?)',
                (student_id, course_id, record_date, status)
            )
        conn.commit()

        # 2. Check course-specific attendance threshold
        for student_id in records.keys():
            student = conn.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
            if not student:
                continue

            stats = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) as present
                FROM attendance
                WHERE student_id = ? AND course_id = ?
            ''', (student_id, course_id)).fetchone()

            total = stats['total']
            present = stats['present'] or 0
            percentage = round((present / total * 100), 1) if total > 0 else 100.0

            if percentage < 75.0:
                warned_students.append(f"{student['name']} ({percentage}%)")
                send_warning_email_async(
                    student_name=student['name'],
                    student_email=student['email'],
                    roll_number=student['roll_number'],
                    course_name=course['course_name'],
                    course_code=course['course_code'],
                    percentage=percentage,
                    present=present,
                    total=total
                )

    msg = f"Attendance logged for {course['course_code']} on {record_date}."
    if warned_students:
        msg += f" ⚠️ {len(warned_students)} low attendance warning(s) triggered (<75%)."

    return jsonify({'message': msg, 'warned_students': warned_students})

@app.route('/api/student/<roll_number>', methods=['GET'])
def get_student_report(roll_number):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        student = conn.execute('SELECT * FROM students WHERE roll_number = ?', (roll_number.strip().upper(),)).fetchone()
        if not student:
            return jsonify({'error': 'Student roll number not found'}), 404
        
        # Course-wise breakdown
        course_stats = conn.execute('''
            SELECT 
                c.id as course_id,
                c.course_name,
                c.course_code,
                COUNT(a.id) as total_classes,
                SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) as present_classes,
                SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) as absent_classes
            FROM courses c
            LEFT JOIN attendance a ON c.id = a.course_id AND a.student_id = ?
            GROUP BY c.id
        ''', (student['id'],)).fetchall()

        course_breakdown = []
        overall_total = 0
        overall_present = 0

        for row in course_stats:
            total = row['total_classes'] or 0
            present = row['present_classes'] or 0
            absent = row['absent_classes'] or 0
            pct = round((present / total * 100), 1) if total > 0 else 0.0
            
            overall_total += total
            overall_present += present

            course_breakdown.append({
                'course_id': row['course_id'],
                'course_name': row['course_name'],
                'course_code': row['course_code'],
                'total_classes': total,
                'present_classes': present,
                'absent_classes': absent,
                'percentage': pct
            })

        overall_percentage = round((overall_present / overall_total * 100), 1) if overall_total > 0 else 0.0

        # Detailed history logs with course name
        history = conn.execute('''
            SELECT a.date, a.status, c.course_name, c.course_code 
            FROM attendance a
            JOIN courses c ON a.course_id = c.id
            WHERE a.student_id = ?
            ORDER BY a.date DESC, a.id DESC
        ''', (student['id'],)).fetchall()

        return jsonify({
            'name': student['name'],
            'roll_number': student['roll_number'],
            'department': student['department'],
            'email': student['email'],
            'overall_total': overall_total,
            'overall_present': overall_present,
            'overall_absent': overall_total - overall_present,
            'overall_percentage': overall_percentage,
            'course_breakdown': course_breakdown,
            'history': [dict(r) for r in history]
        })

@app.route('/api/export', methods=['GET'])
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll Number', 'Student Name', 'Department', 'Email', 'Course Code', 'Course Name', 'Date', 'Status'])

    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT s.roll_number, s.name, s.department, s.email, c.course_code, c.course_name, a.date, a.status 
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            JOIN courses c ON a.course_id = c.id
            ORDER BY a.date DESC, s.roll_number ASC
        ''').fetchall()
        for row in rows:
            writer.writerow([row['roll_number'], row['name'], row['department'], row['email'], row['course_code'], row['course_name'], row['date'], row['status']])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=course_attendance_report.csv"}
    )

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AttendEase Pro - Course & Subject Attendance</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #4f46e5;
            --primary-hover: #4338ca;
            --bg: #f8fafc;
            --surface: #ffffff;
            --border: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --radius: 16px;
            --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Plus Jakarta Sans', sans-serif; }
        body { background: var(--bg); color: var(--text-main); min-height: 100vh; padding: 30px 20px; }
        .wrapper { max-width: 1100px; margin: 0 auto; }

        /* Login Modal Overlay */
        .login-overlay {
            position: fixed; inset: 0; background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(8px);
            display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 20px;
        }
        .login-box {
            background: var(--surface); border-radius: 20px; padding: 36px; max-width: 440px; width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); text-align: center;
        }
        .login-role-tabs { display: flex; background: #f1f5f9; padding: 4px; border-radius: 12px; margin: 20px 0; }
        .login-role-btn { flex: 1; padding: 10px; border: none; background: transparent; border-radius: 8px; font-weight: 600; cursor: pointer; color: var(--text-muted); font-size: 13px; }
        .login-role-btn.active { background: white; color: var(--primary); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
        .input-group { margin-bottom: 15px; text-align: left; }
        .input-group label { font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 6px; display: block; }
        .input-group input, .input-group select { width: 100%; padding: 11px 14px; border: 1px solid var(--border); border-radius: 10px; font-size: 14px; outline: none; background: #fff; }
        
        /* App Header */
        .app-header {
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            padding: 24px 30px; border-radius: var(--radius); color: white;
            box-shadow: 0 15px 30px -5px rgba(79, 70, 229, 0.3);
        }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin-bottom: 25px; }
        .stat-card { background: var(--surface); padding: 20px; border-radius: var(--radius); border: 1px solid var(--border); display: flex; align-items: center; gap: 16px; }
        .stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
        .icon-blue { background: #e0e7ff; color: var(--primary); }
        .icon-green { background: #d1fae5; color: var(--success); }
        .icon-red { background: #fee2e2; color: var(--danger); }
        .icon-purple { background: #f3e8ff; color: #9333ea; }
        
        .nav-tabs { display: flex; gap: 10px; background: var(--surface); padding: 8px; border-radius: var(--radius); border: 1px solid var(--border); margin-bottom: 25px; }
        .nav-btn { flex: 1; padding: 12px 18px; border: none; background: transparent; font-weight: 600; font-size: 14px; color: var(--text-muted); border-radius: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .nav-btn.active { background: var(--primary); color: white; }
        
        .main-card { background: var(--surface); border-radius: var(--radius); border: 1px solid var(--border); padding: 30px; box-shadow: var(--shadow); }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }
        
        .admin-forms-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 35px; }
        .form-card { background: #f8fafc; border: 1px solid var(--border); border-radius: 14px; padding: 22px; }
        .form-card h3 { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }

        .tools-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; margin-bottom: 20px; }
        .search-box { position: relative; flex: 1; min-width: 200px; }
        .search-box i { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }
        .search-box input { width: 100%; padding: 10px 14px 10px 38px; border-radius: 10px; border: 1px solid var(--border); }
        .date-input, .select-input { padding: 9px 14px; border-radius: 10px; border: 1px solid var(--border); background: white; font-size: 14px; outline: none; }
        .quick-btn { padding: 7px 12px; font-size: 12px; font-weight: 600; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); cursor: pointer; }
        
        table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 10px; }
        th { background: #f8fafc; color: var(--text-muted); font-size: 12px; text-transform: uppercase; padding: 14px 16px; border-bottom: 1px solid var(--border); text-align: left; }
        td { padding: 14px 16px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; font-size: 14px; }
        
        .status-toggle { display: inline-flex; background: #f1f5f9; padding: 4px; border-radius: 10px; }
        .status-toggle label { padding: 6px 14px; font-size: 12px; font-weight: 600; border-radius: 8px; cursor: pointer; margin: 0; }
        .status-toggle input { display: none; }
        .status-toggle input[value="Present"]:checked + label { background: var(--success); color: white; }
        .status-toggle input[value="Absent"]:checked + label { background: var(--danger); color: white; }
        
        .btn-primary { width: 100%; background: var(--primary); color: white; border: none; padding: 12px 24px; border-radius: 10px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-primary:hover { background: var(--primary-hover); }

        .btn-action { padding: 6px 10px; border-radius: 8px; border: 1px solid transparent; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-edit { background: #e0e7ff; color: var(--primary); }
        .btn-edit:hover { background: #c7d2fe; }
        .btn-delete { background: #fee2e2; color: var(--danger); margin-left: 6px; }
        .btn-delete:hover { background: #fecaca; }

        .modal {
            position: fixed; inset: 0; background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(4px);
            display: none; align-items: center; justify-content: center; z-index: 10001; padding: 20px;
        }
        .modal-content {
            background: var(--surface); border-radius: 18px; padding: 28px; max-width: 460px; width: 100%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
        }
        
        .analytics-container { display: grid; grid-template-columns: 320px 1fr; gap: 30px; margin-top: 20px; }
        .chart-box { background: #f8fafc; border-radius: var(--radius); padding: 24px; text-align: center; border: 1px solid var(--border); }
        .progress-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 18px; margin-top: 15px; }
        .badge-safe { background: #d1fae5; color: #065f46; }
        .badge-warning { background: #fee2e2; color: #991b1b; }
        
        #toast { position: fixed; bottom: 25px; right: 25px; background: #1e293b; color: white; padding: 14px 22px; border-radius: 12px; font-size: 14px; font-weight: 500; display: none; align-items: center; gap: 10px; z-index: 10000; }

        @media (max-width: 768px) {
            .analytics-container { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

<!-- Login Modal Overlay -->
<div id="loginOverlay" class="login-overlay">
    <div class="login-box">
        <div style="font-size: 40px; color: var(--primary); margin-bottom: 8px;"><i class="fa-solid fa-graduation-cap"></i></div>
        <h2 style="font-weight: 800; font-size: 22px;">AttendEase Pro</h2>
        <p style="color: var(--text-muted); font-size: 13px;">Course & Attendance Portal</p>

        <div class="login-role-tabs">
            <button class="login-role-btn active" id="btnRoleFaculty" onclick="switchLoginRole('faculty')">Faculty / Admin</button>
            <button class="login-role-btn" id="btnRoleStudent" onclick="switchLoginRole('student')">Student Portal</button>
        </div>

        <form id="formFacultyLogin" onsubmit="handleFacultyLogin(event)">
            <div class="input-group">
                <label>Username</label>
                <input type="text" id="facUser" placeholder="e.g. admin or faculty" value="admin" required>
            </div>
            <div class="input-group">
                <label>Password</label>
                <input type="password" id="facPass" placeholder="e.g. admin123" value="admin123" required>
            </div>
            <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 15px;">Admin: <strong>admin</strong> | Faculty: <strong>faculty</strong> (PW: <strong>admin123</strong>)</p>
            <button type="submit" class="btn-primary"><i class="fa-solid fa-lock"></i> Secure Login</button>
        </form>

        <form id="formStudentLogin" onsubmit="handleStudentLogin(event)" style="display: none;">
            <div class="input-group">
                <label>Student Roll Number</label>
                <input type="text" id="stuRollInput" placeholder="e.g. STU001" value="STU001" required>
            </div>
            <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 15px;">Try: <strong>STU001</strong>, <strong>STU002</strong>, or <strong>STU003</strong></p>
            <button type="submit" class="btn-primary"><i class="fa-solid fa-user"></i> Access Subject Records</button>
        </form>
    </div>
</div>

<!-- Main Application Wrapper -->
<div class="wrapper" id="mainApp" style="filter: blur(4px); pointer-events: none;">
    <div class="app-header">
        <div>
            <h1><i class="fa-solid fa-graduation-cap"></i> AttendEase Pro</h1>
            <p id="userGreeting">Logged in as: User</p>
        </div>
        <div style="display: flex; align-items: center; gap: 15px;">
            <div id="liveClock" style="font-weight: 600; font-size: 14px; opacity: 0.9;"></div>
            <button onclick="logout()" style="background: rgba(255,255,255,0.2); border: none; color: white; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 13px;"><i class="fa-solid fa-arrow-right-from-bracket"></i> Logout</button>
        </div>
    </div>

    <div class="stats-grid" id="facultyStatsRow">
        <div class="stat-card"><div class="stat-icon icon-blue"><i class="fa-solid fa-users"></i></div><div><div style="font-size: 12px; color: var(--text-muted);">TOTAL STUDENTS</div><p id="kpiTotal" style="font-size: 24px; font-weight: 800;">0</p></div></div>
        <div class="stat-card"><div class="stat-icon icon-purple"><i class="fa-solid fa-book-open"></i></div><div><div style="font-size: 12px; color: var(--text-muted);">ACTIVE COURSES</div><p id="kpiCourses" style="font-size: 24px; font-weight: 800;">0</p></div></div>
        <div class="stat-card"><div class="stat-icon icon-green"><i class="fa-solid fa-user-check"></i></div><div><div style="font-size: 12px; color: var(--text-muted);">TODAY'S PRESENT</div><p id="kpiPresent" style="font-size: 24px; font-weight: 800;">0</p></div></div>
        <div class="stat-card"><div class="stat-icon icon-red"><i class="fa-solid fa-user-xmark"></i></div><div><div style="font-size: 12px; color: var(--text-muted);">TODAY'S ABSENT</div><p id="kpiAbsent" style="font-size: 24px; font-weight: 800;">0</p></div></div>
    </div>

    <div class="nav-tabs" id="navTabsContainer">
        <button class="nav-btn active" id="tabFacBtn" onclick="switchTab('faculty')"><i class="fa-solid fa-clipboard-user"></i> Course Attendance</button>
        <button class="nav-btn" id="tabAdminBtn" onclick="switchTab('admin')" style="display: none;"><i class="fa-solid fa-user-gear"></i> Admin Management</button>
        <button class="nav-btn" id="tabStuBtn" onclick="switchTab('student')"><i class="fa-solid fa-chart-pie"></i> Student Portal</button>
        <button class="nav-btn" id="tabRepBtn" onclick="switchTab('reports')"><i class="fa-solid fa-file-arrow-down"></i> Export Reports</button>
    </div>

    <div class="main-card">
        <!-- Faculty View -->
        <div id="faculty" class="tab-panel active">
            <div class="tools-row">
                <div>
                    <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); display: block; margin-bottom: 4px;">SELECT COURSE / SUBJECT</label>
                    <select id="facultyCourseSelect" class="select-input" style="font-weight: 600;"></select>
                </div>
                <div>
                    <label style="font-size: 11px; font-weight: 700; color: var(--text-muted); display: block; margin-bottom: 4px;">ATTENDANCE DATE</label>
                    <input type="date" id="attendanceDate" class="date-input">
                </div>
                <div class="search-box" style="margin-top: 15px;">
                    <i class="fa-solid fa-magnifying-glass"></i>
                    <input type="text" id="searchInput" placeholder="Search student name or roll..." onkeyup="filterRoster()">
                </div>
                <div style="display: flex; gap: 8px; margin-top: 15px;">
                    <button class="quick-btn" onclick="setAllAttendance('Present')"><i class="fa-solid fa-check-double" style="color: var(--success);"></i> All Present</button>
                    <button class="quick-btn" onclick="setAllAttendance('Absent')"><i class="fa-solid fa-xmark" style="color: var(--danger);"></i> All Absent</button>
                </div>
            </div>

            <form id="attendanceForm">
                <table>
                    <thead>
                        <tr><th>Student Details</th><th>Department</th><th style="text-align: right;">Status Toggle</th></tr>
                    </thead>
                    <tbody id="rosterList"><tr><td colspan="3">Loading roster...</td></tr></tbody>
                </table>
                <div style="margin-top: 25px; text-align: right;">
                    <button type="submit" class="btn-primary" style="width: auto;"><i class="fa-solid fa-paper-plane"></i> Submit Course Attendance & Trigger Alerts</button>
                </div>
            </form>
        </div>

        <!-- Admin Only Management Tab -->
        <div id="admin" class="tab-panel">
            <div style="margin-bottom: 25px;">
                <h2 style="font-weight: 800; font-size: 20px;"><i class="fa-solid fa-users-gear" style="color: var(--primary);"></i> Academic Directory Management</h2>
                <p style="color: var(--text-muted); font-size: 13px;">Manage subjects, faculty credentials, and student enrollments.</p>
            </div>

            <div class="admin-forms-grid">
                <!-- Course Creation -->
                <div class="form-card">
                    <h3><i class="fa-solid fa-book" style="color: var(--primary);"></i> Add Course / Subject</h3>
                    <form onsubmit="handleRegisterCourse(event)">
                        <div class="input-group">
                            <label>Course Name</label>
                            <input type="text" id="regCourseName" placeholder="e.g. Algorithms" required>
                        </div>
                        <div class="input-group">
                            <label>Course Code</label>
                            <input type="text" id="regCourseCode" placeholder="e.g. CS201" required>
                        </div>
                        <div class="input-group">
                            <label>Department</label>
                            <input type="text" id="regCourseDept" value="Computer Science" required>
                        </div>
                        <button type="submit" class="btn-primary"><i class="fa-solid fa-plus"></i> Create Course</button>
                    </form>
                </div>

                <!-- Staff Creation -->
                <div class="form-card">
                    <h3><i class="fa-solid fa-user-shield" style="color: var(--primary);"></i> Register Staff</h3>
                    <form onsubmit="handleRegisterFaculty(event)">
                        <div class="input-group">
                            <label>Full Name</label>
                            <input type="text" id="regFacName" placeholder="e.g. Dr. Jane Doe" required>
                        </div>
                        <div class="input-group">
                            <label>Username</label>
                            <input type="text" id="regFacUser" placeholder="e.g. janedoe" required>
                        </div>
                        <div class="input-group">
                            <label>Password</label>
                            <input type="password" id="regFacPass" placeholder="Set password" required>
                        </div>
                        <div class="input-group">
                            <label>Role</label>
                            <select id="regFacRole">
                                <option value="faculty">Faculty</option>
                                <option value="admin">Administrator</option>
                            </select>
                        </div>
                        <button type="submit" class="btn-primary"><i class="fa-solid fa-user-plus"></i> Create Account</button>
                    </form>
                </div>

                <!-- Student Creation -->
                <div class="form-card">
                    <h3><i class="fa-solid fa-user-graduate" style="color: var(--success);"></i> Enroll Student</h3>
                    <form onsubmit="handleRegisterStudent(event)">
                        <div class="input-group">
                            <label>Full Name</label>
                            <input type="text" id="regStuName" placeholder="e.g. Kevin Vance" required>
                        </div>
                        <div class="input-group">
                            <label>Roll Number</label>
                            <input type="text" id="regStuRoll" placeholder="e.g. STU007" required>
                        </div>
                        <div class="input-group">
                            <label>Department</label>
                            <input type="text" id="regStuDept" value="Computer Science" required>
                        </div>
                        <div class="input-group">
                            <label>Email Address</label>
                            <input type="email" id="regStuEmail" placeholder="student@example.com" required>
                        </div>
                        <button type="submit" class="btn-primary" style="background: var(--success);"><i class="fa-solid fa-plus"></i> Enroll Student</button>
                    </form>
                </div>
            </div>

            <!-- Courses Directory -->
            <div style="margin-bottom: 35px;">
                <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;"><i class="fa-solid fa-book-bookmark" style="color: var(--primary);"></i> Active Courses & Subjects</h3>
                <div style="border: 1px solid var(--border); border-radius: 12px; overflow: hidden;">
                    <table>
                        <thead>
                            <tr><th>Code</th><th>Course Name</th><th>Department</th><th style="text-align: right;">Actions</th></tr>
                        </thead>
                        <tbody id="adminCourseList"></tbody>
                    </table>
                </div>
            </div>

            <!-- Staff Directory -->
            <div style="margin-bottom: 35px;">
                <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;"><i class="fa-solid fa-user-tie" style="color: var(--primary);"></i> Existing Staff Accounts</h3>
                <div style="border: 1px solid var(--border); border-radius: 12px; overflow: hidden;">
                    <table>
                        <thead>
                            <tr><th>Name</th><th>Username</th><th>Role</th><th style="text-align: right;">Actions</th></tr>
                        </thead>
                        <tbody id="adminFacultyList"></tbody>
                    </table>
                </div>
            </div>

            <!-- Student Directory -->
            <div>
                <h3 style="font-size: 16px; font-weight: 700; margin-bottom: 12px;"><i class="fa-solid fa-graduation-cap" style="color: var(--success);"></i> Registered Students</h3>
                <div style="border: 1px solid var(--border); border-radius: 12px; overflow: hidden;">
                    <table>
                        <thead>
                            <tr><th>Student Details</th><th>Department</th><th>Email</th><th style="text-align: right;">Actions</th></tr>
                        </thead>
                        <tbody id="adminStudentList"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Student Portal -->
        <div id="student" class="tab-panel">
            <div id="studentSearchBar" style="max-width: 500px; margin: 0 auto 30px auto; display: flex; gap: 10px;">
                <input type="text" id="studentSearchRoll" placeholder="Enter Roll Number (e.g. STU001)" class="date-input" style="flex: 1;">
                <button class="btn-primary" onclick="lookupStudent(document.getElementById('studentSearchRoll').value)" style="width: auto;"><i class="fa-solid fa-magnifying-glass"></i> Search</button>
            </div>

            <div id="studentAnalytics" style="display: none;">
                <div class="analytics-container">
                    <div class="chart-box">
                        <h3 id="studentName">Student Name</h3>
                        <p id="studentRollDept" style="color: var(--text-muted); font-size: 13px; margin: 4px 0 16px 0;"></p>
                        <canvas id="attendanceDonutChart" width="180" height="180"></canvas>
                        <div id="pctBadge" class="progress-badge">0%</div>
                    </div>
                    <div>
                        <h4 style="margin-bottom: 12px; font-weight: 700;">Subject-Wise Performance Breakdown</h4>
                        <div style="border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 25px;">
                            <table>
                                <thead>
                                    <tr><th>Subject</th><th>Attended</th><th>Percentage</th></tr>
                                </thead>
                                <tbody id="studentSubjectTable"></tbody>
                            </table>
                        </div>

                        <h4 style="margin-bottom: 12px; font-weight: 700;">Attendance History Logs</h4>
                        <div style="max-height: 220px; overflow-y: auto; border: 1px solid var(--border); border-radius: 12px;">
                            <table>
                                <thead><tr><th>Date</th><th>Course</th><th>Status</th></tr></thead>
                                <tbody id="studentHistoryTable"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Reports -->
        <div id="reports" class="tab-panel" style="text-align: center; padding: 40px 20px;">
            <div style="max-width: 480px; margin: 0 auto;">
                <div style="font-size: 54px; color: var(--primary); margin-bottom: 16px;"><i class="fa-solid fa-file-csv"></i></div>
                <h2 style="font-weight: 800; margin-bottom: 10px;">Export Course Attendance</h2>
                <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 25px;">Download a complete CSV spreadsheet dataset detailing student attendances mapped to subjects.</p>
                <a href="/api/export" style="text-decoration: none;"><button class="btn-primary" style="width: auto;"><i class="fa-solid fa-cloud-arrow-down"></i> Download CSV Dataset</button></a>
            </div>
        </div>
    </div>
</div>

<!-- Edit Course Modal -->
<div id="editCourseModal" class="modal">
    <div class="modal-content">
        <h3 style="font-weight: 700; margin-bottom: 16px;"><i class="fa-solid fa-book"></i> Edit Course</h3>
        <form onsubmit="submitEditCourse(event)">
            <input type="hidden" id="editCourseId">
            <div class="input-group">
                <label>Course Name</label>
                <input type="text" id="editCourseName" required>
            </div>
            <div class="input-group">
                <label>Course Code</label>
                <input type="text" id="editCourseCode" required>
            </div>
            <div class="input-group">
                <label>Department</label>
                <input type="text" id="editCourseDept" required>
            </div>
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button type="button" class="btn-primary" style="background: #94a3b8;" onclick="closeModals()">Cancel</button>
                <button type="submit" class="btn-primary">Update Course</button>
            </div>
        </form>
    </div>
</div>

<!-- Edit Faculty Modal -->
<div id="editFacultyModal" class="modal">
    <div class="modal-content">
        <h3 style="font-weight: 700; margin-bottom: 16px;"><i class="fa-solid fa-pen-to-square"></i> Edit Staff Account</h3>
        <form onsubmit="submitEditFaculty(event)">
            <input type="hidden" id="editFacId">
            <div class="input-group">
                <label>Full Name</label>
                <input type="text" id="editFacName" required>
            </div>
            <div class="input-group">
                <label>Username</label>
                <input type="text" id="editFacUsername" required>
            </div>
            <div class="input-group">
                <label>New Password (leave blank to keep)</label>
                <input type="password" id="editFacPassword" placeholder="Enter new password">
            </div>
            <div class="input-group">
                <label>Role</label>
                <select id="editFacRole">
                    <option value="faculty">Faculty</option>
                    <option value="admin">Admin</option>
                </select>
            </div>
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button type="button" class="btn-primary" style="background: #94a3b8;" onclick="closeModals()">Cancel</button>
                <button type="submit" class="btn-primary">Update Staff</button>
            </div>
        </form>
    </div>
</div>

<!-- Edit Student Modal -->
<div id="editStudentModal" class="modal">
    <div class="modal-content">
        <h3 style="font-weight: 700; margin-bottom: 16px;"><i class="fa-solid fa-pen-to-square"></i> Edit Student Record</h3>
        <form onsubmit="submitEditStudent(event)">
            <input type="hidden" id="editStuId">
            <div class="input-group">
                <label>Full Name</label>
                <input type="text" id="editStuName" required>
            </div>
            <div class="input-group">
                <label>Roll Number</label>
                <input type="text" id="editStuRoll" required>
            </div>
            <div class="input-group">
                <label>Department</label>
                <input type="text" id="editStuDept" required>
            </div>
            <div class="input-group">
                <label>Email Address</label>
                <input type="email" id="editStuEmail" required>
            </div>
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button type="button" class="btn-primary" style="background: #94a3b8;" onclick="closeModals()">Cancel</button>
                <button type="submit" class="btn-primary" style="background: var(--success);">Update Student</button>
            </div>
        </form>
    </div>
</div>

<div id="toast"><i class="fa-solid fa-circle-check" style="color: var(--success);"></i> <span id="toastMsg"></span></div>

<script>
    document.getElementById('attendanceDate').valueAsDate = new Date();
    document.getElementById('liveClock').innerText = new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    let myChart = null;
    let facultyCache = [];
    let studentsCache = [];
    let coursesCache = [];

    function switchLoginRole(role) {
        document.getElementById('btnRoleFaculty').classList.toggle('active', role === 'faculty');
        document.getElementById('btnRoleStudent').classList.toggle('active', role === 'student');
        document.getElementById('formFacultyLogin').style.display = role === 'faculty' ? 'block' : 'none';
        document.getElementById('formStudentLogin').style.display = role === 'student' ? 'block' : 'none';
    }

    function unlockApp(user) {
        document.getElementById('loginOverlay').style.display = 'none';
        const main = document.getElementById('mainApp');
        main.style.filter = 'none';
        main.style.pointerEvents = 'auto';

        loadCourses();

        if (user.role === 'admin' || user.role === 'faculty') {
            document.getElementById('userGreeting').innerText = `Logged in as: ${user.name} (${user.role.toUpperCase()})`;
            document.getElementById('facultyStatsRow').style.display = 'grid';
            document.getElementById('tabFacBtn').style.display = 'flex';
            document.getElementById('tabRepBtn').style.display = 'flex';
            document.getElementById('studentSearchBar').style.display = 'flex';
            
            if (user.role === 'admin') {
                document.getElementById('tabAdminBtn').style.display = 'flex';
                loadAdminTables();
            } else {
                document.getElementById('tabAdminBtn').style.display = 'none';
            }

            switchTab('faculty');
            loadRoster();
        } else if (user.role === 'student') {
            document.getElementById('userGreeting').innerText = `Student: ${user.name} (${user.roll_number})`;
            document.getElementById('facultyStatsRow').style.display = 'none';
            document.getElementById('tabFacBtn').style.display = 'none';
            document.getElementById('tabAdminBtn').style.display = 'none';
            document.getElementById('tabRepBtn').style.display = 'none';
            document.getElementById('studentSearchBar').style.display = 'none';
            switchTab('student');
            lookupStudent(user.roll_number);
        }
    }

    function handleFacultyLogin(e) {
        e.preventDefault();
        const username = document.getElementById('facUser').value;
        const password = document.getElementById('facPass').value;

        fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ role: 'faculty', username, password })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                unlockApp({ role: data.role, name: data.name });
            } else {
                alert(data.message);
            }
        });
    }

    function handleStudentLogin(e) {
        e.preventDefault();
        const roll_number = document.getElementById('stuRollInput').value;

        fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ role: 'student', roll_number })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                unlockApp({ role: 'student', name: data.name, roll_number: data.roll_number });
            } else {
                alert(data.message);
            }
        });
    }

    function loadCourses() {
        fetch('/api/courses')
            .then(res => res.json())
            .then(courses => {
                coursesCache = courses;
                const select = document.getElementById('facultyCourseSelect');
                select.innerHTML = courses.map(c => `
                    <option value="${c.id}">${c.course_code} - ${c.course_name}</option>
                `).join('');
            });
    }

    function handleRegisterCourse(e) {
        e.preventDefault();
        const course_name = document.getElementById('regCourseName').value;
        const course_code = document.getElementById('regCourseCode').value;
        const department = document.getElementById('regCourseDept').value;

        fetch('/api/register/course', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ course_name, course_code, department })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                e.target.reset();
                loadCourses();
                loadAdminTables();
                loadStats();
            } else {
                alert(data.message);
            }
        });
    }

    function handleRegisterFaculty(e) {
        e.preventDefault();
        const name = document.getElementById('regFacName').value;
        const username = document.getElementById('regFacUser').value;
        const password = document.getElementById('regFacPass').value;
        const role = document.getElementById('regFacRole').value;

        fetch('/api/register/faculty', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, username, password, role })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                e.target.reset();
                loadAdminTables();
            } else {
                alert(data.message);
            }
        });
    }

    function handleRegisterStudent(e) {
        e.preventDefault();
        const name = document.getElementById('regStuName').value;
        const roll_number = document.getElementById('regStuRoll').value;
        const department = document.getElementById('regStuDept').value;
        const email = document.getElementById('regStuEmail').value;

        fetch('/api/register/student', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, roll_number, department, email })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                e.target.reset();
                loadRoster();
                loadStats();
                loadAdminTables();
            } else {
                alert(data.message);
            }
        });
    }

    function loadAdminTables() {
        // 1. Courses
        fetch('/api/courses')
            .then(res => res.json())
            .then(courses => {
                coursesCache = courses;
                document.getElementById('adminCourseList').innerHTML = courses.map(c => `
                    <tr>
                        <td><strong>${c.course_code}</strong></td>
                        <td>${c.course_name}</td>
                        <td>${c.department}</td>
                        <td style="text-align: right;">
                            <button class="btn-action btn-edit" onclick="openEditCourse(${c.id})"><i class="fa-solid fa-pen"></i> Edit</button>
                            <button class="btn-action btn-delete" onclick="deleteCourse(${c.id}, '${c.course_code}')"><i class="fa-solid fa-trash"></i></button>
                        </td>
                    </tr>
                `).join('');
            });

        // 2. Staff
        fetch('/api/admin/faculty')
            .then(res => res.json())
            .then(staff => {
                facultyCache = staff;
                document.getElementById('adminFacultyList').innerHTML = staff.map(u => `
                    <tr>
                        <td><strong>${u.name}</strong></td>
                        <td>${u.username}</td>
                        <td><span style="text-transform: uppercase; font-size: 11px; font-weight: 700; background: #e0e7ff; color: var(--primary); padding: 3px 8px; border-radius: 6px;">${u.role}</span></td>
                        <td style="text-align: right;">
                            <button class="btn-action btn-edit" onclick="openEditFaculty(${u.id})"><i class="fa-solid fa-pen"></i> Edit</button>
                            <button class="btn-action btn-delete" onclick="deleteFaculty(${u.id}, '${u.username}')"><i class="fa-solid fa-trash"></i></button>
                        </td>
                    </tr>
                `).join('');
            });

        // 3. Students
        fetch('/api/students')
            .then(res => res.json())
            .then(students => {
                studentsCache = students;
                document.getElementById('adminStudentList').innerHTML = students.map(s => `
                    <tr>
                        <td><strong>${s.name}</strong><br><small style="color: var(--text-muted);">${s.roll_number}</small></td>
                        <td>${s.department}</td>
                        <td>${s.email}</td>
                        <td style="text-align: right;">
                            <button class="btn-action btn-edit" onclick="openEditStudent(${s.id})"><i class="fa-solid fa-pen"></i> Edit</button>
                            <button class="btn-action btn-delete" onclick="deleteStudent(${s.id}, '${s.name}')"><i class="fa-solid fa-trash"></i></button>
                        </td>
                    </tr>
                `).join('');
            });
    }

    function openEditCourse(id) {
        const c = coursesCache.find(x => x.id === id);
        if (!c) return;
        document.getElementById('editCourseId').value = c.id;
        document.getElementById('editCourseName').value = c.course_name;
        document.getElementById('editCourseCode').value = c.course_code;
        document.getElementById('editCourseDept').value = c.department;
        document.getElementById('editCourseModal').style.display = 'flex';
    }

    function submitEditCourse(e) {
        e.preventDefault();
        const id = document.getElementById('editCourseId').value;
        const course_name = document.getElementById('editCourseName').value;
        const course_code = document.getElementById('editCourseCode').value;
        const department = document.getElementById('editCourseDept').value;

        fetch(`/api/admin/course/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ course_name, course_code, department })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                closeModals();
                loadCourses();
                loadAdminTables();
            } else {
                alert(data.message);
            }
        });
    }

    function deleteCourse(id, code) {
        if (!confirm(`Delete course ${code} and all of its attendance records?`)) return;
        fetch(`/api/admin/course/${id}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                showToast(data.message);
                loadCourses();
                loadAdminTables();
                loadStats();
            });
    }

    function openEditFaculty(id) {
        const u = facultyCache.find(x => x.id === id);
        if (!u) return;
        document.getElementById('editFacId').value = u.id;
        document.getElementById('editFacName').value = u.name;
        document.getElementById('editFacUsername').value = u.username;
        document.getElementById('editFacPassword').value = '';
        document.getElementById('editFacRole').value = u.role;
        document.getElementById('editFacultyModal').style.display = 'flex';
    }

    function submitEditFaculty(e) {
        e.preventDefault();
        const id = document.getElementById('editFacId').value;
        const name = document.getElementById('editFacName').value;
        const username = document.getElementById('editFacUsername').value;
        const password = document.getElementById('editFacPassword').value;
        const role = document.getElementById('editFacRole').value;

        fetch(`/api/admin/faculty/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, username, password, role })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                closeModals();
                loadAdminTables();
            } else {
                alert(data.message);
            }
        });
    }

    function deleteFaculty(id, username) {
        if (!confirm(`Are you sure you want to delete staff user "${username}"?`)) return;
        fetch(`/api/admin/faculty/${id}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                showToast(data.message);
                loadAdminTables();
            });
    }

    function openEditStudent(id) {
        const s = studentsCache.find(x => x.id === id);
        if (!s) return;
        document.getElementById('editStuId').value = s.id;
        document.getElementById('editStuName').value = s.name;
        document.getElementById('editStuRoll').value = s.roll_number;
        document.getElementById('editStuDept').value = s.department;
        document.getElementById('editStuEmail').value = s.email;
        document.getElementById('editStudentModal').style.display = 'flex';
    }

    function submitEditStudent(e) {
        e.preventDefault();
        const id = document.getElementById('editStuId').value;
        const name = document.getElementById('editStuName').value;
        const roll_number = document.getElementById('editStuRoll').value;
        const department = document.getElementById('editStuDept').value;
        const email = document.getElementById('editStuEmail').value;

        fetch(`/api/admin/student/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name, roll_number, department, email })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast(data.message);
                closeModals();
                loadAdminTables();
                loadRoster();
            } else {
                alert(data.message);
            }
        });
    }

    function deleteStudent(id, name) {
        if (!confirm(`Are you sure you want to delete student "${name}" and all their attendance history?`)) return;
        fetch(`/api/admin/student/${id}`, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => {
                showToast(data.message);
                loadAdminTables();
                loadRoster();
                loadStats();
            });
    }

    function closeModals() {
        document.getElementById('editCourseModal').style.display = 'none';
        document.getElementById('editFacultyModal').style.display = 'none';
        document.getElementById('editStudentModal').style.display = 'none';
    }

    function logout() {
        fetch('/api/logout', { method: 'POST' }).then(() => {
            location.reload();
        });
    }

    function showToast(msg) {
        const toast = document.getElementById('toast');
        document.getElementById('toastMsg').innerText = msg;
        toast.style.display = 'flex';
        setTimeout(() => toast.style.display = 'none', 4000);
    }

    function switchTab(id) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        const btn = document.getElementById(
            id === 'faculty' ? 'tabFacBtn' : 
            id === 'admin' ? 'tabAdminBtn' : 
            id === 'student' ? 'tabStuBtn' : 'tabRepBtn'
        );
        if (btn) btn.classList.add('active');
        document.getElementById(id).classList.add('active');
        if (id === 'faculty') loadStats();
        if (id === 'admin') loadAdminTables();
    }

    function loadStats() {
        fetch('/api/stats').then(r => r.json()).then(data => {
            document.getElementById('kpiTotal').innerText = data.total_students;
            document.getElementById('kpiCourses').innerText = data.total_courses;
            document.getElementById('kpiPresent').innerText = data.today_present;
            document.getElementById('kpiAbsent').innerText = data.today_absent;
        });
    }

    function loadRoster() {
        fetch('/api/students')
            .then(res => res.json())
            .then(students => {
                document.getElementById('rosterList').innerHTML = students.map(s => `
                    <tr class="roster-row">
                        <td>
                            <strong>${s.name}</strong>
                            <div style="font-size: 12px; color: var(--text-muted);">${s.roll_number} • ${s.email}</div>
                        </td>
                        <td><span style="font-size: 13px; color: var(--text-muted);">${s.department}</span></td>
                        <td style="text-align: right;">
                            <div class="status-toggle">
                                <input type="radio" id="p_${s.id}" name="${s.id}" value="Present" checked>
                                <label for="p_${s.id}"><i class="fa-solid fa-check"></i> Present</label>
                                <input type="radio" id="a_${s.id}" name="${s.id}" value="Absent">
                                <label for="a_${s.id}"><i class="fa-solid fa-xmark"></i> Absent</label>
                            </div>
                        </td>
                    </tr>
                `).join('');
                loadStats();
            });
    }

    function filterRoster() {
        const q = document.getElementById('searchInput').value.toLowerCase();
        document.querySelectorAll('.roster-row').forEach(row => {
            row.style.display = row.innerText.toLowerCase().includes(q) ? '' : 'none';
        });
    }

    function setAllAttendance(status) {
        document.querySelectorAll(`.status-toggle input[value="${status}"]`).forEach(input => input.checked = true);
    }

    document.getElementById('attendanceForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const dateVal = document.getElementById('attendanceDate').value;
        const courseId = document.getElementById('facultyCourseSelect').value;
        const formData = new FormData(this);
        const records = {};
        for (let [studentId, status] of formData.entries()) {
            records[studentId] = status;
        }

        fetch('/api/attendance', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ attendance_date: dateVal, course_id: courseId, records })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert(data.error);
            } else {
                showToast(data.message);
                loadStats();
            }
        });
    });

    function lookupStudent(roll) {
        if (!roll) return;

        fetch('/api/student/' + encodeURIComponent(roll.trim()))
            .then(res => {
                if (!res.ok) throw new Error('Student roll number not found');
                return res.json();
            })
            .then(data => {
                document.getElementById('studentAnalytics').style.display = 'block';
                document.getElementById('studentName').innerText = data.name;
                document.getElementById('studentRollDept').innerText = `${data.roll_number} • ${data.department} • ${data.email}`;
                
                const pct = document.getElementById('pctBadge');
                pct.innerText = data.overall_percentage + '% Total';
                pct.className = 'progress-badge ' + (data.overall_percentage >= 75 ? 'badge-safe' : 'badge-warning');

                // Render Subject-Wise Table
                document.getElementById('studentSubjectTable').innerHTML = data.course_breakdown.map(c => `
                    <tr>
                        <td><strong>${c.course_code}</strong> - ${c.course_name}</td>
                        <td>${c.present_classes} / ${c.total_classes} classes</td>
                        <td>
                            <span style="font-weight: 700; color: ${c.percentage >= 75 ? 'var(--success)' : 'var(--danger)'};">
                                ${c.percentage}%
                            </span>
                        </td>
                    </tr>
                `).join('');

                // Render Detailed Log History
                document.getElementById('studentHistoryTable').innerHTML = data.history.map(h => `
                    <tr>
                        <td>${h.date}</td>
                        <td><strong>${h.course_code}</strong> (${h.course_name})</td>
                        <td><span style="font-weight:700; color: ${h.status === 'Present' ? 'var(--success)' : 'var(--danger)'};">${h.status}</span></td>
                    </tr>
                `).join('');

                // Overall Donut Chart
                if (myChart) myChart.destroy();
                const ctx = document.getElementById('attendanceDonutChart').getContext('2d');
                myChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: ['Present', 'Absent'],
                        datasets: [{
                            data: [data.overall_present, data.overall_absent],
                            backgroundColor: ['#10b981', '#ef4444'],
                            borderWidth: 0
                        }]
                    },
                    options: { cutout: '72%', plugins: { legend: { display: false } } }
                });
            })
            .catch(err => alert(err.message));
    }
</script>
</body>
</html>
"""


    # ... (all your routes, API functions, and HTML_TEMPLATE code above) ...

# Run the database setup whenever the app loads
init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5000)