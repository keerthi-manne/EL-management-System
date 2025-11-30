from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from your_app import mysql
from your_app.auth.routes import roles_required

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/assign_faculty_theme', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def assign_faculty_theme():
    data = request.json or {}
    faculty_user_id = data.get('FacultyUserID')
    theme_id = data.get('ThemeID')

    if not faculty_user_id or not theme_id:
        return jsonify({'error': 'FacultyUserID and ThemeID are required'}), 400

    cur = mysql.connection.cursor()
    try:
        # Optional: ensure user exists and is Faculty
        cur.execute("SELECT Role FROM user WHERE UserID = %s", (faculty_user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'User not found'}), 404
        if row[0] != 'Faculty':
            return jsonify({'error': 'User is not a faculty member'}), 400

        # Optional: ensure theme exists
        cur.execute("SELECT 1 FROM Theme WHERE ThemeID = %s", (theme_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Theme not found'}), 404

        # Upsert: one theme per faculty (FacultyUserID is PK in FacultyTheme)
        cur.execute("""
            INSERT INTO FacultyTheme (FacultyUserID, ThemeID)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE ThemeID = VALUES(ThemeID)
        """, (faculty_user_id, theme_id))

        mysql.connection.commit()
        return jsonify({'message': 'Faculty assigned to theme successfully'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
@admin_bp.route('/faculty_theme_assignments', methods=['GET'])
@jwt_required()
@roles_required('Admin')
def get_faculty_theme_assignments():
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT ft.FacultyUserID, u.Name, ft.ThemeID, t.ThemeName
            FROM FacultyTheme ft
            JOIN user u ON ft.FacultyUserID = u.UserID
            JOIN theme t ON ft.ThemeID = t.ThemeID
            ORDER BY u.Name, t.ThemeName
        """)
        rows = cur.fetchall()
        data = []
        for r in rows:
            data.append({
                'FacultyUserID': r[0],
                'FacultyName': r[1],
                'ThemeID': r[2],
                'ThemeName': r[3]
            })
        return jsonify({'assignments': data}), 200
    finally:
        cur.close()
@admin_bp.route('/unassigned_faculty', methods=['GET'])
@jwt_required()
@roles_required('Admin')
def get_unassigned_faculty():
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT u.UserID, u.Name, u.Email
            FROM user u
            WHERE u.Role = 'Faculty'
              AND NOT EXISTS (
                SELECT 1 FROM FacultyTheme ft
                WHERE ft.FacultyUserID = u.UserID
              )
            ORDER BY u.Name
        """)
        rows = cur.fetchall()
        faculty = []
        for r in rows:
            faculty.append({
                'UserID': r[0],
                'Name': r[1],
                'Email': r[2]
            })
        return jsonify({'faculty': faculty}), 200
    finally:
        cur.close()

