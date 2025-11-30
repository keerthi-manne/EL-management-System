from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql

dashboard_bp = Blueprint('dashboard_bp', __name__)

@dashboard_bp.route('/summary', methods=['GET'])
@jwt_required()
def summary():
    user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM Project WHERE CreatedBy=%s", (user_id,))
    project_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM Evaluation WHERE FacultyUserID=%s", (user_id,))
    evaluation_count = cur.fetchone()[0]
    
    cur.close()

    return jsonify({
        'project_count': project_count,
        'evaluation_count': evaluation_count,
    }), 200
