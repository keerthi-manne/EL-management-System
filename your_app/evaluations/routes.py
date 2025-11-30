from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql
from your_app.auth.routes import roles_required

evaluations_bp = Blueprint('evaluations_bp', __name__)

@evaluations_bp.route('', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def add_evaluation():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    score = data.get('Score')
    comments = data.get('Comments', '')

    if not all([project_id, score]):
        return jsonify({'error': 'ProjectID and Score are required'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO Evaluation (ProjectID, FacultyUserID, Score, Comments) VALUES (%s, %s, %s, %s)",
                    (project_id, current_user_id, score, comments))
        mysql.connection.commit()
        return jsonify({'message': 'Evaluation added'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@evaluations_bp.route('/project/<int:project_id>', methods=['GET'])
@jwt_required()
def get_evaluations(project_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT FacultyUserID, Score, Comments FROM Evaluation WHERE ProjectID=%s", (project_id,))
    evaluations = [{
        'FacultyUserID': row[0],
        'Score': row[1],
        'Comments': row[2]
    } for row in cur.fetchall()]
    cur.close()
    return jsonify(evaluations), 200
