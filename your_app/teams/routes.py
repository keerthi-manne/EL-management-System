from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from your_app import mysql
from your_app.auth.routes import roles_required

teams_bp = Blueprint('teams_bp', __name__)

@teams_bp.route('', methods=['POST'])
@jwt_required()
@roles_required('Admin', 'Faculty')
def add_team_member():
    data = request.json
    project_id = data.get('ProjectID')
    user_id = data.get('UserID')

    if not all([project_id, user_id]):
        return jsonify({'error': 'Missing fields'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, user_id))
        mysql.connection.commit()
        return jsonify({'message': 'Team member added successfully'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@teams_bp.route('/<int:project_id>', methods=['GET'])
@jwt_required()
def get_team(project_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM TeamMember WHERE ProjectID=%s", (project_id,))
    members = cur.fetchall()
    cur.close()
    team = [{'TeamID': m[0], 'ProjectID': m[1], 'UserID': m[2]} for m in members]
    return jsonify(team), 200
# ✅ FIXED VERSION - Replace your entire create_team function
@teams_bp.route('/create', methods=['POST'])
@jwt_required()
@roles_required('Student')
def create_team():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    
    if not project_id:
        return jsonify({'error': 'ProjectID is required'}), 400

    cur = mysql.connection.cursor()
    try:
        # 1. Check project exists
        cur.execute("SELECT * FROM Project WHERE ProjectID=%s", (project_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Project not found'}), 404

        # 2. Check if user already in team
        cur.execute("SELECT * FROM TeamMember WHERE ProjectID=%s AND UserID=%s", (project_id, current_user_id))
        if cur.fetchone():
            return jsonify({'error': 'You are already in this team'}), 400

        # ✅ 3. FIXED: Check OTHER members only (max 3 others + you = 4 total)
        cur.execute("""
            SELECT COUNT(*) FROM TeamMember 
            WHERE ProjectID=%s AND UserID != %s
        """, (project_id, current_user_id))
        other_members = cur.fetchone()[0]
        
        if other_members >= 3:
            return jsonify({'error': f'Team full! ({other_members}/3 other members already)'}), 403

        # 4. Add user to team
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, current_user_id))
        mysql.connection.commit()
        
        return jsonify({
            'message': f'Team joined successfully! Total: {other_members + 1}/4 members',
            'projectId': project_id
        }), 201
        
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


# New API: Remove a member from a team
@teams_bp.route('/<int:project_id>/members/<user_id>', methods=['DELETE'])
@jwt_required()
@roles_required('Admin', 'Faculty')
def remove_team_member(project_id, user_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM TeamMember WHERE ProjectID=%s AND UserID=%s", (project_id, user_id))
        if cur.rowcount == 0:
            return jsonify({'error': 'Member not found in the team'}), 404
        mysql.connection.commit()
        return jsonify({'message': 'Member removed from the team'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# New API: Get teams for a user
@teams_bp.route('/user/<user_id>', methods=['GET'])
@jwt_required()
def get_teams_for_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT DISTINCT ProjectID FROM TeamMember WHERE UserID=%s", (user_id,))
    projects = [row[0] for row in cur.fetchall()]
    cur.close()
    return jsonify({'UserID': user_id, 'Projects': projects}), 200
# ✅ NEW: Send team invitation (Student → Teammate)
@teams_bp.route('/invite', methods=['POST'])
@jwt_required()
@roles_required('Student')
def send_team_invite():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    teammate_user_id = data.get('TeammateUserID')
    
    cur = mysql.connection.cursor()
    try:
        # Check if inviter is in team
        cur.execute("SELECT * FROM TeamMember WHERE ProjectID=%s AND UserID=%s", (project_id, current_user_id))
        if not cur.fetchone():
            return jsonify({'error': 'You must be in the team to invite'}), 403
            
        # Check team not full
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE ProjectID=%s", (project_id,))
        if cur.fetchone()[0] >= 4:
            return jsonify({'error': 'Team is full'}), 403
            
        # Insert invitation
        cur.execute("""
            INSERT INTO TeamInvitations (ProjectID, InvitedUserID, InviterUserID, Status) 
            VALUES (%s, %s, %s, 'Pending')
            ON DUPLICATE KEY UPDATE Status='Pending'
        """, (project_id, teammate_user_id, current_user_id))
        
        # Send notification
        mysql.connection.commit()
        return jsonify({'message': f'Invitation sent to {teammate_user_id}'}), 200
        
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ✅ NEW: Approve team invitation
@teams_bp.route('/invitation/<invited_user_id>/approve/<project_id>', methods=['POST'])
@jwt_required()
@roles_required('Student')
def approve_invitation(invited_user_id, project_id):
    current_user_id = get_jwt_identity()
    
    if current_user_id != invited_user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    cur = mysql.connection.cursor()
    try:
        # Check invitation exists and pending
        cur.execute("""
            SELECT * FROM TeamInvitations 
            WHERE ProjectID=%s AND InvitedUserID=%s AND Status='Pending'
        """, (project_id, current_user_id))
        if not cur.fetchone():
            return jsonify({'error': 'No pending invitation'}), 404
            
        # Check team not full
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE ProjectID=%s", (project_id,))
        if cur.fetchone()[0] >= 4:
            return jsonify({'error': 'Team is full'}), 403
            
        # Add to team
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, current_user_id))
        cur.execute("UPDATE TeamInvitations SET Status='Approved' WHERE ProjectID=%s AND InvitedUserID=%s", (project_id, current_user_id))
        
        mysql.connection.commit()
        return jsonify({'message': '✅ Joined team successfully!'}), 200
        
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ✅ NEW: Reject team invitation
@teams_bp.route('/invitation/<invited_user_id>/reject/<project_id>', methods=['POST'])
@jwt_required()
@roles_required('Student')
def reject_invitation(invited_user_id, project_id):
    current_user_id = get_jwt_identity()
    
    if current_user_id != invited_user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE TeamInvitations SET Status='Rejected' WHERE ProjectID=%s AND InvitedUserID=%s", (project_id, current_user_id))
        mysql.connection.commit()
        return jsonify({'message': 'Invitation rejected'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
