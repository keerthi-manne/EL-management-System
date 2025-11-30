from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql
from your_app.auth.routes import roles_required
from your_app.notifications.routes import send_direct_notification  # ✅ FIXED import
import csv
import io
from flask import Response

projects_bp = Blueprint('projects_bp', __name__)

@projects_bp.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

# ------------------ Create Project ------------------ #
@projects_bp.route('/', methods=['POST'])
@jwt_required()
@roles_required('Student')
def create_project():
    current_user_id = get_jwt_identity()
    data = request.json
    title = data.get('Title')
    abstract = data.get('Abstract')
    problem = data.get('ProblemStatement')
    theme_id = data.get('ThemeID')
    status = data.get('Status', 'Unassigned')

    if not all([title, theme_id]):
        return jsonify({'error': 'Title and ThemeID are required'}), 400

    cur = mysql.connection.cursor()
    try:
        # limit: 10 projects per theme
        cur.execute("SELECT COUNT(*) FROM Project WHERE ThemeID=%s", (theme_id,))
        count = cur.fetchone()[0]
        if count >= 10:
            return jsonify({'error': 'Project limit of 10 reached for this theme'}), 403

        # student must be in some team
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE UserID=%s", (current_user_id,))
        team_count = cur.fetchone()[0]
        if team_count == 0:
            return jsonify({'error': 'You must create or join a team before creating a project.'}), 403

        cur.execute(
            """
            INSERT INTO Project (Title, Abstract, ProblemStatement, ThemeID, Status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (title, abstract, problem, theme_id, status)
        )
        mysql.connection.commit()
        project_id = cur.lastrowid
        return jsonify({'message': 'Project created successfully', 'ProjectID': project_id}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ------------------ Get All Projects (with filters) ------------------ #
@projects_bp.route('/', methods=['GET'])
@jwt_required()
def get_projects():
    theme_id = request.args.get('theme_id')
    status = request.args.get('status')

    cur = mysql.connection.cursor()
    sql = """
        SELECT ProjectID, Title, Abstract, ProblemStatement,
               ThemeID, Status, AggregateScore
        FROM Project
        WHERE 1=1
    """
    params = []

    if theme_id:
        sql += " AND ThemeID=%s"
        params.append(theme_id)

    if status:
        sql += " AND Status=%s"
        params.append(status)

    cur.execute(sql, tuple(params))
    projects = cur.fetchall()
    cur.close()

    results = [{
        'ProjectID': p[0],
        'Title': p[1],
        'Abstract': p[2],
        'ProblemStatement': p[3],
        'ThemeID': p[4],
        'Status': p[5],
        'AggregateScore': p[6],
    } for p in projects]
    return jsonify(results), 200

# ------------------ Get Project by ID ------------------ #
@projects_bp.route('/<int:project_id>', methods=['GET'])
@jwt_required()
def get_project(project_id):
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT ProjectID, Title, Abstract, ProblemStatement,
               ThemeID, Status, AggregateScore
        FROM Project
        WHERE ProjectID=%s
        """,
        (project_id,)
    )
    p = cur.fetchone()
    cur.close()
    if not p:
        return jsonify({'error': 'Project not found'}), 404

    result = {
        'ProjectID': p[0],
        'Title': p[1],
        'Abstract': p[2],
        'ProblemStatement': p[3],
        'ThemeID': p[4],
        'Status': p[5],
        'AggregateScore': p[6],
    }
    return jsonify(result), 200

