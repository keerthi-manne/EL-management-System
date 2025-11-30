from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from your_app import mysql
from your_app.auth.routes import roles_required

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/assign_faculty_theme', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def assign_faculty_theme():
    data = request.json
    faculty_user_id = data.get('FacultyUserID')
    theme_id = data.get('ThemeID')

    if not all([faculty_user_id, theme_id]):
        return jsonify({'error': 'FacultyUserID and ThemeID are required'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO FacultyTheme (FacultyUserID, ThemeID) VALUES (%s, %s)",
                    (faculty_user_id, theme_id))
        mysql.connection.commit()
        return jsonify({'message': 'Faculty assigned to theme successfully'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
