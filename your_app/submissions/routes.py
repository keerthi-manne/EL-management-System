from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql
from your_app.auth.routes import roles_required
from flask import make_response

submissions_bp = Blueprint('submissions_bp', __name__)

@submissions_bp.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

# ✅ FIXED: Matches YOUR schema - SubmissionType=ENUM, SubmissionContent=TEXT
@submissions_bp.route('/create', methods=['POST'])
@jwt_required()
@roles_required('Student')
def add_submission():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    submission_link = data.get('SubmissionType', '').strip()  # Frontend sends URL here
    
    # ✅ Map frontend URL to correct ENUM + content
    submission_type = 'Link'  # Fixed for document links
    submission_content = submission_link  # URL goes in SubmissionContent

    # ✅ VALIDATION
    if not all([project_id, submission_content]):
        return jsonify({'error': 'ProjectID and submission link are required'}), 400
    
    if len(submission_content) > 1000:
        return jsonify({'error': 'Link too long (max 1000 characters)'}), 400
    
    if not submission_content.startswith(('http://', 'https://')):
        return jsonify({'error': 'Must be valid URL (http:// or https://)'}), 400

    cur = mysql.connection.cursor()
    try:
        # ✅ Validate student is on project team
        cur.execute("""
            SELECT COUNT(*) FROM TeamMember 
            WHERE ProjectID = %s AND UserID = %s
        """, (project_id, current_user_id))
        team_check = cur.fetchone()[0]
        if team_check == 0:
            return jsonify({'error': 'You must be on the project team to submit'}), 403

        # ✅ YOUR EXACT SCHEMA: SubmissionType=ENUM, SubmissionContent=TEXT URL
        cur.execute(
            """
            INSERT INTO projectsubmission 
            (ProjectID, UserID, SubmissionType, SubmissionContent, SubmittedAt) 
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (int(project_id), current_user_id, submission_type, submission_content)
        )
        mysql.connection.commit()
        submission_id = cur.lastrowid
        print(f"✅ Submission {submission_id} created for {current_user_id}")
        print(f"   Type: {submission_type}, Link: {submission_content[:80]}...")
        
        return jsonify({
            'message': 'Document link submitted successfully!', 
            'SubmissionID': submission_id
        }), 201
        
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Submission ERROR: {e}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    finally:
        cur.close()

# ✅ FIXED: Fetch matches YOUR schema exactly
@submissions_bp.route('/project/<int:project_id>', methods=['GET'])
@jwt_required()
def get_submissions_by_project(project_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT SubmissionID, ProjectID, UserID, SubmissionType, SubmissionContent, SubmittedAt 
            FROM projectsubmission 
            WHERE ProjectID = %s 
            ORDER BY SubmittedAt DESC
        """, (project_id,))
        
        submissions = []
        for row in cur.fetchall():
            submissions.append({
                'SubmissionID': row[0],
                'ProjectID': row[1],
                'StudentUserID': row[2],
                'SubmissionType': row[3],      # 'Link', 'Video', 'Report'
                'SubmissionContent': row[4],   # ✅ Actual URL stored here!
                'SubmittedAt': row[5].strftime('%Y-%m-%d %H:%M') if row[5] else None
            })
        print(f"📄 Found {len(submissions)} submissions for project {project_id}")
        return jsonify(submissions), 200
    except Exception as e:
        print(f"❌ Submissions fetch error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
