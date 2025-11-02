"""
Configuration management for Shirzad Bot Platform
Handles environment-based configuration with defaults
"""

import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    """Application settings"""
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    
    # Database
    DB_FILE = os.path.join(BASE_DIR, "multi_bot_platform.db")
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Bot Tokens (loaded from config.py at root)
    TELEGRAM_BOT_TOKEN = ""
    BALE_BOT_TOKEN = ""
    ITA_BOT_TOKEN = ""
    
    # Owner IDs
    OWNER_ID = 0
    BALE_OWNER_ID = 0
    ITA_OWNER_ID = ""
    
    # Kavenegar SMS
    KAVENEGAR_API_KEY = ""
    
    # Payping Payment
    PAYPING_TOKEN = ""
    
    # File uploads
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mp3', 'pdf', 'doc', 'docx'}
    
    @staticmethod
    def load_config():
        """Load configuration from config.py file"""
        try:
            import sys
            import importlib.util
            
            config_path = BASE_DIR / 'config.py'
            if config_path.exists():
                spec = importlib.util.spec_from_file_location("config", config_path)
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module)
                
                Settings.TELEGRAM_BOT_TOKEN = getattr(config_module, 'TELEGRAM_BOT_TOKEN', '')
                Settings.BALE_BOT_TOKEN = getattr(config_module, 'BALE_BOT_TOKEN', '')
                Settings.ITA_BOT_TOKEN = getattr(config_module, 'ITA_BOT_TOKEN', '')
                Settings.OWNER_ID = getattr(config_module, 'OWNER_ID', 0)
                Settings.BALE_OWNER_ID = getattr(config_module, 'BALE_OWNER_ID', 0)
                Settings.ITA_OWNER_ID = getattr(config_module, 'ITA_OWNER_ID', '')
                Settings.KAVENEGAR_API_KEY = getattr(config_module, 'KAVENEGAR_API_KEY', '')
                Settings.PAYPING_TOKEN = getattr(config_module, 'PAYPING_TOKEN', '')
                Settings.DB_FILE = getattr(config_module, 'DB_FILE', Settings.DB_FILE)
                
                return True
            return False
        except Exception as e:
            print(f"Error loading config.py: {e}")
            return False

# Load config on import
Settings.load_config()

