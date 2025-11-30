from flask import Flask, make_response, request, Response, json
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_mysqldb import MySQL
from flask_cors import CORS
from datetime import datetime
import time

jwt = JWTManager()
mysql = MySQL()

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    jwt.init_app(app)
    mysql.init_app(app)
    
    # ✅ FIXED: CORS for ALL blueprint routes + credentials
    CORS(app, resources={
        r"/*": {
            "origins": ["http://localhost:3000", "http://localhost:3001"],
            "supports_credentials": True,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })

    @app.before_request
    def handle_cors_preflight():
        if request.method == 'OPTIONS':
            response = make_response()
            response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3001'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response

    # ✅ FIXED: Import ALL blueprints FIRST
    from your_app.auth.routes import auth_bp
    from your_app.themes.routes import themes_bp
    from your_app.projects.routes import projects_bp
    from your_app.teams.routes import teams_bp
    from your_app.mentors_judges.routes import mentors_judges_bp
    from your_app.notifications.routes import notifications_bp
    from your_app.submissions.routes import submissions_bp
    from your_app.evaluations.routes import evaluations_bp
    from your_app.admin.routes import admin_bp
    from your_app.dashboard.routes import dashboard_bp

    # ✅ CRITICAL FIX: Blueprint registration WITH CORRECT PREFIXES
    # StudentDashboard calls these EXACT endpoints:
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(themes_bp, url_prefix='/themes')
    app.register_blueprint(projects_bp, url_prefix='/projects')  # ✅ /projects/student, /projects/:id/details
    app.register_blueprint(teams_bp, url_prefix='/teams')
    app.register_blueprint(mentors_judges_bp, url_prefix='/faculty')
    app.register_blueprint(notifications_bp, url_prefix='/notifications')
    
    # ✅ FIXED: submissions_bp → /projectsubmissions (NOT /submissions!)
    app.register_blueprint(submissions_bp, url_prefix='/projectsubmissions')  # ✅ /projectsubmissions/create
    
    app.register_blueprint(evaluations_bp, url_prefix='/evaluations')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    # ✅ SEND NOTIFICATION HELPER (Use anywhere!)
    def send_notification(user_id, message, notification_type='info'):
        cur = mysql.connection.cursor()
        try:
            cur.execute("""
                INSERT INTO Notification (UserID, Message, Type, Data, Status, Timestamp) 
                VALUES (%s, %s, %s, %s, 'Unread', NOW())
            """, (user_id, message, notification_type, json.dumps({})))
            mysql.connection.commit()
            print(f"🔔 Notification sent to {user_id}: {message}")
        except Exception as e:
            print(f"Notification error: {e}")
        finally:
            cur.close()

    # Make helper available to blueprints
    app.send_notification = send_notification

    return app

# ✅ MAIN ENTRY POINT
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
