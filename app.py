from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
import bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, verify_jwt_in_request, get_jwt
)
from functools import wraps
from datetime import timedelta

app = Flask(__name__)

# MySQL configuration - adjust to your environment
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'keerthimanne999000@'
app.config['MYSQL_DB'] = 'el_management_system'

# JWT configuration
app.config['JWT_SECRET_KEY'] = 'yourSecretKeyHere'  # Use a strong key in production
jwt = JWTManager(app)

mysql = MySQL(app)

# Utils
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(hashed, password_attempt):
    return bcrypt.checkpw(password_attempt.encode('utf-8'), hashed)

def roles_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_role = claims.get("role", None)
            if user_role not in allowed_roles:
                return jsonify({'msg': 'Access forbidden: insufficient role'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# --------- User management (alphanumeric IDs) ---------

@app.route('/create_user', methods=['POST'])

def create_user():
    data = request.json
    user_id = data.get('user_id')  # This is USN or FacultyID or AdminID directly
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'Student')  # default role
    status = data.get('status', 'Approved')

    if not all([user_id, name, email, password, role]):
        return jsonify({'error': 'Missing fields'}), 400

    hashed_pass = hash_password(password)

    cur = mysql.connection.cursor()
    try:
        # Insert into User using user_id as primary key
        cur.execute(
            "INSERT INTO User (UserID, Name, Email, PasswordHash, Role, Status) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, name, email, hashed_pass, role, status)
        )
        mysql.connection.commit()

        # Role-specific extension, no separate USN or FacultyID, just user_id
        if role == 'Student':
            dept = data.get('Dept')
            sem = data.get('Semester')
            if not all([dept, sem]):
                return jsonify({'error': 'Missing student fields'}), 400
            cur.execute(
                "INSERT INTO Student (UserID, Dept, Semester) VALUES (%s, %s, %s)",
                (user_id, dept, sem)
            )
            mysql.connection.commit()
        elif role == 'Faculty':
            dept = data.get('Dept')
            if not dept:
                return jsonify({'error': 'Missing faculty fields'}), 400
            cur.execute(
                "INSERT INTO Faculty (UserID, Dept) VALUES (%s, %s)",
                (user_id, dept)
            )
            mysql.connection.commit()
        elif role == 'Admin':
            dept = data.get('Dept')
            cur.execute(
                "INSERT INTO Coordinator (UserID, Dept) VALUES (%s, %s)", (user_id, dept)
            )
            mysql.connection.commit()

    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500
    cur.close()
    return jsonify({'message': 'User created successfully'}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    if not (email and password):
        return jsonify({'error': 'Missing email or password'}), 400

    cur = mysql.connection.cursor()
    cur.execute("SELECT UserID, PasswordHash, Role FROM User WHERE Email=%s", (email,))
    user = cur.fetchone()
    cur.close()

    if not user:
        return jsonify({'error': 'User not found'}), 404

    user_id, stored_hash, role = user
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')

    if check_password(stored_hash, password):
        access_token = create_access_token(identity=user_id, additional_claims={"role": role})
        return jsonify({'message': 'Login successful', 'access_token': access_token}), 200
    else:
        return jsonify({'error': 'Invalid password'}), 401

# Password management
@app.route('/change_password', methods=['POST'])
@jwt_required()
@roles_required('Student', 'Faculty', 'Admin')
def change_password():
    current_user_id = get_jwt_identity()
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not (old_password and new_password):
        return jsonify({'error': 'Missing fields'}), 400

    cur = mysql.connection.cursor()
    cur.execute("SELECT PasswordHash FROM User WHERE UserID=%s", (current_user_id,))
    user = cur.fetchone()
    if not user:
        cur.close()
        return jsonify({'error': 'User not found'}), 404

    stored_hash = user[0]
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode('utf-8')
    if not check_password(stored_hash, old_password):
        cur.close()
        return jsonify({'error': 'Old password incorrect'}), 401

    new_hashed = hash_password(new_password)
    try:
        cur.execute("UPDATE User SET PasswordHash=%s WHERE UserID=%s", (new_hashed, current_user_id))
        mysql.connection.commit()
    except Exception as e:
        cur.close()
        return jsonify({'error': str(e)}), 500
    cur.close()
    return jsonify({'message': 'Password changed successfully'}), 200
# ======================================================================
# =============== THEME APIs ===========================================
# ======================================================================
@app.route('/themes', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def add_theme():
    data = request.json
    theme_name = data.get('ThemeName')
    description = data.get('Description', None)

    if not theme_name:
        return jsonify({'error': 'ThemeName is required'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO Theme (ThemeName, Description) VALUES (%s, %s)", (theme_name, description))
        mysql.connection.commit()
        return jsonify({'message': 'Theme added successfully'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/themes', methods=['GET'])
@jwt_required()
def get_themes():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Theme")
    rows = cur.fetchall()
    cur.close()
    themes = [{'ThemeID': r[0], 'ThemeName': r[1], 'Description': r[2]} for r in rows]
    return jsonify(themes), 200


@app.route('/themes/<int:theme_id>', methods=['PUT'])
@jwt_required()
@roles_required('Admin')
def update_theme(theme_id):
    data = request.json
    theme_name = data.get('ThemeName')
    description = data.get('Description')
    cur = mysql.connection.cursor()
    try:
        cur.execute("UPDATE Theme SET ThemeName=%s, Description=%s WHERE ThemeID=%s",
                    (theme_name, description, theme_id))
        mysql.connection.commit()
        return jsonify({'message': 'Theme updated successfully'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/themes/<int:theme_id>', methods=['DELETE'])
@jwt_required()
@roles_required('Admin')
def delete_theme(theme_id):
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM Theme WHERE ThemeID=%s", (theme_id,))
        mysql.connection.commit()
        return jsonify({'message': 'Theme deleted successfully'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


# ======================================================================
# =============== PROJECT APIs =========================================
# ======================================================================
@app.route('/projects', methods=['POST'])
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
        # Check existing number of projects for this theme
        cur.execute("SELECT COUNT(*) FROM Project WHERE ThemeID=%s", (theme_id,))
        count = cur.fetchone()[0]
        if count >= 10:
            return jsonify({'error': 'Project limit of 10 reached for this theme'}), 403

        # Check current user team membership
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE UserID=%s", (current_user_id,))
        team_count = cur.fetchone()[0]
        if team_count == 0:
            return jsonify({'error': 'You must create or join a team before creating a project.'}), 403

        # Insert the new project
        cur.execute(
            "INSERT INTO Project (Title, Abstract, ProblemStatement, ThemeID, Status) VALUES (%s, %s, %s, %s, %s)",
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



@app.route('/projects', methods=['GET'])
@jwt_required()
def get_projects():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Project")
    projects = cur.fetchall()
    cur.close()
    results = [{
        'ProjectID': p[0],
        'Title': p[1],
        'Abstract': p[2],
        'ProblemStatement': p[3],
        'ThemeID': p[4],
        'Status': p[5]
    } for p in projects]
    return jsonify(results), 200


# ======================================================================
# =============== TEAM MEMBER APIs =====================================
# ======================================================================
@app.route('/teams', methods=['POST'])
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


@app.route('/teams/<int:project_id>', methods=['GET'])
@jwt_required()
def get_team(project_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM TeamMember WHERE ProjectID=%s", (project_id,))
    members = cur.fetchall()
    cur.close()
    team = [{'TeamID': m[0], 'ProjectID': m[1], 'UserID': m[2]} for m in members]
    return jsonify(team), 200
@app.route('/teams/create', methods=['POST'])
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
        # Ensure project exists
        cur.execute("SELECT * FROM Project WHERE ProjectID=%s", (project_id,))
        if not cur.fetchone():
            return jsonify({'error': 'Project not found'}), 404

        # Check if user is already in the team
        cur.execute("SELECT * FROM TeamMember WHERE ProjectID=%s AND UserID=%s", (project_id, current_user_id))
        if cur.fetchone():
            return jsonify({'error': 'User already in this team'}), 400

        # Enforce max 4 members per team
        cur.execute("SELECT COUNT(*) FROM TeamMember WHERE ProjectID=%s", (project_id,))
        count = cur.fetchone()[0]
        if count >= 4:
            return jsonify({'error': 'Team member limit (4) reached'}), 403

        # Add user to team
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, current_user_id))
        mysql.connection.commit()
        return jsonify({'message': 'Team created (joined project) successfully'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()



# ======================================================================
# =============== NOTIFICATION APIs ====================================
# ======================================================================
@app.route('/notifications', methods=['POST'])
@jwt_required()
@roles_required('Admin')
def send_notification():
    data = request.json
    user_id = data.get('UserID')
    message = data.get('Message')

    if not all([user_id, message]):
        return jsonify({'error': 'Missing UserID or Message'}), 400

    cur = mysql.connection.cursor()
    try:
        cur.execute("INSERT INTO Notification (UserID, Message) VALUES (%s, %s)", (user_id, message))
        mysql.connection.commit()
        return jsonify({'message': 'Notification sent successfully'}), 201
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()


@app.route('/notifications/<user_id>', methods=['GET'])
@jwt_required()
def get_notifications(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Notification WHERE UserID=%s", (user_id,))
    notes = cur.fetchall()
    cur.close()
    data = [{'NotificationID': n[0], 'UserID': n[1], 'Message': n[2], 'Timestamp': str(n[3]), 'Status': n[4]} for n in notes]
    return jsonify(data), 200
@app.route('/judges/self_assign', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def faculty_self_assign_judge():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    selection_type = 'Volunteer'  # or accept dynamically if desired

    if not project_id:
        return jsonify({'error': 'ProjectID is required'}), 400

    cur = mysql.connection.cursor()
    try:
        # Check project's theme
        cur.execute("SELECT ThemeID FROM Project WHERE ProjectID=%s", (project_id,))
        theme_row = cur.fetchone()
        if not theme_row:
            return jsonify({'error': 'Project not found'}), 404
        project_theme_id = theme_row[0]

        # Verify faculty can judge this theme
        cur.execute("SELECT * FROM FacultyTheme WHERE FacultyUserID=%s AND ThemeID=%s",
                    (current_user_id, project_theme_id))
        if not cur.fetchone():
            return jsonify({'error': 'You are not assigned to this theme and cannot judge this project.'}), 403

        # Limit to 5 judged projects
        cur.execute("SELECT COUNT(*) FROM judgeassignment WHERE FacultyUserID=%s", (current_user_id,))
        count = cur.fetchone()[0]
        if count >= 5:
            return jsonify({'error': 'Judge project limit (5) reached.'}), 403

        # Prevent duplicate
        cur.execute("SELECT * FROM judgeassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Already judging this project.'}), 400

        # Insert judge assignment
        cur.execute("INSERT INTO judgeassignment (ProjectID, FacultyUserID, SelectionType) VALUES (%s, %s, %s)",
                    (project_id, current_user_id, selection_type))
        mysql.connection.commit()
        return jsonify({'message': 'Judge assignment successful.'}), 201

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
@app.route('/mentors/self_assign', methods=['POST'])
@jwt_required()
@roles_required('Faculty')
def faculty_self_assign_mentor():
    current_user_id = get_jwt_identity()
    data = request.json
    project_id = data.get('ProjectID')
    status = 'ManualSelection'  # or accept if you want dynamic

    if not project_id:
        return jsonify({'error': 'ProjectID is required'}), 400

    cur = mysql.connection.cursor()
    try:
        # Check the project's theme
        cur.execute("SELECT ThemeID FROM Project WHERE ProjectID=%s", (project_id,))
        theme_row = cur.fetchone()
        if not theme_row:
            return jsonify({'error': 'Project not found'}), 404
        project_theme_id = theme_row[0]

        # Confirm faculty has this theme in FacultyTheme
        cur.execute("SELECT * FROM FacultyTheme WHERE FacultyUserID=%s AND ThemeID=%s",
                    (current_user_id, project_theme_id))
        if not cur.fetchone():
            return jsonify({'error': 'You are not assigned to this theme and cannot mentor this project.'}), 403

        # Check if already mentoring 5 projects
        cur.execute("SELECT COUNT(*) FROM mentorassignment WHERE FacultyUserID=%s", (current_user_id,))
        count = cur.fetchone()[0]
        if count >= 5:
            return jsonify({'error': 'Mentor project limit (5) reached.'}), 403

        # Prevent duplicate assignment
        cur.execute("SELECT * FROM mentorassignment WHERE FacultyUserID=%s AND ProjectID=%s",
                    (current_user_id, project_id))
        if cur.fetchone():
            return jsonify({'error': 'Already mentoring this project.'}), 400

        # Insert mentor assignment
        cur.execute("INSERT INTO mentorassignment (ProjectID, FacultyUserID, Status) VALUES (%s, %s, %s)",
                    (project_id, current_user_id, status))
        mysql.connection.commit()
        return jsonify({'message': 'Mentor assignment successful.'}), 201

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
@app.route('/mentors/my', methods=['GET'])
@jwt_required()
@roles_required('Faculty')
def my_mentor_assignments():
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT ProjectID, Status FROM mentorassignment WHERE FacultyUserID=%s",
        (current_user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    assignments = [{'ProjectID': r[0], 'Status': r[1]} for r in rows]
    return jsonify(assignments), 200
@app.route('/judges/my', methods=['GET'])
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




# Other endpoints (themes, projects, teams, assignments, evaluations, updates, notifications)
# would be added here, following the same pattern:
# - RBAC with @roles_required
# - Database transactions with MySQL cursor
# - Proper error handling

# Example minimal endpoints to illustrate the flow can be added as needed.
# You can reuse the previously provided logic for themes, projects, mentor/judge assignments, etc.

if __name__ == '__main__':
    app.run(debug=True)
