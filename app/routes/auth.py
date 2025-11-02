"""
Authentication routes
Handles login, signup, logout, profile
"""

from flask import Blueprint, request, jsonify, redirect, render_template
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

# This will be imported from services later
# For now, placeholder
def get_auth_service():
    """Get authentication service instance"""
    # Will be implemented with dependency injection
    pass

@bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    return render_template('auth/login.html')

@bp.route('/send-otp', methods=['POST'])
def send_otp():
    """Send OTP to mobile number"""
    # Placeholder - will be implemented
    return jsonify({'success': True, 'message': 'OTP sent'})

@bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP and login"""
    # Placeholder - will be implemented
    return jsonify({'success': True, 'message': 'Logged in'})

@bp.route('/logout', methods=['POST'])
def logout():
    """Logout user"""
    # Placeholder - will be implemented
    response = jsonify({'success': True})
    response.set_cookie('session_token', '', expires=0)
    return response

@bp.route('/me', methods=['GET'])
def get_current_user():
    """Get current user info"""
    # Placeholder - will be implemented
    return jsonify({'id': 1, 'mobile': '09123456789'})

