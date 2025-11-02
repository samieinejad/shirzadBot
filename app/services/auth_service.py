"""
Authentication Service
Handles OTP generation, SMS sending, session management, and user authentication
"""

import secrets
import re
import random
import requests
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)

# Import config
try:
    import config
    KAVENEGAR_API_KEY = getattr(config, 'KAVENEGAR_API_KEY', '')
    PAYPING_TOKEN = getattr(config, 'PAYPING_TOKEN', '')
except:
    KAVENEGAR_API_KEY = ''
    PAYPING_TOKEN = ''

# Import database
try:
    from app.utils.database import get_db_connection
except:
    # Fallback for importing from app.py context
    from utils.database import get_db_connection


class AuthService:
    """Service for authentication operations"""
    
    @staticmethod
    def normalize_mobile(mobile: str) -> str:
        """Normalize Iranian mobile number"""
        mobile = re.sub(r'[^\d]', '', mobile)
        if mobile.startswith('0'):
            mobile = '98' + mobile[1:]
        elif not mobile.startswith('98'):
            mobile = '98' + mobile
        return mobile
    
    @staticmethod
    def generate_otp() -> str:
        """Generate 6-digit OTP code"""
        return ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    @staticmethod
    def send_otp_via_kavenegar(mobile: str, code: str) -> bool:
        """Send OTP code via Kavenegar SMS"""
        try:
            normalized = AuthService.normalize_mobile(mobile)
            
            if not KAVENEGAR_API_KEY:
                logger.warning("KAVENEGAR_API_KEY not configured, using mock mode")
                logger.info(f"[MOCK] OTP code for {mobile}: {code}")
                return True
            
            url = f"https://api.kavenegar.com/v1/{KAVENEGAR_API_KEY}/sms/send.json"
            payload = {
                'receptor': normalized,
                'message': f'کد تایید شما: {code}\nاین کد 5 دقیقه معتبر است.',
                'sender': '1000596446'  # Change to your Kavenegar sender number
            }
            
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if result.get('return', {}).get('status') == 200:
                    logger.info(f"[Kavenegar] OTP sent to {mobile}")
                    return True
                else:
                    logger.error(f"[Kavenegar] Failed: {result}")
                    return False
            else:
                logger.error(f"[Kavenegar] HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[Kavenegar] Error sending OTP: {e}")
            return False
    
    @staticmethod
    def create_session(user_id: int) -> str:
        """Create user session"""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=30)
        
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO user_sessions (user_id, session_token, expires_at)
                VALUES (?, ?, ?)
            ''', (user_id, session_token, expires_at))
            conn.commit()
        
        return session_token
    
    @staticmethod
    def get_user_from_session(session_token: str) -> Optional[Dict[str, Any]]:
        """Get user from session token"""
        if not session_token:
            return None
        
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, ut.telegram_token, ut.bale_token, ut.ita_token,
                       ut.telegram_owner_id, ut.bale_owner_id, ut.ita_owner_id
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                LEFT JOIN user_tokens ut ON u.id = ut.user_id
                WHERE s.session_token = ? AND s.expires_at > datetime('now') AND u.is_active = 1
            ''', (session_token,))
            result = cursor.fetchone()
            return dict(result) if result else None


def require_auth(f: Callable) -> Callable:
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, jsonify, redirect
        
        session_token = request.cookies.get('session_token') or request.headers.get('X-Session-Token')
        user = AuthService.get_user_from_session(session_token)
        
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
            else:
                return redirect('/login')
        
        request.user = user
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f: Callable) -> Callable:
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, jsonify, redirect
        
        session_token = request.cookies.get('session_token') or request.headers.get('X-Session-Token')
        user = AuthService.get_user_from_session(session_token)
        
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
            else:
                return redirect('/login')
        
        if not user.get('is_admin'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Admin access required'}), 403
            else:
                return redirect('/dashboard')
        
        request.user = user
        return f(*args, **kwargs)
    return decorated_function

