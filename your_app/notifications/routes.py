from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from your_app import mysql
import time
from flask import Response

notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
        return response

def send_direct_notification(receiver_id, message, notification_type='info', extra_data={}):
    """✅ Direct DB insert - NO circular imports"""
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """INSERT INTO notification (UserID, Message, Type, Data, Status) 
               VALUES (%s, %s, %s, %s, 'Unread')""",
            (receiver_id, message, notification_type, json.dumps(extra_data))
        )
        mysql.connection.commit()
        print(f"🔔 Direct notification sent to {receiver_id}: {message}")
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Notification error: {e}")
    finally:
        cur.close()

@notifications_bp.route('', methods=['POST'])
@jwt_required()
def send_notification():
    data = request.json
    receiver_id = data.get('ReceiverID')
    message = data.get('Message')
    notification_type = data.get('Type', 'info')
    extra_data = data.get('Data', {})

    if not all([receiver_id, message]):
        return jsonify({'error': 'ReceiverID and Message are required'}), 400

    send_direct_notification(receiver_id, message, notification_type, extra_data)
    return jsonify({'message': 'Notification sent successfully'}), 201

@notifications_bp.route('/inbox', methods=['GET'])
@jwt_required()
def get_notifications():
    user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT NotificationID, UserID, Message, Type, Data, Timestamp, Status 
            FROM notification 
            WHERE UserID=%s 
            ORDER BY Timestamp DESC 
            LIMIT 50
        """, (user_id,))
        
        notifications = []
        for row in cur.fetchall():
            try:
                data = json.loads(row[4]) if row[4] else {}
            except:
                data = {}
                
            notifications.append({
                'NotificationID': row[0],
                'message': row[2],
                'timestamp': row[5].strftime('%Y-%m-%d %H:%M') if row[5] else None,
                'type': row[3] or 'info',
                'projectId': data.get('projectId'),
                'inviterId': data.get('inviterId'),
                'projectName': data.get('projectName'),
                'isRead': row[6] == 'Read'
            })
        
        return jsonify({'notifications': notifications}), 200
    finally:
        cur.close()

@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@jwt_required()
def mark_notification_read(notification_id):
    user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            UPDATE notification 
            SET Status = 'Read' 
            WHERE NotificationID = %s AND UserID = %s
        """, (notification_id, user_id))
        
        if cur.rowcount == 0:
            return jsonify({'error': 'Notification not found'}), 404
            
        mysql.connection.commit()
        return jsonify({'message': 'Notification marked as read'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ✅ FIXED: Team Invite APPROVE
@notifications_bp.route('/team-invite/<int:project_id>/approve', methods=['POST'])
@jwt_required()
def approve_team_invite(project_id):
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            SELECT InviterUserID FROM TeamInvitations 
            WHERE ProjectID = %s AND InvitedUserID = %s AND Status = 'Pending'
        """, (project_id, current_user_id))
        invite = cur.fetchone()
        
        if not invite:
            return jsonify({'error': 'No pending invitation found'}), 404
        
        inviter_id = invite[0]
        
        # Add to TeamMember
        cur.execute("INSERT INTO TeamMember (ProjectID, UserID) VALUES (%s, %s)", (project_id, current_user_id))
        
        # Update TeamInvitations
        cur.execute("""
            UPDATE TeamInvitations 
            SET Status = 'Accepted' 
            WHERE ProjectID = %s AND InvitedUserID = %s
        """, (project_id, current_user_id))
        
        # Get project name and notify creator
        cur.execute("SELECT Title FROM Project WHERE ProjectID = %s", (project_id,))
        project_row = cur.fetchone()
        project_name = project_row[0] if project_row else "Team Project"
            
        send_direct_notification(inviter_id, 
            f"🎉 {current_user_id} accepted your team invitation for '{project_name}'!", 
            'team_joined',
            {'projectId': project_id, 'joinedUserId': current_user_id})
        
        mysql.connection.commit()
        print(f"✅ {current_user_id} joined project {project_id}")
        return jsonify({'message': 'Successfully joined team!', 'ProjectID': project_id}), 200
        
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Team approve error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

@notifications_bp.route('/team-invite/<int:project_id>/reject', methods=['POST'])
@jwt_required()
def reject_team_invite(project_id):
    current_user_id = get_jwt_identity()
    cur = mysql.connection.cursor()
    try:
        cur.execute("""
            UPDATE TeamInvitations 
            SET Status = 'Rejected' 
            WHERE ProjectID = %s AND InvitedUserID = %s AND Status = 'Pending'
        """, (project_id, current_user_id))
        
        if cur.rowcount == 0:
            return jsonify({'error': 'No pending invitation found'}), 404
        
        mysql.connection.commit()
        print(f"❌ {current_user_id} rejected project {project_id}")
        return jsonify({'message': 'Invitation rejected'}), 200
        
    except Exception as e:
        mysql.connection.rollback()
        print(f"❌ Team reject error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()

# ✅ FIXED SSE - NO JWT required (public stream)
@notifications_bp.route('/sse', methods=['GET', 'OPTIONS'])
def sse_notifications():
    """✅ PUBLIC SSE - Filters by userId on frontend"""
    
    def event_stream():
        last_id = 0
        while True:
            try:
                cur = mysql.connection.cursor()
                cur.execute("""
                    SELECT NotificationID, UserID, Message, Type, Data, Timestamp, Status 
                    FROM notification 
                    WHERE Status='Unread' AND NotificationID > %s
                    ORDER BY Timestamp ASC LIMIT 5
                """, (last_id,))
                
                rows = cur.fetchall()
                cur.close()
                
                if rows:
                    for row in rows:
                        last_id = row[0]
                        try:
                            data = json.loads(row[4]) if row[4] else {}
                        except:
                            data = {}
                            
                        notification = {
                            'NotificationID': row[0],
                            'UserID': row[1],
                            'message': row[2],
                            'type': row[3] or 'info',
                            'timestamp': row[5].strftime('%Y-%m-%d %H:%M:%S') if row[5] else None,
                            'projectId': data.get('projectId'),
                            'inviterId': data.get('inviterId'),
                            'projectName': data.get('projectName'),
                            'isRead': row[6] == 'Read'
                        }
                        yield f"data: {json.dumps(notification)}\n\n"
                else:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                    
            except Exception as e:
                print(f"SSE error: {e}")
                yield f"data: {{\"error\": \"Stream error\"}}\n\n"
                break
            
            time.sleep(2)
    
    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers.update({
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Authorization,Content-Type',
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Expose-Headers': '*'
    })
    return response
