"""
General API routes
"""

from flask import Blueprint

bp = Blueprint('api', __name__)

@bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return {'status': 'ok'}

