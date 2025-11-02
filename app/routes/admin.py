"""
Admin routes
Handles admin-only operations
"""

from flask import Blueprint

bp = Blueprint('admin', __name__)

@bp.route('/users', methods=['GET'])
def get_all_users():
    """Get all users"""
    return {'users': []}