# ------------------ Update Project ------------------ #
@projects_bp.route('/<int:project_id>', methods=['PUT'])
@jwt_required()
@roles_required('Student', 'Admin')
def update_project(project_id):
    current_user_id = get_jwt_identity()
    data = request.json
    title = data.get('Title')
    abstract = data.get('Abstract')
    problem = data.get('ProblemStatement')
    theme_id = data.get('ThemeID')
    status = data.get('Status')

    if not any([title, abstract, problem, theme_id, status]):
        return jsonify({'error': 'At least one field must be provided to update.'}), 400

    cur = mysql.connection.cursor()
    try:
        update_fields = []
        params = []

        if title:
            update_fields.append('Title=%s')
            params.append(title)
        if abstract:
            update_fields.append('Abstract=%s')
            params.append(abstract)
        if problem:
            update_fields.append('ProblemStatement=%s')
            params.append(problem)
        if theme_id:
            update_fields.append('ThemeID=%s')
            params.append(theme_id)
        if status:
            update_fields.append('Status=%s')
            params.append(status)

        params.append(project_id)
        sql = f"UPDATE Project SET {', '.join(update_fields)} WHERE ProjectID=%s"
        cur.execute(sql, tuple(params))
        mysql.connection.commit()
        return jsonify({'message': 'Project updated successfully.'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ------------------ Delete Project (Admin) ------------------ #
@projects_bp.route('/<int:project_id>', methods=['DELETE'])
@jwt_required()
@roles_required('Admin')
def delete_project(project_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM Project WHERE ProjectID=%s", (project_id,))
        mysql.connection.commit()
        return jsonify({'message': 'Project deleted successfully.'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ------------------ Search Projects ------------------ #
@projects_bp.route('/search', methods=['GET'])
@jwt_required()
def search_projects():
    query = request.args.get('q', '').strip()
    cur = mysql.connection.cursor()
    sql = """
        SELECT ProjectID, Title, Abstract, ProblemStatement,
               ThemeID, Status, AggregateScore
        FROM Project
        WHERE Title LIKE %s OR Abstract LIKE %s
    """
    like_pattern = f"%{query}%"
    cur.execute(sql, (like_pattern, like_pattern))
    projects = cur.fetchall()
    cur.close()

    results = [{
        'ProjectID': p[0],
        'Title': p[1],
        'Abstract': p[2],
        'ProblemStatement': p[3],
        'ThemeID': p[4],
        'Status': p[5],
        'AggregateScore': p[6],
    } for p in projects]
    return jsonify(results), 200

# ✅ StudentDashboard - /projects/student
@projects_bp.route('/student', methods=['GET'])
@jwt_required()
@roles_required('Student')
def get_student_projects():
    user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    
    try:
        cur.execute("""
            SELECT p.ProjectID, p.Title, p.Abstract, p.ProblemStatement, p.ThemeID, p.Status
            FROM Project p
            WHERE p.ProjectID IN (
                SELECT tm.ProjectID 
                FROM TeamMember tm 
                WHERE tm.UserID = %s
            )
            ORDER BY p.ProjectID DESC
            LIMIT 10
        """, (user_id,))
        
        projects = []
        for row in cur.fetchall():
            projects.append({
                'ProjectID': row[0],
                'ProjectName': row[1] or f'Project {row[0]}',
                'Description': row[2] or row[3] or 'No description',
                'ThemeID': row[4],
                'Status': row[5]
            })
        
        print(f"✅ Loaded {len(projects)} projects for student {user_id}")
        return jsonify({'projects': projects}), 200
        
    except Exception as e:
        print(f"Projects/student ERROR: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ✅ FIXED: Project details with submissions & evaluations
@projects_bp.route('/<int:project_id>/details', methods=['GET'])
@jwt_required()
@roles_required('Faculty','Student', 'Admin')
def get_project_details_with_submissions(project_id):
    cur = mysql.connection.cursor()
    try:
        print(f"🔍 Starting project {project_id}")
        
        # 1. PROJECT
        cur.execute("""
            SELECT ProjectID, Title, Abstract, ProblemStatement, 
                   ThemeID, Status
            FROM Project 
            WHERE ProjectID = %s
        """, (project_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Project not found'}), 404

        theme_name = 'Unknown'
        if row[4]:
            cur.execute("SELECT ThemeName FROM theme WHERE ThemeID = %s", (row[4],))
            theme_row = cur.fetchone()
            theme_name = theme_row[0] if theme_row else 'Unknown'

        project = {
            'ProjectID': row[0],
            'ProjectName': row[1] or f'Project {row[0]}',
            'Description': row[2] or row[3] or 'No description',
            'ThemeID': row[4],
            'ThemeName': theme_name,
            'Status': row[5]
        }

        # 2. SUBMISSIONS
        submissions = []
        try:
            cur.execute("""
                SELECT SubmissionID, ProjectID, UserID, SubmissionType, SubmissionContent, SubmittedAt
                FROM projectsubmission 
                WHERE ProjectID = %s ORDER BY SubmittedAt DESC
            """, (project_id,))
            for s in cur.fetchall():
                submissions.append({
                    'SubmissionID': s[0],
                    'ProjectID': s[1],
                    'StudentUserID': s[2],
                    'SubmissionType': s[3],
                    'SubmissionContent': s[4],
                    'SubmittedAt': s[5].strftime('%Y-%m-%d %H:%M') if s[5] else None
                })
        except Exception as sub_err:
            print(f"⚠️ Submissions error: {sub_err}")

        # 3. EVALUATIONS - YOUR EXACT schema
        evaluations = []
        try:
            cur.execute("""
                SELECT EvaluationID, ProjectID, FacultyUserID, EvaluationType, Score, 
                       Feedback, EvaluationDate, Phase, StudentUserID
                FROM evaluation 
                WHERE ProjectID = %s
                ORDER BY StudentUserID, Phase
            """, (project_id,))
            eval_rows = cur.fetchall()
            print(f"⭐ Evaluations found: {len(eval_rows)} for project {project_id}")
            
            for r in eval_rows:
                evaluations.append({
                    'EvaluationID': r[0],
                    'ProjectID': r[1],
                    'FacultyUserID': r[2],
                    'EvaluationType': r[3],
                    'Score': float(r[4]) if r[4] else None,
                    'Comments': r[5] or '',
                    'CreatedAt': r[6].strftime('%Y-%m-%d %H:%M') if r[6] else None,
                    'Phase': r[7],
                    'StudentUserID': r[8]
                })
            print(f"✅ Processed {len(evaluations)} evaluations")
        except Exception as eval_err:
            print(f"⚠️ Evaluations error: {eval_err}")
            evaluations = []

        print("🎉 FULL SUCCESS!")
        return jsonify({
            'project': project,
            'submissions': submissions,
            'evaluations': evaluations
        }), 200

    except Exception as e:
        print(f"💥 FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    finally:
        cur.close()

@projects_bp.route('/<int:project_id>/team_members', methods=['GET'])
@jwt_required()
def get_project_team_members(project_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT u.UserID, u.Name 
            FROM TeamMember tm
            JOIN User u ON tm.UserID = u.UserID
            WHERE tm.ProjectID = %s
            ORDER BY u.Name
        """, (project_id,))
        rows = cur.fetchall()
        members = [{'UserID': r[0], 'Name': r[1]} for r in rows]
        return jsonify(members), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ------------------ ✅ FIXED: Team Creation with Notifications ------------------ #
@projects_bp.route('/create-team', methods=['POST'])
@jwt_required()
@roles_required('Student')
def create_team_with_teammates():
    current_user_id = get_jwt_identity()
    data = request.json
    
    project_name = data.get('projectName')
    theme_id = data.get('themeId')
    teammate_usns = data.get('teammateUserIds', [])  # ["1rv23is071", "1rv23is072"]
    
    if not project_name or not theme_id:
        return jsonify({'error': 'Project name and theme required'}), 400

    cur = mysql.connection.cursor()
    try:
        # ✅ Check if creator is already in a team
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE UserID = %s", (current_user_id,))
        if cur.fetchone()[0] > 0:
            return jsonify({'error': 'You are already in a team.'}), 403
        
        # ✅ VALIDATE teammates aren't already in teams
        invalid_teammates = []
        for usn in teammate_usns:
            cur.execute("SELECT COUNT(*) FROM TeamMember WHERE UserID = %s", (usn,))
            if cur.fetchone()[0] > 0:
                invalid_teammates.append(usn)
        
        if invalid_teammates:
            return jsonify({
                'error': 'These users are already in teams:',
                'invalid_teammates': invalid_teammates
            }), 400
        
        # ✅ CREATE PROJECT
        cur.execute("""
            INSERT INTO Project (Title, Abstract, ThemeID, Status) 
            VALUES (%s, %s, %s, 'Pending')
        """, (project_name, f"Team created by {current_user_id}", theme_id))
        project_id = cur.lastrowid
        
        # ✅ ADD CREATOR to TeamMember IMMEDIATELY
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, current_user_id))
        
        # ✅ CREATE TeamInvitations & SEND NOTIFICATIONS
        for teammate_usn in teammate_usns:
            # Create invitation
            cur.execute("""
                INSERT INTO TeamInvitations (ProjectID, InvitedUserID, InviterUserID, Status, CreatedAt) 
                VALUES (%s, %s, %s, 'Pending', NOW())
            """, (project_id, teammate_usn, current_user_id))
            
            # ✅ SEND NOTIFICATION using FIXED function
            send_direct_notification(teammate_usn, 
                f"👥 {current_user_id} invited you to join '{project_name}' team!", 
                'team_invite',
                {'projectId': project_id, 'inviterId': current_user_id, 'projectName': project_name}
            )
        
        mysql.connection.commit()
        print(f"✅ Team created! Project {project_id}, Invited: {len(teammate_usns)} teammates")
        
        return jsonify({
            'message': f'Team created! {len(teammate_usns)} teammates notified 🔔',
            'ProjectID': project_id
        }), 201
        
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Team creation error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ------------------ ADMIN Routes (unchanged) ------------------ #
@projects_bp.route('/admin/all_with_aggregates', methods=['GET'])
@jwt_required()
def get_all_projects_with_aggregates():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT Role FROM user WHERE UserID = %s", (current_user_id,))
        user_role = cur.fetchone()
        
        if not user_role or user_role[0] != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        cur.execute("""
            SELECT 
                p.ProjectID, p.Title, p.Status, COALESCE(t.ThemeName, 'Unassigned') as ThemeName,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase1' THEN e.StudentUserID END) as phase1_scored,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase1' THEN 1 END) as phase1_total,
                AVG(CASE WHEN e.Phase='Phase1' THEN e.Score END) as phase1_avg,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase2' THEN e.StudentUserID END) as phase2_scored,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase2' THEN 1 END) as phase2_total,
                AVG(CASE WHEN e.Phase='Phase2' THEN e.Score END) as phase2_avg,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase3' THEN e.StudentUserID END) as phase3_scored,
                COUNT(DISTINCT CASE WHEN e.Phase='Phase3' THEN 1 END) as phase3_total,
                AVG(CASE WHEN e.Phase='Phase3' THEN e.Score END) as phase3_avg,
                COUNT(DISTINCT tm.UserID) as team_size
            FROM project p
            LEFT JOIN theme t ON p.ThemeID = t.ThemeID
            LEFT JOIN teammember tm ON p.ProjectID = tm.ProjectID
            LEFT JOIN evaluation e ON p.ProjectID = e.ProjectID
            GROUP BY p.ProjectID, p.Title, p.Status, t.ThemeName
            ORDER BY p.ProjectID
        """)
        rows = cur.fetchall()
        
        projects = []
        for row in rows:
            projects.append({
                'ProjectID': row[0],
                'Title': row[1],
                'Status': row[2],
                'ThemeName': row[3],
                'phase1_scored': row[4] or 0,
                'phase1_total': row[5] or 0,
                'phase1_avg': float(row[6]) if row[6] else None,
                'phase2_scored': row[7] or 0,
                'phase2_total': row[8] or 0,
                'phase2_avg': float(row[9]) if row[9] else None,
                'phase3_scored': row[10] or 0,
                'phase3_total': row[11] or 0,
                'phase3_avg': float(row[12]) if row[12] else None,
                'team_size': row[13] or 0
            })
        
        return jsonify({'projects': projects}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@projects_bp.route('/<int:project_id>/approve', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def approve_project(project_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE project SET Status = 'Approved' WHERE ProjectID = %s", (project_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Project not found'}), 404
        mysql.connection.commit()
        return jsonify({'message': 'Project approved successfully'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@projects_bp.route('/<int:project_id>/reject', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def reject_project(project_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE project SET Status = 'Rejected' WHERE ProjectID = %s", (project_id,))
        if cur.rowcount == 0:
            return jsonify({'error': 'Project not found'}), 404
        mysql.connection.commit()
        return jsonify({'message': 'Project rejected'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@projects_bp.route('/admin/export_csv', methods=['GET'])
@jwt_required()
@roles_required('Admin')
def export_projects_csv():
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT 
                p.ProjectID, p.Title, p.Status, COALESCE(t.ThemeName, 'Unassigned') as ThemeName,
                AVG(CASE WHEN e.Phase='Phase1' THEN e.Score END) as phase1_avg,
                AVG(CASE WHEN e.Phase='Phase2' THEN e.Score END) as phase2_avg,
                AVG(CASE WHEN e.Phase='Phase3' THEN e.Score END) as phase3_avg,
                COUNT(DISTINCT tm.UserID) as team_size
            FROM project p
            LEFT JOIN theme t ON p.ThemeID = t.ThemeID
            LEFT JOIN teammember tm ON p.ProjectID = tm.ProjectID
            LEFT JOIN evaluation e ON p.ProjectID = e.ProjectID
            GROUP BY p.ProjectID, p.Title, p.Status, t.ThemeName
            ORDER BY p.ProjectID
        """)
        rows = cur.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ProjectID', 'Title', 'Theme', 'Status', 'Phase1 Avg', 'Phase2 Avg', 'Phase3 Avg', 'Team Size'])
        for r in rows:
            writer.writerow([
                r[0], r[1], r[3], r[2],
                f"{r[4]:.2f}" if r[4] else '',
                f"{r[5]:.2f}" if r[5] else '',
                f"{r[6]:.2f}" if r[6] else '',
                r[7]
            ])

        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers.set("Content-Disposition", "attachment", filename="project_rankings.csv")
        return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
