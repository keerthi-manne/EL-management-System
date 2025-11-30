from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql
from your_app.auth.routes import roles_required

mentors_judges_bp = Blueprint('mentors_judges_bp', __name__)

@mentors_judges_bp.route('/self_assign', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def faculty_self_assign_mentor():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    status = 'ManualSelection'

    if not project_id:
        return jsonify({'error': 'ProjectID is required'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT ThemeID FROM Project WHERE ProjectID=%s", (project_id,))
        theme_row = cur.fetchone()
        if not theme_row:
            return jsonify({'error': 'Project not found'}), 404
        project_theme_id = theme_row[0]

        cur.execute("SELECT * FROM FacultyTheme WHERE FacultyUserID=%s AND ThemeID=%s",
                    (current_user_id, project_theme_id))
        if not cur.fetchone():
            return jsonify({'error': 'You are not assigned to this theme and cannot mentor this project.'}), 403

        cur.execute("SELECT COUNT(*) FROM mentorassignment WHERE FacultyUserID=%s", (current_user_id,))
        count = cur.fetchone()[0]
        if count >= 5:
            return jsonify({'error': 'Mentor project limit (5) reached.'}), 403

        cur.execute("SELECT * FROM mentorassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Already mentoring this project.'}), 400

        # Prevent mentoring if also judging
        cur.execute("SELECT * FROM judgeassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Cannot mentor a project you are judging.'}), 403

        cur.execute("INSERT INTO mentorassignment (ProjectID, FacultyUserID, Status) VALUES (%s, %s, %s)",
                    (project_id, current_user_id, status))
        mysql.connection.commit()
        return jsonify({'message': 'Mentor assignment successful.'}), 201

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@mentors_judges_bp.route('/judges/self_assign', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def faculty_self_assign_judge():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    selection_type = 'Volunteer'

    if not project_id:
        return jsonify({'error': 'ProjectID is required'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT ThemeID FROM Project WHERE ProjectID=%s", (project_id,))
        theme_row = cur.fetchone()
        if not theme_row:
            return jsonify({'error': 'Project not found'}), 404
        project_theme_id = theme_row[0]

        cur.execute("SELECT * FROM FacultyTheme WHERE FacultyUserID=%s AND ThemeID=%s",
                    (current_user_id, project_theme_id))
        if not cur.fetchone():
            return jsonify({'error': 'You are not assigned to this theme and cannot judge this project.'}), 403

        cur.execute("SELECT COUNT(*) FROM judgeassignment WHERE FacultyUserID=%s", (current_user_id,))
        count = cur.fetchone()[0]
        if count >= 5:
            return jsonify({'error': 'Judge project limit (5) reached.'}), 403

        cur.execute("SELECT * FROM judgeassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Already judging this project.'}), 400

        # Prevent judging if also mentoring
        cur.execute("SELECT * FROM mentorassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Cannot judge a project you are mentoring.'}), 403

        cur.execute("INSERT INTO judgeassignment (ProjectID, FacultyUserID, SelectionType) VALUES (%s, %s, %s)",
                    (project_id, current_user_id, selection_type))
        mysql.connection.commit()
        return jsonify({'message': 'Judge assignment successful.'}), 201

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@mentors_judges_bp.route('/mentors/my', methods=['GET'])
@jwt_required()
@roles_required('Faculty')
def my_mentor_assignments():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT ma.ProjectID, p.Status FROM mentorassignment ma JOIN Project p ON ma.ProjectID = p.ProjectID WHERE ma.FacultyUserID=%s",
        (current_user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    assignments = [{'ProjectID': r[0], 'Status': r[1]} for r in rows]
    return jsonify(assignments), 200

@mentors_judges_bp.route('/judges/my', methods=['GET'])
@jwt_required()
@roles_required('Faculty')
def my_judge_assignments():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT ProjectID, SelectionType FROM judgeassignment WHERE FacultyUserID=%s",
        (current_user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    assignments = [{'ProjectID': r[0], 'SelectionType': r[1]} for r in rows]
    return jsonify(assignments), 200

@mentors_judges_bp.route('/available_projects', methods=['GET'])
@jwt_required()
@roles_required('Faculty')
def available_projects():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()

    # Get faculty's theme
    cur.execute(
        "SELECT ThemeID FROM FacultyTheme WHERE FacultyUserID=%s",
        (current_user_id,)
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        return jsonify([]), 200
    faculty_theme_id = row[0]

    # List projects in that theme
    cur.execute(
        "SELECT ProjectID, Title, ThemeID, Status FROM Project WHERE ThemeID=%s",
        (faculty_theme_id,)
    )
    rows = cur.fetchall()
    cur.close()

    projects = [
        {
            'ProjectID': r[0],
            'Title': r[1],
            'ThemeID': r[2],
            'Status': r[3]
        }
        for r in rows
    ]
    return jsonify(projects), 200

@mentors_judges_bp.route('/my_theme', methods=['GET'])
@jwt_required()
@roles_required('Faculty')
def my_theme():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT t.ThemeID, t.ThemeName, t.Description
            FROM FacultyTheme ft
            JOIN Theme t ON ft.ThemeID = t.ThemeID
            WHERE ft.FacultyUserID = %s
        """, (current_user_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify(None), 200

        return jsonify({
            'ThemeID': row[0],
            'ThemeName': row[1],
            'Description': row[2],
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


# 🔥 FIXED JUDGES-ONLY EVALUATION ENDPOINT
@mentors_judges_bp.route('/evaluate/<int:project_id>', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def submit_evaluation(project_id):
    current_user_id = get_jwt_identity()
    data = request.json
    score = data.get('Score')
    feedback = data.get('Feedback', '')
    phase = data.get('Phase', 'Phase1')
    student_user_id = data.get('StudentUserID')

    # Validate score
    if score is None:
        return jsonify({'error': 'Score is required'}), 400
    
    try:
        score_val = float(score)
        if not 0 <= score_val <= 10:
            return jsonify({'error': 'Score must be between 0 and 10'}), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'Score must be a valid number'}), 400
    
    if not student_user_id:
        return jsonify({'error': 'StudentUserID is required'}), 400

    if phase not in ['Phase1', 'Phase2', 'Phase3']:
        return jsonify({'error': 'Phase must be Phase1, Phase2, or Phase3'}), 400

    cur = mysql.connection.cursor()
    try:
        # 1. Must be JUDGE for project ✅
        cur.execute("""
            SELECT 1 FROM judgeassignment 
            WHERE FacultyUserID = %s AND ProjectID = %s
        """, (current_user_id, project_id))
        if not cur.fetchone():
            return jsonify({'error': 'Must be JUDGE for this project'}), 403

        # 2. FIXED: Student on project team? (NO Team table join) ✅
        cur.execute("""
            SELECT 1 FROM teammember tm
            WHERE tm.UserID = %s AND tm.ProjectID = %s
        """, (student_user_id, project_id))
        if not cur.fetchone():
            return jsonify({'error': f'Student {student_user_id} not on project team'}), 403

        # 3. Sequential phase check (Phase2 only after Phase1, etc.)
        if phase == 'Phase2':
            cur.execute("""
                SELECT 1 FROM evaluation 
                WHERE ProjectID = %s AND FacultyUserID = %s AND StudentUserID = %s AND Phase = 'Phase1'
            """, (project_id, current_user_id, student_user_id))
            if not cur.fetchone():
                return jsonify({'error': 'Must score Phase1 for this student first'}), 400
        
        elif phase == 'Phase3':
            cur.execute("""
                SELECT 1 FROM evaluation 
                WHERE ProjectID = %s AND FacultyUserID = %s AND StudentUserID = %s AND Phase IN ('Phase1','Phase2')
            """, (project_id, current_user_id, student_user_id))
            if cur.rowcount < 2:
                return jsonify({'error': 'Must score Phase1 AND Phase2 first'}), 400

        # 4. No duplicate evaluation ✅
        cur.execute("""
            SELECT 1 FROM evaluation 
            WHERE ProjectID = %s AND FacultyUserID = %s AND StudentUserID = %s AND Phase = %s
        """, (project_id, current_user_id, student_user_id, phase))
        if cur.fetchone():
            return jsonify({'error': f'Already scored {student_user_id} in {phase}'}), 400

        # 5. INSERT evaluation ✅
        cur.execute("""
            INSERT INTO evaluation (ProjectID, FacultyUserID, EvaluationType, Score, Feedback, Phase, StudentUserID)
            VALUES (%s, %s, 'Judge', %s, %s, %s, %s)
        """, (project_id, current_user_id, score_val, feedback, phase, student_user_id))

        mysql.connection.commit()
        return jsonify({
            'message': f'{student_user_id} {phase} evaluation submitted successfully!',
            'score': score_val,
            'phase': phase
        }), 201
        
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        cur.close()

@mentors_judges_bp.route('/<int:project_id>/phase_aggregate/<phase>', methods=['GET'])
@jwt_required()
def get_project_phase_aggregate(project_id, phase):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT AVG(Score) as aggregate_score,
               COUNT(DISTINCT StudentUserID) as students_scored,
               COUNT(*) as total_evaluations
        FROM evaluation 
        WHERE ProjectID=%s AND Phase=%s
    """, (project_id, phase))
    result = cur.fetchone()
    cur.close()
    
    return jsonify({
        'project_id': project_id,
        'phase': phase,
        'aggregate_score': float(result[0]) if result[0] else None,
        'students_scored': result[1] or 0,
        'total_evaluations': result[2] or 0
    }), 200
