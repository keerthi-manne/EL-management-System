from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from your_app import mysql
from your_app.auth.routes import roles_required

themes_bp = Blueprint('themes_bp', __name__)

@themes_bp.route('', methods=['POST'])
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

@themes_bp.route('', methods=['GET'])
@jwt_required()
def get_themes():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Theme")
    rows = cur.fetchall()
    cur.close()
    themes = [{'ThemeID': r[0], 'ThemeName': r[1], 'Description': r[2]} for r in rows]
    return jsonify(themes), 200

@themes_bp.route('/<int:theme_id>', methods=['PUT'])
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

@themes_bp.route('/<int:theme_id>', methods=['DELETE'])
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
