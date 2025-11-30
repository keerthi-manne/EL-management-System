from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required,
    get_jwt_identity, verify_jwt_in_request, get_jwt
)
from your_app import mysql
from your_app.auth.utils import hash_password, check_password
from functools import wraps

auth_bp = Blueprint('auth_bp', __name__)

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

@auth_bp.route('/create_user', methods=['POST'])
def create_user():
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'Student')
    status = data.get('status', 'Approved')

    if not all([user_id, name, email, password, role]):
        return jsonify({'error': 'Missing fields'}), 400

    hashed_pass = hash_password(password)

    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            INSERT INTO User (UserID, Name, Email, PasswordHash, Role, Status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, name, email, hashed_pass, role, status)
        )
        mysql.connection.commit()

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
                "INSERT INTO Coordinator (UserID, Dept) VALUES (%s, %s)",
                (user_id, dept)
            )
            mysql.connection.commit()

    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500

    cur.close()
    return jsonify({'message': 'User created successfully'}), 201

# ✅ FIXED: Login accepts BOTH email AND UserID (USN)
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    identifier = data.get('username') or data.get('email') or data.get('user_id')  # ✅ Flexible!
    password = data.get('password')

    print(f"🔍 Login attempt for: {identifier}")  # Debug log

    if not (identifier and password):
        return jsonify({'error': 'Username/USN/Email and password required'}), 400

    cur = mysql.connection.cursor()
    try:
        # ✅ Try UserID first (USN), then Email
        cur.execute("SELECT UserID, Name, PasswordHash, Role FROM User WHERE UserID = %s OR Email = %s", (identifier, identifier))
        user = cur.fetchone()
        
        if not user:
            print(f"❌ User not found: {identifier}")
            return jsonify({'error': 'Invalid credentials'}), 401
        
        user_id, name, stored_hash, role = user
        print(f"✅ User found: {user_id} ({role})")
        
        # ✅ Password check with debug
        if check_password(stored_hash, password):
            access_token = create_access_token(
                identity=user_id,
                additional_claims={"role": role}
            )
            print(f"✅ {user_id} ({role}) logged in successfully")
            return jsonify({
                'message': 'Login successful',
                'access_token': access_token,
                'user': {
                    'userId': user_id,
                    'name': name,
                    'role': role
                }
            }), 200
        else:
            print(f"❌ Password mismatch for {user_id}")
            return jsonify({'error': 'Invalid credentials'}), 401
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500
    finally:
        cur.close()

@auth_bp.route('/change_password', methods=['POST'])
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
    try:
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
        cur.execute(
            "UPDATE User SET PasswordHash=%s WHERE UserID=%s",
            (new_hashed, current_user_id)
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        mysql.connection.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 500

# ✅ BONUS: Get current user info
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("SELECT UserID, Name, Email, Role FROM User WHERE UserID=%s", (user_id,))
        user = cur.fetchone()
        if user:
            return jsonify({
                'userId': user[0],
                'name': user[1],
                'email': user[2],
                'role': user[3]
            }), 200
        return jsonify({'error': 'User not found'}), 404
    finally:
        cur.close()
