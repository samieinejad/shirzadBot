# -*- coding: utf-8 -*-
"""
سوپر‌بات ترکیبی: Telegram + Bale (هر دو با python-telegram-bot) + Flask dashboard
نسخه نهایی و کاملاً یکپارچه با رفع تمام خطاها، آپلود فایل، و بهبود داشبورد
سازگار با Windows Server 2016 و Windows 10

نکته: قبل از اجرا، توکن‌ها و OWNER IDs را تنظیم کنید.
نیازمندی‌ها:
pip install python-telegram-bot Flask pandas openpyxl
"""

# حل مشکلات سازگاری قبل از import کردن سایر ماژول‌ها
try:
    from compatibility_fix import fix_compatibility_issues, check_system_compatibility
    if check_system_compatibility():
        fix_compatibility_issues()
except ImportError:
    print("⚠️  فایل compatibility_fix.py یافت نشد - ادامه بدون حل مشکلات سازگاری")

# --- Flask App Initialization ---
from flask import Flask, jsonify, request, render_template, send_from_directory, redirect
import os

# Fix for Python 3.13+ compatibility - imghdr module was removed
try:
    import imghdr
except ImportError:
    # imghdr removed in Python 3.13
    imghdr = None
    
    class imghdr:
        @staticmethod
        def what(filename, h=None):
            """Simple image type detection fallback"""
            if h is None:
                try:
                    with open(filename, 'rb') as f:
                        h = f.read(32)
                except (OSError, IOError):
                    return None
            
            # Check for common image formats
            if h.startswith(b'\xff\xd8\xff'):
                return 'jpeg'
            elif h.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'png'
            elif h.startswith(b'GIF87a') or h.startswith(b'GIF89a'):
                return 'gif'
            elif h.startswith(b'BM'):
                return 'bmp'
            elif h.startswith(b'RIFF') and b'WEBP' in h[:12]:
                return 'webp'
            elif h.startswith(b'\x00\x00\x01\x00'):
                return 'ico'
            elif h.startswith(b'\x00\x00\x02\x00'):
                return 'cur'
            
            # Try mimetypes as fallback
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type and mime_type.startswith('image/'):
                return mime_type.split('/')[1]
            
            return None

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SECRET_KEY'] = os.urandom(24)  # For session management

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
import os
import random
import sqlite3
import asyncio
import logging
import re
import uuid
import time
import jdatetime
import json # For parsing scopes from FormData
import requests
from datetime import datetime, timedelta
from io import BytesIO
import hashlib
import tempfile
import shutil
from urllib.parse import urlparse
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from typing import Dict, List, Set, Any, Optional, Tuple, Union, BinaryIO
from telegram import Bot, InputFile
from telegram.error import BadRequest, TelegramError, RetryAfter

import pandas as pd
try:
    import jdatetime  # optional: for Jalali date formatting
    import pytz  # for timezone handling
except Exception:
    jdatetime = None
    pytz = None
from flask import Flask, jsonify, render_template, request, abort, send_file
from werkzeug.utils import secure_filename # For secure file names

# --- Telegram Imports ---
from telegram import Update as TelegramUpdate, Bot as TelegramBot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application as TelegramApplication, CommandHandler, ChatMemberHandler, ContextTypes as TelegramContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TimedOut

# --- Bale Configuration (using python-telegram-bot with Bale API) ---
BALE_API_BASE_URL = "https://tapi.bale.ai/bot"

# --- Ita Configuration (using direct API calls) ---
ITA_API_BASE_URL = "https://eitaayar.ir/api"

# --- logging ---
# سطح لاگینگ برای خروجی تمیزتر در حالت استفاده عادی به INFO تنظیم شده است.
# برای جزئیات بیشتر در حین اشکال زدایی، میتوانید آن را به logging.DEBUG تغییر دهید.
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.INFO)  # Enable Flask logs
logging.getLogger("telegram.ext.Updater").setLevel(logging.ERROR)  # Suppress conflict errors
logging.getLogger("telegram").setLevel(logging.ERROR)  # Suppress telegram library errors
# Set our main logger to INFO for important messages only
logging.getLogger(__name__).setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# --- تنظیمات اولیه: حتما مقادیر را تغییر دهید ---
# Try to load from config.py first, fallback to defaults
try:
    import config
    TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
    BALE_BOT_TOKEN = config.BALE_BOT_TOKEN
    ITA_BOT_TOKEN = config.ITA_BOT_TOKEN
    OWNER_ID = config.OWNER_ID
    BALE_OWNER_ID = config.BALE_OWNER_ID
    ITA_OWNER_ID = config.ITA_OWNER_ID
    DB_FILE = config.DB_FILE
    TEMPLATE_FOLDER = config.TEMPLATE_FOLDER
    logger.info("✅ Configuration loaded from config.py")
except (ImportError, AttributeError):
    # Fallback to defaults (for local development)
    logger.error("❌ config.py not found! Please create config.py from config.example.py")
    raise ImportError("config.py is required. Copy config.example.py to config.py and add your tokens.")

# --- Broadcast de-duplication ---
BROADCAST_DEDUPE_TTL_SECONDS = 60

def build_broadcast_key(platform: str,
                        content_text: Optional[str],
                        image_id: Optional[str],
                        video_id: Optional[str],
                        document_id: Optional[str],
                        forward_chat_id: Optional[str],
                        forward_message_id: Optional[int],
                        source_platform: Optional[str] = None) -> str:
    # Only apply deduplication for cross-platform broadcasts
    # For same-platform broadcasts, use a unique key to avoid blocking
    source_platform_str = source_platform or platform
    
    if platform == source_platform_str:
        # Same platform broadcast - use timestamp to make it unique
        import time
        timestamp = str(int(time.time() * 1000))  # milliseconds for uniqueness
        base = f"{platform}|{source_platform_str}|{timestamp}|{forward_chat_id or ''}|{forward_message_id or ''}|{image_id or ''}|{video_id or ''}|{document_id or ''}|{(content_text or '')[:200]}"
    else:
        # Cross-platform broadcast - use timestamp to make it unique per target platform
        import time
        timestamp = str(int(time.time() * 1000))  # milliseconds for uniqueness
        base = f"{platform}|{source_platform_str}|{timestamp}|{forward_chat_id or ''}|{forward_message_id or ''}|{image_id or ''}|{video_id or ''}|{document_id or ''}|{(content_text or '')[:200]}"
    
    return hashlib.sha1(base.encode('utf-8', errors='ignore')).hexdigest()

def is_duplicate_broadcast(dedupe_key: str, ttl_seconds: int = BROADCAST_DEDUPE_TTL_SECONDS) -> bool:
    now_ts = int(time.time())
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS broadcast_dedupe (key TEXT PRIMARY KEY, created_at INTEGER)")
            
            # ابتدا پاکسازی کلیدهای قدیمی
            cur.execute("DELETE FROM broadcast_dedupe WHERE created_at < ?", (now_ts - ttl_seconds,))
            conn.commit()
            
            # بررسی وجود کلید
            cur.execute("SELECT created_at FROM broadcast_dedupe WHERE key = ?", (dedupe_key,))
            existing_row = cur.fetchone()
            
            if existing_row:
                # کلید از قبل وجود دارد → duplicate
                return True
            else:
                # کلید جدید → اضافه کردن
                cur.execute("INSERT INTO broadcast_dedupe (key, created_at) VALUES (?, ?)", (dedupe_key, now_ts))
                conn.commit()
                return False
    except Exception as e:
        logger.warning(f"[dedupe] Could not access dedupe table, proceeding without dedupe: {e}")
        return False

# --- Flask Uploads Configuration ---
UPLOAD_FOLDER = 'uploads' # دایرکتوری برای ذخیره موقت فایل‌های آپلود شده
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv', 'webp', 'zip', 'rar', 'doc', 'docx', 'xls', 'xlsx', 'mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- گلوبال‌ها ---
telegram_app: Optional[TelegramApplication] = None
telegram_bot_loop: Optional[asyncio.AbstractEventLoop] = None

bale_app: Optional[TelegramApplication] = None
bale_bot_loop: Optional[asyncio.AbstractEventLoop] = None

# Scheduler for scheduled broadcasts
scheduler: Optional[BackgroundScheduler] = None

user_state: Dict[str, Dict[str, Any]] = {} # وضعیت مکالمه برای ادمین تلگرام
bale_user_state: Dict[str, Dict[str, Any]] = {} # وضعیت مکالمه برای ادمین بله

# Global event loops for thread-safe execution
telegram_bot_loop = None
bale_bot_loop = None

CHAT_TYPE_DISPLAY_NAMES = {"private": "👤 کاربران", "group": "👥 گروه‌ها", "channel": "📢 کانال‌ها"}

# =================================================================
# --- File Handling Functions ---
# =================================================================
def detect_file_extension_from_content(content: bytes) -> str:
    """
    Detect file extension based on file content (magic bytes).
    
    Args:
        content: File content as bytes
        
    Returns:
        File extension with dot (e.g., '.pdf', '.jpg', '.mp4')
    """
    if not content:
        return '.bin'
    
    # Check magic bytes for common file types
    if content.startswith(b'%PDF'):
        return '.pdf'
    elif content.startswith(b'\x89PNG'):
        return '.png'
    elif content.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    elif content.startswith(b'GIF8'):
        return '.gif'
    elif content.startswith(b'RIFF') and b'WEBP' in content[:12]:
        return '.webp'
    elif content.startswith(b'\x00\x00\x00\x18ftypmp42'):
        return '.mp4'
    elif content.startswith(b'\x00\x00\x00\x20ftypM4V'):
        return '.m4v'
    elif content.startswith(b'PK\x03\x04'):
        # ZIP-based formats (docx, xlsx, pptx, etc.)
        if b'word/' in content[:1024]:
            return '.docx'
        elif b'xl/' in content[:1024]:
            return '.xlsx'
        elif b'ppt/' in content[:1024]:
            return '.pptx'
        else:
            return '.zip'
    elif content.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        # OLE2 format (old Office documents)
        if b'WordDocument' in content[:1024]:
            return '.doc'
        elif b'Workbook' in content[:1024]:
            return '.xls'
        else:
            return '.ole'
    elif content.startswith(b'ID3') or content.startswith(b'\xff\xfb') or content.startswith(b'\xff\xfa'):
        return '.mp3'
    elif content.startswith(b'OggS'):
        return '.ogg'
    else:
        return '.bin'  # Unknown type

def get_file_extension_from_id(file_id: str, media_type: str = 'document') -> str:
    """
    Get file extension based on file_id pattern and media type.
    
    Args:
        file_id: The file_id of the file
        media_type: 'photo', 'video', or 'document'
        
    Returns:
        File extension with dot (e.g., '.pdf', '.jpg', '.mp4')
    """
    # Common file extensions based on media type
    if media_type == 'photo':
        return '.jpg'  # Most photos are JPEG
    elif media_type == 'video':
        return '.mp4'  # Most videos are MP4
    elif media_type == 'document':
        # Try to detect document type from file_id pattern
        # Bale document IDs often contain type information
        if 'BQACAg' in file_id:
            return '.pdf'  # Common for PDFs
        elif 'BAADAg' in file_id:
            return '.docx'  # Common for Word docs
        elif 'BQADAg' in file_id:
            return '.xlsx'  # Common for Excel files
        else:
            return '.pdf'  # Default fallback
    else:
        return '.bin'  # Unknown type

async def get_file_info(platform: str, file_id: str, media_type: str = 'document') -> Optional[dict]:
    """
    Get file information including name and extension from file_id.
    
    Args:
        platform: 'telegram', 'bale', or 'ita'
        file_id: The file_id of the file
        media_type: 'photo', 'video', or 'document'
        
    Returns:
        dict with file info or None if failed
    """
    try:
        # Use file_id pattern detection to avoid cross-loop issues
        extension = get_file_extension_from_id(file_id, media_type)
        
        timestamp = int(time.time())
        
        # Create a meaningful filename
        if media_type == 'photo':
            filename = f"photo_{timestamp}{extension}"
        elif media_type == 'video':
            filename = f"video_{timestamp}{extension}"
        else:  # document
            filename = f"document_{timestamp}{extension}"
        
        return {
            'filename': filename,
            'name': filename.split('.')[0],
            'extension': extension,
            'file_path': None  # We don't have the actual path
        }
    except Exception as e:
        logger.error(f"Error generating file info for {file_id} from {platform}: {e}")
        return None

# =========== ITA API Functions ===========
async def send_ita_message(chat_id: str, text: str, parse_mode: str = "HTML") -> Tuple[bool, int]:
    """
    ارسال پیام متنی به ایتا
    Returns: (success, message_id)
    """
    try:
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"[ITA] Sending message to {chat_id} via {url}")
        logger.info(f"[ITA] Data: {data}")
        
        response = requests.post(url, data=data, headers=headers, timeout=30)
        
        logger.info(f"[ITA] Response status: {response.status_code}")
        logger.info(f"[ITA] Response text: {response.text[:200]}...")
        
        if response.status_code == 200:
            result = response.json()
            success = result.get('ok', False)
            logger.info(f"[ITA] API result: {result}")
            
            if not success:
                error_description = result.get('description', 'Unknown error')
                error_code = result.get('error_code', 'Unknown')
                logger.error(f"[ITA] API returned ok=False: {result}")
                logger.error(f"[ITA] Error details - Code: {error_code}, Description: {error_description}")
                return False, 0
            
            # Extract message ID from response
            message_id = 0
            if success and 'result' in result and 'message_id' in result['result']:
                message_id = result['result']['message_id']
                logger.info(f"[ITA] Message ID: {message_id}")
            
            # بررسی آیا پاسخ شامل اطلاعات چت است
            if success and 'result' in result:
                chat_info = result['result'].get('chat', {})
                if chat_info:
                    logger.info(f"[ITA] Chat info from sendMessage: {chat_info}")
                    # ذخیره اطلاعات چت اگر موجود باشد
                    await update_ita_chat_info_from_response(chat_id, chat_info)
            
            return success, message_id
        else:
            logger.error(f"[ITA] API error: {response.status_code} - {response.text}")
            logger.error(f"[ITA] Request details - URL: {url}, Data: {data}")
            return False, 0
            
    except Exception as e:
        logger.error(f"Error sending ITA message: {e}")
        logger.error(f"[ITA] Chat ID: {chat_id}, Text length: {len(text) if text else 0}")
        return False, 0

async def send_ita_message_with_full_response(chat_id: str, text: str, parse_mode: str = "HTML") -> Tuple[bool, dict]:
    """
    ارسال پیام متنی به ایتا و برگرداندن پاسخ کامل
    Returns: (success, full_response)
    """
    try:
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"[ITA Full] Sending message to {chat_id} via {url}")
        logger.info(f"[ITA Full] Data: {data}")
        
        response = requests.post(url, data=data, headers=headers, timeout=30)
        
        logger.info(f"[ITA Full] Response status: {response.status_code}")
        logger.info(f"[ITA Full] Response text: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            success = result.get('ok', False)
            logger.info(f"[ITA Full] API result: {result}")
            
            if not success:
                error_description = result.get('description', 'Unknown error')
                error_code = result.get('error_code', 'Unknown')
                logger.error(f"[ITA Full] API returned ok=False: {result}")
                logger.error(f"[ITA Full] Error details - Code: {error_code}, Description: {error_description}")
                return False, result
            
            return success, result
        else:
            logger.error(f"[ITA Full] API error: {response.status_code} - {response.text}")
            logger.error(f"[ITA Full] Request details - URL: {url}, Data: {data}")
            return False, {"error": f"HTTP {response.status_code}", "response": response.text}
            
    except Exception as e:
        logger.error(f"Error sending ITA message (full response): {e}")
        logger.error(f"[ITA Full] Chat ID: {chat_id}, Text length: {len(text) if text else 0}")
        return False, {"error": str(e)}

async def get_ita_chat_title_from_username(username: str) -> str:
    """
    دریافت نام کانال ایتا از طریق username
    """
    try:
        # روش 1: استفاده از Eitaa Kit (اگر موجود باشد)
        if EITAA_KIT_AVAILABLE:
            try:
                from eitaa import Eitaa
                info = Eitaa.get_info(username)
                if info and info.get('name'):
                    logger.info(f"[ITA Title] Found title via Eitaa Kit: {info['name']}")
                    return info['name']
            except Exception as e:
                logger.warning(f"[ITA Title] Eitaa Kit failed: {e}")
        
        # روش 2: Scraping از صفحه عمومی
        try:
            import requests
            from bs4 import BeautifulSoup
            
            urls = [
                f"https://eitaa.com/{username}",
                f"https://eitaa.com/c/{username}",
                f"https://eitaa.com/channel/{username}",
                f"https://eitaa.com/chat/{username}",
                f"https://eitaa.com/@{username}"
            ]
            
            for url in urls:
                try:
                    response = requests.get(url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # جستجو برای عنوان کانال
                        title_selectors = [
                            'h1',
                            '.channel-title',
                            '.chat-title',
                            'title',
                            '[class*="title"]',
                            '[class*="name"]'
                        ]
                        
                        for selector in title_selectors:
                            elements = soup.select(selector)
                            for element in elements:
                                text = element.get_text().strip()
                                if text and text != 'ایتا' and 'پیام رسان ایتا' not in text:
                                    logger.info(f"[ITA Title] Found title via scraping: {text}")
                                    return text
                except Exception as e:
                    logger.debug(f"[ITA Title] Scraping failed for {url}: {e}")
                    continue
        except Exception as e:
            logger.warning(f"[ITA Title] Scraping method failed: {e}")
        
        # روش 3: استفاده از username به عنوان نام
        logger.info(f"[ITA Title] Using username as title: @{username}")
        return f"@{username}"
        
    except Exception as e:
        logger.error(f"[ITA Title] Error getting title for {username}: {e}")
        return f"@{username}"

async def send_ita_file(chat_id: str, file_path: str, caption: str = None, file_type: str = "document", original_filename: str = None) -> Tuple[bool, int]:
    """
    ارسال فایل به ایتا با استفاده از sendFile API (برای همه نوع فایل‌ها)
    Returns: (success, message_id)
    """
    try:
        # Normalize file path for cross-platform compatibility
        file_path = os.path.normpath(file_path)
        
        if not os.path.exists(file_path):
            logger.error(f"[ITA] File not found: {file_path}")
            return False, 0
        
        # ایتا فقط یک متد دارد: sendFile (برای همه نوع فایل‌ها)
        url = f"https://eitaayar.ir/api/{ITA_BOT_TOKEN}/sendFile"
        
        # استفاده از نام فایل اصلی اگر ارائه شده باشد، در غیر این صورت از مسیر فایل
        if original_filename:
            final_filename = original_filename
            logger.info(f"[ITA] Using original filename: {final_filename}")
        else:
            final_filename = os.path.basename(file_path)
            logger.info(f"[ITA] Using basename from file path: {final_filename}")
        
        # آماده‌سازی داده‌ها برای sendFile API
        data = {
            "chat_id": str(chat_id),
            "caption": caption or "",
            "title": final_filename,
            "date": int(time.time())
        }
        
        logger.info(f"[ITA] Sending file to {chat_id} via {url}")
        logger.info(f"[ITA] File path: {file_path}, File type: {file_type}, Caption: {caption}")
        logger.info(f"[ITA] Final filename: {final_filename}")
        logger.info(f"[ITA] Request data: {data}")
        logger.info(f"[ITA] File size: {os.path.getsize(file_path)} bytes")
        
        # ارسال فایل با استفاده از sendFile API
        with open(file_path, 'rb') as f:
            files = {"file": (final_filename, f)}
            
            response = requests.post(url, data=data, files=files, timeout=60)
            logger.info(f"[ITA] Upload response: {response.status_code} {response.text}")
        
        # پردازش پاسخ
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get("ok"):
                message_id = resp_json["result"].get("message_id", 0)
                logger.info(f"[ITA] File message ID: {message_id}")
                return True, message_id
            else:
                logger.error(f"[ITA] Error response: {resp_json}")
                return False, 0
        else:
            logger.error(f"[ITA] HTTP error: {response.status_code} - {response.text}")
            return False, 0
            
    except Exception as e:
        logger.error(f"[ITA] Exception while sending file: {e}")
        return False, 0

async def forward_ita_message(chat_id: str, from_chat_id: str, message_id: int) -> bool:
    """
    فوروارد پیام در ایتا
    """
    try:
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/forwardMessage"
        data = {
            "chat_id": str(chat_id),
            "from_chat_id": str(from_chat_id),
            "message_id": str(message_id)
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.post(url, data=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('ok', False)
        else:
            logger.warning(f"ITA forward error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error forwarding ITA message: {e}")
        return False

async def delete_ita_message(chat_id: str, message_id: int) -> bool:
    """
    حذف پیام از ایتا
    """
    try:
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/deleteMessage"
        data = {
            "chat_id": str(chat_id),
            "message_id": str(message_id)
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"[ITA] Attempting to delete message {message_id} from chat {chat_id}")
        response = requests.post(url, data=data, headers=headers, timeout=30)
        
        logger.info(f"[ITA] Delete response status: {response.status_code}")
        logger.info(f"[ITA] Delete response text: {response.text[:200]}...")
        
        if response.status_code == 200:
            result = response.json()
            success = result.get('ok', False)
            logger.info(f"[ITA] Delete result: {result}")
            return success
        else:
            logger.warning(f"ITA Delete API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting ITA message: {e}")
        return False

async def get_ita_chat_info(chat_id: str) -> Optional[dict]:
    """
    دریافت اطلاعات کامل چت از ایتا با روش‌های مختلف
    """
    try:
        # روش 1: تلاش برای دریافت از bot API
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChat"
        data = {"chat_id": str(chat_id)}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"[ITA] Getting chat info for {chat_id}")
        logger.info(f"[ITA] Request URL: {url}")
        logger.info(f"[ITA] Request data: {data}")
        
        response = requests.post(url, data=data, headers=headers, timeout=30)
        
        logger.info(f"[ITA] Response status: {response.status_code}")
        logger.info(f"[ITA] Response content: {response.text}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"[ITA] Parsed JSON result: {result}")
                
                if result.get('ok'):
                    chat_info = result.get('result')
                    logger.info(f"[ITA] Chat info retrieved via API: {chat_info}")
                    
                    # اگر اطلاعات کامل نباشد، سعی کنیم آن را تکمیل کنیم
                    if chat_info:
                        # بررسی اینکه آیا نام و یوزرنیم موجود است یا نه
                        title = chat_info.get('title', '')
                        username = chat_info.get('username', '')
                        
                        if not title or not username:
                            logger.warning(f"[ITA] Incomplete info for {chat_id}: title='{title}', username='{username}'")
                            
                            # تلاش برای دریافت اطلاعات بیشتر
                            enhanced_info = await _enhance_ita_chat_info(chat_id, chat_info)
                            if enhanced_info:
                                return enhanced_info
                    
                    return chat_info
                else:
                    logger.warning(f"[ITA] API error for {chat_id}: {result.get('description', 'Unknown error')}")
            except json.JSONDecodeError as e:
                logger.error(f"[ITA] JSON decode error for {chat_id}: {e}")
                logger.debug(f"[ITA] Raw response: {response.text}")
        
        # روش 2: تلاش برای دریافت از API عمومی ایتا (برای شناسه‌های عددی)
        public_info = await _get_ita_public_chat_info(chat_id)
        if public_info:
            return public_info
        
        # روش 2.5: تلاش برای دریافت username از شناسه عددی
        username_info = await _get_ita_username_from_id(chat_id)
        if username_info:
            return username_info
        
        # روش 2.6: تلاش برای دریافت از روش‌های پیشرفته
        advanced_info = await _get_ita_advanced_info(chat_id)
        if advanced_info:
            return advanced_info
        
        # روش 2.7: تلاش برای دریافت از منابع خارجی (غیرفعال برای کاهش خطر)
        # external_info = await _get_ita_external_info(chat_id)
        # if external_info:
        #     return external_info
        
        return None
        
    except Exception as e:
        logger.error(f"[ITA] Error getting chat info for {chat_id}: {e}")
        return None

async def get_ita_chat_info_simple(chat_id: str) -> Optional[dict]:
    """
    دریافت اطلاعات چت ایتا بدون ارسال پیام تست
    فقط از اطلاعات موجود در دیتابیس استفاده می‌کند
    """
    try:
        logger.info(f"[ITA Simple] Getting chat info for {chat_id} from database only (no test message)")
        
        # بررسی اطلاعات موجود در دیتابیس
        existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id,))
        
        if existing_chat:
            chat_title = existing_chat.get('chat_title', '')
            chat_username = existing_chat.get('chat_username', '')
            chat_type = existing_chat.get('chat_type', 'channel')
            
            # اگر title خالی است و username موجود است، از username استفاده کن
            if not chat_title and chat_username:
                chat_title = f"@{chat_username}"
                # به‌روزرسانی دیتابیس
                db_execute("UPDATE chats SET chat_title = ? WHERE chat_id = ? AND platform = 'ita'", (chat_title, chat_id))
                logger.info(f"[ITA Simple] Updated chat title from username: {chat_title}")
            
            logger.info(f"[ITA Simple] Found existing chat info: title='{chat_title}', username='{chat_username}'")
            return {
                'id': chat_id,
                'type': chat_type,
                'title': chat_title,
                'username': chat_username,
                'description': '',
                'member_count': 0
            }
        else:
            logger.warning(f"[ITA Simple] No existing chat info found for {chat_id}")
            return None
            
    except Exception as e:
        logger.error(f"[ITA Simple] Error getting chat info for {chat_id}: {e}")
        return None

async def _enhance_ita_chat_info(chat_id: str, base_info: dict) -> Optional[dict]:
    """
    تکمیل اطلاعات چت ایتا با استفاده از روش‌های مختلف
    """
    try:
        logger.info(f"[ITA] Enhancing chat info for {chat_id}")
        
        enhanced_info = base_info.copy()
        
        # تلاش برای دریافت اطلاعات بیشتر از API های مختلف
        enhanced_info = await _try_ita_chat_enhancement_methods(chat_id, enhanced_info)
        
        # اگر هنوز اطلاعات کامل نیست، از دیتابیس محلی استفاده کنیم
        if not enhanced_info.get('title') or not enhanced_info.get('username'):
            db_info = await _get_ita_info_from_database(chat_id)
            if db_info:
                if not enhanced_info.get('title') and db_info.get('title'):
                    enhanced_info['title'] = db_info['title']
                if not enhanced_info.get('username') and db_info.get('username'):
                    enhanced_info['username'] = db_info['username']
        
        logger.info(f"[ITA] Enhanced info for {chat_id}: {enhanced_info}")
        return enhanced_info
        
    except Exception as e:
        logger.error(f"[ITA] Error enhancing chat info for {chat_id}: {e}")
        return base_info

async def _try_ita_chat_enhancement_methods(chat_id: str, base_info: dict) -> dict:
    """
    تلاش برای تکمیل اطلاعات چت با روش‌های مختلف
    """
    try:
        enhanced_info = base_info.copy()
        
        # روش 1: تلاش برای دریافت از getChatAdministrators
        try:
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatAdministrators"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    admins = result.get('result', [])
                    logger.info(f"[ITA] Found {len(admins)} administrators for {chat_id}")
                    # اگر اطلاعات چت در پاسخ ادمین‌ها باشد
                    if admins and len(admins) > 0:
                        first_admin = admins[0]
                        if 'chat' in first_admin:
                            chat_data = first_admin['chat']
                            if not enhanced_info.get('title') and chat_data.get('title'):
                                enhanced_info['title'] = chat_data['title']
                            if not enhanced_info.get('username') and chat_data.get('username'):
                                enhanced_info['username'] = chat_data['username']
        except Exception as e:
            logger.debug(f"[ITA] Error getting administrators for {chat_id}: {e}")
        
        # روش 2: تلاش برای دریافت از getChatMemberCount
        try:
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatMemberCount"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=15)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    member_count = result.get('result', 0)
                    enhanced_info['member_count'] = member_count
                    logger.info(f"[ITA] Member count for {chat_id}: {member_count}")
        except Exception as e:
            logger.debug(f"[ITA] Error getting member count for {chat_id}: {e}")
        
        return enhanced_info
        
    except Exception as e:
        logger.error(f"[ITA] Error in enhancement methods for {chat_id}: {e}")
        return base_info

async def _get_ita_info_from_database(chat_id: str) -> Optional[dict]:
    """
    دریافت اطلاعات چت ایتا از دیتابیس محلی
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, username, description, member_count 
            FROM chats 
            WHERE chat_id = ? AND platform = 'ita'
        """, (chat_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            name, username, description, member_count = result
            return {
                'title': name,
                'username': username,
                'description': description,
                'member_count': member_count
            }
        
        return None
        
    except Exception as e:
        logger.error(f"[ITA] Error getting info from database for {chat_id}: {e}")
        return None
        
        # روش 3: Scraping از صفحه عمومی (برای username ها)
        scraped_info = await _scrape_ita_chat_info(chat_id)
        if scraped_info:
            return scraped_info
        
        # روش 4: استفاده از مقدار پیش‌فرض
        logger.warning(f"[ITA] Could not get chat info for {chat_id}, using defaults")
        return {
            'id': chat_id,
            'type': 'channel',
            'title': f'کانال ایتا {chat_id}',
            'username': '',
            'description': '',
            'member_count': 0
        }
            
    except Exception as e:
        logger.error(f"Error getting ITA chat info: {e}")
        return None

async def _get_ita_public_chat_info(chat_id: str) -> Optional[dict]:
    """
    دریافت اطلاعات چت از API عمومی ایتا (برای شناسه‌های عددی)
    """
    try:
        import requests
        import re
        
        # تلاش برای دریافت از API عمومی ایتا
        # این API ممکن است اطلاعات محدودی ارائه دهد
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
            'Referer': 'https://eitaa.com/'
        }
        
        # تلاش برای دریافت اطلاعات از endpoint های مختلف
        endpoints = [
            f"https://eitaa.com/api/v1/chats/{chat_id}",
            f"https://eitaa.com/api/chats/{chat_id}",
            f"https://eitaa.com/api/v1/channels/{chat_id}",
            f"https://eitaa.com/api/channels/{chat_id}"
        ]
        
        for endpoint in endpoints:
            try:
                logger.debug(f"[ITA] Trying public API endpoint: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data and isinstance(data, dict):
                            # استخراج اطلاعات مفید
                            title = data.get('title') or data.get('name') or data.get('display_name')
                            username = data.get('username') or data.get('handle')
                            description = data.get('description') or data.get('bio')
                            member_count = data.get('member_count') or data.get('subscribers_count') or data.get('members')
                            
                            if title:
                                logger.info(f"[ITA] Public API info for {chat_id}: title={title}, username={username}")
                                return {
                                    'id': chat_id,
                                    'type': 'channel',
                                    'title': title,
                                    'username': username or '',
                                    'description': description or '',
                                    'member_count': member_count or 0
                                }
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                logger.debug(f"[ITA] Public API endpoint failed {endpoint}: {e}")
                continue
        
        # اگر API عمومی کار نکرد، تلاش برای scraping از صفحه عمومی
        # حتی برای شناسه‌های عددی ممکن است صفحه‌ای وجود داشته باشد
        try:
            url = f"https://eitaa.com/c/{chat_id}"
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                
                # جستجوی نام کانال در HTML
                title_patterns = [
                    r'<title>([^<]+)</title>',
                    r'"title":"([^"]+)"',
                    r'<h1[^>]*>([^<]+)</h1>',
                    r'class="[^"]*title[^"]*"[^>]*>([^<]+)<',
                    r'data-title="([^"]+)"',
                    r'<meta property="og:title" content="([^"]+)"'
                ]
                
                title = None
                for pattern in title_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        title = matches[0].strip()
                        if title and title != 'ایتا' and 'پیام رسان ایتا' not in title and '404' not in title:
                            break
                
                if title:
                    logger.info(f"[ITA] Scraped public page info for {chat_id}: {title}")
                    return {
                        'id': chat_id,
                        'type': 'channel',
                        'title': title,
                        'username': '',
                        'description': '',
                        'member_count': 0
                    }
                    
        except Exception as e:
            logger.debug(f"[ITA] Public page scraping failed for {chat_id}: {e}")
        
        return None
        
    except Exception as e:
        logger.debug(f"[ITA] Public chat info error for {chat_id}: {e}")
        return None

async def _get_ita_username_from_id(chat_id: str) -> Optional[dict]:
    """
    تلاش برای دریافت username از شناسه عددی ایتا
    """
    try:
        import requests
        import re
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
            'Referer': 'https://eitaa.com/'
        }
        
        # تلاش برای دریافت از endpoint های مختلف که ممکن است username را برگردانند
        endpoints = [
            f"https://eitaa.com/api/v1/chats/{chat_id}/info",
            f"https://eitaa.com/api/chats/{chat_id}/info",
            f"https://eitaa.com/api/v1/channels/{chat_id}/info",
            f"https://eitaa.com/api/channels/{chat_id}/info",
            f"https://eitaa.com/api/v1/resolve/{chat_id}",
            f"https://eitaa.com/api/resolve/{chat_id}",
            f"https://eitaa.com/api/v1/chats/{chat_id}",
            f"https://eitaa.com/api/chats/{chat_id}",
            f"https://eitaa.com/api/v1/channels/{chat_id}",
            f"https://eitaa.com/api/channels/{chat_id}",
            f"https://eitaa.com/api/v1/chat/{chat_id}",
            f"https://eitaa.com/api/chat/{chat_id}",
            f"https://eitaa.com/api/v1/channel/{chat_id}",
            f"https://eitaa.com/api/channel/{chat_id}",
            f"https://eitaa.com/api/v1/public/chats/{chat_id}",
            f"https://eitaa.com/api/public/chats/{chat_id}",
            f"https://eitaa.com/api/v1/public/channels/{chat_id}",
            f"https://eitaa.com/api/public/channels/{chat_id}"
        ]
        
        for endpoint in endpoints:
            try:
                logger.debug(f"[ITA] Trying username endpoint: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data and isinstance(data, dict):
                            username = data.get('username') or data.get('handle') or data.get('slug')
                            title = data.get('title') or data.get('name') or data.get('display_name')
                            
                            if username:
                                logger.info(f"[ITA] Found username for {chat_id}: {username}")
                                return {
                                    'id': chat_id,
                                    'type': 'channel',
                                    'title': title or f'کانال ایتا {username}',
                                    'username': username,
                                    'description': data.get('description') or '',
                                    'member_count': data.get('member_count') or 0
                                }
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                logger.debug(f"[ITA] Username endpoint failed {endpoint}: {e}")
                continue
        
        # تلاش برای scraping از صفحه‌های مختلف
        urls_to_try = [
            f"https://eitaa.com/c/{chat_id}",
            f"https://eitaa.com/channel/{chat_id}",
            f"https://eitaa.com/chat/{chat_id}",
            f"https://eitaa.com/{chat_id}",
            f"https://eitaa.com/channels/{chat_id}",
            f"https://eitaa.com/chats/{chat_id}",
            f"https://eitaa.com/public/{chat_id}",
            f"https://eitaa.com/join/{chat_id}",
            f"https://eitaa.com/invite/{chat_id}",
            f"https://eitaa.com/link/{chat_id}",
            f"https://eitaa.com/t/{chat_id}",
            f"https://eitaa.com/me/{chat_id}",
            f"https://eitaa.com/user/{chat_id}",
            f"https://eitaa.com/profile/{chat_id}"
        ]
        
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    content = response.text
                    
                    # جستجوی username در HTML
                    username_patterns = [
                        r'@([a-zA-Z0-9_]+)',
                        r'username["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'handle["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'slug["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'data-username="([^"]+)"',
                        r'data-handle="([^"]+)"',
                        r'data-slug="([^"]+)"',
                        r'data-channel="([^"]+)"',
                        r'data-chat="([^"]+)"',
                        r'channel["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'chat["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'id["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'name["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'title["\']?\s*:\s*["\']([^"\']+)["\']',
                        r'<meta name="twitter:site" content="@([^"]+)"',
                        r'<meta property="og:site_name" content="([^"]+)"',
                        r'<link rel="canonical" href="https://eitaa.com/([^"]+)"',
                        r'href="https://eitaa.com/([^"]+)"',
                        r'src="https://eitaa.com/([^"]+)"'
                    ]
                    
                    username = None
                    for pattern in username_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            potential_username = matches[0].strip()
                            # فیلتر کردن username های نامعتبر
                            if (potential_username and 
                                len(potential_username) > 2 and 
                                potential_username != chat_id and
                                not potential_username.startswith('http')):
                                username = potential_username
                                break
                    
                    if username:
                        # جستجوی نام کانال
                        title_patterns = [
                            r'<title>([^<]+)</title>',
                            r'"title":"([^"]+)"',
                            r'<h1[^>]*>([^<]+)</h1>',
                            r'class="[^"]*title[^"]*"[^>]*>([^<]+)<'
                        ]
                        
                        title = None
                        for pattern in title_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                title = matches[0].strip()
                                if title and title != 'ایتا' and 'پیام رسان ایتا' not in title:
                                    break
                        
                        logger.info(f"[ITA] Found username from scraping {chat_id}: {username}")
                        return {
                            'id': chat_id,
                            'type': 'channel',
                            'title': title or f'کانال ایتا {username}',
                            'username': username,
                            'description': '',
                            'member_count': 0
                        }
                        
            except Exception as e:
                logger.debug(f"[ITA] Scraping failed for {url}: {e}")
                continue
        
        return None
        
    except Exception as e:
        logger.debug(f"[ITA] Username lookup error for {chat_id}: {e}")
        return None

async def _get_ita_advanced_info(chat_id: str) -> Optional[dict]:
    """
    روش‌های پیشرفته برای دریافت اطلاعات چت ایتا
    """
    try:
        import requests
        import re
        import json
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8',
            'Referer': 'https://eitaa.com/',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # روش 1: تلاش برای دریافت از GraphQL endpoint
        try:
            graphql_url = "https://eitaa.com/graphql"
            graphql_query = {
                "query": f"""
                    query {{
                        chat(id: "{chat_id}") {{
                            id
                            title
                            username
                            type
                            description
                            memberCount
                        }}
                    }}
                """
            }
            
            response = requests.post(graphql_url, json=graphql_query, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('chat'):
                    chat_data = data['data']['chat']
                    logger.info(f"[ITA] GraphQL info for {chat_id}: {chat_data}")
                    return {
                        'id': chat_id,
                        'type': chat_data.get('type', 'channel'),
                        'title': chat_data.get('title', ''),
                        'username': chat_data.get('username', ''),
                        'description': chat_data.get('description', ''),
                        'member_count': chat_data.get('memberCount', 0)
                    }
        except Exception as e:
            logger.debug(f"[ITA] GraphQL failed for {chat_id}: {e}")
        
        # روش 2: تلاش برای دریافت از WebSocket endpoint
        try:
            ws_url = f"https://eitaa.com/ws/chat/{chat_id}"
            response = requests.get(ws_url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                # جستجوی JSON در response
                json_patterns = [
                    r'\{[^{}]*"id"[^{}]*"title"[^{}]*\}',
                    r'\{[^{}]*"username"[^{}]*"title"[^{}]*\}',
                    r'\{[^{}]*"chat"[^{}]*\}'
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            if data.get('id') == chat_id or data.get('title'):
                                logger.info(f"[ITA] WebSocket info for {chat_id}: {data}")
                                return {
                                    'id': chat_id,
                                    'type': data.get('type', 'channel'),
                                    'title': data.get('title', ''),
                                    'username': data.get('username', ''),
                                    'description': data.get('description', ''),
                                    'member_count': data.get('memberCount', 0)
                                }
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.debug(f"[ITA] WebSocket failed for {chat_id}: {e}")
        
        # روش 3: تلاش برای دریافت از RSS/Atom feed
        try:
            feed_urls = [
                f"https://eitaa.com/feed/{chat_id}",
                f"https://eitaa.com/rss/{chat_id}",
                f"https://eitaa.com/atom/{chat_id}",
                f"https://eitaa.com/{chat_id}/feed",
                f"https://eitaa.com/{chat_id}/rss",
                f"https://eitaa.com/{chat_id}/atom"
            ]
            
            for feed_url in feed_urls:
                try:
                    response = requests.get(feed_url, headers=headers, timeout=15)
                    if response.status_code == 200:
                        content = response.text
                        
                        # جستجوی نام کانال در feed
                        title_patterns = [
                            r'<title>([^<]+)</title>',
                            r'<channel><title>([^<]+)</title>',
                            r'<feed><title>([^<]+)</title>',
                            r'<name>([^<]+)</name>'
                        ]
                        
                        for pattern in title_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                title = matches[0].strip()
                                if title and title != 'ایتا' and 'پیام رسان ایتا' not in title:
                                    logger.info(f"[ITA] Feed info for {chat_id}: {title}")
                                    return {
                                        'id': chat_id,
                                        'type': 'channel',
                                        'title': title,
                                        'username': '',
                                        'description': '',
                                        'member_count': 0
                                    }
                except Exception as e:
                    logger.debug(f"[ITA] Feed failed for {feed_url}: {e}")
                    continue
        except Exception as e:
            logger.debug(f"[ITA] Feed method failed for {chat_id}: {e}")
        
        # روش 4: تلاش برای دریافت از robots.txt یا sitemap
        try:
            robots_url = "https://eitaa.com/robots.txt"
            response = requests.get(robots_url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                
                # جستجوی sitemap
                sitemap_pattern = r'Sitemap:\s*(https://[^\s]+)'
                sitemaps = re.findall(sitemap_pattern, content, re.IGNORECASE)
                
                for sitemap_url in sitemaps:
                    try:
                        sitemap_response = requests.get(sitemap_url, headers=headers, timeout=15)
                        if sitemap_response.status_code == 200:
                            sitemap_content = sitemap_response.text
                            
                            # جستجوی URL مربوط به chat_id
                            url_pattern = rf'https://eitaa\.com/([^<]+{chat_id}[^<]*)'
                            matches = re.findall(url_pattern, sitemap_content, re.IGNORECASE)
                            
                            if matches:
                                potential_username = matches[0].replace(f'/{chat_id}', '').strip('/')
                                if potential_username and potential_username != chat_id:
                                    logger.info(f"[ITA] Sitemap username for {chat_id}: {potential_username}")
                                    return {
                                        'id': chat_id,
                                        'type': 'channel',
                                        'title': f'کانال ایتا {potential_username}',
                                        'username': potential_username,
                                        'description': '',
                                        'member_count': 0
                                    }
                    except Exception as e:
                        logger.debug(f"[ITA] Sitemap failed for {sitemap_url}: {e}")
                        continue
        except Exception as e:
            logger.debug(f"[ITA] Robots.txt method failed for {chat_id}: {e}")
        
        return None
        
    except Exception as e:
        logger.debug(f"[ITA] Advanced info error for {chat_id}: {e}")
        return None

async def _get_ita_external_info(chat_id: str) -> Optional[dict]:
    """
    تلاش برای دریافت اطلاعات از منابع خارجی
    """
    try:
        import requests
        import re
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8'
        }
        
        # روش 1: جستجو در Google
        try:
            search_query = f"site:eitaa.com {chat_id}"
            google_url = f"https://www.google.com/search?q={search_query}"
            
            response = requests.get(google_url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                
                # جستجوی لینک‌های ایتا در نتایج گوگل
                eita_links = re.findall(r'https://eitaa\.com/([^"\'>\s]+)', content, re.IGNORECASE)
                
                for link in eita_links:
                    if chat_id in link and link != chat_id:
                        potential_username = link.replace(f'/{chat_id}', '').replace(f'{chat_id}', '').strip('/')
                        if potential_username and len(potential_username) > 2:
                            logger.info(f"[ITA] Google search username for {chat_id}: {potential_username}")
                            return {
                                'id': chat_id,
                                'type': 'channel',
                                'title': f'کانال ایتا {potential_username}',
                                'username': potential_username,
                                'description': '',
                                'member_count': 0
                            }
        except Exception as e:
            logger.debug(f"[ITA] Google search failed for {chat_id}: {e}")
        
        # روش 2: جستجو در DuckDuckGo
        try:
            search_query = f"site:eitaa.com {chat_id}"
            ddg_url = f"https://duckduckgo.com/html/?q={search_query}"
            
            response = requests.get(ddg_url, headers=headers, timeout=15)
            if response.status_code == 200:
                content = response.text
                
                # جستجوی لینک‌های ایتا در نتایج DuckDuckGo
                eita_links = re.findall(r'https://eitaa\.com/([^"\'>\s]+)', content, re.IGNORECASE)
                
                for link in eita_links:
                    if chat_id in link and link != chat_id:
                        potential_username = link.replace(f'/{chat_id}', '').replace(f'{chat_id}', '').strip('/')
                        if potential_username and len(potential_username) > 2:
                            logger.info(f"[ITA] DuckDuckGo search username for {chat_id}: {potential_username}")
                            return {
                                'id': chat_id,
                                'type': 'channel',
                                'title': f'کانال ایتا {potential_username}',
                                'username': potential_username,
                                'description': '',
                                'member_count': 0
                            }
        except Exception as e:
            logger.debug(f"[ITA] DuckDuckGo search failed for {chat_id}: {e}")
        
        # روش 3: تلاش برای دریافت از Wayback Machine
        try:
            wayback_url = f"https://web.archive.org/web/*/https://eitaa.com/{chat_id}"
            response = requests.get(wayback_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                content = response.text
                
                # جستجوی URL های مختلف در Wayback Machine
                url_patterns = [
                    rf'https://eitaa\.com/([^"\'>\s]*{chat_id}[^"\'>\s]*)',
                    rf'https://eitaa\.com/([^"\'>\s]+)/{chat_id}',
                    rf'https://eitaa\.com/{chat_id}/([^"\'>\s]+)'
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        if match and match != chat_id and len(match) > 2:
                            logger.info(f"[ITA] Wayback Machine username for {chat_id}: {match}")
                            return {
                                'id': chat_id,
                                'type': 'channel',
                                'title': f'کانال ایتا {match}',
                                'username': match,
                                'description': '',
                                'member_count': 0
                            }
        except Exception as e:
            logger.debug(f"[ITA] Wayback Machine failed for {chat_id}: {e}")
        
        return None
        
    except Exception as e:
        logger.debug(f"[ITA] External info error for {chat_id}: {e}")
        return None

async def _scrape_ita_chat_info(chat_id: str) -> Optional[dict]:
    """
    استخراج اطلاعات چت از صفحه عمومی ایتا با بهبودهای بیشتر
    """
    try:
        # بررسی اینکه آیا chat_id یک username است یا نه
        if chat_id.startswith('-') or chat_id.isdigit():
            # chat_id عددی است، scraping امکان‌پذیر نیست
            return None
        
        # حذف @ از ابتدای username اگر وجود دارد
        username = chat_id.lstrip('@')
        
        import requests
        import re
        
        # تلاش با URL های مختلف
        urls_to_try = [
            f"https://eitaa.com/{username}",
            f"https://eitaa.com/c/{username}",
            f"https://eitaa.com/channel/{username}",
            f"https://eitaa.com/chat/{username}",
            f"https://eitaa.com/{username}/",
            f"https://eitaa.com/@{username}"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fa,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200:
                    content = response.text
                    
                    # جستجوی نام کانال در HTML با الگوهای بیشتر
                    title_patterns = [
                        r'<title>([^<]+)</title>',
                        r'"title":"([^"]+)"',
                        r'"name":"([^"]+)"',
                        r'<h1[^>]*>([^<]+)</h1>',
                        r'<h2[^>]*>([^<]+)</h2>',
                        r'class="[^"]*title[^"]*"[^>]*>([^<]+)<',
                        r'class="[^"]*name[^"]*"[^>]*>([^<]+)<',
                        r'data-title="([^"]+)"',
                        r'data-name="([^"]+)"',
                        r'<meta property="og:title" content="([^"]+)"',
                        r'<meta name="title" content="([^"]+)"'
                    ]
                    
                    title = None
                    for pattern in title_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            potential_title = matches[0].strip()
                            if (potential_title and 
                                potential_title != 'ایتا' and 
                                'پیام رسان ایتا' not in potential_title and
                                'Eitaa' not in potential_title and
                                len(potential_title) > 2):
                                title = potential_title
                                break
                    
                    # جستجوی تعداد اعضا
                    member_count = 0
                    member_patterns = [
                        r'(\d+)\s*عضو',
                        r'(\d+)\s*member',
                        r'member.*?(\d+)',
                        r'(\d+)\s*نفر',
                        r'(\d+)\s*مشترک',
                        r'(\d+)\s*فالوور',
                        r'(\d+)\s*subscriber',
                        r'subscriber.*?(\d+)',
                        r'(\d+)\s*فالو',
                        r'(\d+)\s*follower'
                    ]
                    
                    for pattern in member_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            try:
                                member_count = int(matches[0])
                                if member_count > 0:
                                    break
                            except ValueError:
                                continue
                    
                    if title:
                        logger.info(f"[ITA] Scraped chat info for {username}: {title} (Members: {member_count})")
                        return {
                            'id': chat_id,
                            'type': 'channel',
                            'title': title,
                            'username': username,
                            'description': '',
                            'member_count': member_count
                        }
                    
            except Exception as e:
                logger.debug(f"[ITA] Failed to scrape {url}: {e}")
                continue
            
            logger.debug(f"[ITA] No title found for {username}")
            return None
        else:
            logger.debug(f"[ITA] Scraping failed for {username}: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        logger.debug(f"[ITA] Scraping error for {chat_id}: {e}")
        return None

async def get_chat_administrators(platform: str, chat_id: str) -> List[dict]:
    """
    دریافت لیست ادمین‌های چت برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            administrators = await bot.get_chat_administrators(chat_id)
            result = []
            for admin in administrators:
                user = admin.user
                admin_data = {
                    "user_id": user.id,
                    "status": admin.status,
                    "can_be_edited": getattr(admin, 'can_be_edited', False),
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "username": user.username or "",
                    "is_bot": user.is_bot,
                    "user_type": "ربات" if user.is_bot else ("مالک" if admin.status == "creator" else "ادمین")
                }
                result.append(admin_data)
            return result
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            administrators = await bot.get_chat_administrators(chat_id)
            result = []
            for admin in administrators:
                user = admin.user
                admin_data = {
                    "user_id": user.id,
                    "status": admin.status,
                    "can_be_edited": getattr(admin, 'can_be_edited', False),
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "username": user.username or "",
                    "is_bot": user.is_bot,
                    "user_type": "ربات" if user.is_bot else ("مالک" if admin.status == "creator" else "ادمین")
                }
                result.append(admin_data)
            return result
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatAdministrators"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    administrators = result.get('result', [])
                    # تبدیل فرمت Ita به فرمت یکسان
                    formatted_admins = []
                    for admin in administrators:
                        user = admin.get('user', {})
                        admin_data = {
                            "user_id": user.get('id'),
                            "status": admin.get('status', 'administrator'),
                            "can_be_edited": admin.get('can_be_edited', True),
                            "first_name": user.get('first_name', ''),
                            "last_name": user.get('last_name', ''),
                            "username": user.get('username', ''),
                            "is_bot": user.get('is_bot', False),
                            "user_type": "ربات" if user.get('is_bot') else ("مالک" if admin.get('status') == "creator" else "ادمین")
                        }
                        formatted_admins.append(admin_data)
                    return formatted_admins
            return []
        
        return []
    except Exception as e:
        logger.error(f"Error getting chat administrators for {platform}: {e}")
        return []

def get_sample_members(platform: str, chat_id: str) -> List[dict]:
    """
    این تابع حذف شده است - فقط از داده‌های واقعی استفاده می‌شود
    """
    return []

def save_unique_member(user_id: str, platform: str, first_name: str = None, last_name: str = None, username: str = None, is_bot: bool = False) -> None:
    """ذخیره یا به‌روزرسانی عضو یکتا"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            INSERT OR REPLACE INTO unique_members 
            (user_id, platform, first_name, last_name, username, is_bot, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, platform, first_name, last_name, username, 1 if is_bot else 0))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving unique member: {e}")

def save_chat_membership(user_id: str, platform: str, chat_id: str, chat_type: str) -> None:
    """ذخیره عضویت در چت"""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            INSERT OR REPLACE INTO chat_memberships 
            (user_id, platform, chat_id, chat_type, joined_at, is_active)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
        """, (user_id, platform, chat_id, chat_type))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving chat membership: {e}")

def get_unique_member_stats() -> Dict[str, Any]:
    """دریافت آمار اعضای یکتا"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # آمار کلی اعضای یکتا
        cursor.execute("""
            SELECT platform, COUNT(*) as unique_count
            FROM unique_members 
            WHERE is_bot = 0
            GROUP BY platform
        """)
        platform_stats = {row[0]: row[1] for row in cursor.fetchall()}
        
        # آمار تفصیلی بر اساس نوع چت
        cursor.execute("""
            SELECT 
                cm.platform,
                cm.chat_type,
                COUNT(DISTINCT cm.user_id) as unique_count
            FROM chat_memberships cm
            JOIN unique_members um ON cm.user_id = um.user_id AND cm.platform = um.platform
            WHERE cm.is_active = 1 AND um.is_bot = 0
            GROUP BY cm.platform, cm.chat_type
        """)
        detailed_stats = {}
        for row in cursor.fetchall():
            platform, chat_type, count = row
            if platform not in detailed_stats:
                detailed_stats[platform] = {}
            detailed_stats[platform][chat_type] = count
        
        # آمار مشترکات بین چت‌ها
        cursor.execute("""
            SELECT 
                cm1.platform,
                cm1.user_id,
                COUNT(DISTINCT cm1.chat_id) as chat_count
            FROM chat_memberships cm1
            JOIN unique_members um ON cm1.user_id = um.user_id AND cm1.platform = um.platform
            WHERE cm1.is_active = 1 AND um.is_bot = 0
            GROUP BY cm1.platform, cm1.user_id
            HAVING COUNT(DISTINCT cm1.chat_id) > 1
        """)
        overlap_stats = {}
        for row in cursor.fetchall():
            platform, user_id, chat_count = row
            if platform not in overlap_stats:
                overlap_stats[platform] = {}
            if chat_count not in overlap_stats[platform]:
                overlap_stats[platform][chat_count] = 0
            overlap_stats[platform][chat_count] += 1
        
        conn.close()
        
        return {
            'platform_stats': platform_stats,
            'detailed_stats': detailed_stats,
            'overlap_stats': overlap_stats,
            'total_unique_members': sum(platform_stats.values())
        }
        
    except Exception as e:
        logger.error(f"Error getting unique member stats: {e}")
        return {
            'platform_stats': {},
            'detailed_stats': {},
            'overlap_stats': {},
            'total_unique_members': 0
        }

def update_member_tracking_from_chat(platform: str, chat_id: str, chat_type: str, members: List[Dict[str, Any]]) -> None:
    """به‌روزرسانی ردیابی اعضا از لیست چت"""
    try:
        for member in members:
            user_id = str(member.get('user_id', ''))
            if not user_id:
                continue
                
            # ذخیره عضو یکتا
            save_unique_member(
                user_id=user_id,
                platform=platform,
                first_name=member.get('first_name'),
                last_name=member.get('last_name'),
                username=member.get('username'),
                is_bot=member.get('is_bot', False)
            )
            
            # ذخیره عضویت در چت
            save_chat_membership(
                user_id=user_id,
                platform=platform,
                chat_id=chat_id,
                chat_type=chat_type
            )
            
    except Exception as e:
        logger.error(f"Error updating member tracking: {e}")

async def get_chat_members(platform: str, chat_id: str) -> List[dict]:
    """
    دریافت لیست اعضای چت برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            try:
                # دریافت اطلاعات چت
                chat = await bot.get_chat(chat_id)
                
                # اگر چت خصوصی است، فقط یک عضو دارد
                if chat.type == 'private':
                    return [{
                        "user_id": chat.id,
                        "first_name": chat.first_name or "",
                        "last_name": chat.last_name or "",
                        "username": chat.username or "",
                        "is_bot": False,
                        "user_type": "کاربر"
                    }]
            except Exception as e:
                logger.warning(f"Could not get chat info for {chat_id}: {e}")
                # اگر نتوانستیم اطلاعات چت را دریافت کنیم، لیست خالی برگردانیم
                return []
            
            # برای گروه‌ها و کانال‌ها، دریافت لیست اعضا
            members = []
            try:
                # دریافت لیست اعضا (محدود به 200 عضو)
                member_count = 0
                try:
                    # Get chat members using the correct method
                    chat_members = await bot.get_chat_members(chat_id, limit=200)
                    for member in chat_members:
                        user = member.user
                        user_type = "ربات" if user.is_bot else "کاربر"
                        if member.status == "creator":
                            user_type = "مالک"
                        elif member.status == "administrator":
                            user_type = "ادمین"
                        
                        members.append({
                            "user_id": user.id,
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "username": user.username or "",
                            "is_bot": user.is_bot,
                            "user_type": user_type,
                            "status": member.status
                        })
                        member_count += 1
                except Exception as member_error:
                    logger.warning(f"Could not get chat members for {chat_id}: {member_error}")
                    # Fallback: try to get member count only
                    try:
                        member_count = await bot.get_chat_member_count(chat_id)
                        logger.info(f"Got member count for {chat_id}: {member_count}")
                    except Exception as count_error:
                        logger.warning(f"Could not get member count for {chat_id}: {count_error}")
                
                logger.info(f"Retrieved {member_count} members for {chat_id}")
                
            except Exception as e:
                logger.warning(f"Could not get full member list for {chat_id}: {e}")
                # اگر نتوانستیم لیست کامل را دریافت کنیم، حداقل ادمین‌ها را برگردانیم
                try:
                    administrators = await bot.get_chat_administrators(chat_id)
                    for admin in administrators:
                        user = admin.user
                        members.append({
                            "user_id": user.id,
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "username": user.username or "",
                            "is_bot": user.is_bot,
                            "user_type": "ربات" if user.is_bot else ("مالک" if admin.status == "creator" else "ادمین"),
                            "status": admin.status
                        })
                except Exception as admin_error:
                    logger.error(f"Could not get administrators for {chat_id}: {admin_error}")
            
            return members
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            # دریافت اطلاعات چت
            chat = await bot.get_chat(chat_id)
            
            # اگر چت خصوصی است، فقط یک عضو دارد
            if chat.type == 'private':
                return [{
                    "user_id": chat.id,
                    "first_name": chat.first_name or "",
                    "last_name": chat.last_name or "",
                    "username": chat.username or "",
                    "is_bot": False,
                    "user_type": "کاربر"
                }]
            
            # برای گروه‌ها و کانال‌ها، دریافت لیست اعضا
            members = []
            try:
                # دریافت لیست اعضا (محدود به 200 عضو)
                member_count = 0
                async for member in bot.get_chat_members(chat_id, limit=200):
                    user = member.user
                    user_type = "ربات" if user.is_bot else "کاربر"
                    if member.status == "creator":
                        user_type = "مالک"
                    elif member.status == "administrator":
                        user_type = "ادمین"
                    
                    members.append({
                        "user_id": user.id,
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "username": user.username or "",
                        "is_bot": user.is_bot,
                        "user_type": user_type,
                        "status": member.status
                    })
                    member_count += 1
                
                logger.info(f"Retrieved {member_count} members for {chat_id}")
                
            except Exception as e:
                logger.warning(f"Could not get full member list for {chat_id}: {e}")
                # اگر نتوانستیم لیست کامل را دریافت کنیم، حداقل ادمین‌ها را برگردانیم
                try:
                    administrators = await bot.get_chat_administrators(chat_id)
                    for admin in administrators:
                        user = admin.user
                        members.append({
                            "user_id": user.id,
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "username": user.username or "",
                            "is_bot": user.is_bot,
                            "user_type": "ربات" if user.is_bot else ("مالک" if admin.status == "creator" else "ادمین"),
                            "status": admin.status
                        })
                except Exception as admin_error:
                    logger.error(f"Could not get administrators for {chat_id}: {admin_error}")
            
            return members
        
        elif platform == 'ita':
            # برای ایتا، ابتدا ادمین‌ها را دریافت می‌کنیم
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatAdministrators"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    administrators = result.get('result', [])
                    members = []
                    for admin in administrators:
                        user = admin.get('user', {})
                        members.append({
                            "user_id": user.get('id'),
                            "first_name": user.get('first_name', ''),
                            "last_name": user.get('last_name', ''),
                            "username": user.get('username', ''),
                            "is_bot": user.get('is_bot', False),
                            "user_type": "ربات" if user.get('is_bot') else ("مالک" if admin.get('status') == "creator" else "ادمین"),
                            "status": admin.get('status', 'administrator')
                        })
                    return members
            
            return []
        
        return []
    except Exception as e:
        logger.error(f"Error getting chat members for {platform}: {e}")
        return []

async def promote_chat_member(platform: str, chat_id: str, user_id: int, can_change_info: bool = True, can_delete_messages: bool = True, can_invite_users: bool = True, can_restrict_members: bool = True, can_pin_messages: bool = True, can_promote_members: bool = False) -> bool:
    """
    ارتقای کاربر به ادمین برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=can_change_info,
                can_delete_messages=can_delete_messages,
                can_invite_users=can_invite_users,
                can_restrict_members=can_restrict_members,
                can_pin_messages=can_pin_messages,
                can_promote_members=can_promote_members
            )
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=can_change_info,
                can_delete_messages=can_delete_messages,
                can_invite_users=can_invite_users,
                can_restrict_members=can_restrict_members,
                can_pin_messages=can_pin_messages,
                can_promote_members=can_promote_members
            )
            return True
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/promoteChatMember"
            data = {
                "chat_id": str(chat_id),
                "user_id": user_id,
                "can_change_info": can_change_info,
                "can_delete_messages": can_delete_messages,
                "can_invite_users": can_invite_users,
                "can_restrict_members": can_restrict_members,
                "can_pin_messages": can_pin_messages,
                "can_promote_members": can_promote_members
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error promoting chat member for {platform}: {e}")
        return False

async def demote_chat_member(platform: str, chat_id: str, user_id: int) -> bool:
    """
    تنزل ادمین برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False
            )
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            await bot.promote_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                can_change_info=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_restrict_members=False,
                can_pin_messages=False,
                can_promote_members=False
            )
            return True
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/demoteChatMember"
            data = {"chat_id": str(chat_id), "user_id": user_id}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error demoting chat member for {platform}: {e}")
        return False

async def pin_chat_message(platform: str, chat_id: str, message_id: int, disable_notification: bool = False) -> bool:
    """
    سنجاق کردن پیام برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=disable_notification
            )
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=disable_notification
            )
            return True
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/pinChatMessage"
            data = {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "disable_notification": disable_notification
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error pinning chat message for {platform}: {e}")
        return False

async def unpin_chat_message(platform: str, chat_id: str, message_id: int = None) -> bool:
    """
    برداشتن سنجاق پیام برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            if message_id:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
            else:
                await bot.unpin_all_chat_messages(chat_id=chat_id)
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            if message_id:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
            else:
                await bot.unpin_all_chat_messages(chat_id=chat_id)
            return True
        
        elif platform == 'ita':
            if message_id:
                url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/unpinChatMessage"
                data = {"chat_id": str(chat_id), "message_id": message_id}
            else:
                url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/unpinAllChatMessages"
                data = {"chat_id": str(chat_id)}
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error unpinning chat message for {platform}: {e}")
        return False

async def edit_message_text(platform: str, chat_id: str, message_id: int, text: str, parse_mode: str = "HTML", reply_markup=None) -> bool:
    """
    ویرایش متن پیام برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/editMessageText"
            data = {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup.to_dict()) if hasattr(reply_markup, 'to_dict') else json.dumps(reply_markup)
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error editing message text for {platform}: {e}")
        return False

async def edit_message_caption(platform: str, chat_id: str, message_id: int, caption: str, parse_mode: str = "HTML", reply_markup=None) -> bool:
    """
    ویرایش کپشن پیام برای همه پلتفرم‌ها
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            return True
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/editMessageCaption"
            data = {
                "chat_id": str(chat_id),
                "message_id": message_id,
                "caption": caption,
                "parse_mode": parse_mode
            }
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup.to_dict()) if hasattr(reply_markup, 'to_dict') else json.dumps(reply_markup)
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                return result.get('ok', False)
            return False
        
        return False
    except Exception as e:
        logger.error(f"Error editing message caption for {platform}: {e}")
        return False

async def send_poll(platform: str, chat_id: str, question: str, options: List[str], is_anonymous: bool = True, poll_type: str = "regular", allows_multiple_answers: bool = False, correct_option_id: int = None, explanation: str = None, open_period: int = None, close_date: int = None) -> Tuple[bool, int]:
    """
    ارسال نظرسنجی برای همه پلتفرم‌ها
    Returns: (success, message_id)
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            message = await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=is_anonymous,
                type=poll_type,
                allows_multiple_answers=allows_multiple_answers,
                correct_option_id=correct_option_id,
                explanation=explanation,
                open_period=open_period,
                close_date=close_date
            )
            return True, message.message_id
        
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            message = await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=is_anonymous,
                type=poll_type,
                allows_multiple_answers=allows_multiple_answers,
                correct_option_id=correct_option_id,
                explanation=explanation,
                open_period=open_period,
                close_date=close_date
            )
            return True, message.message_id
        
        elif platform == 'ita':
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/sendPoll"
            data = {
                "chat_id": str(chat_id),
                "question": question,
                "options": json.dumps(options),
                "is_anonymous": is_anonymous,
                "type": poll_type,
                "allows_multiple_answers": allows_multiple_answers
            }
            if correct_option_id is not None:
                data["correct_option_id"] = correct_option_id
            if explanation:
                data["explanation"] = explanation
            if open_period:
                data["open_period"] = open_period
            if close_date:
                data["close_date"] = close_date
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    message_id = result.get('result', {}).get('message_id', 0)
                    return True, message_id
            return False, 0
        
        return False, 0
    except Exception as e:
        logger.error(f"Error sending poll for {platform}: {e}")
        return False, 0

async def test_ita_member_count(chat_id: str) -> dict:
    """
    تست دریافت تعداد اعضای چت از ایتا با جزئیات کامل
    """
    try:
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatMemberCount"
        data = {"chat_id": str(chat_id)}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"[ITA TEST] Getting member count for chat {chat_id} via {url}")
        logger.info(f"[ITA TEST] Request data: {data}")
        
        response = requests.post(url, data=data, headers=headers, timeout=30)
        logger.info(f"[ITA TEST] Response status: {response.status_code}")
        logger.info(f"[ITA TEST] Response text: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"[ITA TEST] Parsed result: {result}")
            return {
                'success': True,
                'status_code': response.status_code,
                'response': result,
                'member_count': result.get('result', 0) if result.get('ok') else 0
            }
        else:
            return {
                'success': False,
                'status_code': response.status_code,
                'response': response.text,
                'member_count': 0
            }
            
    except Exception as e:
        logger.error(f"[ITA TEST] Error: {e}")
        return {
            'success': False,
            'error': str(e),
            'member_count': 0
        }

async def update_ita_chat_info_from_response(chat_id: str, chat_info: dict):
    """
    به‌روزرسانی اطلاعات چت ایتا از پاسخ API
    """
    try:
        # استخراج اطلاعات مفید از پاسخ
        chat_type = chat_info.get('type', 'unknown')
        chat_title = chat_info.get('title', '')
        chat_username = chat_info.get('username', '')
        
        # اگر title خالی است و username موجود است، از username استفاده کنیم
        if not chat_title and chat_username:
            chat_title = f"@{chat_username}"
            logger.info(f"[ITA] Using username as title: {chat_title}")
        
        logger.info(f"[ITA] Updating chat info for {chat_id}: type={chat_type}, title={chat_title}, username={chat_username}")
        
        # به‌روزرسانی جدول chats
        db_execute("""
            UPDATE chats 
            SET name = ?, username = ?, last_active = datetime('now')
            WHERE chat_id = ? AND platform = 'ita'
        """, (chat_title, chat_username, chat_id))
        
        # اگر چت وجود نداشت، آن را اضافه کن
        if db_fetchone("SELECT 1 FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id,)) is None:
            db_execute("""
                INSERT INTO chats (chat_id, chat_type, platform, name, username, created_at, last_active, is_active)
                VALUES (?, ?, 'ita', ?, ?, datetime('now'), datetime('now'), 1)
            """, (chat_id, chat_type, chat_title, chat_username))
            logger.info(f"[ITA] Added new chat {chat_id} to database")
        
        logger.info(f"[ITA] Successfully updated chat info for {chat_id}")
        
    except Exception as e:
        logger.error(f"Error updating ITA chat info: {e}")

async def force_update_ita_chat_names():
    """
    به‌روزرسانی اجباری نام‌های چت‌های ایتا در دیتابیس
    """
    try:
        # دریافت تمام چت‌های ایتا که نام ندارند یا نام خالی دارند
        ita_chats = db_fetchall("""
            SELECT chat_id, name, username 
            FROM chats 
            WHERE platform = 'ita' 
            AND (name IS NULL OR name = '' OR name LIKE 'کانال ایتا%')
        """)
        
        logger.info(f"[ITA] Found {len(ita_chats)} ITA chats to update")
        
        updated_count = 0
        for chat in ita_chats:
            chat_id = chat['chat_id']
            try:
                # دریافت اطلاعات جدید
                chat_info = await get_ita_chat_info_simple(chat_id)
                if chat_info and chat_info.get('title'):
                    # به‌روزرسانی نام در دیتابیس
                    db_execute("""
                        UPDATE chats 
                        SET name = ?, username = ?, last_active = datetime('now')
                        WHERE chat_id = ? AND platform = 'ita'
                    """, (chat_info['title'], chat_info.get('username', ''), chat_id))
                    
                    logger.info(f"[ITA] Updated chat {chat_id}: {chat_info['title']}")
                    updated_count += 1
                else:
                    logger.warning(f"[ITA] Could not get info for chat {chat_id}")
                    
            except Exception as e:
                logger.error(f"[ITA] Error updating chat {chat_id}: {e}")
        
        logger.info(f"[ITA] Successfully updated {updated_count} chat names")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error force updating ITA chat names: {e}")
        return 0

async def get_ita_chat_member_count(chat_id: str) -> int:
    """
    دریافت تعداد اعضای چت از ایتا با روش‌های مختلف
    ابتدا از دیتابیس، سپس scraping، و در نهایت مقدار پیش‌فرض
    """
    try:
        # 1. ابتدا سعی می‌کنیم snapshot روزانه را بگیریم (ساعت 1 صبح)
        daily_metrics = db_fetchone("""
            SELECT members_count FROM chats_metrics 
            WHERE chat_id = ? AND platform = 'ita' AND is_daily_snapshot = 1
            ORDER BY date_key DESC LIMIT 1
        """, (chat_id,))
        
        # اگر snapshot روزانه موجود نباشد، آخرین مقدار را بگیر
        if not daily_metrics:
            latest_metrics = db_fetchone("""
                SELECT members_count FROM chats_metrics 
                WHERE chat_id = ? AND platform = 'ita' 
                ORDER BY date_key DESC LIMIT 1
            """, (chat_id,))
        else:
            latest_metrics = daily_metrics
        
        if latest_metrics and latest_metrics['members_count']:
            member_count = latest_metrics['members_count']
            logger.info(f"[ITA] Using cached member count for {chat_id}: {member_count}")
            return member_count
        
        # 2. تلاش برای scraping از صفحه عمومی (اگر chat_id یک username است)
        scraped_count = await _scrape_ita_member_count(chat_id)
        if scraped_count > 0:
            # ذخیره در دیتابیس
            date_key = time.strftime('%Y-%m-%d')
            db_execute("""
                INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                VALUES (?, 'ita', ?, ?)
            """, (chat_id, date_key, scraped_count))
            
            logger.info(f"[ITA] Got scraped member count for {chat_id}: {scraped_count}")
            return scraped_count
        
        # 3. استفاده از مقدار پیش‌فرض
        chat_info = db_fetchone("SELECT chat_type FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id,))
        if chat_info:
            chat_type = chat_info['chat_type']
            if chat_type == 'channel':
                default_count = 2  # کانال معمولاً 2 عضو دارد
            elif chat_type == 'group':
                default_count = 3  # گروه معمولاً 3 عضو دارد
            else:
                default_count = 1  # private = 1 عضو
        else:
            default_count = 2  # پیش‌فرض برای کانال
        
        # ذخیره مقدار پیش‌فرض در جدول metrics
        date_key = time.strftime('%Y-%m-%d')
        db_execute("""
            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
            VALUES (?, 'ita', ?, ?)
        """, (chat_id, date_key, default_count))
        
        logger.info(f"[ITA] Using and storing default member count for {chat_id}: {default_count}")
        return default_count
            
    except Exception as e:
        logger.error(f"Error getting ITA member count: {e}")
        return 2  # پیش‌فرض

async def _scrape_ita_member_count(chat_id: str) -> int:
    """
    استخراج تعداد اعضا از صفحه عمومی کانال/گروه ایتا با بهبودهای بیشتر
    """
    try:
        # بررسی اینکه آیا chat_id یک username است یا نه
        if chat_id.startswith('-') or chat_id.isdigit():
            # chat_id عددی است، scraping امکان‌پذیر نیست
            return 0
        
        # حذف @ از ابتدای username اگر وجود دارد
        username = chat_id.lstrip('@')
        
        import requests
        import re
        
        # تلاش با URL های مختلف
        urls_to_try = [
            f"https://eitaa.com/{username}",
            f"https://eitaa.com/c/{username}",
            f"https://eitaa.com/channel/{username}",
            f"https://eitaa.com/chat/{username}",
            f"https://eitaa.com/{username}/",
            f"https://eitaa.com/@{username}"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fa,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200:
                    content = response.text
                    
                    # الگوهای مختلف برای تعداد اعضا با بهبود
                    patterns = [
                        r'(\d+)\s*عضو',
                        r'(\d+)\s*member',
                        r'member.*?(\d+)',
                        r'(\d+)\s*نفر',
                        r'(\d+)\s*مشترک',
                        r'(\d+)\s*فالوور',
                        r'(\d+)\s*subscriber',
                        r'subscriber.*?(\d+)',
                        r'(\d+)\s*فالو',
                        r'(\d+)\s*follower',
                        r'(\d+)\s*مشترکین',
                        r'(\d+)\s*اعضا',
                        r'(\d+)\s*کاربر',
                        r'(\d+)\s*user',
                        r'(\d+)\s*person',
                        r'(\d+)\s*people'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            try:
                                member_count = int(matches[0])
                                if member_count > 0:
                                    logger.info(f"[ITA] Scraped member count for {username}: {member_count}")
                                    return member_count
                            except ValueError:
                                continue
                    
                    logger.debug(f"[ITA] No member count pattern found for {username} in {url}")
                else:
                    logger.debug(f"[ITA] Scraping failed for {username} at {url}: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.debug(f"[ITA] Failed to scrape {url}: {e}")
                continue
            return 0
            
    except Exception as e:
        logger.debug(f"[ITA] Scraping error for {chat_id}: {e}")
        return 0

async def get_file_content(platform: str, file_id: str) -> Optional[BytesIO]:
    """
    Download a file from the specified platform using its file_id.
    
    Args:
        platform: 'telegram', 'bale', or 'ita'
        file_id: The file_id of the file to download
        
    Returns:
        BytesIO object containing file content or None if download fails
    """
    global telegram_app, bale_app, telegram_bot_loop, bale_bot_loop
    
    if platform == 'telegram':
        bot_instance = telegram_app.bot if telegram_app else None
        source_loop = telegram_bot_loop
    elif platform == 'bale':
        bot_instance = bale_app.bot if bale_app else None
        source_loop = bale_bot_loop
    elif platform == 'ita':
        # ایتا از API مستقیم استفاده می‌کند، نیازی به bot instance ندارد
        bot_instance = None
        source_loop = None
    else:
        return None
        
    if platform != 'ita' and (not bot_instance or not source_loop):
        logger.error(f"[{platform}] Bot instance or loop not available for file download")
        return None
    
    try:
        logger.info(f"[{platform}] Attempting to download file_id: {file_id}")
        
        if platform == 'ita':
            # ایتا فقط گیرنده است، نیازی به دانلود فایل ندارد
            logger.warning(f"[{platform}] Ita is receiver-only, cannot download files")
            return None
        
        async def download_file():
            file = await bot_instance.get_file(file_id)
            logger.info(f"[{platform}] File object retrieved: {file}")
            
            # Fix file_path for Bale platform
            if platform == 'bale' and hasattr(file, 'file_path') and file.file_path:
                if file.file_path.startswith('https://api.telegram.org/'):
                    # Replace telegram API URL with Bale API URL
                    corrected_path = file.file_path.replace('https://api.telegram.org/', 'https://tapi.bale.ai/')
                    logger.info(f"[{platform}] Corrected file path: {corrected_path}")
                    
                    # Download directly from corrected URL using requests
                    import asyncio
                    def sync_download():
                        response = requests.get(corrected_path, timeout=120)
                        if response.status_code == 200:
                            return BytesIO(response.content)
                        else:
                            logger.error(f"[{platform}] HTTP {response.status_code} when downloading from {corrected_path}")
                            raise Exception(f"HTTP {response.status_code}")
                    
                    # Run sync download in executor
                    loop = asyncio.get_running_loop()
                    file_content = await loop.run_in_executor(None, sync_download)
                    file_content.seek(0)
                    return file_content
            
            # Default download method
            file_content = BytesIO()
            await file.download_to_memory(file_content)
            file_content.seek(0)
            return file_content
            
        # Use the source platform's loop for downloading
        current_loop = asyncio.get_running_loop()
        if current_loop != source_loop:
            # Cross-loop download: schedule on source loop and wait
            future = asyncio.run_coroutine_threadsafe(download_file(), source_loop)
            file_content = future.result(timeout=120)
            logger.info(f"[{platform}] File downloaded successfully (cross-loop), size: {file_content.getbuffer().nbytes} bytes")
            return file_content
        else:
            # Same loop
            file_content = await download_file()
            logger.info(f"[{platform}] File downloaded successfully, size: {file_content.getbuffer().nbytes} bytes")
            return file_content
            
    except Exception as e:
        logger.error(f"Error downloading file {file_id} from {platform}: {e}")
        return None


# =================================================================
# --- دیتابیس ---
# =================================================================
def get_db_connection():
    logger.debug(f"[DB] Connecting to database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    logger.debug(f"[DB] Database connection established")
    return conn

def backup_chats_to_backup_db():
    """Backup چت‌ها از دیتابیس اصلی به backup - فقط برای بازیابی در صورت حذف دیتابیس اصلی"""
    try:
        # Connect to main database (multi_bot_platform.db)
        main_conn = sqlite3.connect(DB_FILE)
        main_cursor = main_conn.cursor()
        
        # Connect to backup database (bot_database.db)
        backup_conn = sqlite3.connect('bot_database.db')
        backup_cursor = backup_conn.cursor()
        
        # Create backup tables if they don't exist (including tags column)
        backup_cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            chat_type TEXT NOT NULL,
            name TEXT,
            username TEXT,
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            UNIQUE(chat_id, platform)
        )
        ''')
        
        # Get all chats from main database (including tags)
        main_cursor.execute("SELECT chat_id, platform, chat_type, name, username, tags, created_at, last_active, is_active FROM chats")
        chats = main_cursor.fetchall()
        
        # Clear backup database and insert fresh data
        backup_cursor.execute("DELETE FROM chats")
        
        # Insert all chats from main database to backup (including tags)
        for chat in chats:
            backup_cursor.execute('''
            INSERT INTO chats (chat_id, platform, chat_type, name, username, tags, created_at, last_active, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', chat)
        
        backup_conn.commit()
        
        logger.info(f"✅ Backup completed: {len(chats)} chats backed up from {DB_FILE} to bot_database.db")
        
        main_conn.close()
        backup_conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Backup failed: {str(e)}")
        return False

def restore_chats_from_backup():
    """Restore چت‌ها از backup به دیتابیس اصلی - فقط در صورت حذف دیتابیس اصلی"""
    try:
        # Connect to backup database
        backup_conn = sqlite3.connect('bot_database.db')
        backup_cursor = backup_conn.cursor()
        
        # Connect to main database (multi_bot_platform.db)
        main_conn = sqlite3.connect(DB_FILE)
        main_cursor = main_conn.cursor()
        
        # Create main tables if they don't exist (including tags column)
        main_cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            chat_type TEXT NOT NULL,
            name TEXT,
            username TEXT,
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            UNIQUE(chat_id, platform)
        )
        ''')
        
        # Get all chats from backup database (including tags)
        backup_cursor.execute("SELECT chat_id, platform, chat_type, name, username, tags, created_at, last_active, is_active FROM chats")
        chats = backup_cursor.fetchall()
        
        # Clear main database and restore from backup
        main_cursor.execute("DELETE FROM chats")
        
        # Insert all chats from backup to main database (including tags)
        for chat in chats:
            main_cursor.execute('''
            INSERT INTO chats (chat_id, platform, chat_type, name, username, tags, created_at, last_active, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', chat)
        
        main_conn.commit()
        
        logger.info(f"✅ Restore completed: {len(chats)} chats restored from bot_database.db to {DB_FILE}")
        
        backup_conn.close()
        main_conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Restore failed: {str(e)}")
        return False

def check_user_tag_status(user_id: str, platform: str) -> bool:
    """بررسی اینکه آیا کاربر تگ‌های خود را انتخاب کرده است یا نه"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT tags FROM chats 
                WHERE chat_id = ? AND platform = ? AND chat_type = 'private'
            """, (str(user_id), platform))
            result = cur.fetchone()
            return bool(result and result[0] and result[0].strip())
    except Exception as e:
        logger.error(f"Error checking user tag status: {e}")
        return False

def update_user_tag_status(user_id: str, platform: str, selected_tags: str):
    """به‌روزرسانی وضعیت تگ‌گذاری کاربر"""
    try:
        # استفاده از register_chat که قبلاً تگ‌ها را در جدول chats ذخیره می‌کند
        register_chat(str(user_id), "private", platform, tags=selected_tags)
        logger.info(f"Updated tag status for user {user_id} on {platform}: {selected_tags}")
    except Exception as e:
        logger.error(f"Error updating user tag status: {e}")

def migrate_user_tag_data():
    """انتقال داده‌های تگ‌گذاری کاربران از user_tag_status به chats"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # بررسی وجود جدول user_tag_status
            cur.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='user_tag_status'
            """)
            if not cur.fetchone():
                logger.info("جدول user_tag_status وجود ندارد - انتقال داده‌ها انجام شد")
                return True
            
            # دریافت تمام داده‌های user_tag_status
            cur.execute("""
                SELECT user_id, platform, selected_tags, created_at
                FROM user_tag_status 
                WHERE has_selected_tags = 1 AND selected_tags IS NOT NULL AND selected_tags != ''
            """)
            user_tags = cur.fetchall()
            
            migrated_count = 0
            for user_id, platform, selected_tags, created_at in user_tags:
                try:
                    # بررسی وجود چت در جدول chats
                    cur.execute("""
                        SELECT chat_id FROM chats 
                        WHERE chat_id = ? AND platform = ?
                    """, (user_id, platform))
                    
                    if cur.fetchone():
                        # به‌روزرسانی تگ‌های موجود
                        cur.execute("""
                            UPDATE chats SET tags = ?, last_active = CURRENT_TIMESTAMP
                            WHERE chat_id = ? AND platform = ?
                        """, (selected_tags, user_id, platform))
                    else:
                        # ایجاد چت جدید
                        cur.execute("""
                            INSERT INTO chats (chat_id, platform, chat_type, tags, created_at, last_active, is_active)
                            VALUES (?, ?, 'private', ?, ?, CURRENT_TIMESTAMP, 1)
                        """, (user_id, platform, selected_tags, created_at))
                    
                    migrated_count += 1
                    logger.info(f"Migrated user {user_id} on {platform} with tags: {selected_tags}")
                    
                except Exception as e:
                    logger.error(f"Error migrating user {user_id} on {platform}: {e}")
                    continue
            
            conn.commit()
            logger.info(f"✅ Migration completed: {migrated_count} users migrated from user_tag_status to chats")
            return True
            
    except Exception as e:
        logger.error(f"Error in migrate_user_tag_data: {e}")
        return False

def build_tag_selection_keyboard(platform: str):
    """ایجاد کیبورد انتخاب تگ‌ها برای کاربران جدید"""
    if platform == 'telegram':
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # ایجاد دکمه‌های تگ از 1 تا 22
        keyboard = []
        for i in range(1, 23):
            if i % 3 == 1:  # هر 3 تگ در یک ردیف
                keyboard.append([])
            keyboard[-1].append(InlineKeyboardButton(f"تگ {i}", callback_data=f"select_tag_{i}"))
        
        # دکمه تایید
        keyboard.append([InlineKeyboardButton("✅ تایید انتخاب", callback_data="confirm_tags")])
        
        return InlineKeyboardMarkup(keyboard)
    else:  # Bale
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        # ایجاد دکمه‌های تگ از 1 تا 22
        keyboard = []
        for i in range(1, 23):
            if i % 3 == 1:  # هر 3 تگ در یک ردیف
                keyboard.append([])
            keyboard[-1].append(InlineKeyboardButton(f"تگ {i}", callback_data=f"select_tag_{i}"))
        
        # دکمه تایید
        keyboard.append([InlineKeyboardButton("✅ تایید انتخاب", callback_data="confirm_tags")])
        
        return InlineKeyboardMarkup(keyboard)

def init_db():
    with get_db_connection() as conn:
        # فعال‌سازی WAL mode برای بهتر شدن همزمانی
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        
        conn.execute('''CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT,
            platform TEXT,
            chat_type TEXT,
            created_at TEXT,
            name TEXT,
            username TEXT,
            tags TEXT DEFAULT '',
            last_active TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            member_count INTEGER,
            description TEXT,
            invite_link TEXT,
            PRIMARY KEY (chat_id, platform)
        )''')
        conn.execute('CREATE TABLE IF NOT EXISTS broadcast_batches (batch_id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, platform TEXT, content_preview TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_deleted INTEGER DEFAULT 0)')
        conn.execute('CREATE TABLE IF NOT EXISTS sent_messages (message_id TEXT, chat_id TEXT, batch_id INTEGER, FOREIGN KEY(batch_id) REFERENCES broadcast_batches(batch_id) ON DELETE CASCADE)')
        
        # جدول جلوگیری از ارسال تکراری
        conn.execute('''CREATE TABLE IF NOT EXISTS broadcast_dedupe (
            key TEXT PRIMARY KEY,
            created_at INTEGER
        )''')
        
        # جدول user_tag_status حذف شده - تگ‌گذاری کاربران حالا در جدول chats انجام می‌شود
        
        # جدول ارسال‌های زماندار
        conn.execute('''CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            platforms TEXT NOT NULL,
            scopes TEXT NOT NULL,
            scheduled_time TIMESTAMP NOT NULL,
            solar_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            job_id TEXT,
            repeat_type TEXT DEFAULT 'once',
            repeat_interval INTEGER DEFAULT 0,
            last_sent TIMESTAMP,
            total_sent INTEGER DEFAULT 0,
            send_to_tagged BOOLEAN DEFAULT 0,
            tag_filter TEXT DEFAULT '',
            content_type TEXT DEFAULT 'text',
            content_data TEXT,
            pin_message BOOLEAN DEFAULT 0
        )''')
        
        # مهاجرت ستون های جدید برای آمار/گزارش بهتر (فقط برای دیتابیس‌های قدیمی)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info('chats')").fetchall()]
            
            # بررسی و اضافه کردن ستون‌های مورد نیاز برای scheduled_broadcasts
            scheduled_cols = [r[1] for r in conn.execute("PRAGMA table_info('scheduled_broadcasts')").fetchall()]
            
            # اضافه کردن ستون title اگر وجود ندارد
            if 'title' not in scheduled_cols:
                conn.execute("ALTER TABLE scheduled_broadcasts ADD COLUMN title TEXT")
                logger.info("Added title column to scheduled_broadcasts table")
            
            # اضافه کردن ستون‌های دیگر اگر وجود ندارند
            required_columns = [
                ('message', 'TEXT'),
                ('platforms', 'TEXT'),
                ('platform', 'TEXT'),  # ستون platform برای سازگاری
                ('scopes', 'TEXT'),
                ('solar_date', 'TEXT'),
                ('send_to_tagged', 'BOOLEAN DEFAULT 0'),
                ('tag_filter', 'TEXT DEFAULT ""'),
                ('content_type', 'TEXT DEFAULT "text"'),
                ('content_data', 'TEXT'),
                ('pin_message', 'BOOLEAN DEFAULT 0'),
                ('content_text', 'TEXT'),
                ('is_recurring', 'INTEGER DEFAULT 0'),
                ('recurring_pattern', 'TEXT'),
                ('executed_at', 'TIMESTAMP'),
                ('notification_message_id', 'INTEGER')
            ]
            
            for col_name, col_type in required_columns:
                if col_name not in scheduled_cols:
                    conn.execute(f"ALTER TABLE scheduled_broadcasts ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added {col_name} column to scheduled_broadcasts table")
            if 'created_at' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN created_at TEXT")
            if 'name' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN name TEXT")
            if 'username' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN username TEXT")
            if 'tags' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN tags TEXT DEFAULT ''")
            if 'last_active' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN last_active TIMESTAMP")
                # به‌روزرسانی رکوردهای موجود
                conn.execute("UPDATE chats SET last_active = datetime('now') WHERE last_active IS NULL")
            if 'is_active' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN is_active INTEGER DEFAULT 1")
            if 'member_count' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN member_count INTEGER")
            if 'description' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN description TEXT")
            if 'invite_link' not in cols:
                conn.execute("ALTER TABLE chats ADD COLUMN invite_link TEXT")
            
            # مهاجرت جدول scheduled_broadcasts
            try:
                scheduled_cols = [r[1] for r in conn.execute("PRAGMA table_info('scheduled_broadcasts')").fetchall()]
                if 'executed_at' not in scheduled_cols:
                    conn.execute("ALTER TABLE scheduled_broadcasts ADD COLUMN executed_at TIMESTAMP")
                if 'notification_message_id' not in scheduled_cols:
                    conn.execute("ALTER TABLE scheduled_broadcasts ADD COLUMN notification_message_id INTEGER")
            except sqlite3.Error as e:
                logger.warning(f"DB migration warning (adding columns to scheduled_broadcasts): {e}")
            
            # جدول ذخیره روزانه تعداد اعضا
            conn.execute("CREATE TABLE IF NOT EXISTS chats_metrics (chat_id TEXT, platform TEXT, date_key TEXT, members_count INTEGER, is_daily_snapshot BOOLEAN DEFAULT 0, PRIMARY KEY (chat_id, platform, date_key))")
            
            # اضافه کردن ستون is_daily_snapshot اگر موجود نباشد
            try:
                metrics_cols = [r[1] for r in conn.execute("PRAGMA table_info('chats_metrics')").fetchall()]
                if 'is_daily_snapshot' not in metrics_cols:
                    conn.execute("ALTER TABLE chats_metrics ADD COLUMN is_daily_snapshot BOOLEAN DEFAULT 0")
                    logger.info("Added is_daily_snapshot column to chats_metrics table")
            except sqlite3.Error as e:
                logger.warning(f"DB migration warning (adding is_daily_snapshot column): {e}")
            
            # جدول آمار پست‌ها و بازدید
            conn.execute("""CREATE TABLE IF NOT EXISTS channel_posts_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                message_id TEXT NOT NULL,
                post_date TIMESTAMP NOT NULL,
                content_type TEXT,
                content_preview TEXT,
                views_count INTEGER DEFAULT 0,
                forwards_count INTEGER DEFAULT 0,
                reactions_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, platform, message_id)
            )""")
            
            # جدول ردیابی اعضای یکتا
            conn.execute("""CREATE TABLE IF NOT EXISTS unique_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                is_bot INTEGER DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, platform)
            )""")
            
            # جدول عضویت در چت‌ها
            conn.execute("""CREATE TABLE IF NOT EXISTS chat_memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, platform, chat_id)
            )""")
            # جدول زمان‌بندی ارسال‌ها
            conn.execute("""CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_time TIMESTAMP NOT NULL,
                platform TEXT NOT NULL,
                scopes TEXT NOT NULL,
                content_text TEXT,
                content_type TEXT,
                content_data TEXT,
                is_recurring INTEGER DEFAULT 0,
                recurring_pattern TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                executed_at TIMESTAMP,
                notification_message_id INTEGER
            )""")
        except sqlite3.Error as e:
            logger.warning(f"DB migration warning (adding columns to chats): {e}")
        
        # ایجاد ایندکس‌ها برای بهبود عملکرد
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_platform_type ON chats(platform, chat_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_metrics_date ON chats_metrics(date_key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_broadcast_batches_timestamp ON broadcast_batches(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_messages_batch ON sent_messages(batch_id)")
            
            # بررسی وجود ستون‌ها قبل از ایجاد ایندکس
            cols = [r[1] for r in conn.execute("PRAGMA table_info('chats')").fetchall()]
            if 'last_active' in cols:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_last_active ON chats(last_active)")
            if 'tags' in cols:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_tags ON chats(tags)")
            if 'is_active' in cols:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_is_active ON chats(is_active)")
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_broadcasts_time ON scheduled_broadcasts(scheduled_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_broadcasts_status ON scheduled_broadcasts(status)")
        except sqlite3.Error as e:
            logger.warning(f"DB index creation warning: {e}")
        
        # مهاجرت ستون is_deleted برای broadcast_batches
        try:
            batch_cols = [r[1] for r in conn.execute("PRAGMA table_info('broadcast_batches')").fetchall()]
            if 'is_deleted' not in batch_cols:
                conn.execute("ALTER TABLE broadcast_batches ADD COLUMN is_deleted INTEGER DEFAULT 0")
        except Exception as e:
            logger.warning(f"Migration error for broadcast_batches table: {e}")
            
        # =================================================================
        # User Authentication Tables
        # =================================================================
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile TEXT UNIQUE NOT NULL,
            full_name TEXT,
            is_verified INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS user_otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mobile TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            is_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attempts INTEGER DEFAULT 0
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS user_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_token TEXT,
            bale_token TEXT,
            ita_token TEXT,
            telegram_owner_id TEXT,
            bale_owner_id TEXT,
            ita_owner_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS user_billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            transaction_id TEXT UNIQUE,
            payping_ref_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS user_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            balance_before INTEGER,
            balance_after INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
        
        # Add admin column to users table
        try:
            user_cols = [r[1] for r in conn.execute("PRAGMA table_info('users')").fetchall()]
            if 'is_admin' not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
                logger.info("Added is_admin column to users table")
        except sqlite3.Error as e:
            logger.warning(f"Migration warning (is_admin column): {e}")
        
        # Indexes for user tables
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_otp_mobile ON user_otp_codes(mobile)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_billing_user ON user_billing(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_billing_ref ON user_billing(payping_ref_id)")
        
        conn.commit()
        
        # انتقال داده‌های تگ‌گذاری کاربران از user_tag_status به chats
        try:
            migrate_user_tag_data()
        except Exception as e:
            logger.error(f"Error during user tag migration: {e}")

def register_chat(chat_id: str, chat_type: str, platform: str, name: Optional[str] = None, 
                  username: Optional[str] = None, tags: Optional[str] = None, member_count: int = 0) -> bool:
    """
    ثبت یا به‌روزرسانی چت در دیتابیس با لاگ‌گیری پیشرفته و مدیریت خطا
    
    Args:
        chat_id: شناسه چت (به صورت رشته ذخیره می‌شود)
        chat_type: نوع چت (channel, group, private, supergroup)
        platform: پلتفرم (telegram, bale, ita)
        name: نام چت (اختیاری)
        username: یوزرنیم چت (اختیاری، بدون @)
        tags: تگ‌های چت (اختیاری، با کاما جدا می‌شوند)
        member_count: تعداد اعضای چت (اختیاری، پیش‌فرض: 0)
    
    Returns:
        bool: True در صورت موفقیت، False در صورت خطا
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[Register Chat {request_id}] ===== STARTING CHAT REGISTRATION =====")
    
    # اعتبارسنجی ورودی‌های اجباری
    if not chat_id:
        logger.error(f"[Register Chat {request_id}] Error: chat_id is required")
        return False
        
    if not chat_type or not isinstance(chat_type, str):
        logger.error(f"[Register Chat {request_id}] Error: chat_type is required and must be a string")
        return False
        
    if not platform or platform.lower() not in ['telegram', 'bale', 'ita']:
        logger.error(f"[Register Chat {request_id}] Error: Invalid platform: {platform}")
        return False
    
    platform = platform.lower()
    chat_id_str = str(chat_id).strip()
    
    logger.info(f"[Register Chat {request_id}] Input - chat_id: '{chat_id_str}' (type: {type(chat_id)}), "
               f"chat_type: '{chat_type}', platform: '{platform}'")
    logger.info(f"[Register Chat {request_id}] Additional info - name: '{name}', "
               f"username: '{username}', tags: '{tags}'")
    
    # نرمال‌سازی نوع چت
    normalized_type = chat_type.lower()
    if normalized_type == 'supergroup':
        normalized_type = 'group'
    elif normalized_type not in ['channel', 'group', 'private']:
        logger.warning(f"[Register Chat {request_id}] Invalid chat type: '{chat_type}'. Defaulting to 'channel'")
        normalized_type = 'channel'
    
    # نرمال‌سازی نام و یوزرنیم
    name = name.strip() if name and isinstance(name, str) else None
    username = username.lstrip('@').strip() if username and isinstance(username, str) else None
    
    # نرمال‌سازی تگ‌ها
    if tags:
        if isinstance(tags, str):
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            tags = ','.join(tag_list) if tag_list else None
        elif not isinstance(tags, (str, type(None))):
            logger.warning(f"[Register Chat {request_id}] Invalid tags format. Expected string or None, got {type(tags)}")
            tags = None
    
    logger.info(f"[Register Chat {request_id}] Normalized - type: '{normalized_type}', "
               f"name: '{name}', username: '{username}', tags: '{tags}'")
    
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            try:
                # بررسی وجود چت در دیتابیس
                logger.info(f"[Register Chat {request_id}] Checking if chat exists - chat_id: {chat_id_str}, platform: {platform}")
                cur.execute("""
                    SELECT chat_id, platform, chat_type, name, username, tags, created_at, is_active
                    FROM chats 
                    WHERE chat_id = ? AND platform = ?
                """, (chat_id_str, platform))
                
                existing_chat = cur.fetchone()
                
                if existing_chat:
                    logger.info(f"[Register Chat {request_id}] Chat exists: {dict(existing_chat)}")
                else:
                    logger.info(f"[Register Chat {request_id}] New chat - Will create new record")
                
                # ایجاد جدول در صورتی که وجود نداشته باشد
                logger.info(f"[Register Chat {request_id}] Ensuring chats table exists")
                cur.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT,
                    platform TEXT,
                    chat_type TEXT,
                    created_at TEXT,
                    name TEXT,
                    username TEXT,
                    tags TEXT,
                    last_active TIMESTAMP,
                    is_active INTEGER,
                    member_count INTEGER,
                    description TEXT,
                    invite_link TEXT,
                    PRIMARY KEY (chat_id, platform)
                )
                ''')
                
                # دریافت created_at موجود یا ایجاد زمان جدید
                created_at = time.strftime('%Y-%m-%d %H:%M:%S')
                if existing_chat and existing_chat['created_at']:
                    created_at = existing_chat['created_at']
                    logger.info(f"[Register Chat {request_id}] Using existing created_at: {created_at}")
                
                # درج یا به‌روزرسانی رکورد
                logger.info(f"[Register Chat {request_id}] Executing INSERT OR UPDATE query")
                
                # پارامترهای کوئری
                params = {
                    'chat_id': chat_id_str,
                    'chat_type': normalized_type,
                    'platform': platform,
                    'created_at': created_at,
                    'name': name,
                    'username': username,
                    'tags': tags,
                    'member_count': member_count,
                    'now': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # ساخت کوئری به صورت دینامیک برای به‌روزرسانی فقط فیلدهای موجود
                update_fields = []
                update_values = []
                
                update_fields.append("chat_type = :chat_type")
                update_fields.append("last_active = datetime(:now)")
                update_fields.append("is_active = 1")
                
                if name is not None:
                    update_fields.append("name = COALESCE(:name, name)")
                if username is not None:
                    update_fields.append("username = COALESCE(:username, username)")
                if tags is not None:
                    update_fields.append("tags = COALESCE(:tags, tags)")
                if member_count is not None and member_count > 0:
                    update_fields.append("member_count = :member_count")
                
                update_clause = ", ".join(update_fields)
                
                query = f"""
                INSERT OR REPLACE INTO chats (
                    chat_id, platform, chat_type, created_at, 
                    name, username, tags, member_count, last_active, is_active
                )
                VALUES (
                    :chat_id, :platform, :chat_type, :created_at,
                    :name, :username, :tags, :member_count, datetime(:now), 1
                )
                """
                
                logger.debug(f"[Register Chat {request_id}] Executing query: {query}")
                logger.debug(f"[Register Chat {request_id}] With params: {params}")
                
                cur.execute(query, params)
                
                logger.info(f"[Register Chat {request_id}] Successfully updated database for chat {chat_id_str}")
                
                # تأیید ثبت در دیتابیس
                cur.execute("""
                    SELECT chat_id, platform, chat_type, name, username, tags, 
                           created_at, last_active, is_active
                    FROM chats 
                    WHERE chat_id = ? AND platform = ?
                """, (chat_id_str, platform))
                
                updated = cur.fetchone()
                
                if updated:
                    logger.info(f"[Register Chat {request_id}] Successfully verified registration: {dict(updated)}")
                    
                    # لاگ تغییرات در صورت آپدیت
                    if existing_chat:
                        changes = []
                        for field in ['name', 'username', 'chat_type', 'tags']:
                            old_val = existing_chat[field]
                            new_val = updated[field]
                            if old_val != new_val:
                                changes.append(f"{field}: '{old_val}' -> '{new_val}'")
                        
                        if changes:
                            logger.info(f"[Register Chat {request_id}] Updated fields: {', '.join(changes)}")
                else:
                    error_msg = "Failed to verify chat registration in database"
                    logger.error(f"[Register Chat {request_id}] {error_msg}")
                    conn.rollback()
                    return False
                
                logger.info(f"[Register Chat {request_id}] Committing transaction")
                conn.commit()
                logger.info(f"[Register Chat {request_id}] Transaction committed successfully")
                
                # ذخیره در فایل backup
                try:
                    save_chat_to_backup(chat_id_str, normalized_type, platform, name, username, tags)
                    logger.info(f"[Register Chat {request_id}] Successfully backed up chat info")
                except Exception as e:
                    logger.error(f"[Register Chat {request_id}] Error backing up chat info: {e}", exc_info=True)
                
                # دریافت نام خودکار برای ایتا (اگر نام موجود نیست)
                if platform == 'ita' and (not name or name.strip() == ''):
                    try:
                        # اجرای async در executor بدون ایجاد event loop جدید
                        import asyncio
                        import concurrent.futures
                        
                        def get_ita_name():
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                result = loop.run_until_complete(get_ita_chat_info_simple(chat_id_str))
                                loop.close()
                                return result
                            except Exception as e:
                                logger.warning(f"[Register Chat {request_id}] Failed to get ITA chat info: {e}")
                                return None
                        
                        # اجرا در thread جداگانه
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(get_ita_name)
                            ita_info = future.result(timeout=15)  # timeout 15 ثانیه
                            
                            if ita_info and ita_info.get('title'):
                                # به‌روزرسانی نام در دیتابیس
                                cur.execute("""
                                    UPDATE chats SET name = ? WHERE chat_id = ? AND platform = ?
                                """, (ita_info['title'], chat_id_str, platform))
                                conn.commit()
                                logger.info(f"[Register Chat {request_id}] Auto-updated ITA chat name: {ita_info['title']}")
                    except Exception as e:
                        logger.warning(f"[Register Chat {request_id}] Error getting ITA chat name: {e}")
                
                # ثبت snapshot فوری برای چت جدید
                try:
                    # اجرای async در executor بدون ایجاد event loop جدید
                    import asyncio
                    import concurrent.futures
                    
                    def run_snapshot():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            result = loop.run_until_complete(
                                create_chat_snapshot(chat_id_str, platform, normalized_type)
                            )
                            loop.close()
                            return result
                        except Exception as e:
                            logger.warning(f"[Register Chat {request_id}] Failed to create snapshot: {e}")
                            return False
                    
                    # اجرا در thread جداگانه
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(run_snapshot)
                        result = future.result(timeout=10)  # timeout 10 ثانیه
                        if result:
                            logger.info(f"[Register Chat {request_id}] Successfully created snapshot for chat {chat_id_str}")
                except Exception as e:
                    logger.warning(f"[Register Chat {request_id}] Error creating snapshot: {e}")
                
                return True
                
            except sqlite3.Error as e:
                error_msg = f"Database error: {str(e)}"
                logger.error(f"[Register Chat {request_id}] {error_msg}", exc_info=True)
                if conn:
                    conn.rollback()
                return False
                
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[Register Chat {request_id}] {error_msg}", exc_info=True)
        return False
    
    finally:
        logger.info(f"[Register Chat {request_id}] ===== REGISTRATION PROCESS COMPLETED =====\n")
    
    logger.info(f"[{platform}] Registered chat {chat_id} with API type: {chat_type}, stored as: {normalized_type}")

def manual_register_chat(chat_id: str, chat_type: str, platform: str, name: Optional[str] = None, 
                       username: Optional[str] = None, tags: Optional[str] = None, member_count: int = 0) -> bool:
    """
    ثبت دستی چت در دیتابیس با لاگ‌گیری پیشرفته و مدیریت خطا
    
    Args:
        chat_id: شناسه چت (به صورت رشته ذخیره می‌شود)
        chat_type: نوع چت (channel, group, private)
        platform: پلتفرم (telegram, bale, ita)
        name: نام چت (اختیاری)
        username: یوزرنیم چت (اختیاری)
        tags: تگ‌های چت (اختیاری، با کاما جدا می‌شوند)
        member_count: تعداد اعضای چت (اختیاری، پیش‌فرض: 0)
        
    Returns:
        bool: True در صورت موفقیت، False در صورت خطا
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[Manual Register {request_id}] ===== STARTING CHAT REGISTRATION =====")
    logger.info(f"[Manual Register {request_id}] Input - chat_id: '{chat_id}' (type: {type(chat_id)}), "
               f"chat_type: '{chat_type}', platform: '{platform}', name: '{name}', "
               f"username: '{username}', tags: '{tags}'")
    
    try:
        # اعتبارسنجی و نرمال‌سازی ورودی‌ها
        if not chat_id or not isinstance(chat_id, (str, int, float)):
            error_msg = f"Invalid chat_id: {chat_id}. Must be a non-empty string or number"
            logger.error(f"[Manual Register {request_id}] {error_msg}")
            return False
            
        if not chat_type or not isinstance(chat_type, str):
            error_msg = f"Invalid chat_type: {chat_type}. Must be a non-empty string"
            logger.error(f"[Manual Register {request_id}] {error_msg}")
            return False
            
        if not platform or not isinstance(platform, str) or platform.lower() not in ['telegram', 'bale', 'ita']:
            error_msg = f"Invalid platform: {platform}. Must be one of: telegram, bale, ita"
            logger.error(f"[Manual Register {request_id}] {error_msg}")
            return False
        
        # نرمال‌سازی نوع چت
        normalized_type = chat_type.lower()
        if normalized_type not in ['channel', 'group', 'private']:
            logger.warning(f"[Manual Register {request_id}] Invalid chat type: {chat_type}. Defaulting to 'channel'")
            normalized_type = 'channel'
        
        # تبدیل chat_id به رشته و حذف فاصله‌های اضافی
        chat_id_str = str(chat_id).strip()
        logger.info(f"[Manual Register {request_id}] Processed chat_id: '{chat_id_str}' (type: {type(chat_id_str)})")
        
        # نرمال‌سازی نام و یوزرنیم
        name = name.strip() if name and isinstance(name, str) else None
        username = username.lstrip('@').strip() if username and isinstance(username, str) else None
        
        # نرمال‌سازی تگ‌ها
        tag_list = []
        if tags:
            if isinstance(tags, str):
                tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
            elif isinstance(tags, (list, tuple, set)):
                tag_list = [str(tag).strip() for tag in tags if tag and str(tag).strip()]
        
        tags_str = ','.join(tag_list) if tag_list else None
        
        logger.info(f"[Manual Register {request_id}] Normalized - name: '{name}', username: '{username}', tags: '{tags_str}'")
        
        # بررسی وجود چت قبل از ثبت
        existing_chat = None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id, platform, chat_type, name, username, tags, is_active 
                FROM chats 
                WHERE chat_id = ? AND platform = ?
            """, (chat_id_str, platform.lower()))
            existing_chat = cursor.fetchone()
            
            if existing_chat:
                logger.warning(f"[Manual Register {request_id}] Chat already exists in database: {dict(existing_chat)}")
            else:
                logger.info(f"[Manual Register {request_id}] No existing chat found, will create new record")
        
        # فراخوانی تابع ثبت اصلی
        logger.info(f"[Manual Register {request_id}] Calling register_chat function")
        register_chat(
            chat_id=chat_id_str,
            chat_type=normalized_type,
            platform=platform.lower(),
            name=name,
            username=username,
            tags=tags_str,
            member_count=member_count
        )
        
        # تأیید ثبت در دیتابیس
        registered_chat = None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id, platform, chat_type, name, username, tags, is_active,
                       created_at, last_active
                FROM chats 
                WHERE chat_id = ? AND platform = ?
            """, (chat_id_str, platform.lower()))
            registered_chat = cursor.fetchone()
        
        if registered_chat:
            logger.info(f"[Manual Register {request_id}] Successfully registered/updated chat: {dict(registered_chat)}")
            
            # لاگ تغییرات در صورت آپدیت
            if existing_chat:
                changes = []
                for field in ['name', 'username', 'chat_type', 'tags']:
                    old_val = existing_chat[field]
                    new_val = registered_chat[field]
                    if old_val != new_val:
                        changes.append(f"{field}: '{old_val}' -> '{new_val}'")
                
                if changes:
                    logger.info(f"[Manual Register {request_id}] Updated fields: {', '.join(changes)}")
            
            logger.info(f"[Manual Register {request_id}] ===== REGISTRATION COMPLETED SUCCESSFULLY =====")
            
            # دریافت نام خودکار برای ایتا (اگر نام موجود نیست)
            if platform.lower() == 'ita' and (not name or name.strip() == ''):
                try:
                    # اجرای async در executor بدون ایجاد event loop جدید
                    import asyncio
                    import concurrent.futures
                    
                    def get_ita_name():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            result = loop.run_until_complete(get_ita_chat_info_simple(chat_id_str))
                            loop.close()
                            return result
                        except Exception as e:
                            logger.warning(f"[Manual Register {request_id}] Failed to get ITA chat info: {e}")
                            return None
                    
                    # اجرا در thread جداگانه
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(get_ita_name)
                        ita_info = future.result(timeout=15)  # timeout 15 ثانیه
                        
                        if ita_info and ita_info.get('title'):
                            # به‌روزرسانی نام در دیتابیس
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE chats SET name = ? WHERE chat_id = ? AND platform = ?
                                """, (ita_info['title'], chat_id_str, platform.lower()))
                                conn.commit()
                                logger.info(f"[Manual Register {request_id}] Auto-updated ITA chat name: {ita_info['title']}")
                except Exception as e:
                    logger.warning(f"[Manual Register {request_id}] Error getting ITA chat name: {e}")
            
            # Update backup database
            try:
                backup_chats_to_backup_db()
                logger.info(f"[Manual Register {request_id}] Backup updated successfully")
            except Exception as e:
                logger.warning(f"[Manual Register {request_id}] Backup update failed: {e}")
            
            return True
        else:
            error_msg = "Failed to verify chat registration in database"
            logger.error(f"[Manual Register {request_id}] {error_msg}")
            return False
            
    except sqlite3.Error as e:
        error_msg = f"Database error while registering chat: {str(e)}"
        logger.error(f"[Manual Register {request_id}] {error_msg}", exc_info=True)
        return False
        
    except Exception as e:
        error_msg = f"Unexpected error while registering chat: {str(e)}"
        logger.error(f"[Manual Register {request_id}] {error_msg}", exc_info=True)
        return False
    
    finally:
        # لاگ نهایی در هر صورت
        logger.info(f"[Manual Register {request_id}] ===== REGISTRATION PROCESS COMPLETED =====\n")

def get_all_chats():
    """
    دریافت تمام چت‌های ثبت شده
    """
    return db_fetchall("SELECT * FROM chats ORDER BY created_at DESC, platform, chat_type")

async def create_chat_snapshot(chat_id: str, platform: str, chat_type: str):
    """
    ایجاد snapshot فوری برای یک چت
    """
    try:
        # دریافت تعداد اعضا از API
        members_count = await get_chat_member_count(chat_id, platform, chat_type)
        
        # ثبت در جدول metrics
        date_key = time.strftime('%Y-%m-%d')
        db_execute("""
            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
            VALUES (?, ?, ?, ?)
        """, (chat_id, platform, date_key, members_count))
        
        logger.info(f"[{platform}] Created snapshot for chat {chat_id}: {members_count} members")
        return True
    except Exception as e:
        logger.error(f"Error creating snapshot for chat {chat_id}: {e}")
        return False

async def get_chat_member_count(chat_id: str, platform: str, chat_type: str) -> int:
    """
    دریافت تعداد اعضای یک چت از API
    """
    try:
        if chat_type == 'private':
            return 1  # کاربر private = 1 عضو
        
        # برای گروه/کانال، از bot instance استفاده کن
        if platform == 'telegram' and 'telegram_app' in globals():
            try:
                bot = telegram_app.bot
                chat_member_count = await asyncio.wait_for(bot.get_chat_member_count(chat_id=int(chat_id)), timeout=10)
                return chat_member_count
            except Exception as e:
                # Silently ignore event loop errors and network errors
                if any(keyword in str(e).lower() for keyword in ["event loop is closed", "network error", "timeout"]):
                    logger.debug(f"Ignoring Telegram member count error for {chat_id}: {e}")
                else:
                    logger.warning(f"Failed to get Telegram member count for {chat_id}: {e}")
                return 1
        elif platform == 'bale' and 'bale_app' in globals():
            try:
                # استفاده از API مستقیم بله به دلیل مشکل python-telegram-bot
                import requests
                url = f"{BALE_API_BASE_URL}{BALE_BOT_TOKEN}/getChatMemberCount"
                data = {"chat_id": int(chat_id)}
                response = requests.post(url, json=data, timeout=10)
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        return result['result']
                logger.warning(f"Failed to get Bale member count for {chat_id}: API returned {response.status_code}")
                return 1
            except Exception as e:
                logger.warning(f"Failed to get Bale member count for {chat_id}: {e}")
                return 1
        elif platform == 'ita':
            try:
                # استفاده از API مستقیم ایتا
                return await get_ita_chat_member_count(chat_id)
            except Exception as e:
                logger.warning(f"Failed to get Ita member count for {chat_id}: {e}")
                return 1
        else:
            return 1
    except Exception as e:
        logger.error(f"Error getting member count for {chat_id}: {e}")
        return 1

def create_snapshots_for_all_chats():
    """
    ایجاد snapshot برای تمام چت‌های موجود
    """
    try:
        chats = get_all_chats()
        success_count = 0
        
        for chat in chats:
            try:
                # اجرای async در executor بدون ایجاد event loop جدید
                import asyncio
                import concurrent.futures
                
                def run_snapshot():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(create_chat_snapshot(chat['chat_id'], chat['platform'], chat['chat_type']))
                        loop.close()
                        return result
                    except Exception as e:
                        logger.warning(f"Failed to create snapshot for chat {chat['chat_id']}: {e}")
                        return False
                
                # اجرا در thread جداگانه
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_snapshot)
                    result = future.result(timeout=10)  # timeout 10 ثانیه
                    if result:
                        success_count += 1
            except Exception as e:
                logger.warning(f"Failed to create snapshot for chat {chat['chat_id']}: {e}")
        
        logger.info(f"Created snapshots for {success_count}/{len(chats)} chats")
        return success_count
    except Exception as e:
        logger.error(f"Error creating snapshots for all chats: {e}")
        return 0

def force_register_all_chats():
    """
    ثبت اجباری تمام چت‌های موجود (برای حل مشکل عدم ثبت)
    """
    try:
        # این تابع باید از bot instance استفاده کند تا چت‌ها را پیدا کند
        # فعلاً فقط چت‌های موجود در دیتابیس را به‌روزرسانی می‌کند
        chats = get_all_chats()
        success_count = 0
        
        for chat in chats:
            try:
                register_chat(chat['chat_id'], chat['chat_type'], chat['platform'], 
                            chat['name'], chat['username'])
                success_count += 1
            except Exception as e:
                logger.error(f"Error re-registering chat {chat['chat_id']}: {e}")
        
        logger.info(f"Force registered {success_count}/{len(chats)} chats")
        return success_count
    except Exception as e:
        logger.error(f"Error force registering all chats: {e}")
        return 0

async def discover_all_chats_from_api(platform: str):
    """
    شناسایی تمام چت‌ها از API (برای تلگرام و بله)
    """
    try:
        if platform == 'telegram' and 'telegram_app' in globals():
            bot = telegram_app.bot
            # تلگرام API محدودیت دارد و نمی‌تواند تمام چت‌ها را لیست کند
            # فقط می‌تواند چت‌هایی که ربات در آن‌ها عضو است را ببیند
            logger.info("Telegram API does not support listing all chats. Use /sync in each group/channel.")
            logger.info("📱 برای تلگرام: در هر گروه/کانال که ربات ادمین است، دستور /sync را ارسال کنید")
            return 0
        elif platform == 'bale' and 'bale_app' in globals():
            bot = bale_app.bot
            # بله API محدودیت دارد و نمی‌تواند تمام چت‌ها را لیست کند
            # فقط می‌تواند چت‌هایی که ربات در آن‌ها عضو است را ببیند
            logger.info("Bale API does not support listing all chats. Use /sync in each group/channel.")
            logger.info("💬 برای بله: در هر گروه/کانال که ربات ادمین است، دستور /sync را ارسال کنید")
            return 0
        elif platform == 'ita':
            # ایتا از API مستقیم استفاده می‌کند
            logger.info("Ita API does not support listing all chats. Use /sync in each group/channel.")
            logger.info("📲 برای ایتا: در هر گروه/کانال که ربات ادمین است، دستور /sync را ارسال کنید")
            return 0
        else:
            logger.warning(f"Bot instance not available for {platform}")
            return 0
    except Exception as e:
        logger.error(f"Error discovering chats from API for {platform}: {e}")
        return 0

def create_bulk_sync_command():
    """
    ایجاد دستور bulk sync برای شناسایی تمام چت‌ها
    """
    try:
        # این تابع یک راهنمای کامل برای sync کردن تمام چت‌ها ارائه می‌دهد
        instructions = """
🔧 راهنمای شناسایی تمام گروه‌ها و کانال‌ها:

📱 تلگرام:
1. در هر گروه/کانال تلگرام که ربات ادمین است، دستور /sync را اجرا کنید
2. یا یک پیام در گروه ارسال کنید (ربات خودکار شناسایی می‌کند)

💬 بله:
1. در هر گروه/کانال بله که ربات ادمین است، دستور /sync را اجرا کنید
2. یا یک پیام در گروه ارسال کنید (ربات خودکار شناسایی می‌کند)

⚠️ نکته مهم:
- API تلگرام و بله اجازه لیست کردن تمام چت‌ها را نمی‌دهد
- باید در هر گروه/کانال جداگانه دستور /sync را اجرا کنید
- یا یک پیام در هر گروه ارسال کنید تا خودکار شناسایی شود

✅ راه حل خودکار:
- هر پیام در گروه/کانال، چت را خودکار ثبت می‌کند
- دیگر نیازی به حذف و اضافه کردن ربات نیست
        """
        return instructions
    except Exception as e:
        logger.error(f"Error creating bulk sync command: {e}")
        return "خطا در ایجاد راهنمای sync"

def get_target_ids_by_scope(scopes: List[str], platform: str) -> Dict[str, Set[str]]:
    target_ids_by_scope = {}
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for scope in scopes:
            # Only select active chats to avoid sending to inactive/duplicate chats
            # Also exclude admin users from the target list
            if scope == 'private':
                # For private chats, exclude admin users
                if platform == 'telegram':
                    cursor.execute("SELECT chat_id FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1 AND chat_id != ?", (scope, platform, str(OWNER_ID)))
                elif platform == 'bale':
                    cursor.execute("SELECT chat_id FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1 AND chat_id != ?", (scope, platform, str(BALE_OWNER_ID)))
                else:
                    cursor.execute("SELECT chat_id FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1", (scope, platform))
            else:
                cursor.execute("SELECT chat_id FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1", (scope, platform))
            ids = {row[0] for row in cursor.fetchall()} # Correctly extract chat_id from sqlite3.Row object
            target_ids_by_scope[scope] = ids
    return target_ids_by_scope

def cleanup_inactive_chats():
    """Clean up inactive chats and mark them as inactive"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Mark chats as inactive if they haven't been active for more than 30 days
            cursor.execute("""
                UPDATE chats 
                SET is_active = 0 
                WHERE last_active < datetime('now', '-30 days') 
                AND is_active = 1
            """)
            affected_rows = cursor.rowcount
            conn.commit()
            if affected_rows > 0:
                logger.info(f"Marked {affected_rows} chats as inactive")
            return affected_rows
    except Exception as e:
        logger.error(f"Error cleaning up inactive chats: {e}")
        return 0

def get_chat_statistics():
    """Get detailed chat statistics for debugging"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get active chat counts by platform and type
            cursor.execute("""
                SELECT platform, chat_type, COUNT(*) as count 
                FROM chats 
                WHERE is_active = 1 
                GROUP BY platform, chat_type 
                ORDER BY created_at DESC, platform, chat_type
            """)
            active_chats = cursor.fetchall()
            
            # Get inactive chat counts by platform and type
            cursor.execute("""
                SELECT platform, chat_type, COUNT(*) as count 
                FROM chats 
                WHERE is_active = 0 
                GROUP BY platform, chat_type 
                ORDER BY created_at DESC, platform, chat_type
            """)
            inactive_chats = cursor.fetchall()
            
            # Get total counts
            cursor.execute("""
                SELECT platform, chat_type, COUNT(*) as count 
                FROM chats 
                GROUP BY platform, chat_type 
                ORDER BY created_at DESC, platform, chat_type
            """)
            total_chats = cursor.fetchall()
            
            return {
                'active': active_chats,
                'inactive': inactive_chats,
                'total': total_chats
            }
    except Exception as e:
        logger.error(f"Error getting chat statistics: {e}")
        return None

def remove_duplicate_chats():
    """Remove duplicate or unnecessary chats based on user requirements"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get all private chats (users) by platform
            cursor.execute("""
                SELECT chat_id, platform, name, username, last_active
                FROM chats 
                WHERE chat_type = 'private' AND is_active = 1
                ORDER BY created_at DESC, platform, last_active DESC
            """)
            private_chats = cursor.fetchall()
            
            removed_count = 0
            
            # Keep only the most recent private chat per platform
            platform_private_chats = {}
            for row in private_chats:
                chat_id, platform, name, username, last_active = row
                if platform not in platform_private_chats:
                    platform_private_chats[platform] = []
                platform_private_chats[platform].append((chat_id, name, username, last_active))
            
            for platform, chats in platform_private_chats.items():
                if len(chats) > 1:
                    # Sort by last_active (most recent first)
                    chats.sort(key=lambda x: x[3], reverse=True)
                    
                    # Keep the first (most recent) and remove the rest
                    for chat_id, name, username, last_active in chats[1:]:
                        cursor.execute("UPDATE chats SET is_active = 0 WHERE chat_id = ? AND platform = ?", (chat_id, platform))
                        removed_count += 1
                        logger.info(f"Marked duplicate private chat as inactive: {platform} - {chat_id} ({name} @{username})")
            
            conn.commit()
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} duplicate private chats")
            else:
                logger.info("No duplicate private chats found")
            
            return removed_count
            
    except Exception as e:
        logger.error(f"Error removing duplicate chats: {e}")
        return 0

def get_broadcast_target_statistics():
    """Get statistics for broadcast targets (excluding admin users)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            platforms = ['telegram', 'bale', 'ita']
            
            for platform in platforms:
                stats[platform] = {}
                for scope in ['private', 'group', 'channel']:
                    if scope == 'private':
                        # Exclude admin users for private chats
                        if platform == 'telegram':
                            cursor.execute("SELECT COUNT(*) FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1 AND chat_id != ?", (scope, platform, str(OWNER_ID)))
                        elif platform == 'bale':
                            cursor.execute("SELECT COUNT(*) FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1 AND chat_id != ?", (scope, platform, str(BALE_OWNER_ID)))
                        else:
                            cursor.execute("SELECT COUNT(*) FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1", (scope, platform))
                    else:
                        cursor.execute("SELECT COUNT(*) FROM chats WHERE chat_type = ? AND platform = ? AND is_active = 1", (scope, platform))
                    
                    count = cursor.fetchone()[0]
                    stats[platform][scope] = count
            
            return stats
            
    except Exception as e:
        logger.error(f"Error getting broadcast target statistics: {e}")
        return None

def fix_bale_user_count():
    """Fix Bale user count by reactivating the non-admin user"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Reactivate the non-admin Bale user that was accidentally deactivated
            cursor.execute("UPDATE chats SET is_active = 1 WHERE chat_id = '1076896238' AND platform = 'bale'")
            conn.commit()
            
            # Check if the update was successful
            cursor.execute("SELECT chat_id, name, username, is_active FROM chats WHERE chat_id = '1076896238' AND platform = 'bale'")
            result = cursor.fetchone()
            
            if result:
                chat_id, name, username, is_active = result
                if is_active:
                    logger.info(f"Successfully reactivated Bale user: {chat_id} ({name} @{username})")
                    return True
                else:
                    logger.warning(f"Failed to reactivate Bale user: {chat_id}")
                    return False
            else:
                logger.warning("Bale user 1076896238 not found in database")
                return False
                
    except Exception as e:
        logger.error(f"Error fixing Bale user count: {e}")
        return False

def db_fetchall(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    try:
        with get_db_connection() as conn: return conn.cursor().execute(query, params).fetchall()
    except sqlite3.Error as e:
        logger.error(f"DB FetchAll Error: {e}")
        return []

def db_fetchone(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    try:
        with get_db_connection() as conn: return conn.cursor().execute(query, params).fetchone()
    except sqlite3.Error as e:
        logger.error(f"DB FetchOne Error: {e}")
        return None

def db_execute(query: str, params: tuple = ()):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"DB Execute Error: {e}")
        return None

def get_chat_name_by_id(chat_id: str, platform: str) -> str:
    """
    دریافت نام کانال/گروه بر اساس شناسه
    """
    try:
        chat_info = db_fetchone(
            "SELECT name, username, chat_type FROM chats WHERE chat_id = ? AND platform = ?", 
            (chat_id, platform)
        )
        if chat_info:
            name = chat_info.get('name', '')
            username = chat_info.get('username', '')
            chat_type = chat_info.get('chat_type', '')
            
            # تعیین نوع چت
            if chat_type == 'channel':
                chat_type_name = 'کانال'
            elif chat_type == 'group':
                chat_type_name = 'گروه'
            else:
                chat_type_name = 'چت'
            
            if name:
                return f"{chat_type_name} {name}" + (f" (@{username})" if username else "")
            elif username:
                return f"{chat_type_name} @{username}"
        
        # اگر اطلاعاتی پیدا نشد، از شناسه استفاده کن
        return f"کانال {chat_id}"
    except Exception:
        return f"کانال {chat_id}"

def generate_detailed_content_info(text: Optional[str] = None, photo_path: Optional[str] = None, 
                                 video_path: Optional[str] = None, document_path: Optional[str] = None,
                                 forward_from_chat_id: Optional[str] = None, 
                                 forward_from_message_id: Optional[int] = None,
                                 original_media_name: Optional[str] = None,
                                 source_platform: Optional[str] = None) -> str:
    """
    تولید اطلاعات جزئی محتوا برای گزارش‌های ارسال
    """
    content_parts = []
    
    # بررسی نوع محتوا
    if forward_from_chat_id:
        # دریافت نام کانال به جای شناسه
        chat_name = get_chat_name_by_id(forward_from_chat_id, source_platform or 'telegram')
        content_parts.append(f"فوروارد پیام از {chat_name}")
        if forward_from_message_id:
            content_parts.append(f"(شناسه پیام: {forward_from_message_id})")
        
        # تشخیص نوع فایل در فوروارد بر اساس مسیر فایل
        if photo_path:
            file_name = original_media_name or os.path.basename(photo_path) if not photo_path.startswith('AgACAg') else 'فایل تصویری'
            content_parts.append(f"نوع فایل: تصویر ({file_name})")
        elif video_path:
            file_name = original_media_name or os.path.basename(video_path) if not video_path.startswith('BAACAg') else 'فایل ویدئویی'
            content_parts.append(f"نوع فایل: ویدئو ({file_name})")
        elif document_path:
            file_name = original_media_name or os.path.basename(document_path) if not document_path.startswith('BQACAg') else 'فایل پیوستی'
            content_parts.append(f"نوع فایل: سند ({file_name})")
        else:
            content_parts.append("نوع فایل: متن")
            
    elif photo_path:
        file_name = original_media_name or os.path.basename(photo_path) if not photo_path.startswith('AgACAg') else 'فایل تصویری'
        content_parts.append(f"نوع فایل: تصویر ({file_name})")
    elif video_path:
        file_name = original_media_name or os.path.basename(video_path) if not video_path.startswith('BAACAg') else 'فایل ویدئویی'
        content_parts.append(f"نوع فایل: ویدئو ({file_name})")
    elif document_path:
        file_name = original_media_name or os.path.basename(document_path) if not document_path.startswith('BQACAg') else 'فایل پیوستی'
        content_parts.append(f"نوع فایل: سند ({file_name})")
    else:
        content_parts.append("نوع فایل: متن")
    
    # اضافه کردن متن
    if text:
        # محدود کردن طول متن برای گزارش
        display_text = text[:100] + "..." if len(text) > 100 else text
        content_parts.append(f"متن: {display_text}")
    
    return " | ".join(content_parts)

def generate_unified_broadcast_report(platform_name: str, sent: int, failed: int, 
                                    detailed_content_info: str) -> str:
    """
    تولید گزارش یکسان برای ارسال‌های انبوه در هر دو پلتفرم
    """
    return f"✅ ارسال به {platform_name} کامل شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}\n📝 محتوا: {detailed_content_info}"

def generate_detailed_stats_report(results: list) -> str:
    """
    تولید آمار دقیق‌تر برای گزارش ارسال زمان‌بندی شده
    """
    if not results:
        return "📊 آمار: هیچ نتیجه‌ای یافت نشد"
    
    report_lines = ["📊 آمار تفصیلی:"]
    
    for result in results:
        platform = result.get('platform', 'unknown')
        detailed_results = result.get('detailed_results', {})
        total_sent = result.get('sent', 0)
        total_failed = result.get('failed', 0)
        
        # نام پلتفرم به فارسی
        platform_names = {
            'telegram': '📱 تلگرام',
            'bale': '💬 بله', 
            'ita': '📱 ایتا'
        }
        platform_display = platform_names.get(platform, f'📱 {platform}')
        
        report_lines.append(f"\n{platform_display}:")
        
        if detailed_results:
            # آمار تفکیک شده بر اساس نوع چت
            for scope, stats in detailed_results.items():
                sent_count = stats.get('sent', 0)
                failed_count = stats.get('failed', 0)
                
                # نام scope به فارسی
                scope_names = {
                    'private': '👤 کاربران',
                    'group': '👥 گروه‌ها', 
                    'channel': '📢 کانال‌ها'
                }
                scope_display = scope_names.get(scope, scope)
                
                # Only show scope stats if there are actual targets
                if sent_count > 0 or failed_count > 0:
                    report_lines.append(f"  {scope_display}: ✅{sent_count} ❌{failed_count}")
        else:
            # اگر detailed_results موجود نباشد، آمار کلی نمایش دهیم
            if total_sent > 0 or total_failed > 0:
                report_lines.append(f"  ✅ موفق: {total_sent}")
                report_lines.append(f"  ❌ ناموفق: {total_failed}")
    
    return "\n".join(report_lines)

async def cleanup_original_temp_files(info: dict):
    """
    پاک کردن فایل‌های موقت اصلی بعد از اتمام همه broadcast ها
    """
    temp_files_to_cleanup = []
    
    # استفاده از فایل temp اصلی ذخیره شده
    original_temp_file = info.get('original_temp_file')
    if original_temp_file and os.path.exists(original_temp_file):
        temp_files_to_cleanup.append(original_temp_file)
    
    # همچنین فایل‌های موقت اصلی از مسیرهای قدیمی
    for file_type in ['image_path', 'video_path', 'document_path']:
        file_path = info.get(file_type)
        if file_path and os.path.exists(file_path):
            # بررسی اینکه آیا این فایل اصلی است (نه کپی شده)
            if not any(f"mbot_{platform}_" in os.path.basename(file_path) for platform in ['telegram', 'bale', 'ita']):
                if file_path not in temp_files_to_cleanup:  # جلوگیری از تکرار
                    temp_files_to_cleanup.append(file_path)
    
    # پاک کردن فایل‌های اصلی
    for temp_file in temp_files_to_cleanup:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                logger.info(f"Cleaned up original temp file after all broadcasts: {temp_file}")
        except Exception as e:
            logger.warning(f"Error cleaning up original temp file {temp_file}: {e}")

async def delete_user_completely(chat_id: str, platform: str):
    """
    حذف کامل کاربر از سیستم - شامل حذف از chats و sent_messages
    """
    try:
        # حذف از جدول chats
        await async_db_execute("DELETE FROM chats WHERE chat_id = ? AND platform = ?", (chat_id, platform))

        # حذف پیام‌های ارسال شده به این کاربر
        await async_db_execute("DELETE FROM sent_messages WHERE chat_id = ? AND platform = ?", (chat_id, platform))

        logger.info(f"Completely deleted user {chat_id} from {platform} - removed from chats and sent_messages")
        return True
    except Exception as e:
        logger.error(f"Error completely deleting user {chat_id} from {platform}: {e}")
        return False

async def send_admin_notification(message: str, platform: str = None):
    """
    ارسال اطلاعیه به ادمین در همه پلتفرم‌ها
    """
    try:
        # ارسال به تلگرام
        if telegram_app and telegram_app.bot:
            try:
                await telegram_app.bot.send_message(
                    chat_id=TELEGRAM_OWNER_ID,
                    text=f"🔔 اطلاعیه جدید:\n\n{message}",
                    parse_mode='HTML'
                )
                logger.info(f"Admin notification sent to Telegram: {message}")
            except Exception as e:
                logger.error(f"Failed to send admin notification to Telegram: {e}")

        # ارسال به بله
        if bale_app and bale_app.bot:
            try:
                await bale_app.bot.send_message(
                    chat_id=BALE_OWNER_ID,
                    text=f"🔔 اطلاعیه جدید:\n\n{message}",
                    parse_mode='HTML'
                )
                logger.info(f"Admin notification sent to Bale: {message}")
            except Exception as e:
                logger.error(f"Failed to send admin notification to Bale: {e}")

    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

def generate_unified_chat_stats() -> str:
    """
    تولید آمار یکسان چت‌ها برای همه پلتفرم‌ها (تلگرام، بله، ایتا)
    """
    # دریافت آمار تلگرام (بدون ادمین)
    telegram_rows = db_fetchall("SELECT chat_type, COUNT(*) as c FROM chats WHERE platform='telegram' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(OWNER_ID),))
    telegram_counts = {r['chat_type']: r['c'] for r in telegram_rows}
    
    # دریافت آمار بله (بدون ادمین)
    bale_rows = db_fetchall("SELECT chat_type, COUNT(*) as c FROM chats WHERE platform='bale' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(BALE_OWNER_ID),))
    bale_counts = {r['chat_type']: r['c'] for r in bale_rows}
    
    # دریافت آمار ایتا
    ita_rows = db_fetchall("SELECT chat_type, COUNT(*) as c FROM chats WHERE platform='ita' AND is_active=1 GROUP BY chat_type")
    ita_counts = {r['chat_type']: r['c'] for r in ita_rows}
    
    # دریافت آخرین تاریخ snapshot
    latest_date = db_fetchone("SELECT MAX(date_key) as latest_date FROM chats_metrics")
    latest_date_str = latest_date['latest_date'] if latest_date and latest_date['latest_date'] else None
    
    # تبدیل تاریخ به شمسی
    if latest_date_str:
        persian_date = latest_date_str
        if jdatetime:
            try:
                y, m, d = map(int, latest_date_str.split('-'))
                persian_date = jdatetime.date.fromgregorian(year=y, month=m, day=d).strftime('%Y/%m/%d')
            except Exception:
                pass
    else:
        persian_date = "هنوز snapshot گرفته نشده"
    
    # دریافت مجموع اعضا از جدول metrics (با fallback به جدول chats)
    telegram_members = db_fetchall("""
        SELECT c.chat_type, SUM(m.members_count) as total_members
        FROM chats_metrics m
        JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
        WHERE m.platform = 'telegram' AND c.chat_type != 'private' AND m.date_key = (
            SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
        )
        GROUP BY c.chat_type
    """)
    telegram_member_counts = {r['chat_type']: r['total_members'] for r in telegram_members}
    
    # اگر metrics خالی است، از جدول chats استفاده کن (هر کاربر = 1 عضو)
    if not telegram_member_counts:
        telegram_member_counts = {chat_type: count for chat_type, count in telegram_counts.items()}
    
    bale_members = db_fetchall("""
        SELECT c.chat_type, SUM(m.members_count) as total_members
        FROM chats_metrics m
        JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
        WHERE m.platform = 'bale' AND c.chat_type != 'private' AND m.date_key = (
            SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
        )
        GROUP BY c.chat_type
    """)
    bale_member_counts = {r['chat_type']: r['total_members'] for r in bale_members}
    
    # اگر metrics خالی است، از جدول chats استفاده کن (هر کاربر = 1 عضو)
    if not bale_member_counts:
        bale_member_counts = {chat_type: count for chat_type, count in bale_counts.items()}
    
    # دریافت آمار اعضای ایتا
    ita_members = db_fetchall("""
        SELECT c.chat_type, SUM(m.members_count) as total_members
        FROM chats_metrics m
        JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
        WHERE m.platform = 'ita' AND c.chat_type != 'private' AND m.date_key = (
            SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
        )
        GROUP BY c.chat_type
    """)
    ita_member_counts = {r['chat_type']: r['total_members'] for r in ita_members}
    
    # اگر metrics خالی است، از جدول chats استفاده کن (هر کاربر = 1 عضو)
    if not ita_member_counts:
        ita_member_counts = {chat_type: count for chat_type, count in ita_counts.items()}
    
    # محاسبه مجموع
    telegram_total = sum(telegram_counts.values())
    bale_total = sum(bale_counts.values())
    ita_total = sum(ita_counts.values())
    grand_total = telegram_total + bale_total + ita_total
    
    # محاسبه مجموع اعضا
    telegram_users = telegram_counts.get('private', 0)
    telegram_groups = telegram_counts.get('group', 0)
    telegram_channels = telegram_counts.get('channel', 0)
    
    bale_users = bale_counts.get('private', 0)
    bale_groups = bale_counts.get('group', 0)
    bale_channels = bale_counts.get('channel', 0)
    
    ita_users = ita_counts.get('private', 0)
    ita_groups = ita_counts.get('group', 0)
    ita_channels = ita_counts.get('channel', 0)
    
    # مجموع اعضا
    total_users = telegram_users + bale_users + ita_users
    total_groups = telegram_groups + bale_groups + ita_groups
    total_channels = telegram_channels + bale_channels + ita_channels
    
    # مجموع اعضا در گروه‌ها و کانال‌ها
    telegram_group_members = telegram_member_counts.get('group', 0)
    telegram_channel_members = telegram_member_counts.get('channel', 0)
    # برای کاربران: تعداد اعضا = تعداد کاربران (هر کاربر یک عضو است)
    telegram_user_members = telegram_users
    
    bale_group_members = bale_member_counts.get('group', 0)
    bale_channel_members = bale_member_counts.get('channel', 0)
    # برای کاربران: تعداد اعضا = تعداد کاربران (هر کاربر یک عضو است)
    bale_user_members = bale_users
    
    ita_group_members = ita_member_counts.get('group', 0)
    ita_channel_members = ita_member_counts.get('channel', 0)
    # برای کاربران: تعداد اعضا = تعداد کاربران (هر کاربر یک عضو است)
    ita_user_members = ita_users
    
    # مجموع کل اعضا (با بررسی None)
    total_group_members = (telegram_group_members or 0) + (bale_group_members or 0) + (ita_group_members or 0)
    total_channel_members = (telegram_channel_members or 0) + (bale_channel_members or 0) + (ita_channel_members or 0)
    total_user_members = (telegram_user_members or 0) + (bale_user_members or 0) + (ita_user_members or 0)
    total_all_members = total_group_members + total_channel_members + total_user_members
    
    # تولید گزارش به صورت ساده
    stats_text = "📊 آمار چت‌ها\n"
    stats_text += f"📅 آخرین snapshot: {persian_date}\n"
    stats_text += "ℹ️ آمار اعضا از آخرین snapshot روزانه (ساعت 1 صبح)\n\n"
    
    # آمار تلگرام
    stats_text += "📱 تلگرام:\n"
    stats_text += f"👤 کاربران: {telegram_users} (اعضا: {telegram_user_members or 0:,})\n"
    stats_text += f"👥 گروه‌ها: {telegram_groups} (اعضا: {telegram_group_members or 0:,})\n"
    stats_text += f"📢 کانال‌ها: {telegram_channels} (اعضا: {telegram_channel_members or 0:,})\n"
    stats_text += f"📊 مجموع تلگرام: {telegram_total}\n\n"
    
    # آمار بله
    stats_text += "💬 بله:\n"
    stats_text += f"👤 کاربران: {bale_users} (اعضا: {bale_user_members or 0:,})\n"
    stats_text += f"👥 گروه‌ها: {bale_groups} (اعضا: {bale_group_members or 0:,})\n"
    stats_text += f"📢 کانال‌ها: {bale_channels} (اعضا: {bale_channel_members or 0:,})\n"
    stats_text += f"📊 مجموع بله: {bale_total}\n\n"
    
    # آمار ایتا
    stats_text += "📱 ایتا:\n"
    stats_text += f"👤 کاربران: {ita_users} (اعضا: {ita_user_members or 0:,})\n"
    stats_text += f"👥 گروه‌ها: {ita_groups} (اعضا: {ita_group_members or 0:,})\n"
    stats_text += f"📢 کانال‌ها: {ita_channels} (اعضا: {ita_channel_members or 0:,})\n"
    stats_text += f"📊 مجموع ایتا: {ita_total}\n\n"
    
    # مجموع کل
    stats_text += "🎯 مجموع کل:\n"
    stats_text += f"👤 کل کاربران: {total_users} (اعضا: {total_user_members:,})\n"
    stats_text += f"👥 کل گروه‌ها: {total_groups} (اعضا: {total_group_members:,})\n"
    stats_text += f"📢 کل کانال‌ها: {total_channels} (اعضا: {total_channel_members:,})\n"
    stats_text += f"📊 مجموع کل چت‌ها: {grand_total}\n"
    stats_text += f"👥 مجموع کل اعضا: {total_all_members:,}"
    
    return stats_text

def save_post_stats_to_db(chat_id: str, platform: str, message_id: str, content_type: str = None, content_preview: str = None):
    """ذخیره آمار پست در کانال‌ها"""
    try:
        db_execute("""
            INSERT OR REPLACE INTO channel_posts_stats 
            (chat_id, platform, message_id, post_date, content_type, content_preview, updated_at)
            VALUES (?, ?, ?, datetime('now'), ?, ?, datetime('now'))
        """, (chat_id, platform, message_id, content_type, content_preview))
        logger.info(f"[{platform}] Post stats saved for message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error saving post stats: {e}")

def update_post_views(chat_id: str, platform: str, message_id: str, views: int, forwards: int = 0, reactions: int = 0):
    """به‌روزرسانی آمار بازدید پست"""
    try:
        db_execute("""
            UPDATE channel_posts_stats 
            SET views_count = ?, forwards_count = ?, reactions_count = ?, updated_at = datetime('now')
            WHERE chat_id = ? AND platform = ? AND message_id = ?
        """, (views, forwards, reactions, chat_id, platform, message_id))
        logger.info(f"[{platform}] Post views updated for message {message_id}: {views} views")
    except Exception as e:
        logger.error(f"Error updating post views: {e}")

def get_post_stats_by_batch(batch_id: int):
    """دریافت آمار پست‌های یک batch"""
    try:
        return db_fetchall("""
            SELECT cps.*, c.name as channel_name, c.username as channel_username
            FROM channel_posts_stats cps
            LEFT JOIN chats c ON c.chat_id = cps.chat_id AND c.platform = cps.platform
            LEFT JOIN sent_messages sm ON sm.chat_id = cps.chat_id AND sm.message_id = cps.message_id
            WHERE sm.batch_id = ?
            ORDER BY cps.post_date DESC
        """, (batch_id,))
    except Exception as e:
        logger.error(f"Error getting post stats by batch: {e}")
        return []

def save_broadcast_to_db(scope_str: str, preview: str, platform: str, messages: List[Tuple[Any, Any]]) -> Optional[int]:
    # Always save broadcast attempt to database, even if no messages were sent
    batch_id = db_execute("INSERT INTO broadcast_batches (scope, content_preview, platform) VALUES (?, ?, ?)", (scope_str, preview, platform))
    if batch_id and messages:
        msg_data = [(str(mid), str(cid), batch_id) for cid, mid in messages]
        try:
            with get_db_connection() as conn:
                conn.cursor().executemany("INSERT OR IGNORE INTO sent_messages (message_id, chat_id, batch_id) VALUES (?, ?, ?)", msg_data)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving sent messages: {e}")
            # Don't delete the batch if there's an error saving messages
    return batch_id

async def async_save_broadcast_to_db(scope_str: str, preview: str, platform: str, messages: List[Tuple[Any, Any]]) -> Optional[int]:
    """
    ذخیره نتایج broadcast به صورت async
    """
    # Always save broadcast attempt to database, even if no messages were sent
    # تبدیل scope_str به string اگر لیست باشد
    scope_str_final = scope_str if isinstance(scope_str, str) else str(scope_str)
    batch_id = await async_db_execute("INSERT INTO broadcast_batches (scope, content_preview, platform) VALUES (?, ?, ?)", (scope_str_final, preview, platform))
    if batch_id and messages:
        msg_data = [(str(mid), str(cid), batch_id) for cid, mid in messages]
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: save_sent_messages_sync(msg_data))
        except Exception as e:
            logger.error(f"Error saving sent messages: {e}")
            # Don't delete the batch if there's an error saving messages
    return batch_id

def save_sent_messages_sync(msg_data: List[Tuple[str, str, int]]):
    """
    ذخیره پیام‌های ارسال شده به صورت sync (برای استفاده در executor)
    """
    try:
        with get_db_connection() as conn:
            conn.cursor().executemany("INSERT OR IGNORE INTO sent_messages (message_id, chat_id, batch_id) VALUES (?, ?, ?)", msg_data)
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error saving sent messages: {e}")
        raise

def delete_batch_from_db(batch_id: int):
    db_execute("DELETE FROM broadcast_batches WHERE batch_id = ?", (batch_id,))

# =================================================================
# --- توابع کمکی ساخت منوها ---
# =================================================================
def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str): text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def build_telegram_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚀 ارسال انبوه", callback_data="menu_broadcast")],
        [InlineKeyboardButton("📅 صف انتشار", callback_data="menu_scheduling_queue")],
        [InlineKeyboardButton("📊 آمار چت‌ها", callback_data="menu_list")],
        [InlineKeyboardButton("👑 مدیریت ادمین", callback_data="menu_admin_panel")],
        [InlineKeyboardButton("🗑 تاریخچه ارسال", callback_data="menu_delete_history")],
        [InlineKeyboardButton("📊 گزارش جامع", callback_data="comprehensive_report_start")],
        [InlineKeyboardButton("💡 راهنما", callback_data="menu_about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_bale_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚀 ارسال انبوه", callback_data="menu_broadcast")],
        [InlineKeyboardButton("📅 صف انتشار", callback_data="menu_scheduling_queue")],
        [InlineKeyboardButton("📊 آمار چت‌ها", callback_data="menu_list")],
        [InlineKeyboardButton("👑 مدیریت ادمین", callback_data="menu_admin_panel")], # شامل این دکمه برای یکسانی در UI
        [InlineKeyboardButton("🗑 تاریخچه ارسال", callback_data="menu_delete_history")],
        [InlineKeyboardButton("📊 گزارش جامع", callback_data="comprehensive_report_start")],
        [InlineKeyboardButton("💡 راهنما", callback_data="menu_about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_scope_keyboard_telegram(selected_scopes: list) -> InlineKeyboardMarkup:
    options = {"private": "👤 کاربران", "group": "👥 گروه‌ها", "channel": "📢 کانال‌ها"}
    row = [InlineKeyboardButton(f"{'✅ ' if scope in selected_scopes else ''}{text}", callback_data=f"togglescope_{scope}") for scope, text in options.items()]
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("✅ انتخاب همه", callback_data="select_all_scopes")],
        [InlineKeyboardButton("🚀 تایید و ادامه", callback_data="confirm_scope")],
        [InlineKeyboardButton("🔙 لغو", callback_data="broadcast_cancel")]
    ])

def generate_scope_keyboard_bale(selected_scopes: list) -> InlineKeyboardMarkup:
    options = {"private": "👤 کاربران", "group": "👥 گروه‌ها", "channel": "📢 کانال‌ها"}
    row = [InlineKeyboardButton(f"{'✅ ' if scope in selected_scopes else ''}{text}", callback_data=f"togglescope_{scope}") for scope, text in options.items()]
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton("✅ انتخاب همه", callback_data="select_all_scopes")],
        [InlineKeyboardButton("🚀 تایید و ادامه", callback_data="confirm_scope")],
        [InlineKeyboardButton("🔙 لغو", callback_data="broadcast_cancel")]
    ])

def build_platform_select_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("تلگرام", callback_data="select_platform_telegram")],
        [InlineKeyboardButton("بله", callback_data="select_platform_bale")],
        [InlineKeyboardButton("ایتا", callback_data="select_platform_ita")],
        [InlineKeyboardButton("هر سه", callback_data="select_platform_all")],
        [InlineKeyboardButton("🔙 لغو", callback_data="broadcast_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_scheduling_keyboard() -> InlineKeyboardMarkup:
    """
    ایجاد منوی زمان‌بندی ارسال
    """
    keyboard = [
        [InlineKeyboardButton("🚀 همین الان", callback_data="schedule_now")],
        [InlineKeyboardButton("⏰ 1 ساعت بعد", callback_data="schedule_1h")],
        [InlineKeyboardButton("⏰ 2 ساعت بعد", callback_data="schedule_2h")],
        [InlineKeyboardButton("📅 1 روز بعد", callback_data="schedule_1d")],
        [InlineKeyboardButton("📅 انتخاب تاریخ و زمان", callback_data="schedule_custom")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="broadcast_cancel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_scheduling_queue_keyboard() -> InlineKeyboardMarkup:
    """
    ایجاد منوی صف انتشار
    """
    keyboard = [
        [InlineKeyboardButton("📅 امروز", callback_data="queue_today")],
        [InlineKeyboardButton("📅 فردا", callback_data="queue_tomorrow")],
        [InlineKeyboardButton("📅 دو روز بعد", callback_data="queue_day_after")],
        [InlineKeyboardButton("📅 این هفته", callback_data="queue_this_week")],
        [InlineKeyboardButton("📋 کل لیست انتشار", callback_data="queue_all")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# =================================================================
# --- عملکرد ارسال: عمومی برای هر دو پلتفرم ---
# =================================================================
async def perform_broadcast_async(app: TelegramApplication, scopes: List[str], platform: str, text: Optional[str] = None, 
                               photo_path: Optional[str] = None, video_path: Optional[str] = None, 
                               document_path: Optional[str] = None, owner_id: int = None,
                               forward_from_chat_id: Optional[str] = None, 
                               forward_from_message_id: Optional[int] = None,
                               source_platform: Optional[str] = None,
                               original_media_name: Optional[str] = None,
                               original_file_id: Optional[str] = None,
                               pin_message: bool = False,
                               target_chats: Optional[Dict[str, List[str]]] = None):
    """
    Perform a broadcast to multiple chats with support for cross-platform file transfers.
    
    Args:
        app: The TelegramApplication instance
        scopes: List of scopes to send to (e.g., ['private', 'group', 'channel'])
        platform: Target platform ('telegram' or 'bale')
        text: Optional text message
        photo_path: Path to photo or file_id
        video_path: Path to video or file_id
        document_path: Path to document or file_id
        owner_id: ID of the user who initiated the broadcast
        forward_from_chat_id: Chat ID to forward message from
        forward_from_message_id: Message ID to forward
        source_platform: Platform where the file was originally uploaded ('telegram' or 'bale')
        original_media_name: Optional original media name for the file
        original_file_id: Original file_id from the source platform for cross-platform transfers
    """
    logger.info(f"[{platform}] Starting broadcast with scopes: {scopes}")
    logger.info(f"[{platform}] Content - text: {bool(text)}, photo: {bool(photo_path)}, video: {bool(video_path)}, document: {bool(document_path)}")
    logger.info(f"[{platform}] Forward - from_chat: {forward_from_chat_id}, message_id: {forward_from_message_id}")
    
    # Dedupe guard to avoid repeated broadcasts
    dedupe_key = build_broadcast_key(
        platform,
        text,
        photo_path,
        video_path,
        document_path,
        forward_from_chat_id,
        forward_from_message_id,
        source_platform
    )
    if is_duplicate_broadcast(dedupe_key):
        logger.info(f"[{platform}] Duplicate broadcast detected within TTL. Skipping.")
        return {'sent': 0, 'failed': 0, 'batch_id': None, 'platform': platform, 'content_preview': 'duplicate-skipped'}
    
    # Semaphore for controlling concurrency (max 30 concurrent requests)
    semaphore = asyncio.Semaphore(30)
    
    # برای ایتا، app برابر None است
    bot_instance = app.bot if app else None
    
    # اگر target_chats مشخص شده باشد، از آن استفاده کن، در غیر این صورت از scopes استفاده کن
    if target_chats:
        target_ids_by_scope = target_chats
        logger.info(f"[{platform}] Using target_chats for broadcast: {target_ids_by_scope}")
    else:
        target_ids_by_scope = get_target_ids_by_scope(scopes, platform)
        logger.info(f"[{platform}] Found target IDs: {target_ids_by_scope}")
    
    detailed_results = {scope: {'sent': 0, 'failed': 0} for scope in target_ids_by_scope.keys()}
    all_sent_info, total_sent, total_failed = [], 0, 0
    downloaded_files = {}  # Cache for downloaded files

    if not any([text, photo_path, video_path, document_path, forward_from_chat_id]):
        return {"error": "No content provided for broadcast."}

    # Generate detailed content info for reports
    detailed_content_info = generate_detailed_content_info(
        text=text,
        photo_path=photo_path,
        video_path=video_path,
        document_path=document_path,
        forward_from_chat_id=forward_from_chat_id,
        forward_from_message_id=forward_from_message_id,
        original_media_name=original_media_name,
        source_platform=source_platform
    )
    
    # Determine content type for preview (shorter version for database)
    preview_content = text if text else ""
    if photo_path: 
        preview_content = f"تصویر: {os.path.basename(photo_path) if not photo_path.startswith('AgACAg') else 'فایل تصویری'}" + (f" (کپشن: {text[:50]}{'...' if text and len(text)>50 else ''})" if text else "")
    elif video_path: 
        preview_content = f"ویدئو: {os.path.basename(video_path) if not video_path.startswith('BAACAg') else 'فایل ویدئویی'}" + (f" (کپشن: {text[:50]}{'...' if text and len(text)>50 else ''})" if text else "")
    elif document_path: 
        preview_content = f"فایل: {os.path.basename(document_path) if not document_path.startswith('BQACAg') else 'فایل پیوستی'}" + (f" (کپشن: {text[:50]}{'...' if text and len(text)>50 else ''})" if text else "")
    elif forward_from_chat_id:
        preview_content = f"فوروارد از پیام {forward_from_message_id}" + (f" (متن: {text[:50]}{'...' if text and len(text)>50 else ''})" if text else "")
    preview = preview_content[:100]  # محدودیت طول پیش‌نمایش در تاریخچه

    temp_files = []
    try:
        # Copy existing temp files for cross-platform broadcasts to prevent cleanup conflicts
        if source_platform and source_platform != platform:
            logger.info(f"[{platform}] Cross-platform broadcast detected - copying temp files to prevent cleanup conflicts")
            import shutil
            import tempfile
            
            # Copy photo file if it exists
            logger.info(f"[{platform}] DEBUG - photo_path: {photo_path}, exists: {os.path.exists(photo_path) if photo_path else 'N/A'}")
            if photo_path and os.path.exists(photo_path):
                logger.info(f"[{platform}] Copying existing photo temp file: {photo_path}")
                temp_dir = tempfile.gettempdir()
                original_filename = os.path.basename(photo_path)
                temp_file = os.path.join(temp_dir, f"mbot_{platform}_photo_{os.urandom(8).hex()}_{original_filename}")
                shutil.copy2(photo_path, temp_file)
                photo_path = temp_file
                temp_files.append(temp_file)
                logger.info(f"[{platform}] Copied photo temp file: {temp_file}")
            else:
                logger.warning(f"[{platform}] Photo file not found or not provided: {photo_path}")
        else:
            # For same-platform broadcasts, add original temp files to cleanup list
            # But only if this is NOT a cross-platform broadcast (source_platform is None)
            if not source_platform:
                if photo_path and os.path.exists(photo_path):
                    temp_files.append(photo_path)
                    logger.info(f"[{platform}] Added original photo temp file to cleanup list: {photo_path}")
                if video_path and os.path.exists(video_path):
                    temp_files.append(video_path)
                    logger.info(f"[{platform}] Added original video temp file to cleanup list: {video_path}")
                if document_path and os.path.exists(document_path):
                    temp_files.append(document_path)
                    logger.info(f"[{platform}] Added original document temp file to cleanup list: {document_path}")
            else:
                logger.info(f"[{platform}] Skipping original temp file cleanup - cross-platform broadcast detected")
        
        # Handle file downloads if needed (for cross-platform transfers)
        logger.info(f"[{platform}] Cross-platform transfer check - source_platform: {source_platform}, target_platform: {platform}, photo_path: {photo_path}, video_path: {video_path}, document_path: {document_path}")
        if source_platform and source_platform != platform:
            try:
                current_loop = asyncio.get_running_loop()
                # Helper function to check if a path is a file_id
                def is_file_id(path):
                    if not isinstance(path, str):
                        return False
                    # Check for known file_id patterns
                    file_id_patterns = ('BAAD', 'AgAC', 'BAAH', 'CAAH')
                    if path.startswith(file_id_patterns):
                        return True
                    # Additional check: if it's a long string without path separators and doesn't exist as a file
                    if (len(path) > 20 and 
                        not os.path.exists(path) and 
                        not path.startswith(('C:\\', '/', 'http://', 'https://')) and
                        '\\' not in path and '/' not in path):
                        return True
                    return False
                
                if photo_path and not os.path.exists(photo_path) and is_file_id(photo_path):
                    logger.info(f"[{platform}] Cross-platform photo transfer - photo_path: {photo_path}, is_file_id: True")
                    # Get file info to preserve original name and extension
                    file_info = await get_file_info(source_platform, photo_path, 'photo')
                    file_content = await get_file_content(source_platform, photo_path)
                    if file_content:
                        # Use secure temporary file creation
                        original_filename = file_info.get('filename', 'photo.jpg') if file_info else 'photo.jpg'
                        temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_photo_")
                        
                        # Verify file was created successfully
                        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                            photo_path = temp_file
                            temp_files.append(temp_file)
                            logger.info(f"Downloaded photo from {source_platform} for sending on {platform}. Temp file: {temp_file} (size: {os.path.getsize(temp_file)} bytes)")
                            # Small delay to ensure file is fully written
                            await asyncio.sleep(0.1)
                        else:
                            logger.error(f"Failed to create temp file: {temp_file}")
                            raise Exception(f"Failed to create temp file: {temp_file}")
                elif photo_path and os.path.exists(photo_path):
                    logger.info(f"[{platform}] Cross-platform photo transfer - using existing local file: {photo_path}")
                else:
                    logger.warning(f"[{platform}] Cross-platform photo transfer - photo_path: {photo_path}, exists: {os.path.exists(photo_path) if photo_path else 'N/A'}")
                    # If file doesn't exist, try to get it from the original source
                    if photo_path and not os.path.exists(photo_path):
                        logger.info(f"[{platform}] Attempting to recover photo from original source: {photo_path}")
                        # Use the passed original_file_id parameter first
                        recovery_file_id = original_file_id
                        
                        # If not provided, try to get from other sources
                        if not recovery_file_id:
                            # Try to get from the current user state
                            try:
                                from __main__ import current_user_state
                                key = f"{source_platform}:{user_id}"
                                if key in current_user_state and 'broadcast_info' in current_user_state[key]:
                                    recovery_file_id = current_user_state[key]['broadcast_info'].get('original_file_id')
                            except:
                                pass
                        
                        if recovery_file_id:
                            logger.info(f"[{platform}] Found original file_id: {recovery_file_id}")
                            try:
                                file_info = await get_file_info(source_platform, recovery_file_id, 'photo')
                                file_content = await get_file_content(source_platform, recovery_file_id)
                                if file_content:
                                    original_filename = file_info.get('filename', 'photo.jpg') if file_info else 'photo.jpg'
                                    temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_photo_")
                                    if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                                        photo_path = temp_file
                                        temp_files.append(temp_file)
                                        logger.info(f"[{platform}] Successfully recovered photo from original source: {temp_file}")
                                    else:
                                        logger.error(f"[{platform}] Failed to create temp file from original source: {temp_file}")
                                else:
                                    logger.error(f"[{platform}] Failed to get file content from original source: {recovery_file_id}")
                            except Exception as e:
                                logger.error(f"[{platform}] Error recovering photo from original source: {e}")
                        else:
                            logger.error(f"[{platform}] No original file_id found to recover photo")
                
                if video_path and not os.path.exists(video_path) and is_file_id(video_path):
                    logger.info(f"[{platform}] Cross-platform video transfer - video_path: {video_path}, is_file_id: True")
                    # Get file info to preserve original name and extension
                    file_info = await get_file_info(source_platform, video_path, 'video')
                    file_content = await get_file_content(source_platform, video_path)
                    if file_content:
                        # Use secure temporary file creation
                        original_filename = file_info.get('filename', 'video.mp4') if file_info else 'video.mp4'
                        temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_video_")
                        
                        # Verify file was created successfully
                        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                            video_path = temp_file
                            temp_files.append(temp_file)
                            logger.info(f"Downloaded video from {source_platform} for sending on {platform}. Temp file: {temp_file} (size: {os.path.getsize(temp_file)} bytes)")
                            # Small delay to ensure file is fully written
                            await asyncio.sleep(0.1)
                        else:
                            logger.error(f"Failed to create temp file: {temp_file}")
                            raise Exception(f"Failed to create temp file: {temp_file}")
                elif video_path and os.path.exists(video_path):
                    logger.info(f"[{platform}] Cross-platform video transfer - copying existing local file: {video_path}")
                    # Copy video file for cross-platform broadcast
                    temp_dir = tempfile.gettempdir()
                    original_filename = os.path.basename(video_path)
                    temp_file = os.path.join(temp_dir, f"mbot_{platform}_video_{os.urandom(8).hex()}_{original_filename}")
                    shutil.copy2(video_path, temp_file)
                    video_path = temp_file
                    temp_files.append(temp_file)
                    logger.info(f"[{platform}] Copied video temp file: {temp_file}")
                elif video_path and not os.path.exists(video_path):
                    logger.warning(f"[{platform}] Video file not found for cross-platform transfer: {video_path}")
                    # Try to recover from original file_id if available
                    recovery_file_id = original_file_id
                    if not recovery_file_id:
                        try:
                            from __main__ import current_user_state
                            key = f"{source_platform}:{user_id}"
                            if key in current_user_state and 'broadcast_info' in current_user_state[key]:
                                recovery_file_id = current_user_state[key]['broadcast_info'].get('original_file_id')
                        except:
                            pass
                    
                    if recovery_file_id:
                        logger.info(f"[{platform}] Attempting to recover video from original file_id: {recovery_file_id}")
                        try:
                            file_info = await get_file_info(source_platform, recovery_file_id, 'video')
                            file_content = await get_file_content(source_platform, recovery_file_id)
                            if file_content:
                                original_filename = file_info.get('filename', 'video.mp4') if file_info else 'video.mp4'
                                temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_video_")
                                if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                                    video_path = temp_file
                                    temp_files.append(temp_file)
                                    logger.info(f"[{platform}] Successfully recovered video from original source: {temp_file}")
                                else:
                                    logger.error(f"[{platform}] Failed to create temp file from original source: {temp_file}")
                            else:
                                logger.error(f"[{platform}] Failed to get file content from original source: {recovery_file_id}")
                        except Exception as e:
                            logger.error(f"[{platform}] Error recovering video from original source: {e}")
                    else:
                        logger.error(f"[{platform}] No original file_id found to recover video")
                
                if document_path and not os.path.exists(document_path) and is_file_id(document_path):
                    logger.info(f"[{platform}] Cross-platform document transfer - document_path: {document_path}, is_file_id: True")
                    # Get file info to preserve original name and extension
                    file_info = await get_file_info(source_platform, document_path, 'document')
                    file_content = await get_file_content(source_platform, document_path)
                    if file_content:
                        # Use secure temporary file creation
                        if original_media_name:
                            original_filename = original_media_name
                        elif file_info and file_info.get('filename'):
                            original_filename = file_info['filename']
                        else:
                            # Fallback: detect extension from content
                            detected_ext = detect_file_extension_from_content(file_content.getvalue())
                            if detected_ext == '.bin' and isinstance(document_path, str) and '.' in document_path:
                                detected_ext = os.path.splitext(document_path)[1]
                            original_filename = f"document{detected_ext}"
                        
                        temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_doc_")
                        
                        # Verify file was created successfully
                        if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                            document_path = temp_file
                            temp_files.append(temp_file)
                            logger.info(f"Downloaded document from {source_platform} for sending on {platform}. Temp file: {temp_file} (size: {os.path.getsize(temp_file)} bytes)")
                            # Small delay to ensure file is fully written
                            await asyncio.sleep(0.1)
                        else:
                            logger.error(f"Failed to create temp file: {temp_file}")
                            raise Exception(f"Failed to create temp file: {temp_file}")
                elif document_path and os.path.exists(document_path):
                    logger.info(f"[{platform}] Cross-platform document transfer - copying existing local file: {document_path}")
                    # Copy document file for cross-platform broadcast
                    temp_dir = tempfile.gettempdir()
                    original_filename = os.path.basename(document_path)
                    # حفظ پسوند فایل اصلی
                    file_ext = os.path.splitext(original_filename)[1]
                    temp_file = os.path.join(temp_dir, f"mbot_{platform}_document_{os.urandom(8).hex()}_{original_filename}")
                    shutil.copy2(document_path, temp_file)
                    document_path = temp_file
                    temp_files.append(temp_file)
                    logger.info(f"[{platform}] Copied document temp file: {temp_file}")
                elif document_path and not os.path.exists(document_path):
                    logger.warning(f"[{platform}] Document file not found for cross-platform transfer: {document_path}")
                    # Try to recover from original file_id if available
                    recovery_file_id = original_file_id
                    if not recovery_file_id:
                        try:
                            from __main__ import current_user_state
                            key = f"{source_platform}:{user_id}"
                            if key in current_user_state and 'broadcast_info' in current_user_state[key]:
                                recovery_file_id = current_user_state[key]['broadcast_info'].get('original_file_id')
                        except:
                            pass
                    
                    if recovery_file_id:
                        logger.info(f"[{platform}] Attempting to recover document from original file_id: {recovery_file_id}")
                        try:
                            file_info = await get_file_info(source_platform, recovery_file_id, 'document')
                            file_content = await get_file_content(source_platform, recovery_file_id)
                            if file_content:
                                if original_media_name:
                                    original_filename = original_media_name
                                elif file_info and file_info.get('filename'):
                                    original_filename = file_info['filename']
                                else:
                                    original_filename = 'document.bin'
                                temp_file = create_temp_file_with_cleanup(file_content.getvalue(), original_filename, f"mbot_{platform}_doc_")
                                if os.path.exists(temp_file) and os.path.getsize(temp_file) > 0:
                                    document_path = temp_file
                                    temp_files.append(temp_file)
                                    logger.info(f"[{platform}] Successfully recovered document from original source: {temp_file}")
                                else:
                                    logger.error(f"[{platform}] Failed to create temp file from original source: {temp_file}")
                            else:
                                logger.error(f"[{platform}] Failed to get file content from original source: {recovery_file_id}")
                        except Exception as e:
                            logger.error(f"[{platform}] Error recovering document from original source: {e}")
                    else:
                        logger.error(f"[{platform}] No original file_id found to recover document")
                        
            except Exception as e:
                logger.error(f"Error downloading media from {source_platform}: {e}", exc_info=True)
                # Don't return error immediately, try to send as text if available
                if text:
                    logger.info(f"Attempting to send text fallback after media download failure: {text[:50]}...")
                else:
                    return {"error": f"Failed to download media from {source_platform}: {str(e)}"}
        
        # Track temporary files for cleanup
        if photo_path and isinstance(photo_path, str) and os.path.exists(photo_path) and photo_path not in temp_files:
            temp_files.append(photo_path)
        if video_path and isinstance(video_path, str) and os.path.exists(video_path) and video_path not in temp_files:
            temp_files.append(video_path)
        if document_path and isinstance(document_path, str) and os.path.exists(document_path) and document_path not in temp_files:
            temp_files.append(document_path)
        
    except Exception as e:
        logger.error(f"Error handling file downloads: {e}")
        raise

    logger.info(f"[{platform}] Starting broadcast to scopes: {scopes}")
    total_targets = 0
    for scope, ids_set in target_ids_by_scope.items():
        logger.info(f"[{platform}] Scope '{scope}' has {len(ids_set)} targets")
        total_targets += len(ids_set)
    
    if total_targets == 0:
        logger.warning(f"[{platform}] No targets found for scopes: {scopes}")
        return {
            "sent": 0,
            "failed": 0,
            "detailed_results": detailed_results,
            "batch_id": None,
            "preview_content": preview_content
        }
    
    for scope, ids_set in target_ids_by_scope.items():
        for cid_str in ids_set:
            try: 
                cid = int(cid_str)
            except ValueError:
                logger.warning(f"[{platform}] Invalid chat_id '{cid_str}' found in DB for scope '{scope}'. Skipping.")
                detailed_results[scope]['failed'] += 1
                total_failed += 1
                continue
            if cid == owner_id: 
                logger.debug(f"[{platform}] Skipping owner chat {cid}")
                continue

            try:
                sent_msg = None
                parse_mode_option = ParseMode.HTML if platform == 'telegram' else ParseMode.HTML

                if forward_from_chat_id and forward_from_message_id:
                    try:
                        # Convert chat_id to integer for forwarding
                        forward_chat_id = int(forward_from_chat_id)
                        
                        # بررسی معتبر بودن chat_id برای Bale
                        if platform == 'bale' and forward_chat_id < 0:
                            logger.warning(f"[{platform}] Skipping forward from negative chat_id {forward_chat_id} (not valid for Bale)")
                            raise Exception("Invalid chat_id for Bale platform")
                        
                        # برای cross-platform broadcasts، forward را غیرفعال کن
                        if source_platform and source_platform != platform:
                            logger.info(f"[{platform}] Cross-platform broadcast detected - skipping forward, will send media with caption instead")
                            raise Exception("Cross-platform forward not supported")
                        
                        logger.info(f"[{platform}] Attempting to forward message {forward_from_message_id} from chat {forward_chat_id} to {cid}")
                        if platform == 'ita':
                            # فوروارد پیام در ایتا
                            success = await forward_ita_message(cid, forward_chat_id, forward_from_message_id)
                            if success:
                                all_sent_info.append((cid, 0))  # ایتا message_id ندارد
                                detailed_results[scope]['sent'] += 1
                                total_sent += 1
                                logger.info(f"[{platform}] Forwarding successful to {cid}, skipping media sending")
                                continue
                            else:
                                raise Exception("Failed to forward message to Ita")
                        else:
                            sent_msg = await send_with_concurrency_control(
                            semaphore,
                            bot_instance.forward_message,
                            chat_id=cid,
                            from_chat_id=forward_chat_id,
                            message_id=forward_from_message_id,
                            disable_notification=True
                        )
                        # Note: For forwarded messages, we don't send additional text
                        # The forwarded message itself contains all the content
                        all_sent_info.append((cid, sent_msg.message_id))
                        detailed_results[scope]['sent'] += 1
                        total_sent += 1
                        logger.info(f"[{platform}] Forwarding successful to {cid}, skipping media sending")
                        continue
                    except Exception as e:
                        logger.error(f"Error forwarding message to {cid} from chat {forward_chat_id} message {forward_from_message_id}: {e}")
                        # Handle "Chat not found" errors by removing the chat from database
                        if "Chat not found" in str(e).lower():
                            try:
                                await delete_user_completely(str(cid), platform)
                                logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                            except Exception as db_error:
                                logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                            detailed_results[scope]['failed'] += 1
                            total_failed += 1
                            continue
                        # If forwarding fails, try to send media with caption if available
                        logger.debug(f"[{platform}] Forward failed, checking media and text: text='{text}', photo={bool(photo_path)}, video={bool(video_path)}, document={bool(document_path)}")
                        if any([photo_path, video_path, document_path]):
                            logger.info(f"[{platform}] Forward failed, attempting to send media with caption to {cid}")
                            # Continue to media sending logic below instead of skipping
                        elif text:
                            logger.info(f"[{platform}] Forward failed, attempting to send text directly to {cid}")
                            try:
                                if platform == 'ita':
                                    # برای ایتا از API مستقیم استفاده می‌کنیم
                                    success, message_id = await send_ita_message(cid, text, parse_mode_option)
                                    if success:
                                        all_sent_info.append((cid, message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent text message to {cid} after forward failure")
                                    else:
                                        raise Exception("Failed to send text message to Ita")
                                else:
                                    sent_msg = await send_with_concurrency_control(
                                        semaphore,
                                        bot_instance.send_message,
                                        chat_id=cid,
                                        text=text,
                                        parse_mode=parse_mode_option,
                                        disable_notification=True
                                    )
                                    all_sent_info.append((cid, sent_msg.message_id))
                                    detailed_results[scope]['sent'] += 1
                                    total_sent += 1
                                    logger.info(f"[{platform}] Successfully sent text message to {cid} after forward failure")
                                    continue
                            except Exception as text_error:
                                logger.error(f"Failed to send text message to {cid} after forward failure: {text_error}")
                                # Handle "Chat not found" errors by removing the chat from database
                                if "Chat not found" in str(text_error).lower():
                                    try:
                                        await delete_user_completely(str(cid), platform)
                                        logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                                    except Exception as db_error:
                                        logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                                detailed_results[scope]['failed'] += 1
                                total_failed += 1
                                continue
                        else:
                            logger.info(f"[{platform}] Forward failed, no content to send to {cid}")
                            detailed_results[scope]['failed'] += 1
                            total_failed += 1
                            continue

                # Only text message
                if text and not any([photo_path, video_path, document_path]):
                    try:
                        if platform == 'ita':
                            # ارسال پیام به ایتا
                            success, message_id = await send_ita_message(cid, text)
                            if success:
                                all_sent_info.append((cid, message_id))  # ایتا message_id دارد
                                detailed_results[scope]['sent'] += 1
                                total_sent += 1
                                logger.debug(f"[{platform}] Successfully sent text message to {cid} with message_id {message_id}. Total sent: {total_sent}")
                                sent_msg = "success"  # برای ایتا، نشان‌دهنده موفقیت
                            else:
                                raise Exception("Failed to send message to Ita")
                        else:
                            sent_msg = await send_with_concurrency_control(
                                semaphore,
                                bot_instance.send_message,
                                chat_id=cid,
                                text=text,
                                parse_mode=parse_mode_option,
                                disable_notification=True
                            )
                            all_sent_info.append((cid, sent_msg.message_id))
                            detailed_results[scope]['sent'] += 1
                            total_sent += 1
                            logger.debug(f"[{platform}] Successfully sent text message to {cid}. Total sent: {total_sent}")
                    except Exception as e:
                        logger.error(f"Failed to send text message to {cid}: {e}")
                        # Handle "Chat not found" errors by removing the chat from database
                        if "Chat not found" in str(e).lower():
                            try:
                                await delete_user_completely(str(cid), platform)
                                logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                            except Exception as db_error:
                                logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                        detailed_results[scope]['failed'] += 1
                        total_failed += 1
                        continue

                # Handle media with retry logic
                if any([photo_path, video_path, document_path]):
                    logger.info(f"[{platform}] About to process media for {cid} - photo_path: {photo_path}, video_path: {video_path}, document_path: {document_path}")
                    
                    # Note: Cross-platform file conversion is handled in the media sending sections below
                    
                    max_retries = 2
                    for attempt in range(max_retries + 1):
                        # Photo with optional caption
                        if photo_path:
                            try:
                                if platform == 'ita':
                                    # تشخیص بهتر file_id vs file path برای ایتا
                                    is_file_id = isinstance(photo_path, str) and (
                                        photo_path.startswith('BAAD') or  # Bale file_id
                                        photo_path.startswith('AgAC') or  # Telegram photo file_id
                                        photo_path.startswith('BAAH') or  # Telegram document file_id
                                        photo_path.startswith('CAAH') or  # Telegram video file_id
                                        (len(photo_path) > 20 and not os.path.exists(photo_path) and not photo_path.startswith('C:\\') and not photo_path.startswith('/') and not photo_path.startswith('C:\\Users\\'))  # Other file_ids (but not Windows/Unix paths)
                                    )
                                    is_local_file = isinstance(photo_path, str) and os.path.exists(photo_path) and not is_file_id
                                    is_url = isinstance(photo_path, str) and (photo_path.startswith('http://') or photo_path.startswith('https://'))
                                    logger.info(f"[{platform}] Photo path: {photo_path}, is_local_file: {is_local_file}, is_url: {is_url}")
                                    
                                    # اگر فایل محلی است، مستقیماً ارسال کن
                                    if is_local_file:
                                        logger.info(f"[{platform}] Sending photo (file) to {cid} (scope: {scope}). File: {photo_path}")
                                        logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                        success, message_id = await send_ita_file(cid, photo_path, text, "photo", original_media_name)
                                        sent_msg = "success" if success else None
                                        if success:
                                            all_sent_info.append((cid, message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent photo to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send photo to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending photo to {cid}")
                                            raise Exception("Failed to send photo to Ita")
                                    else:
                                        # ارسال عکس به ایتا (برای file_id یا URL)
                                        logger.info(f"[{platform}] Attempting to send photo to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                        logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                        success, message_id = await send_ita_file(cid, photo_path, text, "photo", original_media_name)
                                        sent_msg = "success" if success else None
                                        if success:
                                            all_sent_info.append((cid, message_id))  # ایتا message_id دارد
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent photo to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"  # برای ایتا، نشان‌دهنده موفقیت
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send photo to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending photo to {cid}")
                                            raise Exception("Failed to send photo to Ita")
                                else:
                                    # تشخیص ساده و دقیق فایل محلی برای تلگرام و بله
                                    is_local_file = os.path.exists(photo_path) if isinstance(photo_path, str) else False
                                    is_url = isinstance(photo_path, str) and photo_path.startswith(('http://', 'https://'))
                                    logger.info(f"[{platform}] Photo path: {photo_path}, is_local_file: {is_local_file}, is_url: {is_url}")
                                    
                                    # اگر فایل به صورت محلی وجود دارد، مستقیماً ارسال شود
                                    if is_local_file:
                                        logger.info(f"[{platform}] Sending photo (local file) to {cid}. File: {photo_path}")
                                        with open(photo_path, 'rb') as photo_file:
                                            sent_msg = await bot_instance.send_photo(
                                                chat_id=cid,
                                                photo=InputFile(photo_file, filename=original_media_name or 'photo.jpg'),
                                                caption=text[:1024] if text else None,
                                                parse_mode=parse_mode_option,
                                                disable_notification=True
                                            )
                                        all_sent_info.append((cid, sent_msg.message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent photo to {cid}. Total sent: {total_sent}")
                                        break
                                    
                                    # اگر فایل محلی نیست و یک انتقال بین پلتفرمی است، آن را دانلود کن
                                    elif source_platform and source_platform != platform:
                                        logger.info(f"[{platform}] Cross-platform photo detected. Downloading from {source_platform} for {cid}")
                                        try:
                                            # `photo_path` در اینجا همان file_id است
                                            downloaded_photo_path = await download_file_to_temp(source_platform, photo_path, 'photo.jpg')
                                            if downloaded_photo_path:
                                                temp_files.append(downloaded_photo_path) # اضافه کردن به لیست پاکسازی
                                                logger.info(f"[{platform}] Sending downloaded photo file to {cid}. File: {downloaded_photo_path}")
                                                with open(downloaded_photo_path, 'rb') as photo_file:
                                                    sent_msg = await bot_instance.send_photo(
                                        chat_id=cid,
                                                        photo=InputFile(photo_file, filename=original_media_name or 'photo.jpg'),
                                        caption=text[:1024] if text else None,
                                        parse_mode=parse_mode_option,
                                        disable_notification=True
                                    )
                                                    all_sent_info.append((cid, sent_msg.message_id))
                                                    detailed_results[scope]['sent'] += 1
                                                    total_sent += 1
                                                    logger.info(f"[{platform}] Successfully sent downloaded photo to {cid}. Total sent: {total_sent}")
                                                    break
                                            else:
                                                raise Exception("Failed to download cross-platform photo")
                                        except Exception as e:
                                            logger.error(f"[{platform}] Error handling cross-platform photo for {cid}: {e}")
                                            # به تلاش بعدی در حلقه retry ادامه بده یا شکست بخور
                                            if attempt == max_retries:
                                                raise e # اگر آخرین تلاش بود، خطا را نمایش بده
                                            await asyncio.sleep(1) # قبل از تلاش مجدد صبر کن
                                            continue # به تلاش بعدی برو
                                    else:
                                        # در غیر این صورت، آن را به عنوان file_id یا URL ارسال کن
                                        logger.info(f"[{platform}] Sending photo (id/url) to {cid}")
                                        sent_msg = await bot_instance.send_photo(
                                                    chat_id=cid,
                                            photo=photo_path,
                                                    caption=text[:1024] if text else None,
                                                parse_mode=parse_mode_option,
                                                disable_notification=True
                                            )
                                        all_sent_info.append((cid, sent_msg.message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent photo to {cid}. Total sent: {total_sent}")
                                        break
                            except Exception as e:
                                logger.error(f"[{platform}] Error sending photo to {cid}: {e}")
                                if attempt == max_retries:
                                    raise e
                                await asyncio.sleep(1)
                                continue
                        
                        # اگر photo ارسال شد، به چت بعدی برو
                        if sent_msg:
                                continue

                        # Video with optional caption
                        if video_path:
                            try:
                                is_local_file = False
                                if platform == 'ita':
                                    # تشخیص ساده و دقیق فایل محلی برای ایتا
                                    is_local_file = os.path.exists(video_path) if isinstance(video_path, str) else False
                                    is_url = isinstance(video_path, str) and video_path.startswith(('http://', 'https://'))
                                    logger.info(f"[{platform}] Video path: {video_path}, is_local_file: {is_local_file}, is_url: {is_url}")
                                else:
                                    # کد مربوط به پلتفرم‌های دیگر
                                    is_local_file = os.path.exists(video_path) if isinstance(video_path, str) else False
                                
                                
                                # اگر فایل محلی است، مستقیماً ارسال کن
                                if is_local_file:
                                    logger.info(f"[{platform}] Sending video (file) to {cid} (scope: {scope}). File: {video_path}")
                                    if platform == 'ita':
                                        success, message_id = await send_ita_file(cid, video_path, text, "video", original_media_name)
                                        sent_msg = "success" if success else None
                                    else:
                                        # برای تلگرام و بله از API خودشان استفاده کن
                                        with open(video_path, 'rb') as video_file:
                                            sent_msg = await bot_instance.send_video(
                                                chat_id=cid,
                                                video=InputFile(video_file, filename=original_media_name or 'video.mp4'),
                                                caption=text[:1024] if text else None,
                                                parse_mode=parse_mode_option,
                                                disable_notification=True
                                            )
                                        success, message_id = True, sent_msg.message_id
                                    if success:
                                        all_sent_info.append((cid, message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent video to {cid}. Total sent: {total_sent}")
                                        sent_msg = "success"
                                        break
                                    else:
                                        logger.warning(f"[{platform}] Failed to send video to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                        if attempt < max_retries:
                                            logger.info(f"[{platform}] Will retry sending video to {cid}")
                                        raise Exception("Failed to send video to Ita")
                                else:
                                    # ارسال ویدیو (برای file_id یا URL)
                                    logger.info(f"[{platform}] Attempting to send video to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                    if platform == 'ita':
                                        success, message_id = await send_ita_file(cid, video_path, text, "video", original_media_name)
                                        sent_msg = "success" if success else None
                                    else:
                                        # برای تلگرام و بله از API خودشان استفاده کن
                                        with open(video_path, 'rb') as video_file:
                                            if platform == 'telegram':
                                                sent_msg = await telegram_app.bot.send_video(
                                                    chat_id=cid,
                                                    video=video_file,
                                                    caption=text,
                                                    parse_mode='HTML'
                                                )
                                            elif platform == 'bale':
                                                sent_msg = await bale_app.bot.send_video(
                                                    chat_id=cid,
                                                    video=video_file,
                                                    caption=text,
                                                    parse_mode='HTML'
                                                )
                                            success = sent_msg is not None
                                            message_id = sent_msg.message_id if sent_msg else 0
                                    if success:
                                        all_sent_info.append((cid, message_id))  # ایتا message_id دارد
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent video to {cid}. Total sent: {total_sent}")
                                        sent_msg = "success"  # برای ایتا، نشان‌دهنده موفقیت
                                        break
                                    else:
                                        logger.warning(f"[{platform}] Failed to send video to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                        if attempt < max_retries:
                                            logger.info(f"[{platform}] Will retry sending video to {cid}")
                                        raise Exception("Failed to send video to Ita")
                                
                                # اگر فایل به صورت محلی وجود دارد، مستقیماً ارسال شود
                                if is_local_file:
                                    logger.info(f"[{platform}] Sending video (local file) to {cid}. File: {video_path}")
                                    with open(video_path, 'rb') as video_file:
                                        sent_msg = await bot_instance.send_video(
                                            chat_id=cid,
                                            video=InputFile(video_file, filename=original_media_name or 'video.mp4'),
                                            caption=text[:1024] if text else None,
                                            parse_mode=parse_mode_option,
                                            disable_notification=True
                                        )
                                    all_sent_info.append((cid, sent_msg.message_id))
                                    detailed_results[scope]['sent'] += 1
                                    total_sent += 1
                                    logger.info(f"[{platform}] Successfully sent video to {cid}. Total sent: {total_sent}")
                                    break
                                    
                                # اگر فایل محلی نیست و یک انتقال بین پلتفرمی است، آن را دانلود کن
                                elif source_platform and source_platform != platform:
                                    logger.info(f"[{platform}] Cross-platform video detected. Downloading from {source_platform} for {cid}")
                                    try:
                                        # `video_path` در اینجا همان file_id است
                                        downloaded_video_path = await download_file_to_temp(source_platform, video_path, 'video.mp4')
                                        if downloaded_video_path:
                                            temp_files.append(downloaded_video_path) # اضافه کردن به لیست پاکسازی
                                            logger.info(f"[{platform}] Sending downloaded video file to {cid}. File: {downloaded_video_path}")
                                            with open(downloaded_video_path, 'rb') as video_file:
                                                sent_msg = await bot_instance.send_video(
                                                    chat_id=cid,
                                                    video=InputFile(video_file, filename=original_media_name or 'video.mp4'),
                                                    caption=text[:1024] if text else None,
                                                    parse_mode=parse_mode_option,
                                                    disable_notification=True
                                                )
                                            all_sent_info.append((cid, sent_msg.message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent downloaded video to {cid}. Total sent: {total_sent}")
                                            break
                                        else:
                                            raise Exception("Failed to download cross-platform video")
                                    except Exception as e:
                                        logger.error(f"[{platform}] Error handling cross-platform video for {cid}: {e}")
                                        # به تلاش بعدی در حلقه retry ادامه بده یا شکست بخور
                                        if attempt == max_retries:
                                            raise e # اگر آخرین تلاش بود، خطا را نمایش بده
                                        await asyncio.sleep(1) # قبل از تلاش مجدد صبر کن
                                        continue # به تلاش بعدی برو
                                    else:
                                        # در غیر این صورت، آن را به عنوان file_id یا URL ارسال کن
                                        logger.info(f"[{platform}] Sending video (id/url) to {cid}")
                                        sent_msg = await bot_instance.send_video(
                                            chat_id=cid,
                                            video=video_path,
                                            caption=text[:1024] if text else None,
                                            parse_mode=parse_mode_option,
                                            disable_notification=True
                                        )
                                        all_sent_info.append((cid, sent_msg.message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent video to {cid}. Total sent: {total_sent}")
                                        break
                            except Exception as e:
                                logger.error(f"[{platform}] Error sending video to {cid}: {e}")
                                if attempt == max_retries:
                                    raise e
                                await asyncio.sleep(1)
                                continue
                        
                        # اگر video ارسال شد، به چت بعدی برو
                        if sent_msg:
                                continue

                        # Document with optional caption
                        if document_path:
                            try:
                                is_local_file = False
                                if platform == 'ita':
                                    # تشخیص ساده و دقیق فایل محلی برای ایتا
                                    is_local_file = os.path.exists(document_path) if isinstance(document_path, str) else False
                                    is_url = isinstance(document_path, str) and document_path.startswith(('http://', 'https://'))
                                    logger.info(f"[{platform}] Document path: {document_path}, is_local_file: {is_local_file}, is_url: {is_url}")
                                    
                                    # اگر فایل محلی است، مستقیماً ارسال کن
                                    if is_local_file:
                                        logger.info(f"[{platform}] Sending document (file) to {cid} (scope: {scope}). File: {document_path}")
                                        logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                        logger.info(f"[{platform}] About to call send_ita_file with: cid={cid}, document_path={document_path}, text={text}, file_type=document, original_media_name={original_media_name}")
                                        success, message_id = await send_ita_file(cid, document_path, text, "document", original_media_name)
                                        logger.info(f"[{platform}] send_ita_file returned: success={success}, message_id={message_id}")
                                        sent_msg = "success" if success else None
                                        logger.info(f"[{platform}] sent_msg set to: {sent_msg}")
                                        
                                        if success:
                                            all_sent_info.append((cid, message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending document to {cid}")
                                            raise Exception("Failed to send document to Ita")
                                    else:
                                        # ارسال فایل (برای file_id یا URL)
                                        logger.info(f"[{platform}] Attempting to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                        logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                        success, message_id = await send_ita_file(cid, document_path, text, "document", original_media_name)
                                        sent_msg = "success" if success else None
                                        
                                        if success:
                                            all_sent_info.append((cid, message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending document to {cid}")
                                            raise Exception("Failed to send document to Ita")
                                else:
                                    # کد مربوط به پلتفرم‌های دیگر
                                    is_local_file = os.path.exists(document_path) if isinstance(document_path, str) else False
                                    logger.info(f"[{platform}] DEBUG: document_path={document_path}, is_local_file={is_local_file}")
                                    
                                    # اگر فایل محلی است، مستقیماً ارسال کن
                                    if is_local_file:
                                        logger.info(f"[{platform}] Sending document (file) to {cid} (scope: {scope}). File: {document_path}")
                                        logger.info(f"[{platform}] DEBUG: platform value is '{platform}', checking if platform == 'ita': {platform == 'ita'}")
                                        if platform == 'ita':
                                            logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                            logger.info(f"[{platform}] About to call send_ita_file with: cid={cid}, document_path={document_path}, text={text}, file_type=document, original_media_name={original_media_name}")
                                            success, message_id = await send_ita_file(cid, document_path, text, "document", original_media_name)
                                            logger.info(f"[{platform}] send_ita_file returned: success={success}, message_id={message_id}")
                                            sent_msg = "success" if success else None
                                            logger.info(f"[{platform}] sent_msg set to: {sent_msg}")
                                        else:
                                            # برای تلگرام و بله از API خودشان استفاده کن
                                            # حذف پیشوند mbot_platform_ از نام فایل برای نمایش بهتر
                                            display_filename = original_media_name
                                            if display_filename and display_filename.startswith(('mbot_telegram_', 'mbot_bale_', 'mbot_ita_')):
                                                # استخراج نام فایل اصلی بعد از آخرین _
                                                parts = display_filename.split('_')
                                                if len(parts) > 3:
                                                    # فرمت: mbot_platform_type_hash_originalname.ext
                                                    display_filename = '_'.join(parts[4:])
                                                    logger.info(f"[{platform}] Cleaned filename from {original_media_name} to {display_filename}")
                                            
                                            logger.info(f"[{platform}] Sending document with filename: {display_filename or 'document'}")
                                            with open(document_path, 'rb') as document_file:
                                                sent_msg = await bot_instance.send_document(
                                                    chat_id=cid,
                                                    document=InputFile(document_file, filename=display_filename or 'document'),
                                                    caption=text[:1024] if text else None,
                                                    parse_mode=parse_mode_option,
                                                    disable_notification=True
                                                )
                                            success, message_id = True, sent_msg.message_id
                                        if success:
                                            all_sent_info.append((cid, message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending document to {cid}")
                                            raise Exception("Failed to send document to Ita")
                                    else:
                                        # ارسال فایل (برای file_id یا URL)
                                        logger.info(f"[{platform}] Attempting to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                        if platform == 'ita':
                                            logger.info(f"[{platform}] Passing original_media_name to Ita: {original_media_name}")
                                            success, message_id = await send_ita_file(cid, document_path, text, "document", original_media_name)
                                            sent_msg = "success" if success else None
                                        else:
                                            # برای تلگرام و بله از API خودشان استفاده کن
                                            with open(document_path, 'rb') as document_file:
                                                if platform == 'telegram':
                                                    sent_msg = await telegram_app.bot.send_document(
                                                        chat_id=cid,
                                                        document=document_file,
                                                        caption=text,
                                                        parse_mode='HTML'
                                                    )
                                                elif platform == 'bale':
                                                    sent_msg = await bale_app.bot.send_document(
                                                        chat_id=cid,
                                                        document=document_file,
                                                        caption=text,
                                                        parse_mode='HTML'
                                                    )
                                                success = sent_msg is not None
                                                message_id = sent_msg.message_id if sent_msg else 0
                                        if success:
                                            all_sent_info.append((cid, message_id))  # ایتا message_id دارد
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                            sent_msg = "success"  # برای ایتا، نشان‌دهنده موفقیت
                                            break
                                        else:
                                            logger.warning(f"[{platform}] Failed to send document to {cid} (attempt {attempt + 1}/{max_retries + 1})")
                                            if attempt < max_retries:
                                                logger.info(f"[{platform}] Will retry sending document to {cid}")
                                            raise Exception("Failed to send document to Ita")
                                            
                                    # تشخیص ساده و دقیق فایل محلی برای تلگرام و بله
                                    is_local_file = os.path.exists(document_path) if isinstance(document_path, str) else False
                                    is_url = isinstance(document_path, str) and document_path.startswith(('http://', 'https://'))
                                    logger.info(f"[{platform}] Document path: {document_path}, is_local_file: {is_local_file}, is_url: {is_url}")
                                    
                                    # اگر فایل به صورت محلی وجود دارد، مستقیماً ارسال شود
                                    if is_local_file:
                                        logger.info(f"[{platform}] Sending document (local file) to {cid}. File: {document_path}")
                                        with open(document_path, 'rb') as document_file:
                                            sent_msg = await bot_instance.send_document(
                                                chat_id=cid,
                                                document=InputFile(document_file, filename=original_media_name or os.path.basename(document_path)),
                                                caption=text[:1024] if text else None,
                                                parse_mode=parse_mode_option,
                                                disable_notification=True
                                            )
                                        all_sent_info.append((cid, sent_msg.message_id))
                                        detailed_results[scope]['sent'] += 1
                                        total_sent += 1
                                        logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                        break
                                    
                                    # اگر فایل محلی نیست و یک انتقال بین پلتفرمی است، آن را دانلود کن
                                    elif source_platform and source_platform != platform:
                                        logger.info(f"[{platform}] Cross-platform document detected. Downloading from {source_platform} for {cid}")
                                        try:
                                            # `document_path` در اینجا همان file_id است
                                            downloaded_document_path = await download_file_to_temp(source_platform, document_path, 'document')
                                            if downloaded_document_path:
                                                temp_files.append(downloaded_document_path) # اضافه کردن به لیست پاکسازی
                                                logger.info(f"[{platform}] Sending downloaded document file to {cid}. File: {downloaded_document_path}")
                                                with open(downloaded_document_path, 'rb') as document_file:
                                                    sent_msg = await bot_instance.send_document(
                                                        chat_id=cid,
                                                        document=InputFile(document_file, filename=original_media_name or os.path.basename(downloaded_document_path)),
                                                        caption=text[:1024] if text else None,
                                                        parse_mode=parse_mode_option,
                                                        disable_notification=True
                                                    )
                                                all_sent_info.append((cid, sent_msg.message_id))
                                                detailed_results[scope]['sent'] += 1
                                                total_sent += 1
                                                logger.info(f"[{platform}] Successfully sent downloaded document to {cid}. Total sent: {total_sent}")
                                                break
                                            else:
                                                raise Exception("Failed to download cross-platform document")
                                        except Exception as e:
                                            logger.error(f"[{platform}] Error handling cross-platform document for {cid}: {e}")
                                            # به تلاش بعدی در حلقه retry ادامه بده یا شکست بخور
                                            if attempt == max_retries:
                                                raise e # اگر آخرین تلاش بود، خطا را نمایش بده
                                            await asyncio.sleep(1) # قبل از تلاش مجدد صبر کن
                                            continue # به تلاش بعدی برو
                                        else:
                                            # در غیر این صورت، آن را به عنوان file_id یا URL ارسال کن
                                            logger.info(f"[{platform}] Sending document (id/url) to {cid}")
                                            sent_msg = await bot_instance.send_document(
                                                chat_id=cid,
                                                document=document_path,
                                                caption=text[:1024] if text else None,
                                                parse_mode=parse_mode_option,
                                                disable_notification=True
                                            )
                                            all_sent_info.append((cid, sent_msg.message_id))
                                            detailed_results[scope]['sent'] += 1
                                            total_sent += 1
                                            logger.info(f"[{platform}] Successfully sent document to {cid}. Total sent: {total_sent}")
                                            break
                            except Exception as e:
                                logger.error(f"[{platform}] Error sending document to {cid}: {e}")
                                if attempt == max_retries:
                                    raise e
                                await asyncio.sleep(1)
                                continue

                    # برای ایتا، sent_msg = "success" است که باعث دوبله شدن total_sent می‌شود
                    # پس این بخش را برای ایتا اجرا نمی‌کنیم
                    if sent_msg and platform != 'ita':
                        logger.info(f"[{platform}] sent_msg is truthy: {sent_msg} for {cid}")
                        # all_sent_info و detailed_results قبلاً در حلقه retry اضافه شده‌اند
                        # پس اینجا دوباره اضافه نمی‌کنیم
                    elif platform == 'ita' and sent_msg == "success":
                        # برای ایتا، "success" نشان‌دهنده موفقیت است
                        logger.info(f"[{platform}] Ita send successful: {sent_msg} for {cid}")
                        # total_sent قبلاً در بخش ایتا اضافه شده است
                    else:
                        logger.warning(f"[{platform}] sent_msg is falsy: {sent_msg} for {cid}")
                        # If media sending failed completely, try sending just text (Telegram only)
                        if text and platform == 'telegram':
                            try:
                                sent_msg = await send_with_concurrency_control(
                                    semaphore,
                                    bot_instance.send_message,
                                    chat_id=cid,
                                    text=f"⚠️ Could not send media. {text}",
                                    parse_mode=parse_mode_option,
                                    disable_notification=True
                                )
                                all_sent_info.append((cid, sent_msg.message_id))
                                detailed_results[scope]['sent'] += 1
                                total_sent += 1
                            except Exception as text_error:
                                logger.error(f"Failed to send fallback text to {cid}: {text_error}")
                                # Handle "Chat not found" errors by removing the chat from database
                                if "Chat not found" in str(text_error).lower():
                                    try:
                                        await delete_user_completely(str(cid), platform)
                                        logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                                    except Exception as db_error:
                                        logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                                    detailed_results[scope]['failed'] += 1
                                    total_failed += 1
                                else:
                                    raise Exception("Failed to send media and fallback text")
                        else:
                            # برای ایتا، اگر ارسال موفق بوده، نباید failed محسوب شود
                            if platform == 'ita':
                                # ایتا message_id ندارد، پس اگر به اینجا رسیدیم یعنی ارسال ناموفق بوده
                                detailed_results[scope]['failed'] += 1
                                total_failed += 1
                                logger.warning(f"[{platform}] Ita media send failed for {cid}, marking as failed")
                            else:
                                detailed_results[scope]['failed'] += 1
                                total_failed += 1

            except (BadRequest, Forbidden) as e:
                logger.warning(f"[{platform}] Failed to send message to {cid} (scope '{scope}'): {e}")
                # Handle "Chat not found" errors by removing the chat from database
                if "Chat not found" in str(e).lower():
                    try:
                        await delete_user_completely(str(cid), platform)
                        logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                    except Exception as db_error:
                        logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                detailed_results[scope]['failed'] += 1
                total_failed += 1
            except TimedOut:
                logger.warning(f"[{platform}] Timed out sending to {cid} (scope '{scope}'). Skipping.")
                detailed_results[scope]['failed'] += 1
                total_failed += 1
            except Exception as e:
                logger.error(f"[{platform}] Unexpected error sending to {cid} (scope '{scope}'): {e}", exc_info=True)
                # Handle "Chat not found" errors by removing the chat from database
                if "Chat not found" in str(e).lower():
                    try:
                        await delete_user_completely(str(cid), platform)
                        logger.info(f"[{platform}] Removed chat {cid} from database due to 'Chat not found' error")
                    except Exception as db_error:
                        logger.error(f"[{platform}] Failed to remove chat {cid} from database: {db_error}")
                detailed_results[scope]['failed'] += 1
                total_failed += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)

    # Clean up temporary files after ALL sending is complete
    # Note: For cross-platform broadcasts, we delay cleanup to allow other platform to copy files
    if temp_files:
        logger.info(f"[{platform}] Cleaning up {len(temp_files)} temporary files after broadcast completion")
    for temp_file in temp_files:
        try:
            if os.path.exists(temp_file):
                # For cross-platform broadcasts, only clean up copied files, not original files
                if source_platform and source_platform != platform:
                    # Check if this is a copied file (has platform prefix) or original file
                    if f"mbot_{platform}_" in os.path.basename(temp_file):
                        # This is a copied file, safe to delete
                        logger.info(f"[{platform}] Cleaning up copied temp file: {temp_file}")
                        os.remove(temp_file)
                        logger.debug(f"Cleaned up temporary file: {temp_file}")
                    else:
                        # This is an original file, keep it for other platforms
                        logger.info(f"[{platform}] Keeping original temp file for other platforms: {temp_file}")
                else:
                    # Not a cross-platform broadcast, safe to delete
                    # But first check if this might be an original file that other platforms need
                    if not f"mbot_{platform}_" in os.path.basename(temp_file):
                        # This looks like an original file, keep it for potential cross-platform use
                        logger.info(f"[{platform}] Keeping original temp file (potential cross-platform use): {temp_file}")
                    else:
                        # This is a platform-specific file, safe to delete
                        os.remove(temp_file)
                        logger.debug(f"Cleaned up temporary file: {temp_file}")
            else:
                logger.debug(f"Temporary file already removed: {temp_file}")
        except Exception as e:
            logger.warning(f"Error cleaning up temporary file {temp_file}: {e}")

    # Save broadcast results to database
    batch_id = await async_save_broadcast_to_db(",".join(scopes), preview, platform, all_sent_info)
    
    # ذخیره آمار پست‌ها برای کانال‌ها و سنجاق پیام‌ها
    for chat_id, message_id in all_sent_info:
        # بررسی اینکه آیا چت یک کانال است
        chat_info = db_fetchone("SELECT chat_type FROM chats WHERE chat_id = ? AND platform = ?", (str(chat_id), platform))
        if chat_info and chat_info['chat_type'] == 'channel':
            # تعیین نوع محتوا
            content_type = 'text'
            if photo_path:
                content_type = 'photo'
            elif video_path:
                content_type = 'video'
            elif document_path:
                content_type = 'document'
            
            # ذخیره آمار پست
            save_post_stats_to_db(str(chat_id), platform, str(message_id), content_type, preview)
            
            # سنجاق پیام در کانال‌ها اگر درخواست شده باشد
            if pin_message:
                try:
                    await pin_chat_message(platform, str(chat_id), message_id, disable_notification=True)
                    logger.info(f"[{platform}] Message {message_id} pinned in channel {chat_id}")
                except Exception as e:
                    logger.error(f"[{platform}] Failed to pin message {message_id} in channel {chat_id}: {e}")
    
    logger.info(f"[{platform.upper()}] Broadcast completed. Sent: {total_sent}, Failed: {total_failed}. Batch ID: {batch_id}")
    
    return {
        "sent": total_sent,
        "failed": total_failed,
        "detailed_results": detailed_results,
        "batch_id": batch_id,
        "preview_content": preview_content,
        "detailed_content_info": detailed_content_info,
        "platform": platform
    }

async def delete_messages_async(app: TelegramApplication, batch_id: int, platform: str):
    # Mark batch as deleted instead of actually deleting messages
    db_execute("UPDATE broadcast_batches SET is_deleted = 1 WHERE batch_id = ?", (batch_id,))
    
    # For platforms that support message deletion, try to delete messages
    if (app and app.bot) or platform == 'ita':
        bot_instance = app.bot if app else None
        messages = await async_db_fetchall("SELECT chat_id, message_id FROM sent_messages WHERE batch_id = ?", (batch_id,))
        deleted, failed = 0, 0
        
        # Process deletions in batches of 20 to avoid rate limiting
        batch_size = 20
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            tasks = []
            
            for row in batch:
                chat_id = int(row['chat_id'])
                message_id = int(row['message_id'])
                
                async def delete_single_message(c_id, m_id):
                    try:
                        if platform == 'ita':
                            # Use Ita-specific delete function
                            success = await delete_ita_message(str(c_id), m_id)
                            return (c_id, m_id, success)
                        else:
                            # Use regular bot delete for Telegram/Bale
                            await bot_instance.delete_message(chat_id=c_id, message_id=m_id)
                            return (c_id, m_id, True)
                    except Exception as e:
                        error_msg = str(e).lower()
                        # Check if it's a "message not found" error - this often means the message was already deleted
                        if any(phrase in error_msg for phrase in ['message to delete not found', 'message not found', 'bad request: message to delete not found']):
                            logger.info(f"[{platform}] Message {m_id} in chat {c_id} was already deleted or not found - treating as success")
                            return (c_id, m_id, True)  # Treat as success since message is gone
                        else:
                            logger.warning(f"[{platform}] Delete failed for chat {c_id} message {m_id}: {e}")
                            return (c_id, m_id, False)
                
                tasks.append(delete_single_message(chat_id, message_id))
        
        # Process current batch in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results - handle exceptions properly
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[{platform}] Delete task error: {result}")
                failed += 1
                continue
            
            # Unpack the result tuple safely
            try:
                chat_id, message_id, success = result
                if success:
                    deleted += 1
                else:
                    failed += 1
            except (ValueError, TypeError) as e:
                logger.error(f"[{platform}] Invalid result format: {result}, error: {e}")
                failed += 1
        
        # Small delay between batches to avoid hitting rate limits
        if i + batch_size < len(messages):
            await asyncio.sleep(1)
    else:
        # For platforms that don't support message deletion through bot API
        if platform == 'ita':
            # Ita supports deletion through its own API
            messages = await async_db_fetchall("SELECT chat_id, message_id FROM sent_messages WHERE batch_id = ?", (batch_id,))
            deleted, failed = 0, 0
            
            for row in messages:
                chat_id = str(row['chat_id'])
                message_id = int(row['message_id'])
                
                try:
                    success = await delete_ita_message(chat_id, message_id)
                    if success:
                        deleted += 1
                    else:
                        failed += 1
                except Exception as e:
                    error_msg = str(e).lower()
                    # Check if it's a "message not found" error - this often means the message was already deleted
                    if any(phrase in error_msg for phrase in ['message to delete not found', 'message not found', 'bad request: message to delete not found']):
                        logger.info(f"[{platform}] Message {message_id} in chat {chat_id} was already deleted or not found - treating as success")
                        deleted += 1  # Treat as success since message is gone
                    else:
                        logger.warning(f"[{platform}] Delete failed for chat {chat_id} message {message_id}: {e}")
                        failed += 1
        else:
            # For other platforms that truly don't support message deletion, just mark as deleted
            messages = await async_db_fetchall("SELECT chat_id, message_id FROM sent_messages WHERE batch_id = ?", (batch_id,))
            deleted = len(messages) if messages else 0
            failed = 0
    
    # Batch is already marked as deleted in the database
    logger.info(f"[{platform}] Batch {batch_id} marked as deleted. Deleted: {deleted}, Failed: {failed}")
    return {"deleted": deleted, "failed": failed}

# =================================================================
# --- Flask web server ---
# =================================================================
app = Flask(__name__, template_folder=TEMPLATE_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # حداکثر سایز آپلود 50 مگابایت

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =================================================================
# User Authentication System
# =================================================================

# Import from refactored auth service
try:
    from app.services.auth_service import AuthService, require_auth, require_admin
except ImportError:
    logger.error("Failed to import auth service, falling back to inline functions")
    import secrets
    import re
    
    # Fallback: define inline if import fails
    class AuthService:
        @staticmethod
        def normalize_mobile(mobile):
            mobile = re.sub(r'[^\d]', '', mobile)
            if mobile.startswith('0'):
                mobile = '98' + mobile[1:]
            elif not mobile.startswith('98'):
                mobile = '98' + mobile
            return mobile
        
        @staticmethod
        def generate_otp():
            return ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        @staticmethod
        def send_otp_via_kavenegar(mobile, code):
            # Fallback implementation
            logger.info(f"[MOCK] OTP code for {mobile}: {code}")
            return True
        
        @staticmethod
        def create_session(user_id):
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
        def get_user_from_session(session_token):
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
    
    # Fallback decorators
    def require_auth(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session_token = request.cookies.get('session_token') or request.headers.get('X-Session-Token')
            user = AuthService.get_user_from_session(session_token)
            if not user:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
                else:
                    from flask import redirect, url_for
                    return redirect('/login')
            request.user = user
            return f(*args, **kwargs)
        return decorated_function
    
    def require_admin(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
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

# Kavenegar API configuration (add to config.py)
try:
    import config
    KAVENEGAR_API_KEY = getattr(config, 'KAVENEGAR_API_KEY', '')
    PAYPING_TOKEN = getattr(config, 'PAYPING_TOKEN', '')
except:
    KAVENEGAR_API_KEY = os.environ.get('KAVENEGAR_API_KEY', '')
    PAYPING_TOKEN = os.environ.get('PAYPING_TOKEN', '')

# Alias for backward compatibility
normalize_mobile = AuthService.normalize_mobile
send_otp_via_kavenegar = AuthService.send_otp_via_kavenegar
generate_otp = AuthService.generate_otp
create_session = AuthService.create_session
get_user_from_session = AuthService.get_user_from_session

# Authentication Routes
@app.route('/login')
@app.route('/signup')
def auth_page():
    """Login/Signup page"""
    try:
        return render_template('auth.html')
    except:
        return """
        <!DOCTYPE html>
        <html lang="fa" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>ورود / ثبت نام</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; }
                .auth-card { background: white; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }
                .form-control:focus { border-color: #667eea; box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25); }
                .btn-primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-5">
                        <div class="auth-card p-5">
                            <h2 class="text-center mb-4">ورود / ثبت نام</h2>
                            <div id="auth-form">
                                <div class="mb-3">
                                    <label class="form-label">شماره موبایل</label>
                                    <input type="tel" id="mobile" class="form-control" placeholder="09123456789" maxlength="11">
                                </div>
                                <button onclick="sendOTP()" class="btn btn-primary w-100">ارسال کد تایید</button>
                                <div id="otp-section" style="display:none" class="mt-3">
                                    <div class="mb-3">
                                        <label class="form-label">کد تایید</label>
                                        <input type="text" id="otp" class="form-control" placeholder="123456" maxlength="6">
                                    </div>
                                    <button onclick="verifyOTP()" class="btn btn-primary w-100">تایید</button>
                                </div>
                                <div id="message" class="mt-3"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                function sendOTP() {
                    const mobile = document.getElementById('mobile').value;
                    if (!/^09\d{9}$/.test(mobile)) {
                        showMessage('شماره موبایل معتبر وارد کنید', 'danger');
                        return;
                    }
                    fetch('/api/auth/send-otp', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({mobile: mobile})
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            showMessage('کد تایید ارسال شد', 'success');
                            document.getElementById('otp-section').style.display = 'block';
                        } else {
                            showMessage(data.error || 'خطا در ارسال کد', 'danger');
                        }
                    });
                }
                function verifyOTP() {
                    const mobile = document.getElementById('mobile').value;
                    const otp = document.getElementById('otp').value;
                    fetch('/api/auth/verify-otp', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({mobile: mobile, code: otp})
                    })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            window.location.href = '/';
                        } else {
                            showMessage(data.error || 'کد نامعتبر', 'danger');
                        }
                    });
                }
                function showMessage(msg, type) {
                    const div = document.getElementById('message');
                    div.className = 'alert alert-' + type;
                    div.textContent = msg;
                }
            </script>
        </body>
        </html>
        """

@app.route('/api/auth/send-otp', methods=['POST'])
def api_send_otp():
    """Send OTP to mobile number"""
    try:
        data = request.json
        mobile = data.get('mobile', '').strip()
        
        if not mobile or not re.match(r'^09\d{9}$', mobile):
            return jsonify({'success': False, 'error': 'شماره موبایل معتبر وارد کنید'}), 400
        
        # Generate OTP
        code = generate_otp()
        expires_at = datetime.now() + timedelta(minutes=5)
        
        # Store OTP
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO user_otp_codes (mobile, code, expires_at)
                VALUES (?, ?, ?)
            ''', (mobile, code, expires_at))
            conn.commit()
        
        # Send via Kavenegar
        if send_otp_via_kavenegar(mobile, code):
            logger.info(f"[Auth] OTP sent to {mobile}")
            return jsonify({'success': True, 'message': 'کد تایید ارسال شد'})
        else:
            return jsonify({'success': False, 'error': 'خطا در ارسال پیامک'}), 500
            
    except Exception as e:
        logger.error(f"[Auth] Error sending OTP: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/verify-otp', methods=['POST'])
def api_verify_otp():
    """Verify OTP and login/register user"""
    try:
        data = request.json
        mobile = data.get('mobile', '').strip()
        code = data.get('code', '').strip()
        
        if not mobile or not code:
            return jsonify({'success': False, 'error': 'اطلاعات کامل وارد کنید'}), 400
        
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Development bypass: code 11111 works for all users
            if code == '11111':
                logger.info(f"[Auth] Development bypass OTP used for {mobile}")
            else:
                # Check OTP normally
                cursor.execute('''
                    SELECT * FROM user_otp_codes
                    WHERE mobile = ? AND code = ? AND expires_at > datetime('now') AND is_used = 0
                    ORDER BY created_at DESC LIMIT 1
                ''', (mobile, code))
                otp_record = cursor.fetchone()
                
                if not otp_record:
                    return jsonify({'success': False, 'error': 'کد تایید نامعتبر یا منقضی شده'}), 400
                
                # Mark OTP as used
                cursor.execute('UPDATE user_otp_codes SET is_used = 1 WHERE id = ?', (otp_record['id'],))
            
            # Check if user exists
            cursor.execute('SELECT * FROM users WHERE mobile = ?', (mobile,))
            user = cursor.fetchone()
            
            if not user:
                # Create new user
                cursor.execute('''
                    INSERT INTO users (mobile, is_verified, balance)
                    VALUES (?, 1, 0)
                ''', (mobile,))
                user_id = cursor.lastrowid
                
                # Create default token record
                cursor.execute('''
                    INSERT INTO user_tokens (user_id)
                    VALUES (?)
                ''', (user_id,))
            else:
                user_id = user['id']
                # Update last login
                cursor.execute('UPDATE users SET last_login = datetime("now"), is_verified = 1 WHERE id = ?', (user_id,))
            
            conn.commit()
            
            # Create session
            session_token = create_session(user_id)
            
            response = jsonify({'success': True, 'message': 'ورود موفق'})
            response.set_cookie('session_token', session_token, max_age=30*24*60*60, httponly=True, samesite='Lax')
            return response
            
    except Exception as e:
        logger.error(f"[Auth] Error verifying OTP: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def api_logout():
    """Logout user"""
    session_token = request.cookies.get('session_token')
    if session_token:
        with get_db_connection() as conn:
            conn.execute('DELETE FROM user_sessions WHERE session_token = ?', (session_token,))
            conn.commit()
    response = jsonify({'success': True})
    response.set_cookie('session_token', '', expires=0)
    return response

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def api_get_user():
    """Get current user info"""
    user = request.user
    return jsonify({
        'id': user['id'],
        'mobile': user['mobile'],
        'full_name': user['full_name'],
        'balance': user['balance'],
        'has_tokens': bool(user.get('telegram_token') or user.get('bale_token') or user.get('ita_token'))
    })

@app.route('/api/auth/update-tokens', methods=['POST'])
@require_auth
def api_update_tokens():
    """Update user bot tokens"""
    try:
        user = request.user
        data = request.json
        
        telegram_token = data.get('telegram_token', '').strip()
        bale_token = data.get('bale_token', '').strip()
        ita_token = data.get('ita_token', '').strip()
        telegram_owner_id = data.get('telegram_owner_id', '').strip()
        bale_owner_id = data.get('bale_owner_id', '').strip()
        ita_owner_id = data.get('ita_owner_id', '').strip()
        
        with get_db_connection() as conn:
            # Check if token record exists
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM user_tokens WHERE user_id = ?', (user['id'],))
            token_record = cursor.fetchone()
            
            if token_record:
                # Update existing
                cursor.execute('''
                    UPDATE user_tokens 
                    SET telegram_token = ?, bale_token = ?, ita_token = ?,
                        telegram_owner_id = ?, bale_owner_id = ?, ita_owner_id = ?,
                        updated_at = datetime('now')
                    WHERE user_id = ?
                ''', (telegram_token or None, bale_token or None, ita_token or None,
                      telegram_owner_id or None, bale_owner_id or None, ita_owner_id or None,
                      user['id']))
            else:
                # Create new
                cursor.execute('''
                    INSERT INTO user_tokens 
                    (user_id, telegram_token, bale_token, ita_token,
                     telegram_owner_id, bale_owner_id, ita_owner_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user['id'], telegram_token or None, bale_token or None, ita_token or None,
                      telegram_owner_id or None, bale_owner_id or None, ita_owner_id or None))
            
            conn.commit()
        
        return jsonify({'success': True, 'message': 'توکن‌ها به‌روزرسانی شد'})
        
    except Exception as e:
        logger.error(f"[Auth] Error updating tokens: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/profile', methods=['GET'])
@require_auth
def profile_page():
    """User profile page"""
    user = request.user
    return f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>پروفایل کاربری</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5">
            <h2>پروفایل کاربری</h2>
            <p>شماره موبایل: {user['mobile']}</p>
            <p>موجودی: {user['balance']:,} تومان</p>
            <a href="/" class="btn btn-primary">بازگشت به داشبورد</a>
            <a href="/billing" class="btn btn-success">شارژ حساب</a>
        </div>
    </body>
    </html>
    """

@app.route('/api/payping/create-payment', methods=['POST'])
@require_auth
def api_create_payping_payment():
    """Create Payping payment"""
    try:
        user = request.user
        data = request.json
        amount = int(data.get('amount', 0))
        
        if amount < 1000:
            return jsonify({'success': False, 'error': 'حداقل مبلغ ۱۰۰۰ تومان'}), 400
        
        if not PAYPING_TOKEN:
            return jsonify({'success': False, 'error': 'Payping تنظیم نشده'}), 500
        
        import requests
        import uuid
        
        # Create transaction record
        transaction_id = str(uuid.uuid4())
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO user_billing (user_id, amount, transaction_id, status)
                VALUES (?, ?, ?, 'pending')
            ''', (user['id'], amount, transaction_id))
            conn.commit()
        
        # Call Payping API
        payping_url = "https://api.payping.io/v2/pay"
        callback_url = request.host_url.rstrip('/') + '/api/payping/callback'
        
        payload = {
            'amount': amount,
            'payerIdentity': user['mobile'],
            'payerName': user.get('full_name', user['mobile']),
            'returnUrl': callback_url,
            'clientRefId': transaction_id,
            'description': f'شارژ حساب - {amount:,} تومان'
        }
        
        headers = {
            'Authorization': f'Bearer {PAYPING_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(payping_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            code = result.get('code')
            payping_ref_id = result.get('refId')
            
            # Update transaction with Payping ref ID
            with get_db_connection() as conn:
                conn.execute('''
                    UPDATE user_billing SET payping_ref_id = ? WHERE transaction_id = ?
                ''', (payping_ref_id, transaction_id))
                conn.commit()
            
            payment_url = f"https://api.payping.io/v2/pay/gotoipg/{code}"
            return jsonify({
                'success': True,
                'payment_url': payment_url,
                'code': code
            })
        else:
            logger.error(f"[Payping] Error: {response.text}")
            return jsonify({'success': False, 'error': 'خطا در ایجاد تراکنش'}), 500
            
    except Exception as e:
        logger.error(f"[Payping] Error creating payment: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/payping/callback', methods=['GET'])
def api_payping_callback():
    """Payping payment callback"""
    try:
        refid = request.args.get('refid')
        clientrefid = request.args.get('clientrefid')
        
        if not refid or not clientrefid:
            return redirect('/billing?error=invalid_callback')
        
        # Verify payment with Payping
        if not PAYPING_TOKEN:
            return redirect('/billing?error=config_error')
        
        import requests
        
        verify_url = f"https://api.payping.io/v2/pay/verify/{refid}"
        headers = {
            'Authorization': f'Bearer {PAYPING_TOKEN}'
        }
        
        response = requests.post(verify_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            amount = result.get('amount', 0)
            
            # Update transaction
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM user_billing WHERE transaction_id = ? AND status = 'pending'
                ''', (clientrefid,))
                transaction = cursor.fetchone()
                
                if transaction:
                    user_id = transaction['user_id']
                    
                    # Get current balance
                    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
                    user = cursor.fetchone()
                    balance_before = user['balance'] if user else 0
                    balance_after = balance_before + amount
                    
                    # Update balance
                    cursor.execute('''
                        UPDATE users SET balance = ? WHERE id = ?
                    ''', (balance_after, user_id))
                    
                    # Update transaction
                    cursor.execute('''
                        UPDATE user_billing 
                        SET status = 'completed', verified_at = datetime('now')
                        WHERE transaction_id = ?
                    ''', (clientrefid,))
                    
                    # Record transaction
                    cursor.execute('''
                        INSERT INTO user_transactions 
                        (user_id, type, amount, description, balance_before, balance_after)
                        VALUES (?, 'charge', ?, ?, ?, ?)
                    ''', (user_id, amount, f'شارژ از Payping', balance_before, balance_after))
                    
                    conn.commit()
                    return redirect('/billing?success=1')
        
        return redirect('/billing?error=verification_failed')
        
    except Exception as e:
        logger.error(f"[Payping] Callback error: {e}")
        return redirect('/billing?error=server_error')

@app.route('/api/admin/users', methods=['GET'])
@require_admin
def api_get_all_users():
    """Get all users (API)"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, 
                       COALESCE(SUM(CASE WHEN ub.status = 'completed' THEN ub.amount ELSE 0 END), 0) as total_charge,
                       COUNT(CASE WHEN ub.status = 'completed' THEN 1 END) as transaction_count
                FROM users u
                LEFT JOIN user_billing ub ON u.id = ub.user_id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            ''')
            users = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'users': [dict(user) for user in users]
        })
    except Exception as e:
        logger.error(f"[Admin] Error getting users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/make-admin', methods=['POST'])
@require_admin
def api_make_admin():
    """Make a user admin"""
    try:
        data = request.json
        user_id = int(data.get('user_id'))
        is_admin = int(data.get('is_admin', 1))
        
        with get_db_connection() as conn:
            conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (is_admin, user_id))
            conn.commit()
        
        return jsonify({'success': True, 'message': 'وضعیت ادمین تغییر کرد'})
    except Exception as e:
        logger.error(f"[Admin] Error updating admin status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/users', methods=['GET'])
@require_admin
def admin_users_page():
    """Admin panel - View all users"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, 
                       COALESCE(SUM(CASE WHEN ub.status = 'completed' THEN ub.amount ELSE 0 END), 0) as total_charge,
                       COUNT(CASE WHEN ub.status = 'completed' THEN 1 END) as transaction_count
                FROM users u
                LEFT JOIN user_billing ub ON u.id = ub.user_id
                GROUP BY u.id
                ORDER BY u.created_at DESC
            ''')
            users = cursor.fetchall()
        
        users_html = ''.join([f"""
            <tr>
                <td>{idx + 1}</td>
                <td>{user['mobile']}</td>
                <td>{user['full_name'] or '-'}</td>
                <td>{'✓' if user['is_verified'] else '✗'}</td>
                <td>{user['balance']:,} تومان</td>
                <td>{user['total_charge']:,} تومان</td>
                <td>{user['transaction_count']}</td>
                <td>{user['created_at'][:19] if user['created_at'] else '-'}</td>
                <td>{user['last_login'][:19] if user['last_login'] else '-'}</td>
                <td>
                    <span class="badge bg-{'success' if user['is_active'] else 'danger'}">
                        {'فعال' if user['is_active'] else 'غیرفعال'}
                    </span>
                </td>
            </tr>
        """ for idx, user in enumerate(users)])
        
        return f"""
        <!DOCTYPE html>
        <html lang="fa" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>مدیریت کاربران</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background: #f5f5f5; }}
                .admin-header {{ background: white; padding: 1rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                .table-container {{ background: white; border-radius: 10px; padding: 2rem; margin-top: 2rem; }}
            </style>
        </head>
        <body>
            <div class="admin-header">
                <div class="container">
                    <div class="d-flex justify-content-between align-items-center">
                        <h4 class="mb-0">پنل مدیریتی</h4>
                        <div>
                            <a href="/dashboard" class="btn btn-primary btn-sm">بازگشت به داشبورد</a>
                            <a href="/api/auth/logout" onclick="return confirm('خروج؟')" class="btn btn-outline-danger btn-sm">خروج</a>
                        </div>
                    </div>
                </div>
            </div>
            <div class="container">
                <div class="table-container">
                    <h3 class="mb-4">لیست کاربران</h3>
                    <div class="table-responsive">
                        <table class="table table-striped table-hover">
                            <thead class="table-dark">
                                <tr>
                                    <th>#</th>
                                    <th>موبایل</th>
                                    <th>نام</th>
                                    <th>وضعیت</th>
                                    <th>موجودی</th>
                                    <th>کل شارژ</th>
                                    <th>تعداد تراکنش</th>
                                    <th>تاریخ ثبت</th>
                                    <th>آخرین ورود</th>
                                    <th>وضعیت حساب</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        logger.error(f"[Admin] Error loading users: {e}")
        return f"<h3>خطا در بارگذاری کاربران</h3><p>{str(e)}</p>", 500

@app.route('/billing', methods=['GET'])
@require_auth
def billing_page():
    """Billing page"""
    user = request.user
    return f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>شارژ حساب</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background: #f5f5f5; }}
            .billing-card {{ background: white; border-radius: 10px; padding: 2rem; margin-top: 2rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="row justify-content-center">
                <div class="col-md-6">
                    <div class="billing-card">
                        <h3>شارژ حساب</h3>
                        <p>موجودی فعلی: <strong>{user['balance']:,} تومان</strong></p>
                        <div class="mb-3">
                            <label>مبلغ (تومان)</label>
                            <input type="number" id="amount" class="form-control" min="1000" step="1000" value="10000">
                        </div>
                        <button onclick="charge()" class="btn btn-success w-100">پرداخت با Payping</button>
                        <div id="message" class="mt-3"></div>
                    </div>
                </div>
            </div>
        </div>
        <script>
            function charge() {{
                const amount = document.getElementById('amount').value;
                if (amount < 1000) {{
                    showMessage('حداقل مبلغ ۱۰۰۰ تومان', 'danger');
                    return;
                }}
                fetch('/api/payping/create-payment', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{amount: amount}})
                }})
                .then(r => r.json())
                .then(data => {{
                    if (data.success) {{
                        window.location.href = data.payment_url;
                    }} else {{
                        showMessage(data.error || 'خطا', 'danger');
                    }}
                }});
            }}
            function showMessage(msg, type) {{
                const div = document.getElementById('message');
                div.className = 'alert alert-' + type;
                div.textContent = msg;
            }}
        </script>
    </body>
    </html>
    """

@app.route('/')
def landing_page():
    """Public landing page"""
    return """
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>پلتفرم مدیریت بات‌های ترکیبی - Shirzad Bot</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" rel="stylesheet">
        <style>
            :root {
                --primary: #5D3EBE;
                --secondary: #7B68EE;
                --gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            .hero-section {
                background: var(--gradient);
                color: white;
                padding: 80px 0;
                text-align: center;
            }
            .feature-card {
                border: none;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                transition: transform 0.3s;
                height: 100%;
            }
            .feature-card:hover {
                transform: translateY(-10px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.15);
            }
            .feature-icon {
                font-size: 3rem;
                color: var(--primary);
                margin-bottom: 1rem;
            }
            .btn-primary {
                background: var(--gradient);
                border: none;
                padding: 12px 40px;
                font-size: 1.1rem;
            }
            .btn-primary:hover { opacity: 0.9; }
        </style>
    </head>
    <body>
        <!-- Hero Section -->
        <section class="hero-section">
            <div class="container">
                <h1 class="display-4 mb-4">پلتفرم مدیریت بات‌های ترکیبی</h1>
                <p class="lead mb-5">مدیریت حرفه‌ای تلگرام، بله و ایتا با یک داشبورد قدرتمند</p>
                <a href="/login" class="btn btn-light btn-lg">
                    <i class="fas fa-rocket me-2"></i>شروع کنید
                </a>
            </div>
        </section>

        <!-- Features Section -->
        <section class="py-5">
            <div class="container">
                <h2 class="text-center mb-5">قابلیت‌های اصلی</h2>
                <div class="row g-4">
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-paper-plane feature-icon"></i>
                            <h4>ارسال گروهی</h4>
                            <p>ارسال پیام، تصویر، ویدیو و فایل به هزاران کاربر به صورت همزمان</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-clock feature-icon"></i>
                            <h4>زمان‌بندی</h4>
                            <p>برنامه‌ریزی ارسال‌ها برای زمان‌های مشخص و تکرار خودکار</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-chart-line feature-icon"></i>
                            <h4>گزارشات دقیق</h4>
                            <p>آمار و گزارشات کامل از عملکرد و نرخ بازخورد پیام‌ها</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-tags feature-icon"></i>
                            <h4>تگ‌گذاری</h4>
                            <p>دسته‌بندی و مدیریت چت‌ها با سیستم تگ‌گذاری پیشرفته</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-users feature-icon"></i>
                            <h4>مدیریت ادمین</h4>
                            <p>افزودن و حذف ادمین، پین و ویرایش پیام‌ها</p>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card feature-card p-4 text-center">
                            <i class="fas fa-sync feature-icon"></i>
                            <h4>همگام‌سازی</h4>
                            <p>سینک خودکار داده‌ها بین پلتفرم‌های مختلف</p>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- CTA Section -->
        <section class="py-5" style="background: #f8f9fa;">
            <div class="container text-center">
                <h2 class="mb-4">آماده شروع هستید؟</h2>
                <p class="lead mb-4">همین حالا ثبت نام کنید و تجربه مدیریت حرفه‌ای بات‌ها را داشته باشید</p>
                <a href="/login" class="btn btn-primary btn-lg">
                    <i class="fas fa-user-plus me-2"></i>ثبت نام رایگان
                </a>
            </div>
        </section>

        <!-- Footer -->
        <footer class="bg-dark text-white text-center py-4">
            <p class="mb-0">&copy; ۱۴۰۴ Shirzad Bot Platform. تمامی حقوق محفوظ است.</p>
        </footer>
    </body>
    </html>
    """

@app.route('/dashboard')
@app.route('/admin')
@require_admin
def admin_dashboard():
    """Admin dashboard - Main bot management page"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"[Flask] Error rendering index.html: {e}", exc_info=True)
        return "<h3>Multi Bot Dashboard</h3><p>API endpoints are available at /api/*.</p>"

@app.route('/api/stats')
def api_stats():
    try: # مدیریت خطای کلی برای اطمینان از پاسخ JSON
        # دریافت تعداد چت‌ها (بدون ادمین‌ها)
        t_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='telegram' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(OWNER_ID),))
        b_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='bale' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(BALE_OWNER_ID),))
        i_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='ita' AND is_active=1 GROUP BY chat_type")
        
        telegram_counts = {r['chat_type']: r['cnt'] for r in t_rows}; 
        bale_counts = {r['chat_type']: r['cnt'] for r in b_rows}; 
        ita_counts = {r['chat_type']: r['cnt'] for r in i_rows}; 
        
        # دریافت آمار اعضا از جدول metrics (بدون ادمین‌ها)
        telegram_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'telegram' AND c.is_active=1 AND (c.chat_type != 'private' OR c.chat_id != ?) AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """, (str(OWNER_ID),))
        telegram_member_counts = {r['chat_type']: r['total_members'] for r in telegram_members}
        
        bale_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'bale' AND c.is_active=1 AND (c.chat_type != 'private' OR c.chat_id != ?) AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """, (str(BALE_OWNER_ID),))
        bale_member_counts = {r['chat_type']: r['total_members'] for r in bale_members}
        
        ita_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'ita' AND c.is_active=1 AND c.chat_type != 'private' AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """)
        ita_member_counts = {r['chat_type']: r['total_members'] for r in ita_members}
        
        # اگر metrics خالی است، از جدول chats استفاده کن (هر کاربر = 1 عضو)
        if not telegram_member_counts:
            telegram_member_counts = {}
            for chat_type, count in telegram_counts.items():
                if chat_type == 'private':
                    telegram_member_counts[chat_type] = count  # هر کاربر private = 1 عضو
                else:
                    telegram_member_counts[chat_type] = count
        if not bale_member_counts:
            bale_member_counts = {}
            for chat_type, count in bale_counts.items():
                if chat_type == 'private':
                    bale_member_counts[chat_type] = count  # هر کاربر private = 1 عضو
                else:
                    bale_member_counts[chat_type] = count
        if not ita_member_counts:
            ita_member_counts = {}
            for chat_type, count in ita_counts.items():
                if chat_type == 'private':
                    ita_member_counts[chat_type] = count  # هر کاربر private = 1 عضو
                else:
                    ita_member_counts[chat_type] = count
        
        # اطمینان از وجود کلیدها با مقدار پیش‌فرض 0 برای نمایش در داشبورد
        # برای private chats، اگر تعداد اعضا 0 است، آن را برابر با تعداد چت‌ها قرار بده
        telegram_private_members = telegram_member_counts.get("private", 0)
        if telegram_private_members == 0 and telegram_counts.get("private", 0) > 0:
            telegram_private_members = telegram_counts.get("private", 0)
        
        telegram_stats = {
            "users": telegram_counts.get("private", 0),
            "groups": telegram_counts.get("group", 0),
            "channels": telegram_counts.get("channel", 0),
            "users_members": telegram_private_members,
            "groups_members": telegram_member_counts.get("group", 0),
            "channels_members": telegram_member_counts.get("channel", 0),
            "total_members": (telegram_private_members + 
                             telegram_member_counts.get("group", 0) + 
                             telegram_member_counts.get("channel", 0))
        }
        # برای Bale private chats
        bale_private_members = bale_member_counts.get("private", 0)
        if bale_private_members == 0 and bale_counts.get("private", 0) > 0:
            bale_private_members = bale_counts.get("private", 0)
        
        bale_stats = {
            "users": bale_counts.get("private", 0),
            "groups": bale_counts.get("group", 0),
            "channels": bale_counts.get("channel", 0),
            "users_members": bale_private_members,
            "groups_members": bale_member_counts.get("group", 0),
            "channels_members": bale_member_counts.get("channel", 0),
            "total_members": (bale_private_members + 
                             bale_member_counts.get("group", 0) + 
                             bale_member_counts.get("channel", 0))
        }
        # برای ITA private chats
        ita_private_members = ita_member_counts.get("private", 0)
        if ita_private_members == 0 and ita_counts.get("private", 0) > 0:
            ita_private_members = ita_counts.get("private", 0)
        
        ita_stats = {
            "users": ita_counts.get("private", 0),
            "groups": ita_counts.get("group", 0),
            "channels": ita_counts.get("channel", 0),
            "users_members": ita_private_members,
            "groups_members": ita_member_counts.get("group", 0),
            "channels_members": ita_member_counts.get("channel", 0),
            "total_members": (ita_private_members + 
                             ita_member_counts.get("group", 0) + 
                             ita_member_counts.get("channel", 0))
        }
        
        response_data = {"telegram": telegram_stats, "bale": bale_stats, "ita": ita_stats}
        return jsonify(response_data)
    except Exception as e:
        logger.critical(f"[Flask API] Uncaught exception in /api/stats: {e}", exc_info=True)
        # در صورت خطا، آمار خالی برگردان
        empty_stats = {
            "users": 0, "groups": 0, "channels": 0,
            "users_members": 0, "groups_members": 0, "channels_members": 0, "total_members": 0
        }
        return jsonify({"telegram": empty_stats, "bale": empty_stats, "ita": empty_stats})


@app.route('/api/broadcast', methods=['POST'])
def api_broadcast():
    try: # مدیریت خطاهای کلی Flask برای اطمینان از پاسخ JSON
        import asyncio
        logger.info(f"[Flask API] Broadcast request received")
        
        # Check if request is JSON or form data
        if request.is_json:
            data = request.get_json()
            platform = data.get('platform')
            platforms = data.get('platforms', [])
            scopes = data.get('scopes', [])
            content_type = data.get('content_type')
            content_text = data.get('content_text')
            content_photo = data.get('content_photo')
            content_video = data.get('content_video')
            content_document = data.get('content_document')
        else:
            platform = request.form.get('platform')
            platforms_str = request.form.get('platforms')
            scopes_str = request.form.get('scopes')
            content_type = request.form.get('content_type')
            content_text = request.form.get('content_text')
            content_photo = request.form.get('content_photo')
            content_video = request.form.get('content_video')
            content_document = request.form.get('content_document')
            
            # Parse platforms if it's a string
            if platforms_str:
                if isinstance(platforms_str, str):
                    try:
                        platforms = json.loads(platforms_str)
                        logger.info(f"[Flask API] Successfully parsed JSON platforms: {platforms}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"[Flask API] JSON parsing failed for platforms: {e}, using single platform")
                        platforms = [platform] if platform else []
                else:
                    platforms = platforms_str
            else:
                platforms = [platform] if platform else []
            
            # Parse scopes if it's a string
            if scopes_str:
                if isinstance(scopes_str, str):
                    try:
                        # Try to parse as JSON first (for frontend requests)
                        scopes = json.loads(scopes_str)
                        logger.info(f"[Flask API] Successfully parsed JSON scopes: {scopes}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"[Flask API] JSON parsing failed: {e}, trying fallback parsing")
                        # Fallback to comma-separated parsing with better cleanup
                        scopes = []
                        for s in scopes_str.split(','):
                            cleaned = s.strip().strip('"').strip("'").strip('[').strip(']').strip()
                            if cleaned:
                                scopes.append(cleaned)
                        logger.info(f"[Flask API] Fallback parsed scopes: {scopes}")
                else:
                    scopes = scopes_str
            else:
                scopes = []
        
        logger.info(f"[Flask API] Platforms: {platforms}, Scopes: {scopes}")
        
        if not platforms or not scopes:
            logger.error(f"[Flask API] Missing platforms or scopes - platforms: {platforms}, scopes: {scopes}")
            return jsonify({"error": "Missing 'platform' or 'scopes' in request data."}), 400
        
        # scopes is already parsed above, no need to parse again
        logger.info(f"[Flask API] Parsed scopes: {scopes}")

        # Get message content based on request type
        if request.is_json:
            message_text_or_caption = data.get('message') or content_text
            caption_text = data.get('caption')
        else:
            message_text_or_caption = request.form.get('message') or content_text
            caption_text = request.form.get('caption')
        
        # گزینه سنجاق پیام
        if request.is_json:
            pin_message = data.get('pin_message', False)
        else:
            pin_message = request.form.get('pin_message', 'false').lower() == 'true'
        
        # Get file uploads (only available in form data)
        image_file = request.files.get('image')
        video_file = request.files.get('video')
        document_file = request.files.get('document')
        
        # Forwarding parameters
        if request.is_json:
            forward_from_chat_id = data.get('forward_from_chat_id')
            forward_from_message_id = data.get('forward_from_message_id')
            source_platform = data.get('source_platform')
        else:
            forward_from_chat_id = request.form.get('forward_from_chat_id')
            forward_from_message_id = request.form.get('forward_from_message_id')
            source_platform = request.form.get('source_platform')

        # Validate content types from frontend
        has_media_file = bool(image_file or video_file or document_file)
        has_forwarding = bool(forward_from_chat_id and forward_from_message_id)
        has_pure_text_message = bool(message_text_or_caption and not has_media_file and not has_forwarding)

        if not (has_pure_text_message or has_media_file or has_forwarding):
            return jsonify({"error": "No content (pure text, image, video, document, or forwarding) provided for broadcast."}), 400
        
        # Validate that only one content type is selected
        content_types_count = sum([has_pure_text_message, has_media_file, has_forwarding])
        if content_types_count > 1:
            return jsonify({"error": "Cannot send multiple content types simultaneously. Please choose only one: text, file, or forwarding."}), 400
        
        # Validate forwarding parameters
        if has_forwarding and (not forward_from_chat_id or not forward_from_message_id):
            return jsonify({"error": "Both forward_from_chat_id and forward_from_message_id are required for forwarding."}), 400
        
        # Validate forwarding chat_id format
        if has_forwarding:
            try:
                int(forward_from_chat_id)
            except ValueError:
                return jsonify({"error": "forward_from_chat_id must be a valid integer."}), 400
        
        file_path, file_type = None, None
        content_text_param = None 

        if has_pure_text_message: # اگر محتوا فقط پیام متنی خالص است
            content_text_param = message_text_or_caption
        elif has_media_file: # اگر فایل داریم
            content_text_param = caption_text or message_text_or_caption # اولویت با کپشن جداگانه
            file = image_file or video_file or document_file # فایلی که انتخاب شده
            if file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                file_type = 'photo' if image_file else ('video' if video_file else 'document')
            else:
                return jsonify({"error": "Invalid file type or unsupported extension."}), 400
        elif has_forwarding: # اگر فوروارد داریم
            content_text_param = message_text_or_caption # متن اضافی با فوروارد
            try:
                forward_from_message_id = int(forward_from_message_id)
                forward_from_chat_id = int(forward_from_chat_id)  # Ensure it's an integer
            except ValueError:
                return jsonify({"error": "Invalid forward_from_message_id or forward_from_chat_id. Must be numbers."}), 400
        else: # این بخش نباید اجرا شود اگر اعتبارسنجی اولیه درست کار کند
            return jsonify({"error": "No valid content provided for broadcast (internal error in content type detection)."}), 400


        # Handle multiple platforms
        results = []
        
        for platform in platforms:
            logger.info(f"[Flask API] Processing platform: {platform}")
            
            loop_target, app_target, owner_id_target = None, None, None

            if platform == 'telegram':
                if not telegram_bot_loop or not telegram_app: 
                    logger.error(f"[Flask API] Telegram bot not initialized")
                    results.append({"error": "Telegram bot not initialized.", "platform": platform})
                    continue
                loop_target, app_target, owner_id_target = telegram_bot_loop, telegram_app, OWNER_ID
                logger.info(f"[Flask API] Using Telegram bot")
            elif platform == 'bale':
                if not bale_bot_loop or not bale_app: 
                    logger.error(f"[Flask API] Bale bot not initialized")
                    results.append({"error": "Bale bot not initialized.", "platform": platform})
                    continue
                loop_target, app_target, owner_id_target = bale_bot_loop, bale_app, BALE_OWNER_ID
                logger.info(f"[Flask API] Using Bale bot")
            elif platform == 'ita':
                # ایتا از API مستقیم استفاده می‌کند، نیازی به loop و app ندارد
                loop_target, app_target, owner_id_target = None, None, ITA_OWNER_ID
                logger.info(f"[Flask API] Using Ita direct API")
            else:
                logger.error(f"[Flask API] Invalid platform: {platform}")
                results.append({"error": f"Invalid platform: {platform}", "platform": platform})
                continue

            # Get original media name from uploaded file
            original_media_name = None
            if has_media_file:
                file = image_file or video_file or document_file
                if file and file.filename:
                    original_media_name = file.filename

            # Tag filtering logic
            tag_filter = request.form.get("tag_filter", "").strip()
            send_to_tagged = request.form.get("send_to_tagged", "false") == "true"

            # اگر گزینه تگ فعال است، فهرست چت‌ها را بر اساس تگ محدود کن
            if send_to_tagged and tag_filter:
                # پشتیبانی از چندین تگ (جدا شده با کاما)
                tag_list = [tag.strip() for tag in tag_filter.split(',') if tag.strip()]
                logger.info(f"📌 Broadcasting only to chats with tags: {tag_list}")
                
                # ساخت query برای جستجوی چندین تگ
                if len(tag_list) == 1:
                    # یک تگ
                    tagged_chats = db_fetchall("""
                        SELECT chat_id, platform FROM chats WHERE tags LIKE ? AND platform = ?
                    """, (f"%{tag_list[0]}%", platform))
                else:
                    # چندین تگ - استفاده از OR
                    placeholders = ' OR '.join(['tags LIKE ?' for _ in tag_list])
                    params = [f"%{tag}%" for tag in tag_list] + [platform]
                    tagged_chats = db_fetchall(f"""
                        SELECT chat_id, platform FROM chats WHERE ({placeholders}) AND platform = ?
                    """, params)
                
                if not tagged_chats:
                    logger.warning(f"No chats found with tags '{tag_filter}' in platform '{platform}'. Skipping this platform.")
                    results.append({
                        "sent": 0, 
                        "failed": 0, 
                        "batch_id": None, 
                        "platform": platform, 
                        "content_preview": f"No chats with tags '{tag_filter}' found in {platform}",
                        "skipped": True
                    })
                    continue

                # تبدیل به ساختار مناسب برای perform_broadcast_async
                target_chats = {}
                for chat in tagged_chats:
                    platform_chat = chat["platform"]
                    target_chats.setdefault(platform_chat, []).append(chat["chat_id"])

                # اضافه کردن target_chats به broadcast_kwargs
                broadcast_kwargs = {
                    'app': app_target, 'scopes': scopes, 'platform': platform, 'owner_id': owner_id_target,
                    'text': content_text_param, 
                    'photo_path': file_path if file_type == 'photo' else None,
                    'video_path': file_path if file_type == 'video' else None,
                    'document_path': file_path if file_type == 'document' else None,
                    'forward_from_chat_id': forward_from_chat_id if has_forwarding else None,
                    'forward_from_message_id': forward_from_message_id if has_forwarding else None,
                    'original_media_name': original_media_name,
                    'source_platform': 'telegram' if file_path and 'temp/' in file_path else platform,
                    'pin_message': pin_message,
                    'target_chats': target_chats,
                }
            else:
                broadcast_kwargs = {
                    'app': app_target, 'scopes': scopes, 'platform': platform, 'owner_id': owner_id_target,
                    'text': content_text_param, 
                    'photo_path': file_path if file_type == 'photo' else None,
                    'video_path': file_path if file_type == 'video' else None,
                    'document_path': file_path if file_type == 'document' else None,
                    'forward_from_chat_id': forward_from_chat_id if has_forwarding else None,
                    'forward_from_message_id': forward_from_message_id if has_forwarding else None,
                    'original_media_name': original_media_name,
                    'source_platform': 'telegram' if file_path and 'temp/' in file_path else platform,
                    'pin_message': pin_message,
                }

            content_type = 'forwarding' if has_forwarding else ('text' if content_text_param and not file_type else file_type)
            logger.info(f"[Flask API] Initiating broadcast for {platform} with scopes {scopes} and content type: {content_type}. File path: {file_path}. Text/Caption: {content_text_param}. Forward: {forward_from_chat_id}:{forward_from_message_id if has_forwarding else 'None'}")
            
            if platform == 'ita':
                # ایتا از API مستقیم استفاده می‌کند، نیازی به asyncio.run_coroutine_threadsafe ندارد
                result = asyncio.run(perform_broadcast_async(**broadcast_kwargs))
                # اضافه کردن اطلاعات جزئی محتوا به نتیجه API
                if result and 'detailed_content_info' not in result:
                    result['detailed_content_info'] = result.get('preview_content', '')
                results.append(result)
            else:
                # Check if the target loop is still running and not closed
                if loop_target and loop_target.is_closed():
                    logger.error(f"[Flask API] Target event loop for {platform} is closed. Cannot perform broadcast.")
                    if file_path and os.path.exists(file_path): os.remove(file_path)
                    results.append({"error": f"Bot service for {platform} is not available. Please restart the application.", "platform": platform})
                    continue
                
                try:
                    fut_result = asyncio.run_coroutine_threadsafe(perform_broadcast_async(**broadcast_kwargs), loop_target)
                except RuntimeError as e:
                    if "Event loop is closed" in str(e):
                        logger.error(f"[Flask API] Event loop is closed for {platform}. Cannot perform broadcast.")
                        if file_path and os.path.exists(file_path): os.remove(file_path)
                        results.append({"error": f"Bot service for {platform} is not available. Please restart the application.", "platform": platform})
                        continue
                    else:
                        raise e
            
                try:
                    result = fut_result.result(timeout=120)
                    # اضافه کردن اطلاعات جزئی محتوا به نتیجه API
                    if result and 'detailed_content_info' not in result:
                        result['detailed_content_info'] = result.get('preview_content', '')
                    results.append(result)
                except asyncio.TimeoutError:
                    if file_path and os.path.exists(file_path): os.remove(file_path)
                    logger.error(f"[Flask API] Broadcast timed out for {platform}. Temp file {file_path} deleted.")
                    results.append({"error": "Broadcast operation timed out.", "platform": platform})
                except RuntimeError as e:
                    if "Event loop is closed" in str(e):
                        logger.error(f"[Flask API] Event loop closed during broadcast for {platform}: {e}")
                        if file_path and os.path.exists(file_path): os.remove(file_path)
                        results.append({"error": f"Bot service for {platform} became unavailable during broadcast. Please restart the application.", "platform": platform})
                    else:
                        raise e
                except Exception as e:
                    if file_path and os.path.exists(file_path): os.remove(file_path)
                    logger.error(f"[Flask API] Error during broadcast for {platform}: {e}. Temp file {file_path} deleted.", exc_info=True)
                    results.append({"error": f"Failed to perform broadcast: {str(e)}", "platform": platform})
        
        # محاسبه آمار کلی
        total_sent = sum(r.get('sent', 0) for r in results if 'sent' in r)
        total_failed = sum(r.get('failed', 0) for r in results if 'failed' in r)
        
        # بازگشت نتیجه کلی
        return jsonify({
            "sent": total_sent,
            "failed": total_failed,
            "platform_results": results,
            "total_platforms": len(platforms),
            "successful_platforms": len([r for r in results if r.get('sent', 0) > 0])
        })
    except Exception as e: # مدیریت خطاهای غیرمنتظره در خود مسیر Flask
        logger.critical(f"[Flask API] Uncaught exception in /api/broadcast: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred during broadcast: {str(e)}"}), 500

@app.route('/api/history')
def api_history():
    try: # مدیریت خطاهای کلی Flask برای اطمینان از پاسخ JSON
        # بررسی پارامترهای صفحه‌بندی
        limit = request.args.get('limit', 20, type=int)
        page = request.args.get('page', 1, type=int)
        
        # محدود کردن limit
        limit = min(limit, 100)  # حداکثر 100 مورد در هر صفحه
        
        # محاسبه offset
        offset = (page - 1) * limit
        
        # دریافت تعداد کل رکوردها
        total_count_query = """
            SELECT COUNT(*) FROM broadcast_batches 
            WHERE is_deleted = 0
        """
        total_count = db_fetchall(total_count_query)[0][0]
        total_pages = (total_count + limit - 1) // limit  # محاسبه تعداد صفحات
        
        # دریافت داده‌ها با صفحه‌بندی
        rows = db_fetchall("""
            SELECT bb.batch_id, bb.scope, bb.platform, bb.content_preview, 
                   bb.timestamp,
                   COUNT(sm.message_id) as sent_count
            FROM broadcast_batches bb
            LEFT JOIN sent_messages sm ON bb.batch_id = sm.batch_id
            WHERE bb.is_deleted = 0
            GROUP BY bb.batch_id, bb.scope, bb.platform, bb.content_preview, bb.timestamp
            ORDER BY bb.timestamp DESC 
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        result = []
        for r in rows:
            # محاسبه تعداد ناموفق بر اساس scope و platform
            target_count = 0
            scopes = r['scope'].split(',') if r['scope'] else []
            
            # تخمین تعداد هدف بر اساس scope و platform
            for scope in scopes:
                scope = scope.strip()
                if r['platform'] == 'telegram':
                    count_query = "SELECT COUNT(*) FROM chats WHERE platform='telegram' AND is_active=1 AND chat_type=? AND (chat_type != 'private' OR chat_id != ?)"
                    count_result = db_fetchall(count_query, (scope, str(OWNER_ID)))
                elif r['platform'] == 'bale':
                    count_query = "SELECT COUNT(*) FROM chats WHERE platform='bale' AND is_active=1 AND chat_type=? AND (chat_type != 'private' OR chat_id != ?)"
                    count_result = db_fetchall(count_query, (scope, str(BALE_OWNER_ID)))
                else:  # ita
                    count_query = "SELECT COUNT(*) FROM chats WHERE platform='ita' AND is_active=1 AND chat_type=?"
                    count_result = db_fetchall(count_query, (scope,))
                
                if count_result:
                    target_count += count_result[0][0]
            
            sent_count = r['sent_count'] or 0
            failed_count = max(0, target_count - sent_count)
            
            # تبدیل زمان به شمسی
            timestamp_shamsi = r['timestamp']
            try:
                import jdatetime
                if r['timestamp']:
                    # تبدیل از فرمت YYYY-MM-DD HH:MM:SS به شمسی
                    timestamp_str = str(r['timestamp'])
                    if len(timestamp_str) >= 19:
                        year, month, day, hour, minute, second = map(int, [
                            timestamp_str[0:4], timestamp_str[5:7], timestamp_str[8:10],
                            timestamp_str[11:13], timestamp_str[14:16], timestamp_str[17:19]
                        ])
                        jdt = jdatetime.datetime.fromgregorian(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
                        timestamp_shamsi = jdt.strftime('%Y/%m/%d %H:%M')
            except Exception as e:
                # در صورت خطا، زمان میلادی را نمایش بده
                timestamp_shamsi = r['timestamp']
            
            result.append({
                'id': r['batch_id'], 
                'batch_id': r['batch_id'],
                'platform': r['platform'], 
                'scope': r['scope'], 
                'content_preview': r['content_preview'], 
                'sent': sent_count,
                'failed': failed_count,
                'timestamp': timestamp_shamsi
            })
        
        return jsonify({
            "history": result,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        })
    except Exception as e:
        logger.critical(f"[Flask API] Uncaught exception in /api/history: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred while fetching history: {str(e)}"}), 500

@app.route('/api/history/delete_multiple', methods=['POST'])
def api_delete_multiple_history():
    """حذف چندگانه از تاریخچه ارسال‌ها"""
    try:
        data = request.get_json()
        history_ids = data.get('history_ids', [])
        
        if not history_ids:
            return jsonify({"error": "هیچ ارسالی انتخاب نشده"}), 400
        
        deleted_count = 0
        for history_id in history_ids:
            try:
                # حذف از دیتابیس
                db_execute("UPDATE broadcast_batches SET is_deleted = 1 WHERE batch_id = ?", (history_id,))
                deleted_count += 1
                logger.info(f"History record {history_id} deleted")
            except Exception as e:
                logger.error(f"Error deleting history record {history_id}: {e}")
                continue
        
        return jsonify({
            "success": True,
            "deleted_count": deleted_count,
            "total_requested": len(history_ids)
        })
    except Exception as e:
        logger.error(f"Error in api_delete_multiple_history: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete_broadcast_batch/<int:batch_id>', methods=['DELETE'])
def api_delete_broadcast_batch(batch_id: int):
    try: # Ensure this endpoint always returns JSON, even on unexpected errors.
        batch_info = db_fetchall("SELECT platform FROM broadcast_batches WHERE batch_id = ?", (batch_id,))
        if not batch_info:
            return jsonify({"error": "Batch not found."}), 404

        platform = batch_info[0]['platform']
        
        loop_target, app_target = None, None
        if platform == 'telegram':
            if not telegram_bot_loop or not telegram_app: return jsonify({"error": "Telegram bot not initialized."}), 503
            loop_target, app_target = telegram_bot_loop, telegram_app
        elif platform == 'bale':
            if not bale_bot_loop or not bale_app: return jsonify({"error": "Bale bot not initialized."}), 503
            loop_target, app_target = bale_bot_loop, bale_app
        elif platform == 'ita':
            # ایتا از API مستقیم استفاده می‌کند، نیازی به loop و app ندارد
            # اجرای حذف پیام‌های ایتا به صورت مستقیم
            try:
                result = asyncio.run(delete_messages_async(None, batch_id, platform))
                return jsonify({"success": True, "deleted_from_platform": result.get('deleted',0), "failed_on_platform": result.get('failed',0)})
            except Exception as e:
                logger.error(f"[Flask API] Error during ITA deletion for batch {batch_id}: {e}", exc_info=True)
                return jsonify({"error": f"Failed to delete ITA batch: {str(e)}"}), 500
        else:
            return jsonify({"error": "Invalid platform."}), 400
        
        try:
            fut_result = asyncio.run_coroutine_threadsafe(delete_messages_async(app_target, batch_id, platform), loop_target)
            
            result = fut_result.result(timeout=60)
            
            return jsonify({"success": True, "deleted_from_platform": result.get('deleted',0), "failed_on_platform": result.get('failed',0)})
        except asyncio.TimeoutError:
            logger.error(f"[Flask API] Delete operation timed out for batch {batch_id} on {platform}.")
            return jsonify({"error": "Delete operation timed out on bot platform."}), 504
        except Exception as e:
            logger.error(f"[Flask API] Error during deletion for batch {batch_id} on {platform}: {e}", exc_info=True)
            return jsonify({"error": f"Failed to delete batch: {str(e)}"}), 500
    except Exception as e: # Catch any other unexpected errors in the route itself
        logger.critical(f"[Flask API] Critical error in api_delete_broadcast_batch for batch {batch_id}: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

@app.route('/api/trigger_report/<string:platform>', methods=['POST'])
def api_trigger_report(platform: str):
    try:
        user_id_str = request.form.get('user_id') # Assume user_id (admin ID) is passed from frontend or hardcoded if for owner
        if not user_id_str: return jsonify({"error": "Admin user ID is required."}), 400
        user_id = int(user_id_str) # Convert to int

        loop_target, app_target, owner_id_target = None, None, None

        if platform == 'telegram':
            if not telegram_bot_loop or not telegram_app: return jsonify({"error": "Telegram bot not initialized."}), 503
            loop_target, app_target, owner_id_target = telegram_bot_loop, telegram_app, OWNER_ID
        elif platform == 'bale':
            if not bale_bot_loop or not bale_app: return jsonify({"error": "Bale bot not initialized."}), 503
            loop_target, app_target, owner_id_target = bale_bot_loop, bale_app, BALE_OWNER_ID
        elif platform == 'ita':
            # ایتا از API مستقیم استفاده می‌کند، نیازی به loop و app ندارد
            loop_target, app_target, owner_id_target = None, None, ITA_OWNER_ID
        else:
            return jsonify({"error": "Invalid platform."}), 400

        if user_id != owner_id_target:
             return jsonify({"error": "Only the bot owner can trigger reports."}), 403

        # ساخت mock objects برای export_handler_base
        from telegram import User, Message, Chat
        
        mock_user = User(id=user_id, is_bot=False, first_name="Admin")
        mock_chat = Chat(id=user_id, type="private")
        mock_message = Message(message_id=int(time.time()), date=int(time.time()), chat=mock_chat, from_user=mock_user)
        mock_update = TelegramUpdate(update_id=int(time.time()), message=mock_message)
        
        # ساخت context ساده
        class MockContext:
            def __init__(self, bot):
                self.bot = bot
                self._bot = bot  # برای shortcuts
        
        mock_context = MockContext(app_target.bot) if app_target else None

        logger.info(f"[Flask API] Triggering export for {platform} by admin {user_id}.")
        
        # ساخت گزارش اکسل مستقیماً
        try:
            rows = db_fetchall(f"SELECT chat_id, chat_type FROM chats WHERE platform='{platform}'")
            report_data = []
            
            for r in rows:
                cid_str, ctype_db = r['chat_id'], r['chat_type']
                try:
                    if platform == 'ita':
                        # ایتا از API مستقیم استفاده می‌کند - استفاده از asyncio.run برای sync context
                        try:
                            chat_info = asyncio.run(get_ita_chat_info(cid_str))
                            if chat_info:
                                members = asyncio.run(get_ita_chat_member_count(cid_str))
                                report_data.append({"ID": cid_str, "Title": chat_info.get('title', '') or (f"{chat_info.get('first_name', '')} {chat_info.get('last_name', '')}".strip()), 
                                                  "Type": ctype_db, "Members": members, "Username": chat_info.get('username', '')})
                            else:
                                report_data.append({"ID": cid_str, "Title": "Error: Could not get chat info", "Type": ctype_db, "Members": 1, "Username": ""})
                        except Exception as e:
                            logger.warning(f"Failed to get Ita chat info for {cid_str}: {e}")
                            report_data.append({"ID": cid_str, "Title": "Error: Could not get chat info", "Type": ctype_db, "Members": 1, "Username": ""})
                    else:
                        cid = int(cid_str)
                    # استفاده از asyncio.run_coroutine_threadsafe برای async calls
                    chat_info_future = asyncio.run_coroutine_threadsafe(app_target.bot.get_chat(cid), loop_target)
                    chat_info = chat_info_future.result(timeout=10)
                    
                    logger.info(f"[{platform} Export] Checking chat {cid_str}, DB type: {ctype_db}, API type from get_chat: {chat_info.type}")

                    members = 1 if chat_info.type == ChatType.PRIVATE else 1 
                    try: 
                        members_future = asyncio.run_coroutine_threadsafe(app_target.bot.get_chat_member_count(cid), loop_target)
                        members = members_future.result(timeout=10)
                        # اگر تعداد اعضا صفر است، آن را به یک تبدیل کن
                        if members == 0:
                            members = 1
                    except Exception as ex: 
                        logger.warning(f"[{platform} Export] Could not get member count for chat {cid_str} (API type: {chat_info.type}): {ex}")
                        members = 1
                    
                    report_data.append({"ID": chat_info.id, "Title": chat_info.title or (f"{chat_info.first_name or ''} {chat_info.last_name or ''}".strip()), 
                                      "Type": chat_info.type, "Members": members, "Username": chat_info.username or ""})
                except Exception as ex:
                    logger.warning(f"[{platform} Export] Could not get info for chat {cid_str}: {ex}")
                    report_data.append({"ID": cid_str, "Title": f"Error: {ex}", "Type": ctype_db, "Members": 1, "Username": ""})
            
            # ساخت فایل اکسل
            try:
                import pandas as pd
            except ImportError:
                logger.error("pandas not installed. Please install it with: pip install pandas openpyxl")
                return jsonify({"error": "pandas library not installed"}), 500
            df = pd.DataFrame(report_data)
            excel_filename = f"chats_export_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)
            df.to_excel(excel_path, index=False)
            
            # تعیین نام فارسی پلتفرم
            platform_name = {
                'telegram': 'تلگرام',
                'bale': 'بله',
                'ita': 'ایتا'
            }.get(platform, platform)
            
            # ارسال فایل به کاربر
            if platform == 'ita':
                # ایتا از API مستقیم استفاده می‌کند
                with open(excel_path, 'rb') as excel_file:
                    # ایتا از API مستقیم استفاده می‌کند، نیازی به ارسال فایل ندارد
                    logger.info(f"[{platform} Export] Excel file created: {excel_path}")
            else:
                with open(excel_path, 'rb') as excel_file:
                    send_future = asyncio.run_coroutine_threadsafe(
                    app_target.bot.send_document(chat_id=user_id, document=excel_file, 
                                                   caption=f"📊 گزارش چت‌های {platform_name} ({len(report_data)} مورد)"), 
                    loop_target)
                send_future.result(timeout=30)
            
            # حذف فایل موقت
            os.remove(excel_path)
            
            result = {"success": True, "message": f"گزارش اکسل برای {platform} ارسال شد"}
            
        except Exception as e:
            logger.error(f"[Flask API] Error creating export for {platform}: {e}", exc_info=True)
            result = {"success": False, "error": str(e)}
        
        return jsonify({"success": True, "message": f"Report generation triggered for {platform}. Check your bot's private chat for the file."})
    except Exception as e:
        logger.error(f"[Flask API] Error triggering report for {platform}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to trigger report: {str(e)}"}), 500

@app.route('/api/comprehensive_report', methods=['GET'])
def api_comprehensive_report():
    """گزارش جامع از تمام چت‌ها و آمار سیستم"""
    try:
        # دریافت آمار کلی
        stats_data = {}
        
        # آمار چت‌ها (بدون ادمین‌ها)
        t_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='telegram' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(OWNER_ID),))
        b_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='bale' AND is_active=1 AND (chat_type != 'private' OR chat_id != ?) GROUP BY chat_type", (str(BALE_OWNER_ID),))
        i_rows = db_fetchall("SELECT chat_type, COUNT(*) as cnt FROM chats WHERE platform='ita' AND is_active=1 GROUP BY chat_type")
        
        telegram_counts = {r['chat_type']: r['cnt'] for r in t_rows}
        bale_counts = {r['chat_type']: r['cnt'] for r in b_rows}
        ita_counts = {r['chat_type']: r['cnt'] for r in i_rows}
        
        # آمار اعضا
        telegram_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'telegram' AND c.chat_type != 'private' AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """)
        telegram_member_counts = {r['chat_type']: r['total_members'] for r in telegram_members}
        
        bale_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'bale' AND c.chat_type != 'private' AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """)
        bale_member_counts = {r['chat_type']: r['total_members'] for r in bale_members}
        
        ita_members = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = 'ita' AND c.chat_type != 'private' AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """)
        ita_member_counts = {r['chat_type']: r['total_members'] for r in ita_members}
        
        # اگر metrics خالی است، از جدول chats استفاده کن
        if not telegram_member_counts:
            telegram_member_counts = {chat_type: count for chat_type, count in telegram_counts.items()}
        if not bale_member_counts:
            bale_member_counts = {chat_type: count for chat_type, count in bale_counts.items()}
        if not ita_member_counts:
            ita_member_counts = {chat_type: count for chat_type, count in ita_counts.items()}
        
        # محاسبه مجموع‌ها
        telegram_total_chats = sum(telegram_counts.values())
        bale_total_chats = sum(bale_counts.values())
        ita_total_chats = sum(ita_counts.values())
        telegram_total_members = sum(telegram_member_counts.values()) if telegram_member_counts else 0
        bale_total_members = sum(bale_member_counts.values()) if bale_member_counts else 0
        ita_total_members = sum(ita_member_counts.values()) if ita_member_counts else 0
        
        # آمار ارسال‌ها
        broadcast_stats = db_fetchall("""
            SELECT platform, COUNT(*) as total_broadcasts, 
                   SUM(sent_count) as total_sent, 
                   SUM(failed_count) as total_failed
            FROM broadcast_batches 
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY platform
        """)
        
        broadcast_data = {}
        for stat in broadcast_stats:
            broadcast_data[stat['platform']] = {
                'total_broadcasts': int(stat['total_broadcasts']),
                'total_sent': int(stat['total_sent'] or 0),
                'total_failed': int(stat['total_failed'] or 0)
            }
        
        # لیست کامل چت‌ها (مرتب شده بر اساس آخرین عضویت)
        all_chats_raw = db_fetchall("""
            SELECT c.*, 
                   COALESCE(m.members_count, 1) as current_members,
                   m.date_key as last_metrics_update
            FROM chats c
            LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                AND m.date_key = (
                    SELECT MAX(date_key) FROM chats_metrics 
                    WHERE chat_id = c.chat_id AND platform = c.platform
                )
            ORDER BY c.created_at DESC, c.platform, c.chat_type, c.name
        """)
        
        # تبدیل Row objects به dictionary برای JSON serialization
        all_chats = []
        for chat in all_chats_raw:
            chat_dict = {
                'chat_id': str(chat['chat_id']),
                'platform': str(chat['platform']),
                'chat_type': str(chat['chat_type']),
                'name': str(chat['name']) if chat['name'] else None,
                'username': str(chat['username']) if chat['username'] else None,
                'is_active': bool(chat['is_active']),
                'tags': str(chat['tags']) if chat['tags'] else None,
                'created_at': str(chat['created_at']) if chat['created_at'] else None,
                'last_active': str(chat['last_active']) if chat['last_active'] else None,
                'current_members': int(chat['current_members']),
                'last_metrics_update': str(chat['last_metrics_update']) if chat['last_metrics_update'] else None
            }
            all_chats.append(chat_dict)
        
        # ساخت گزارش جامع
        # تبدیل زمان تولید گزارش به شمسی
        report_time = datetime.now()
        try:
            import jdatetime
            jdt = jdatetime.datetime.fromgregorian(year=report_time.year, month=report_time.month, day=report_time.day, 
                                                 hour=report_time.hour, minute=report_time.minute, second=report_time.second)
            report_time_shamsi = jdt.strftime('%Y/%m/%d %H:%M:%S')
        except Exception:
            report_time_shamsi = report_time.strftime("%Y-%m-%d %H:%M:%S")
        
        comprehensive_report = {
            "report_generated_at": report_time_shamsi,
            "summary": {
                "telegram": {
                    "total_chats": telegram_total_chats,
                    "total_members": telegram_total_members,
                    "users": telegram_counts.get("private", 0),
                    "groups": telegram_counts.get("group", 0),
                    "channels": telegram_counts.get("channel", 0),
                    "users_members": telegram_member_counts.get("private", 0),
                    "groups_members": telegram_member_counts.get("group", 0),
                    "channels_members": telegram_member_counts.get("channel", 0)
                },
                "bale": {
                    "total_chats": bale_total_chats,
                    "total_members": bale_total_members,
                    "users": bale_counts.get("private", 0),
                    "groups": bale_counts.get("group", 0),
                    "channels": bale_counts.get("channel", 0),
                    "users_members": bale_member_counts.get("private", 0),
                    "groups_members": bale_member_counts.get("group", 0),
                    "channels_members": bale_member_counts.get("channel", 0)
                },
                "ita": {
                    "total_chats": ita_total_chats,
                    "total_members": ita_total_members,
                    "users": ita_counts.get("private", 0),
                    "groups": ita_counts.get("group", 0),
                    "channels": ita_counts.get("channel", 0),
                    "users_members": ita_member_counts.get("private", 0),
                    "groups_members": ita_member_counts.get("group", 0),
                    "channels_members": ita_member_counts.get("channel", 0)
                },
                "grand_totals": {
                    "total_chats": telegram_total_chats + bale_total_chats + ita_total_chats,
                    "total_members": telegram_total_members + bale_total_members + ita_total_members,
                    "total_users": telegram_counts.get("private", 0) + bale_counts.get("private", 0) + ita_counts.get("private", 0),
                    "total_groups": telegram_counts.get("group", 0) + bale_counts.get("group", 0) + ita_counts.get("group", 0),
                    "total_channels": telegram_counts.get("channel", 0) + bale_counts.get("channel", 0) + ita_counts.get("channel", 0)
                }
            },
            "broadcast_statistics": broadcast_data,
            "detailed_chats": all_chats
        }
        
        return jsonify(comprehensive_report)
        
    except Exception as e:
        logger.error(f"[Flask API] Error generating comprehensive report: {e}", exc_info=True)
        return jsonify({"error": f"Failed to generate comprehensive report: {str(e)}"}), 500

@app.route('/api/generate_excel_report', methods=['POST'])
def api_generate_excel_report():
    """تولید و دانلود گزارش اکسلی - دقیقاً مطابق گزارش جامع ربات"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        selected_platforms = data.get('platforms', ['telegram', 'bale', 'ita'])
        if not isinstance(selected_platforms, list):
            selected_platforms = [selected_platforms]
        
        # بررسی نصب pandas
        try:
            import pandas as pd
            import openpyxl
        except ImportError:
            logger.error("pandas or openpyxl not installed. Please install them with: pip install pandas openpyxl")
            return jsonify({"error": "pandas or openpyxl library not installed"}), 500
        
        # --- شیت ۱: لیست چت‌ها (مطابق ربات) ---
        df_chats = pd.DataFrame()
        rows_all = []
        
        for pf in selected_platforms:
            db_rows = db_fetchall("SELECT chat_id, chat_type, name, username, created_at FROM chats WHERE platform= ?", (pf,))
            for r in db_rows:
                cid_str = r['chat_id']
                cid = int(cid_str) if str(cid_str).lstrip('-').isdigit() else None
                name_db, user_db, created_at = r['name'], r['username'], r['created_at']
                
                # اطلاعات پایه (بدون fetch_live_info برای سرعت)
                name_final = name_db or ''
                username_final = user_db or ''
                link = ''
                if username_final:
                    if pf == 'telegram':
                        link = f"https://t.me/{username_final}"
                    elif pf == 'bale':
                        link = f"https://ble.ir/{username_final}"
                    elif pf == 'ita':
                        link = f"https://eitaa.com/{username_final}"
                
                # تبدیل تاریخ به شمسی
                date_display = created_at or ''
                if created_at and jdatetime:
                    try:
                        y, m, d = int(created_at[0:4]), int(created_at[5:7]), int(created_at[8:10])
                        hh, mm, ss = int(created_at[11:13]), int(created_at[14:16]), int(created_at[17:19])
                        jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                        date_display = jdt.strftime('%Y/%m/%d %H:%M:%S')
                    except Exception: 
                        pass
                
                # تعداد اعضا از metrics
                member_count = 1
                if r['chat_type'] == 'private':
                    # برای کاربران خصوصی، تعداد اعضا همیشه 1 است
                    member_count = 1
                else:
                    try:
                        member_row = db_fetchone("""
                            SELECT members_count FROM chats_metrics 
                            WHERE chat_id = ? AND platform = ? 
                            ORDER BY date_key DESC LIMIT 1
                        """, (cid_str, pf))
                        if member_row and member_row['members_count']:
                            member_count = member_row['members_count']
                            # اگر تعداد اعضا صفر است، آن را به یک تبدیل کن
                            if member_count == 0:
                                member_count = 1
                    except Exception:
                        pass
                
                # دریافت تگ‌های چت
                chat_tags = get_chat_tags(cid_str, pf) or 'ندارد'
                
                rows_all.append({
                    'پلتفرم': 'تلگرام' if pf == 'telegram' else ('بله' if pf == 'bale' else 'ایتا'),
                    'شناسه چت': cid_str, 'نوع چت': r['chat_type'], 'نام': name_final,
                    'نام‌کاربری': username_final or 'ندارد', 'لینک': link or 'ندارد', 
                    'تگ‌ها': chat_tags, 'تعداد اعضا': member_count,
                    'تاریخ ثبت': date_display, '_sort': created_at or ''
                })
        
        if rows_all:
            df_chats = pd.DataFrame(rows_all)
            if '_sort' in df_chats.columns: 
                df_chats = df_chats.sort_values(by=['_sort'], ascending=False)
            df_chats = df_chats[['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تگ‌ها','تعداد اعضا','تاریخ ثبت']]
        else:
            df_chats = pd.DataFrame(columns=['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تگ‌ها','تعداد اعضا','تاریخ ثبت'])

        # --- شیت ۲: گزارش ارسال‌ها (مطابق ربات) ---
        df_broadcasts = pd.DataFrame()
        q_platforms = ' AND b.platform IN ({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else ''
        params = selected_platforms
        sql = f"""
        SELECT b.platform, b.batch_id, b.scope, b.content_preview, b.timestamp,
               COUNT(s.message_id) as total_sent,
               SUM(CASE WHEN c.chat_type = 'private' THEN 1 ELSE 0 END) as private_cnt,
               SUM(CASE WHEN c.chat_type = 'group' THEN 1 ELSE 0 END) as group_cnt,
               SUM(CASE WHEN c.chat_type = 'channel' THEN 1 ELSE 0 END) as channel_cnt
        FROM broadcast_batches b
        LEFT JOIN sent_messages s ON b.batch_id = s.batch_id
        LEFT JOIN chats c ON s.chat_id = c.chat_id AND b.platform = c.platform
        WHERE 1=1 {q_platforms}
        GROUP BY b.batch_id, b.platform, b.scope, b.content_preview, b.timestamp
        ORDER BY b.timestamp DESC
        """
        
        try:
            rows_broadcasts = db_fetchall(sql, tuple(params))
        except Exception as e:
            logger.error(f"Error fetching broadcast data: {e}")
            rows_broadcasts = []
        
        broadcast_data = []
        if rows_broadcasts:
            for r in rows_broadcasts:
                tstamp = r['timestamp']
                date_display = tstamp
                if jdatetime and tstamp:
                    try:
                        y, m, d, hh, mm, ss = map(int, [tstamp[0:4], tstamp[5:7], tstamp[8:10], tstamp[11:13], tstamp[14:16], tstamp[17:19]])
                        jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                        date_display = jdt.strftime('%Y/%m/%d %H:%M')
                    except Exception: 
                        pass
                
                platform_name = {
                    'telegram': 'تلگرام',
                    'bale': 'بله',
                    'ita': 'ایتا'
                }.get(r['platform'], r['platform'])
                
                broadcast_data.append({
                    'پلتفرم': platform_name,
                    'شناسه دسته': r['batch_id'], 'تاریخ': date_display, 'مقصدها': r['scope'],
                    'پیش‌نمایش محتوا': r['content_preview'], 'تعداد کل ارسال': r['total_sent'] or 0,
                    'کاربران': r['private_cnt'] or 0, 'گروه‌ها': r['group_cnt'] or 0, 'کانال‌ها': r['channel_cnt'] or 0,
                    '_sort': tstamp
                })
        
        if broadcast_data:
            df_broadcasts = pd.DataFrame(broadcast_data)
            if '_sort' in df_broadcasts.columns: 
                df_broadcasts = df_broadcasts.sort_values(by=['_sort'], ascending=False)
            df_broadcasts = df_broadcasts[['پلتفرم','شناسه دسته','تاریخ','مقصدها','پیش‌نمایش محتوا','تعداد کل ارسال','کاربران','گروه‌ها','کانال‌ها']]
        else:
            df_broadcasts = pd.DataFrame(columns=['پلتفرم','شناسه دسته','تاریخ','مقصدها','پیش‌نمایش محتوا','تعداد کل ارسال','کاربران','گروه‌ها','کانال‌ها'])

        # --- شیت ۳: آمار روزانه اعضا (مطابق ربات) ---
        df_daily_pivot = pd.DataFrame()
        q_platforms_daily = ' AND m.platform IN ({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else ''
        params_daily = selected_platforms
        sql_daily = f"""
        SELECT m.platform, m.chat_id, m.date_key, m.members_count,
               c.chat_type, c.name, c.username
        FROM chats_metrics m
        LEFT JOIN chats c ON c.chat_id=m.chat_id AND c.platform=m.platform
        WHERE 1=1 {q_platforms_daily} AND c.chat_type != 'private'
        """
        
        try:
            rows_daily = db_fetchall(sql_daily, tuple(params_daily))
        except Exception as e:
            logger.error(f"Error fetching daily data: {e}")
            rows_daily = []
        
        daily_data = []
        if rows_daily:
            for r in rows_daily:
                pf = r['platform']
                uname, nm = r['username'] or '', r['name'] or ''
                link = ''
                if uname:
                    if pf == 'telegram':
                        link = f"https://t.me/{uname}"
                    elif pf == 'bale':
                        link = f"https://ble.ir/{uname}"
                    elif pf == 'ita':
                        link = f"https://eitaa.com/{uname}"
                
                date_display = r['date_key']
                if jdatetime: 
                    try:
                        y,m,d = map(int, r['date_key'].split('-'))
                        date_display = jdatetime.date.fromgregorian(year=y, month=m, day=d).strftime('%Y/%m/%d')
                    except Exception: 
                        pass
                
                daily_data.append({
                    'پلتفرم': 'تلگرام' if pf=='telegram' else ('بله' if pf=='bale' else 'ایتا'), 
                    'شناسه چت': r['chat_id'], 'نوع چت': r['chat_type'],
                    'نام': nm, 'نام‌کاربری': uname, 'لینک': link, 'تاریخ': date_display,
                    'تعداد اعضا': r['members_count'], '_date_key': r['date_key']
                })
        
        if daily_data:
            df_daily_raw = pd.DataFrame(daily_data)
            if not df_daily_raw.empty:
                idx_cols = ['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک']
                pivot = df_daily_raw.pivot_table(index=idx_cols, columns='_date_key', values='تعداد اعضا', aggfunc='last')
                pivot = pivot.reindex(sorted(pivot.columns, reverse=True), axis=1)
                date_map = df_daily_raw.drop_duplicates('_date_key').set_index('_date_key')['تاریخ'].to_dict()
                pivot.rename(columns=date_map, inplace=True)
                df_daily_pivot = pivot.reset_index()
        else:
            df_daily_pivot = pd.DataFrame(columns=['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک'])

        # --- شیت ۴: تحلیل رشد (مطابق ربات) ---
        df_growth = pd.DataFrame()
        q_platforms_growth = '({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else '()'
        params_growth = selected_platforms

        # محاسبه تاریخ شروع و پایان برای تحلیل رشد (30 روز گذشته)
        from datetime import datetime as dt, timedelta
        end_date = dt.now().strftime('%Y-%m-%d')
        start_date = (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        sql_growth = f"""
        WITH rng AS (
          SELECT chat_id, platform,
                 MIN(date_key) AS d_start,
                 MAX(date_key) AS d_end
          FROM chats_metrics
          WHERE date_key BETWEEN ? AND ? AND platform IN {q_platforms_growth}
          GROUP BY chat_id, platform
        ),
        s AS (
          SELECT m.chat_id, m.platform, m.members_count AS start_members
          FROM chats_metrics m
          JOIN rng ON rng.chat_id=m.chat_id AND rng.platform=m.platform AND rng.d_start=m.date_key
        ),
        e AS (
          SELECT m.chat_id, m.platform, m.members_count AS end_members
          FROM chats_metrics m
          JOIN rng ON rng.chat_id=m.chat_id AND rng.platform=m.platform AND rng.d_end=m.date_key
        )
        SELECT r.platform, r.chat_id, r.d_start, r.d_end,
               s.start_members, e.end_members,
               c.chat_type, c.name, c.username
        FROM rng r
        LEFT JOIN s ON s.chat_id=r.chat_id AND s.platform=r.platform
        LEFT JOIN e ON e.chat_id=r.chat_id AND e.platform=r.platform
        LEFT JOIN chats c ON c.chat_id=r.chat_id AND c.platform=r.platform
        WHERE c.is_active = 1 AND c.chat_type != 'private'
        """
        
        params_growth_with_dates = [start_date, end_date] + params_growth
        try:
            rows_growth = db_fetchall(sql_growth, tuple(params_growth_with_dates))
        except Exception as e:
            logger.error(f"Error fetching growth data: {e}")
            rows_growth = []
        
        growth_data = []
        if rows_growth:
            for r in rows_growth:
                pf = r['platform']
                uname, nm = r['username'] or '', r['name'] or ''
                link = ''
                if uname:
                    if pf == 'telegram':
                        link = f"https://t.me/{uname}"
                    elif pf == 'bale':
                        link = f"https://ble.ir/{uname}"
                    elif pf == 'ita':
                        link = f"https://eitaa.com/{uname}"
                
                start_m, end_m = r['start_members'] or 0, r['end_members'] or 0
                growth = end_m - start_m
                growth_pct = (growth / start_m * 100.0) if start_m > 0 else (100.0 if end_m > 0 else 0.0)
                
                # محاسبه تعداد روزها بین تاریخ شروع و پایان
                try:
                    start_date_obj = dt.strptime(r['d_start'], '%Y-%m-%d')
                    end_date_obj = dt.strptime(r['d_end'], '%Y-%m-%d')
                    days = (end_date_obj - start_date_obj).days + 1
                except Exception:
                    days = 1
                
                avg_daily = growth / float(days) if days > 0 else 0
                start_disp, end_disp = r['d_start'], r['d_end']
                
                if jdatetime:
                    try:
                        y1,m1,d1 = map(int, start_disp.split('-'))
                        y2,m2,d2 = map(int, end_disp.split('-'))
                        start_disp = jdatetime.date.fromgregorian(year=y1, month=m1, day=d1).strftime('%Y/%m/%d')
                        end_disp = jdatetime.date.fromgregorian(year=y2, month=m2, day=d2).strftime('%Y/%m/%d')
                    except Exception: 
                        pass
                
                growth_data.append({
                    'پلتفرم': 'تلگرام' if pf=='telegram' else ('بله' if pf=='bale' else 'ایتا'),
                    'شناسه چت': r['chat_id'], 'نوع چت': r['chat_type'], 'نام': nm,
                    'نام‌کاربری': uname, 'لینک': link, 'اعضا در شروع': start_m,
                    'اعضا در پایان': end_m, 'رشد خالص': growth, 'رشد درصدی': round(growth_pct, 2),
                    'میانگین رشد روزانه': round(avg_daily, 2), 'تاریخ شروع': start_disp, 'تاریخ پایان': end_disp
                })
        
        if growth_data:
            df_growth = pd.DataFrame(growth_data)
        else:
            df_growth = pd.DataFrame(columns=['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','اعضا در شروع','اعضا در پایان','رشد خالص','رشد درصدی','میانگین رشد روزانه','تاریخ شروع','تاریخ پایان'])

        # --- ایجاد فایل اکسل با نام فارسی و تاریخ شمسی ---
        import time
        ts = int(time.time())
        
        # نام فایل با تاریخ شمسی
        if jdatetime:
            try:
                now = dt.now()
                jdt = jdatetime.datetime.fromgregorian(year=now.year, month=now.month, day=now.day, hour=now.hour, minute=now.minute)
                date_str = jdt.strftime('%Y%m%d_%H%M')
                filename = f"گزارش_مختصر_عملکرد_{date_str}.xlsx"
            except Exception:
                filename = f"گزارش_مختصر_عملکرد_{ts}.xlsx"
        else:
            filename = f"گزارش_مختصر_عملکرد_{ts}.xlsx"
        
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        # --- شیت ۵: آمار ربات‌ها ---
        df_bot_stats = generate_bot_statistics_sheet(selected_platforms)
        
        # --- شیت ۶: آمار روزانه ربات‌ها ---
        df_daily_bot_stats = generate_daily_bot_statistics_sheet(selected_platforms)
        
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df_chats.to_excel(writer, sheet_name="لیست چت‌ها", index=False)
            df_broadcasts.to_excel(writer, sheet_name="گزارش ارسال انبوه", index=False)
            df_daily_pivot.to_excel(writer, sheet_name="آمار روزانه اعضا", index=False)
            df_growth.to_excel(writer, sheet_name="تحلیل رشد", index=False)
            df_bot_stats.to_excel(writer, sheet_name="آمار ربات‌ها", index=False)
            df_daily_bot_stats.to_excel(writer, sheet_name="آمار روزانه ربات‌ها", index=False)
        
        # بازگرداندن فایل
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"[Flask API] Error generating Excel report: {e}", exc_info=True)
        return jsonify({"error": f"Failed to generate Excel report: {str(e)}"}), 500

@app.route('/api/daily_bot_statistics', methods=['GET'])
def api_daily_bot_statistics():
    """دریافت آمار روزانه ربات‌ها"""
    try:
        from datetime import datetime, timedelta
        import json
        import os
        
        # دریافت پارامترهای اختیاری
        days = request.args.get('days', 7, type=int)  # تعداد روزهای گذشته
        platform = request.args.get('platform')  # پلتفرم خاص (اختیاری)
        
        # محدود کردن تعداد روزها
        days = min(max(days, 1), 30)  # بین 1 تا 30 روز
        
        snapshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
        
        if not os.path.exists(snapshots_dir):
            return jsonify({"error": "No snapshots directory found"}), 404
        
        # دریافت فایل‌های snapshot
        snapshot_files = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            file_path = os.path.join(snapshots_dir, f'bot_statistics_{date}.json')
            if os.path.exists(file_path):
                snapshot_files.append((date, file_path))
        
        if not snapshot_files:
            return jsonify({"error": "No snapshots found"}), 404
        
        # خواندن snapshot ها
        snapshots_data = []
        for date, file_path in snapshot_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    snapshots_data.append(data)
            except Exception as e:
                logger.warning(f"Error reading snapshot {file_path}: {e}")
                continue
        
        # فیلتر کردن بر اساس پلتفرم اگر مشخص شده
        if platform:
            filtered_snapshots = []
            for snapshot in snapshots_data:
                if platform in snapshot.get('platforms', {}):
                    filtered_snapshot = {
                        'date': snapshot['date'],
                        'date_jalali': snapshot['date_jalali'],
                        'timestamp': snapshot['timestamp'],
                        'platforms': {platform: snapshot['platforms'][platform]},
                        'totals': snapshot['totals']
                    }
                    filtered_snapshots.append(filtered_snapshot)
            snapshots_data = filtered_snapshots
        
        return jsonify({
            "success": True,
            "data": snapshots_data,
            "total_snapshots": len(snapshots_data),
            "requested_days": days,
            "platform_filter": platform
        })
        
    except Exception as e:
        logger.error(f"Error getting daily bot statistics: {e}")
        return jsonify({"error": f"Failed to get daily bot statistics: {str(e)}"}), 500

@app.route('/api/post_stats/<int:batch_id>', methods=['GET'])
def api_post_stats(batch_id: int):
    """دریافت آمار بازدید پست‌های یک batch"""
    try:
        # دریافت آمار پست‌ها
        posts_stats = get_post_stats_by_batch(batch_id)
        
        if not posts_stats:
            return jsonify({"error": "No post stats found for this batch"}), 404
        
        # محاسبه آمار کلی
        total_posts = len(posts_stats)
        total_views = sum(post['views_count'] or 0 for post in posts_stats)
        total_forwards = sum(post['forwards_count'] or 0 for post in posts_stats)
        total_reactions = sum(post['reactions_count'] or 0 for post in posts_stats)
        
        # آمار بر اساس پلتفرم
        platform_stats = {}
        for post in posts_stats:
            pf = post['platform']
            if pf not in platform_stats:
                platform_stats[pf] = {
                    'posts_count': 0,
                    'total_views': 0,
                    'total_forwards': 0,
                    'total_reactions': 0,
                    'avg_views': 0
                }
            
            platform_stats[pf]['posts_count'] += 1
            platform_stats[pf]['total_views'] += post['views_count'] or 0
            platform_stats[pf]['total_forwards'] += post['forwards_count'] or 0
            platform_stats[pf]['total_reactions'] += post['reactions_count'] or 0
        
        # محاسبه میانگین بازدید
        for pf in platform_stats:
            if platform_stats[pf]['posts_count'] > 0:
                platform_stats[pf]['avg_views'] = round(platform_stats[pf]['total_views'] / platform_stats[pf]['posts_count'], 2)
        
        # تبدیل تاریخ‌ها به شمسی
        for post in posts_stats:
            if post['post_date'] and jdatetime:
                try:
                    # تبدیل تاریخ میلادی به شمسی
                    date_str = str(post['post_date'])
                    if len(date_str) >= 19:
                        y, m, d, hh, mm, ss = map(int, [
                            date_str[0:4], date_str[5:7], date_str[8:10],
                            date_str[11:13], date_str[14:16], date_str[17:19]
                        ])
                        jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                        post['post_date_shamsi'] = jdt.strftime('%Y/%m/%d %H:%M')
                    else:
                        post['post_date_shamsi'] = post['post_date']
                except Exception:
                    post['post_date_shamsi'] = post['post_date']
            else:
                post['post_date_shamsi'] = post['post_date']
        
        result = {
            'batch_id': batch_id,
            'summary': {
                'total_posts': total_posts,
                'total_views': total_views,
                'total_forwards': total_forwards,
                'total_reactions': total_reactions,
                'avg_views_per_post': round(total_views / total_posts, 2) if total_posts > 0 else 0
            },
            'platform_stats': platform_stats,
            'detailed_posts': posts_stats
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"[Flask API] Error getting post stats: {e}", exc_info=True)
        return jsonify({"error": f"Failed to get post stats: {str(e)}"}), 500

@app.route('/api/chat_administrators/<platform>/<chat_id>', methods=['GET'])
def api_get_chat_administrators(platform: str, chat_id: str):
    """دریافت لیست ادمین‌های چت"""
    try:
        import asyncio
        import concurrent.futures
        
        def run_async():
            try:
                # ایجاد loop جدید برای هر درخواست
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(get_chat_administrators(platform, chat_id))
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Error in async execution: {e}")
                return []
        
        # اجرا در thread جداگانه
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async)
            administrators = future.result(timeout=30)
        
        return jsonify({
            'success': True,
            'platform': platform,
            'chat_id': chat_id,
            'administrators': administrators
        })
    except Exception as e:
        logger.error(f"[Flask API] Error getting chat administrators: {e}", exc_info=True)
        return jsonify({"error": f"Failed to get administrators: {str(e)}"}), 500

@app.route('/api/chat_members/<platform>/<chat_id>', methods=['GET'])
def api_get_chat_members(platform: str, chat_id: str):
    """دریافت لیست اعضای چت"""
    try:
        # دریافت اعضای واقعی چت
        import asyncio
        members = asyncio.run(get_chat_members(platform, chat_id))
        
        # به‌روزرسانی ردیابی اعضای یکتا
        chat_type = 'channel' if chat_id.startswith('-100') else 'private'
        update_member_tracking_from_chat(platform, chat_id, chat_type, members)
        
        return jsonify({
            'success': True,
            'platform': platform,
            'chat_id': chat_id,
            'members': members
        })
    except Exception as e:
        logger.error(f"[Flask API] Error getting chat members: {e}", exc_info=True)
        return jsonify({"error": f"Failed to get chat members: {str(e)}"}), 500

# @app.route('/api/unique_member_stats', methods=['GET'])
# def api_get_unique_member_stats():
#     """دریافت آمار اعضای یکتا - غیرفعال برای توسعه آینده"""
#     try:
#         # بررسی اینکه آیا جداول خالی هستند یا نه
#         conn = sqlite3.connect(DB_FILE)
#         cursor = conn.cursor()
#         
#         # بررسی وجود داده در جداول
#         cursor.execute("SELECT COUNT(*) FROM unique_members")
#         unique_count = cursor.fetchone()[0]
#         
#         cursor.execute("SELECT COUNT(*) FROM chat_memberships")
#         membership_count = cursor.fetchone()[0]
#         
#         conn.close()
#         
#         # اگر جداول خالی هستند، سعی کنیم آنها را پر کنیم
#         if unique_count == 0 or membership_count == 0:
#             logger.info("Tables are empty, populating with existing data...")
#             populate_unique_members_from_existing_data()
#         
#         stats = get_unique_member_stats()
#         return jsonify({
#             'success': True,
#             'stats': stats
#         })
#     except Exception as e:
#         logger.error(f"[Flask API] Error getting unique member stats: {e}", exc_info=True)
#         return jsonify({"error": f"Failed to get unique member stats: {str(e)}"}), 500

@app.route('/api/unique_member_stats', methods=['GET'])
def api_get_unique_member_stats():
    """دریافت آمار اعضای یکتا - غیرفعال"""
    return jsonify({
        'success': False,
        'message': 'آمار اعضای یکتا موقتاً غیرفعال است و در نسخه‌های آینده فعال خواهد شد',
        'disabled': True,
        'stats': {
            'total_unique_members': 0,
            'platform_breakdown': {},
            'chat_breakdown': []
        }
    }), 200

def populate_unique_members_from_existing_data():
    """پر کردن جداول unique_members و chat_memberships با داده‌های موجود"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # دریافت تمام چت‌های فعال
        cursor.execute("""
            SELECT chat_id, platform, chat_type, name, username 
            FROM chats 
            WHERE is_active = 1
        """)
        chats = cursor.fetchall()
        
        logger.info(f"Found {len(chats)} active chats to process")
        
        for chat_id, platform, chat_type, name, username in chats:
            try:
                # دریافت اعضای چت از API
                if platform == 'telegram':
                    members = get_telegram_chat_members(chat_id)
                elif platform == 'bale':
                    members = get_bale_chat_members(chat_id)
                elif platform == 'ita':
                    members = get_ita_chat_members(chat_id)
                else:
                    continue
                
                if not members:
                    logger.warning(f"No members found for {platform} chat {chat_id}")
                    continue
                
                logger.info(f"Processing {len(members)} members for {platform} chat {chat_id}")
                
                # ذخیره اعضای یکتا و عضویت‌ها
                for member in members:
                    user_id = str(member.get('user_id', ''))
                    if not user_id:
                        continue
                    
                    # ذخیره عضو یکتا
                    cursor.execute("""
                        INSERT OR REPLACE INTO unique_members 
                        (user_id, platform, first_name, last_name, username, is_bot, last_seen)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        user_id, 
                        platform, 
                        member.get('first_name'), 
                        member.get('last_name'), 
                        member.get('username'), 
                        1 if member.get('is_bot', False) else 0
                    ))
                    
                    # ذخیره عضویت در چت
                    cursor.execute("""
                        INSERT OR REPLACE INTO chat_memberships 
                        (user_id, platform, chat_id, chat_type, joined_at, is_active)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                    """, (user_id, platform, chat_id, chat_type))
                
                conn.commit()
                logger.info(f"Successfully processed {platform} chat {chat_id}")
                
            except Exception as e:
                logger.error(f"Error processing {platform} chat {chat_id}: {e}")
                continue
        
        conn.close()
        logger.info("Finished populating unique members from existing data")
        
    except Exception as e:
        logger.error(f"Error populating unique members: {e}")

def get_telegram_chat_members(chat_id):
    """دریافت اعضای چت تلگرام"""
    try:
        # استفاده از متغیر global telegram_app
        global telegram_app
        if not telegram_app or not telegram_app.bot:
            logger.warning("Telegram app not initialized")
            return []
        
        members = []
        try:
            # دریافت اطلاعات چت
            chat = telegram_app.bot.get_chat(chat_id)
            if not chat:
                return []
            
            # برای چت‌های خصوصی
            if chat.type == 'private':
                members.append({
                    'user_id': chat.id,
                    'first_name': chat.first_name or "",
                    'last_name': chat.last_name or "",
                    'username': chat.username or "",
                    'is_bot': False
                })
            else:
                # برای گروه‌ها و کانال‌ها - فقط ادمین‌ها
                try:
                    administrators = telegram_app.bot.get_chat_administrators(chat_id)
                    for admin in administrators:
                        members.append({
                            'user_id': admin.user.id,
                            'first_name': admin.user.first_name or "",
                            'last_name': admin.user.last_name or "",
                            'username': admin.user.username or "",
                            'is_bot': admin.user.is_bot
                        })
                except Exception as e:
                    logger.warning(f"Could not get administrators for {chat_id}: {e}")
                
                # تلاش برای دریافت اعضای عادی (محدود)
                try:
                    chat_members = telegram_app.bot.get_chat_members(chat_id, limit=50)
                    for member in chat_members:
                        # جلوگیری از تکرار ادمین‌ها
                        if not any(m['user_id'] == member.user.id for m in members):
                            members.append({
                                'user_id': member.user.id,
                                'first_name': member.user.first_name or "",
                                'last_name': member.user.last_name or "",
                                'username': member.user.username or "",
                                'is_bot': member.user.is_bot
                            })
                except Exception as e:
                    logger.warning(f"Could not get regular members for {chat_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error getting members for telegram chat {chat_id}: {e}")
            return []
        
        logger.info(f"Retrieved {len(members)} members for telegram chat {chat_id}")
        return members
        
    except Exception as e:
        logger.error(f"Error getting telegram chat members for {chat_id}: {e}")
        return []

def get_telegram_chat_members_comprehensive(chat_id):
    """دریافت جامع اعضای چت تلگرام با تلاش برای دریافت حداکثر اعضا"""
    try:
        global telegram_app
        if not telegram_app or not telegram_app.bot:
            logger.warning("Telegram app not initialized")
            return []
        
        members = []
        try:
            # استفاده از تابع موجود که قبلاً کار می‌کرد
            members = get_telegram_chat_members(chat_id)
            
            # اگر اعضا دریافت شد، تلاش برای دریافت بیشتر
            if members:
                logger.info(f"Retrieved {len(members)} members using standard method for {chat_id}")
                
                # تلاش برای دریافت تعداد کل اعضا
                try:
                    member_count = telegram_app.bot.get_chat_member_count(chat_id)
                    logger.info(f"Total member count for {chat_id}: {member_count}")
                    
                    # اگر تعداد کل بیشتر از اعضای دریافت شده است
                    if member_count > len(members):
                        logger.warning(f"⚠️ Only retrieved {len(members)} out of {member_count} total members for {chat_id}")
                        logger.warning("This may indicate API limitations or insufficient permissions")
                    else:
                        logger.info(f"✅ Successfully retrieved all {len(members)} members for {chat_id}")
                        
                except Exception as e:
                    logger.warning(f"Could not get member count for {chat_id}: {e}")
            else:
                logger.warning(f"No members retrieved for {chat_id}")
        
        except Exception as e:
            logger.error(f"Error getting comprehensive members for telegram chat {chat_id}: {e}")
            return []
        
        logger.info(f"Comprehensive retrieval: {len(members)} total members for telegram chat {chat_id}")
        return members
        
    except Exception as e:
        logger.error(f"Error getting comprehensive telegram chat members for {chat_id}: {e}")
        return []

def get_bale_chat_members(chat_id):
    """دریافت اعضای چت بله"""
    try:
        # استفاده از متغیر global bale_app
        global bale_app
        if not bale_app or not bale_app.bot:
            logger.warning("Bale app not initialized")
            return []
        
        members = []
        try:
            # دریافت اطلاعات چت
            chat = bale_app.bot.get_chat(chat_id)
            if not chat:
                return []
            
            # برای چت‌های خصوصی
            if chat.type == 'private':
                members.append({
                    'user_id': chat.id,
                    'first_name': chat.first_name or "",
                    'last_name': chat.last_name or "",
                    'username': chat.username or "",
                    'is_bot': False
                })
            else:
                # برای گروه‌ها و کانال‌ها - فقط ادمین‌ها
                try:
                    administrators = bale_app.bot.get_chat_administrators(chat_id)
                    for admin in administrators:
                        members.append({
                            'user_id': admin.user.id,
                            'first_name': admin.user.first_name or "",
                            'last_name': admin.user.last_name or "",
                            'username': admin.user.username or "",
                            'is_bot': admin.user.is_bot
                        })
                except Exception as e:
                    logger.warning(f"Could not get administrators for bale chat {chat_id}: {e}")
                
                # تلاش برای دریافت اعضای عادی (محدود)
                try:
                    chat_members = bale_app.bot.get_chat_members(chat_id, limit=50)
                    for member in chat_members:
                        # جلوگیری از تکرار ادمین‌ها
                        if not any(m['user_id'] == member.user.id for m in members):
                            members.append({
                                'user_id': member.user.id,
                                'first_name': member.user.first_name or "",
                                'last_name': member.user.last_name or "",
                                'username': member.user.username or "",
                                'is_bot': member.user.is_bot
                            })
                except Exception as e:
                    logger.warning(f"Could not get regular members for bale chat {chat_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error getting members for bale chat {chat_id}: {e}")
            return []
        
        logger.info(f"Retrieved {len(members)} members for bale chat {chat_id}")
        return members
    
    except Exception as e:
        logger.error(f"Outer error getting members for bale chat {chat_id}: {e}")
        return []

def get_bale_chat_members_comprehensive(chat_id):
    """دریافت جامع اعضای چت بله با تلاش برای دریافت حداکثر اعضا"""
    try:
        global bale_app
        if not bale_app or not bale_app.bot:
            logger.warning("Bale app not initialized")
            return []
        
        members = []
        try:
            # استفاده از تابع موجود که قبلاً کار می‌کرد
            members = get_bale_chat_members(chat_id)
            
            # اگر اعضا دریافت شد، تلاش برای دریافت بیشتر
            if members:
                logger.info(f"Retrieved {len(members)} members using standard method for bale chat {chat_id}")
                
                # تلاش برای دریافت تعداد کل اعضا
                try:
                    member_count = bale_app.bot.get_chat_member_count(chat_id)
                    logger.info(f"Total member count for bale chat {chat_id}: {member_count}")
                    
                    # اگر تعداد کل بیشتر از اعضای دریافت شده است
                    if member_count > len(members):
                        logger.warning(f"⚠️ Only retrieved {len(members)} out of {member_count} total members for bale chat {chat_id}")
                        logger.warning("This may indicate API limitations or insufficient permissions")
                    else:
                        logger.info(f"✅ Successfully retrieved all {len(members)} members for bale chat {chat_id}")
                        
                except Exception as e:
                    logger.warning(f"Could not get member count for bale chat {chat_id}: {e}")
            else:
                logger.warning(f"No members retrieved for bale chat {chat_id}")
        
        except Exception as e:
            logger.error(f"Error getting comprehensive members for bale chat {chat_id}: {e}")
            return []
        
        logger.info(f"Comprehensive retrieval: {len(members)} total members for bale chat {chat_id}")
        return members
        
    except Exception as e:
        logger.error(f"Error getting comprehensive bale chat members for {chat_id}: {e}")
        return []

def get_ita_chat_members(chat_id):
    """دریافت اعضای چت ایتا"""
    try:
        # ایتا از API مستقیم استفاده می‌کند
        # برای حال حاضر، فقط یک عضو پیش‌فرض برمی‌گردانیم
        # چون API ایتا برای دریافت اعضا محدودیت دارد
        
        logger.info(f"Getting ITA chat members for {chat_id}")
        
        # برای حال حاضر، یک عضو پیش‌فرض برمی‌گردانیم
        # در آینده می‌توان این را با API ایتا بهبود داد
        members = []
        
        try:
            # دریافت اطلاعات چت از API ایتا
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChat"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                chat_info = response.json()
                if chat_info.get('ok'):
                    result = chat_info.get('result', {})
                    
                    # برای چت‌های خصوصی
                    if result.get('type') == 'private':
                        members.append({
                            'user_id': result.get('id'),
                            'first_name': result.get('first_name'),
                            'last_name': result.get('last_name'),
                            'username': result.get('username'),
                            'is_bot': False
                        })
                    else:
                        # برای گروه‌ها و کانال‌ها، یک عضو پیش‌فرض اضافه می‌کنیم
                        members.append({
                            'user_id': result.get('id', chat_id),
                            'first_name': result.get('title', 'Unknown'),
                            'last_name': '',
                            'username': '',
                            'is_bot': False
                        })
                else:
                    logger.warning(f"ITA API error for chat {chat_id}: {chat_info.get('description', 'Unknown error')}")
            else:
                logger.warning(f"ITA API request failed for chat {chat_id}: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error getting ITA chat info for {chat_id}: {e}")
        
        return members
        
    except Exception as e:
        logger.error(f"Error getting ita chat members for {chat_id}: {e}")
        return []

def get_ita_chat_members_comprehensive(chat_id):
    """دریافت جامع اعضای چت ایتا با تلاش برای دریافت حداکثر اعضا"""
    try:
        logger.info(f"Getting comprehensive ITA chat members for {chat_id}")
        
        members = []
        
        try:
            # دریافت اطلاعات چت از API ایتا
            url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChat"
            data = {"chat_id": str(chat_id)}
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, data=data, headers=headers, timeout=15)
            
            if response.status_code == 200:
                chat_info = response.json()
                if chat_info.get('ok'):
                    result = chat_info.get('result', {})
                    
                    # برای چت‌های خصوصی
                    if result.get('type') == 'private':
                        members.append({
                            'user_id': result.get('id'),
                            'first_name': result.get('first_name'),
                            'last_name': result.get('last_name'),
                            'username': result.get('username'),
                            'is_bot': False
                        })
                    else:
                        # برای گروه‌ها و کانال‌ها، تلاش برای دریافت اعضا
                        try:
                            # تلاش برای دریافت لیست اعضا
                            members_url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChatMembers"
                            members_data = {"chat_id": str(chat_id)}
                            
                            members_response = requests.post(members_url, data=members_data, headers=headers, timeout=15)
                            
                            if members_response.status_code == 200:
                                members_info = members_response.json()
                                if members_info.get('ok'):
                                    for member in members_info.get('result', []):
                                        members.append({
                                            'user_id': member.get('user', {}).get('id'),
                                            'first_name': member.get('user', {}).get('first_name'),
                                            'last_name': member.get('user', {}).get('last_name'),
                                            'username': member.get('user', {}).get('username'),
                                            'is_bot': member.get('user', {}).get('is_bot', False)
                                        })
                                    logger.info(f"Retrieved {len(members_info.get('result', []))} members from ITA chat {chat_id}")
                                else:
                                    logger.warning(f"ITA members API error for chat {chat_id}: {members_info.get('description', 'Unknown error')}")
                            else:
                                logger.warning(f"ITA members API request failed for chat {chat_id}: {members_response.status_code}")
                                
                        except Exception as e:
                            logger.warning(f"Error getting ITA chat members for {chat_id}: {e}")
                            
                            # Fallback: یک عضو پیش‌فرض
                            members.append({
                                'user_id': result.get('id', chat_id),
                                'first_name': result.get('title', 'Unknown'),
                                'last_name': '',
                                'username': '',
                                'is_bot': False
                            })
                else:
                    logger.warning(f"ITA API error for chat {chat_id}: {chat_info.get('description', 'Unknown error')}")
            else:
                logger.warning(f"ITA API request failed for chat {chat_id}: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error getting comprehensive ITA chat info for {chat_id}: {e}")
        
        logger.info(f"Comprehensive retrieval: {len(members)} total members for ITA chat {chat_id}")
        return members
        
    except Exception as e:
        logger.error(f"Error getting comprehensive ita chat members for {chat_id}: {e}")
        return []

@app.route('/api/update_unique_members', methods=['POST'])
def api_update_unique_members():
    """به‌روزرسانی دستی آمار اعضای یکتا"""
    try:
        logger.info("Manual update of unique members requested")
        populate_unique_members_from_existing_data()
        
        stats = get_unique_member_stats()
        return jsonify({
            'success': True,
            'message': 'آمار اعضای یکتا به‌روزرسانی شد',
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error updating unique members: {e}", exc_info=True)
        return jsonify({"error": f"Failed to update unique members: {str(e)}"}), 500

# @app.route('/api/collect_all_members', methods=['POST'])
# def api_collect_all_members():
#     """API endpoint to comprehensively collect members from all chats - DISABLED"""

@app.route('/api/collect_all_members', methods=['POST'])
def api_collect_all_members():
    """API endpoint to comprehensively collect members from all chats - DISABLED"""
    return jsonify({
        "success": False,
        "message": "جمع‌آوری اعضا موقتاً غیرفعال است و در نسخه‌های آینده فعال خواهد شد",
        "disabled": True,
        "total_collected": 0,
        "platform_stats": {},
        "final_stats": {
            "total_unique_members": 0,
            "platform_breakdown": {},
            "chat_breakdown": []
        }
    }), 200

@app.route('/api/verify_member_stats', methods=['POST'])
def api_verify_member_stats():
    """API endpoint to verify the accuracy of member statistics - DISABLED"""
    return jsonify({
        "success": False,
        "message": "بررسی صحت آمار موقتاً غیرفعال است و در نسخه‌های آینده فعال خواهد شد",
        "disabled": True,
        "results": {
            "total_chats": 0,
            "verified_chats": 0,
            "incomplete_chats": 0,
            "chat_details": [],
            "summary": {
                "fully_verified": 0,
                "partially_verified": 0,
                "verification_failed": 0
            },
            "accuracy_percentage": 0
        }
    }), 200

@app.route('/api/test_ita_chat_info', methods=['POST'])
def api_test_ita_chat_info():
    """API endpoint to test ITA chat info retrieval"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        if not chat_id:
            return jsonify({"error": "Missing chat_id"}), 400
        
        logger.info(f"🔍 [Test ITA] Testing chat info for ID: {chat_id}")
        
        # تست دریافت اطلاعات چت
        url = f"{ITA_API_BASE_URL}/{ITA_BOT_TOKEN}/getChat"
        data = {"chat_id": str(chat_id)}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        logger.info(f"📡 [Test ITA] Request to: {url}")
        logger.info(f"📋 [Test ITA] Data: {data}")
        
        response = requests.post(url, data=data, headers=headers, timeout=15)
        
        logger.info(f"📊 [Test ITA] Response status: {response.status_code}")
        logger.info(f"📄 [Test ITA] Response content: {response.text}")
        
        result = {
            "chat_id": chat_id,
            "request_url": url,
            "request_data": data,
            "response_status": response.status_code,
            "response_content": response.text,
            "parsed_result": None
        }
        
        if response.status_code == 200:
            try:
                json_result = response.json()
                result["parsed_result"] = json_result
                
                if json_result.get('ok'):
                    chat_info = json_result.get('result', {})
                    result["success"] = True
                    result["chat_info"] = {
                        "id": chat_info.get('id'),
                        "title": chat_info.get('title', 'نام یافت نشد'),
                        "username": chat_info.get('username', 'یوزرنیم یافت نشد'),
                        "type": chat_info.get('type', 'نوع یافت نشد'),
                        "description": chat_info.get('description', 'توضیحات یافت نشد'),
                        "member_count": chat_info.get('member_count', 'تعداد یافت نشد'),
                        "invite_link": chat_info.get('invite_link', 'لینک یافت نشد')
                    }
                else:
                    result["success"] = False
                    result["error"] = json_result.get('description', 'خطای نامشخص')
            except json.JSONDecodeError as e:
                result["success"] = False
                result["error"] = f"خطا در تجزیه JSON: {e}"
        else:
            result["success"] = False
            result["error"] = f"خطا در درخواست HTTP: {response.status_code}"
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"❌ [Test ITA] Error: {e}")
        return jsonify({"error": f"Failed to test ITA chat info: {str(e)}"}), 500

@app.route('/api/promote_member', methods=['POST'])
def api_promote_member():
    """ارتقای کاربر به ادمین"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        
        if not all([platform, chat_id, user_id]):
            return jsonify({"error": "platform, chat_id, and user_id are required"}), 400
        
        # تبدیل user_id به integer
        try:
            user_id = int(user_id)
            logger.info(f"[Flask API] Promoting user {user_id} in {platform} chat {chat_id}")
        except (ValueError, TypeError):
            logger.error(f"[Flask API] Invalid user_id: {user_id}")
            return jsonify({"error": "user_id must be a valid integer"}), 400
        
        import asyncio
        import concurrent.futures
        
        def run_async_promote():
            try:
                # استفاده از asyncio.run در thread جداگانه
                return asyncio.run(promote_chat_member(
                    platform=platform,
                    chat_id=chat_id,
                    user_id=user_id,
                    can_change_info=data.get('can_change_info', True),
                    can_delete_messages=data.get('can_delete_messages', True),
                    can_invite_users=data.get('can_invite_users', True),
                    can_restrict_members=data.get('can_restrict_members', True),
                    can_pin_messages=data.get('can_pin_messages', True),
                    can_promote_members=data.get('can_promote_members', False)
                ))
            except Exception as e:
                logger.error(f"Error in async promote execution: {e}")
                return False
        
        # اجرا در thread جداگانه
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async_promote)
            success = future.result(timeout=30)
        
        return jsonify({
            'success': success,
            'message': 'Member promoted successfully' if success else 'Failed to promote member'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error promoting member: {e}", exc_info=True)
        return jsonify({"error": f"Failed to promote member: {str(e)}"}), 500

@app.route('/api/demote_member', methods=['POST'])
def api_demote_member():
    """تنزل ادمین"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        user_id = data.get('user_id')
        
        if not all([platform, chat_id, user_id]):
            return jsonify({"error": "platform, chat_id, and user_id are required"}), 400
        
        # تبدیل user_id به integer
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "user_id must be a valid integer"}), 400
        
        import asyncio
        import concurrent.futures
        
        def run_async_demote():
            try:
                # استفاده از asyncio.run در thread جداگانه
                return asyncio.run(demote_chat_member(platform, chat_id, user_id))
            except Exception as e:
                logger.error(f"Error in async demote execution: {e}")
                return False
        
        # اجرا در thread جداگانه
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async_demote)
            success = future.result(timeout=30)
        
        return jsonify({
            'success': success,
            'message': 'Member demoted successfully' if success else 'Failed to demote member'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error demoting member: {e}", exc_info=True)
        return jsonify({"error": f"Failed to demote member: {str(e)}"}), 500

@app.route('/api/pin_message', methods=['POST'])
def api_pin_message():
    """سنجاق کردن پیام"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        message_id = data.get('message_id')
        
        if not all([platform, chat_id, message_id]):
            return jsonify({"error": "platform, chat_id, and message_id are required"}), 400
        
        import asyncio
        
        # استفاده از asyncio.run به جای ایجاد loop جدید
        success = asyncio.run(pin_chat_message(
            platform=platform,
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=data.get('disable_notification', False)
        ))
        
        return jsonify({
            'success': success,
            'message': 'Message pinned successfully' if success else 'Failed to pin message'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error pinning message: {e}", exc_info=True)
        return jsonify({"error": f"Failed to pin message: {str(e)}"}), 500

@app.route('/api/unpin_message', methods=['POST'])
def api_unpin_message():
    """برداشتن سنجاق پیام"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        message_id = data.get('message_id')  # اختیاری
        
        if not all([platform, chat_id]):
            return jsonify({"error": "platform and chat_id are required"}), 400
        
        import asyncio
        
        # استفاده از asyncio.run به جای ایجاد loop جدید
        success = asyncio.run(unpin_chat_message(platform, chat_id, message_id))
        
        return jsonify({
            'success': success,
            'message': 'Message unpinned successfully' if success else 'Failed to unpin message'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error unpinning message: {e}", exc_info=True)
        return jsonify({"error": f"Failed to unpin message: {str(e)}"}), 500

@app.route('/api/edit_message', methods=['POST'])
def api_edit_message():
    """ویرایش پیام"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        message_id = data.get('message_id')
        text = data.get('text')
        caption = data.get('caption')
        
        if not all([platform, chat_id, message_id]):
            return jsonify({"error": "platform, chat_id, and message_id are required"}), 400
        
        if not text and not caption:
            return jsonify({"error": "text or caption is required"}), 400
        
        import asyncio
        
        # استفاده از asyncio.run به جای ایجاد loop جدید
        if text:
            success = asyncio.run(edit_message_text(
                platform=platform,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=data.get('parse_mode', 'HTML')
            ))
        else:
            success = asyncio.run(edit_message_caption(
                platform=platform,
                chat_id=chat_id,
                message_id=message_id,
                caption=caption,
                parse_mode=data.get('parse_mode', 'HTML')
            ))
        
        return jsonify({
            'success': success,
            'message': 'Message edited successfully' if success else 'Failed to edit message'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error editing message: {e}", exc_info=True)
        return jsonify({"error": f"Failed to edit message: {str(e)}"}), 500

@app.route('/api/send_poll', methods=['POST'])
def api_send_poll():
    """ارسال نظرسنجی"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON data required"}), 400
        
        platform = data.get('platform')
        chat_id = data.get('chat_id')
        question = data.get('question')
        options = data.get('options', [])
        
        if not all([platform, chat_id, question, options]):
            return jsonify({"error": "platform, chat_id, question, and options are required"}), 400
        
        if len(options) < 2:
            return jsonify({"error": "At least 2 options are required"}), 400
        
        import asyncio
        
        # استفاده از asyncio.run به جای ایجاد loop جدید
        success, message_id = asyncio.run(send_poll(
            platform=platform,
            chat_id=chat_id,
            question=question,
            options=options,
            is_anonymous=data.get('is_anonymous', True),
            poll_type=data.get('poll_type', 'regular'),
            allows_multiple_answers=data.get('allows_multiple_answers', False),
            correct_option_id=data.get('correct_option_id'),
            explanation=data.get('explanation'),
            open_period=data.get('open_period'),
            close_date=data.get('close_date')
        ))
        
        return jsonify({
            'success': success,
            'message_id': message_id,
            'message': 'Poll sent successfully' if success else 'Failed to send poll'
        })
    except Exception as e:
        logger.error(f"[Flask API] Error sending poll: {e}", exc_info=True)
        return jsonify({"error": f"Failed to send poll: {str(e)}"}), 500

@app.route('/api/chats', methods=['GET'])
def api_get_chats():
    """دریافت لیست چت‌های ثبت شده"""
    try:
        platform = request.args.get('platform')
        
        if platform:
            query = "SELECT * FROM chats WHERE platform = ? AND is_active = 1 ORDER BY created_at DESC, name"
            chats = db_fetchall(query, (platform,))
        else:
            query = "SELECT * FROM chats WHERE is_active = 1 ORDER BY created_at DESC, platform, name"
            chats = db_fetchall(query)
        
        # تبدیل Row objects به dictionary برای JSON serialization
        chats_list = []
        for chat in chats:
            chat_dict = dict(chat)
            chats_list.append(chat_dict)
        
        return jsonify({
            'success': True,
            'chats': chats_list
        })
    except Exception as e:
        logger.error(f"[Flask API] Error getting chats: {e}", exc_info=True)
        return jsonify({"error": f"Failed to get chats: {str(e)}"}), 500

# =================================================================
# --- New API Endpoints for Segmentation and Scheduler ---
# =================================================================

@app.route('/api/segmentation/chats', methods=['GET'])
def api_get_chats_by_segmentation():
    """دریافت چت‌ها بر اساس معیارهای segmentation"""
    try:
        platform = request.args.get('platform')
        chat_type = request.args.get('chat_type')
        tags = request.args.get('tags')
        is_active = request.args.get('is_active')
        days_since_active = request.args.get('days_since_active')
        
        # تبدیل پارامترها
        is_active_bool = None
        if is_active is not None:
            is_active_bool = is_active.lower() == 'true'
        
        days_since_active_int = None
        if days_since_active is not None:
            try:
                days_since_active_int = int(days_since_active)
            except ValueError:
                return jsonify({"error": "Invalid days_since_active parameter"}), 400
        
        chats = get_chats_by_segmentation(
            platform=platform,
            chat_type=chat_type,
            tags=tags,
            is_active=is_active_bool,
            days_since_active=days_since_active_int
        )
        
        return jsonify([dict(chat) for chat in chats])
    except Exception as e:
        logger.error(f"Error in api_get_chats_by_segmentation: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/schedule_broadcast', methods=['POST'])
def api_schedule_broadcast():
    """زمان‌بندی یک ارسال"""
    try:
        title = request.form.get('title')
        platforms = json.loads(request.form.get('platforms', '[]'))
        scopes = json.loads(request.form.get('scopes', '[]'))
        scheduled_time = request.form.get('scheduled_time')
        solar_date = request.form.get('solar_date')
        tags = request.form.get('tags', '')
        pin_message = request.form.get('pin_message', 'false') == 'true'
        
        # دریافت پارامترهای فیلتر تگ
        send_to_tagged = request.form.get('send_to_tagged', 'false') == 'true'
        tag_filter = request.form.get('tag_filter', '').strip()
        
        # دریافت محتوا
        message = request.form.get('message', '')
        caption = request.form.get('caption', '')
        
        # دریافت فایل‌ها
        image_file = request.files.get('image')
        video_file = request.files.get('video')
        document_file = request.files.get('document')
        
        if not title or not platforms or not scopes or not scheduled_time:
            return jsonify({"error": "Missing required fields"}), 400
        
        # ذخیره در دیتابیس
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # آماده کردن محتوا
            content_type = 'text'
            content_data = message or caption
            
            if image_file:
                content_type = 'photo'
                # ذخیره فایل
                filename = f"scheduled_{uuid.uuid4()}_{image_file.filename}"
                filepath = os.path.join('uploads', filename)
                os.makedirs('uploads', exist_ok=True)
                image_file.save(filepath)
                content_data = filepath
            elif video_file:
                content_type = 'video'
                filename = f"scheduled_{uuid.uuid4()}_{video_file.filename}"
                filepath = os.path.join('uploads', filename)
                os.makedirs('uploads', exist_ok=True)
                video_file.save(filepath)
                content_data = filepath
            elif document_file:
                content_type = 'document'
                filename = f"scheduled_{uuid.uuid4()}_{document_file.filename}"
                filepath = os.path.join('uploads', filename)
                os.makedirs('uploads', exist_ok=True)
                document_file.save(filepath)
                content_data = filepath
            
            # ذخیره در جدول scheduled_broadcasts (با schema جدید)
            # تعیین platform اصلی (اولین پلتفرم)
            primary_platform = platforms[0] if platforms else 'telegram'
            
            cursor.execute('''
                INSERT INTO scheduled_broadcasts 
                (title, message, platforms, platform, scopes, scheduled_time, solar_date, 
                 send_to_tagged, tag_filter, content_type, content_data, content_text, pin_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                title,
                message or caption,  # message
                json.dumps(platforms),  # platforms
                primary_platform,  # platform (ستون اصلی)
                json.dumps(scopes),  # scopes
                scheduled_time,  # scheduled_time
                solar_date,  # solar_date
                send_to_tagged,  # send_to_tagged
                tag_filter,  # tag_filter
                content_type,  # content_type
                content_data,  # content_data
                message or caption,  # content_text (متن اصلی)
                pin_message  # pin_message
            ))
            
            scheduled_id = cursor.lastrowid
            
            # زمان‌بندی با APScheduler
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.date import DateTrigger
            
            def send_scheduled_broadcast():
                try:
                    # اجرای ارسال از دیتابیس
                    from flask import current_app
                    asyncio.run(execute_scheduled_broadcast_from_db(scheduled_id, current_app))
                except Exception as e:
                    logger.error(f"Error executing scheduled broadcast {scheduled_id}: {e}")
            
            # اضافه کردن job به scheduler موجود
            if scheduler:
                # اگر scheduled_time string است، آن را به datetime تبدیل کن
                if isinstance(scheduled_time, str):
                    scheduled_time = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
                
                # اطمینان از timezone
                if scheduled_time.tzinfo is None:
                    scheduled_time = scheduled_time.replace(tzinfo=None)
                
                trigger = DateTrigger(run_date=scheduled_time)
                job_id = f"scheduled_{scheduled_id}"
                
                scheduler.add_job(
                    send_scheduled_broadcast,
                    trigger=trigger,
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Added scheduled job {job_id} for {scheduled_time}")
            else:
                logger.warning("Scheduler not available for scheduled broadcast")
            
            # job_id در schema موجود وجود ندارد، بنابراین حذف شد
            # cursor.execute('UPDATE scheduled_broadcasts SET job_id = ? WHERE id = ?', (job_id, scheduled_id))
            # conn.commit()
            
            logger.info(f"Scheduled broadcast {scheduled_id} for {scheduled_time}")
            
            return jsonify({
                "success": True,
                "message": "Broadcast scheduled successfully",
                "scheduled_id": scheduled_id,
                "scheduled_time": scheduled_time,
                "platforms": platforms
            })
            
    except Exception as e:
        logger.error(f"Error scheduling broadcast: {e}")
        return jsonify({"error": str(e)}), 500

async def execute_scheduled_broadcast(scheduled_id):
    """اجرای ارسال زماندار"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # دریافت اطلاعات ارسال زماندار
            cursor.execute('''
                SELECT * FROM scheduled_broadcasts WHERE id = ?
            ''', (scheduled_id,))
            
            scheduled = cursor.fetchone()
            if not scheduled:
                logger.error(f"Scheduled broadcast {scheduled_id} not found")
                return
            
            # به‌روزرسانی وضعیت به در حال اجرا
            cursor.execute('''
                UPDATE scheduled_broadcasts SET status = 'running' WHERE id = ?
            ''', (scheduled_id,))
            conn.commit()
            
            # استخراج اطلاعات از schema جدید
            platforms = json.loads(scheduled['platforms']) if scheduled['platforms'] else []
            scopes = json.loads(scheduled['scopes']) if scheduled['scopes'] else []
            content_text = scheduled['message'] or ''
            content_type = scheduled['content_type'] or 'text'
            content_data = scheduled['content_data'] or ''
            send_to_tagged = scheduled.get('send_to_tagged', False)
            tag_filter = scheduled.get('tag_filter', '')
            pin_message = scheduled.get('pin_message', False)
            
            # اجرای ارسال برای هر پلتفرم
            for platform in platforms:
                try:
                    # اگر فیلتر تگ فعال است، چت‌های تگ‌دار را پیدا کن
                    if send_to_tagged and tag_filter:
                        # پشتیبانی از چندین تگ (جدا شده با کاما)
                        tag_list = [tag.strip() for tag in tag_filter.split(',') if tag.strip()]
                        logger.info(f"📌 Scheduled broadcast using tag filters: {tag_list}")
                        
                        # ساخت query برای جستجوی چندین تگ
                        if len(tag_list) == 1:
                            # یک تگ
                            tagged_chats = db_fetchall("""
                                SELECT chat_id, platform FROM chats WHERE tags LIKE ? AND platform = ?
                            """, (f"%{tag_list[0]}%", platform))
                        else:
                            # چندین تگ - استفاده از OR
                            placeholders = ' OR '.join(['tags LIKE ?' for _ in tag_list])
                            params = [f"%{tag}%" for tag in tag_list] + [platform]
                            tagged_chats = db_fetchall(f"""
                                SELECT chat_id, platform FROM chats WHERE ({placeholders}) AND platform = ?
                            """, params)
                        
                        if not tagged_chats:
                            logger.warning(f"No chats found with tags: {tag_list} in platform: {platform}. Skipping this platform.")
                            continue
                        
                        # تبدیل به ساختار مناسب
                        target_chats = {}
                        for chat in tagged_chats:
                            platform_chat = chat["platform"]
                            target_chats.setdefault(platform_chat, []).append(chat["chat_id"])
                        
                        # ارسال با target_chats
                        if content_type == 'text':
                            await send_broadcast_message_with_targets(
                                platform=platform,
                                scopes=scopes,
                                message=content_text,
                                pin_message=pin_message,
                                target_chats=target_chats
                            )
                        elif content_type == 'photo':
                            await send_broadcast_photo_with_targets(
                                platform=platform,
                                scopes=scopes,
                                photo_path=content_data,
                                caption=content_text,
                                pin_message=pin_message,
                                target_chats=target_chats
                            )
                        elif content_type == 'video':
                            await send_broadcast_video_with_targets(
                                platform=platform,
                                scopes=scopes,
                                video_path=content_data,
                                caption=content_text,
                                pin_message=pin_message,
                                target_chats=target_chats
                            )
                        elif content_type == 'document':
                            await send_broadcast_document_with_targets(
                                platform=platform,
                                scopes=scopes,
                                document_path=content_data,
                                caption=content_text,
                                pin_message=pin_message,
                                target_chats=target_chats
                            )
                    else:
                        # ارسال عادی بدون فیلتر تگ
                        if content_type == 'text':
                            await send_broadcast_message(
                                platform=platform,
                                scopes=scopes,
                                message=content_text,
                                pin_message=pin_message
                            )
                        elif content_type == 'photo':
                            await send_broadcast_photo(
                                platform=platform,
                                scopes=scopes,
                                photo_path=content_data,
                                caption=content_text,
                                pin_message=pin_message
                            )
                        elif content_type == 'video':
                            await send_broadcast_video(
                                platform=platform,
                                scopes=scopes,
                                video_path=content_data,
                                caption=content_text,
                                pin_message=pin_message
                            )
                        elif content_type == 'document':
                            await send_broadcast_document(
                                platform=platform,
                                scopes=scopes,
                                document_path=content_data,
                                caption=content_text,
                                pin_message=pin_message
                            )
                    
                    logger.info(f"Scheduled broadcast {scheduled_id} sent to {platform}")
                    
                except Exception as e:
                    logger.error(f"Error sending scheduled broadcast {scheduled_id} to {platform}: {e}")
            
            # به‌روزرسانی وضعیت به تکمیل شده
            cursor.execute('''
                UPDATE scheduled_broadcasts 
                SET status = 'completed', last_sent = CURRENT_TIMESTAMP, total_sent = total_sent + 1
                WHERE id = ?
            ''', (scheduled_id,))
            conn.commit()
            
            logger.info(f"Scheduled broadcast {scheduled_id} completed successfully")
            
    except Exception as e:
        logger.error(f"Error executing scheduled broadcast {scheduled_id}: {e}")
        
        # به‌روزرسانی وضعیت به خطا
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE scheduled_broadcasts SET status = 'failed' WHERE id = ?
                ''', (scheduled_id,))
                conn.commit()
        except:
            pass

@app.route('/api/scheduled_broadcasts', methods=['GET'])
def api_get_scheduled_broadcasts():
    """دریافت لیست ارسال‌های زماندار"""
    try:
        status = request.args.get('status', 'all')
        logger.info(f"Getting scheduled broadcasts with status: {status}")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وجود جدول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_broadcasts'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                logger.warning("Table scheduled_broadcasts does not exist, creating it...")
                # ایجاد جدول
                cursor.execute('''CREATE TABLE scheduled_broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    platforms TEXT,
                    scopes TEXT,
                    scheduled_time TIMESTAMP NOT NULL,
                    solar_date TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    tags TEXT,
                    content_text TEXT,
                    content_type TEXT DEFAULT 'text',
                    content_data TEXT
                )''')
                conn.commit()
                logger.info("Table scheduled_broadcasts created successfully")
                return jsonify([])
            
            # بررسی ساختار جدول
            cursor.execute("PRAGMA table_info(scheduled_broadcasts)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            logger.info(f"Scheduled broadcasts table columns: {column_names}")
            
            if status == 'all':
                cursor.execute('''
                    SELECT * FROM scheduled_broadcasts 
                    ORDER BY scheduled_time DESC
                ''')
            else:
                cursor.execute('''
                    SELECT * FROM scheduled_broadcasts 
                    WHERE status = ?
                    ORDER BY scheduled_time DESC
                ''', (status,))
            
            broadcasts = cursor.fetchall()
            logger.info(f"Found {len(broadcasts)} scheduled broadcasts")
            
            # تبدیل به لیست دیکشنری (با schema موجود)
            result = []
            for broadcast in broadcasts:
                try:
                    # تبدیل broadcast به دیکشنری
                    broadcast_dict = dict(broadcast)
                    
                    # بررسی وجود ستون‌ها
                    title = str(broadcast_dict.get('title', '')) if 'title' in column_names else ''
                    solar_date = str(broadcast_dict.get('solar_date', '')) if 'solar_date' in column_names else ''
                    tags = str(broadcast_dict.get('tags', '')) if 'tags' in column_names else ''
                    content_text = str(broadcast_dict.get('content_text', '')) if 'content_text' in column_names else ''
                    content_type = str(broadcast_dict.get('content_type', 'text')) if 'content_type' in column_names else 'text'
                    content_data = str(broadcast_dict.get('content_data', '')) if 'content_data' in column_names else ''
                    
                    # مدیریت platforms و scopes
                    platforms = []
                    scopes = []
                    
                    if 'platforms' in column_names and broadcast_dict.get('platforms'):
                        try:
                            platforms = json.loads(broadcast_dict['platforms'])
                        except Exception as e:
                            logger.warning(f"Error parsing platforms JSON: {e}")
                            platforms = []
                    
                    if 'scopes' in column_names and broadcast_dict.get('scopes'):
                        try:
                            scopes = json.loads(broadcast_dict['scopes'])
                        except Exception as e:
                            logger.warning(f"Error parsing scopes JSON: {e}")
                            scopes = []
                    
                    result.append({
                        'id': int(broadcast_dict['id']),
                        'title': title,
                        'platforms': platforms,
                        'scopes': scopes,
                        'scheduled_time': str(broadcast_dict['scheduled_time']),
                        'solar_date': solar_date,
                        'status': str(broadcast_dict['status']),
                        'tags': tags,
                        'created_at': str(broadcast_dict['created_at']),
                        'content_text': content_text,
                        'content_type': content_type,
                        'content_data': content_data
                    })
                except Exception as e:
                    logger.error(f"Error processing broadcast: {e}")
                    continue
            
            logger.info(f"Returning {len(result)} scheduled broadcasts")
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"Error getting scheduled broadcasts: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug_scheduled_broadcasts', methods=['GET'])
def api_debug_scheduled_broadcasts():
    """بررسی ساختار جدول scheduled_broadcasts و محتویات آن"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وجود جدول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_broadcasts'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                return jsonify({
                    "table_exists": False,
                    "message": "Table scheduled_broadcasts does not exist"
                })
            
            # بررسی ساختار جدول
            cursor.execute("PRAGMA table_info(scheduled_broadcasts)")
            columns = cursor.fetchall()
            
            # بررسی تعداد رکوردها
            cursor.execute("SELECT COUNT(*) FROM scheduled_broadcasts")
            total_count = cursor.fetchone()[0]
            
            # بررسی رکوردهای موجود
            cursor.execute("SELECT * FROM scheduled_broadcasts LIMIT 5")
            sample_records = cursor.fetchall()
            
            # بررسی وضعیت‌های مختلف
            cursor.execute("SELECT status, COUNT(*) FROM scheduled_broadcasts GROUP BY status")
            status_counts = cursor.fetchall()
            
            # تبدیل sample_records به لیست قابل JSON serialization
            sample_records_list = []
            for record in sample_records:
                try:
                    sample_records_list.append({key: record[key] for key in record.keys()})
                except Exception as e:
                    logger.warning(f"Error converting record: {e}")
                    continue
            
            # تبدیل status_counts به دیکشنری قابل JSON serialization
            status_counts_dict = {}
            for row in status_counts:
                try:
                    status_counts_dict[str(row[0])] = int(row[1])
                except Exception as e:
                    logger.warning(f"Error converting status count: {e}")
                    continue
            
            # تبدیل columns به لیست قابل JSON serialization
            columns_list = []
            for col in columns:
                try:
                    columns_list.append({"name": str(col[1]), "type": str(col[2])})
                except Exception as e:
                    logger.warning(f"Error converting column: {e}")
                    continue
            
            return jsonify({
                "table_exists": True,
                "table_structure": columns_list,
                "total_records": int(total_count),
                "sample_records": sample_records_list,
                "status_counts": status_counts_dict,
                "message": "Debug information for scheduled_broadcasts table"
            })
            
    except Exception as e:
        logger.error(f"Error in debug_scheduled_broadcasts: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/create_scheduled_broadcasts_table', methods=['POST'])
def api_create_scheduled_broadcasts_table():
    """ایجاد جدول scheduled_broadcasts اگر وجود نداشته باشد"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # بررسی وجود جدول
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_broadcasts'")
            table_exists = cursor.fetchone()
            
            if table_exists:
                return jsonify({
                    "success": True,
                    "message": "Table scheduled_broadcasts already exists"
                })
            
            # ایجاد جدول
            cursor.execute('''CREATE TABLE scheduled_broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                platforms TEXT,
                scopes TEXT,
                scheduled_time TIMESTAMP NOT NULL,
                solar_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                tags TEXT,
                content_text TEXT,
                content_type TEXT DEFAULT 'text',
                content_data TEXT
            )''')
            
            conn.commit()
            
            return jsonify({
                "success": True,
                "message": "Table scheduled_broadcasts created successfully"
            })
            
    except Exception as e:
        logger.error(f"Error creating scheduled_broadcasts table: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scheduled_broadcasts/<int:broadcast_id>', methods=['DELETE'])
def api_delete_scheduled_broadcast(broadcast_id):
    """حذف ارسال زماندار"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # دریافت اطلاعات ارسال
            cursor.execute('SELECT * FROM scheduled_broadcasts WHERE id = ?', (broadcast_id,))
            broadcast = cursor.fetchone()
            
            if not broadcast:
                return jsonify({"error": "Scheduled broadcast not found"}), 404
            
            # حذف از scheduler (استفاده از scheduler موجود)
            try:
                if scheduler:
                    scheduler.remove_job(f"scheduled_{broadcast_id}")
            except Exception as e:
                logger.warning(f"Failed to remove scheduled job scheduled_{broadcast_id}: {e}")
            
            # حذف از دیتابیس
            cursor.execute('DELETE FROM scheduled_broadcasts WHERE id = ?', (broadcast_id,))
            conn.commit()
            
            return jsonify({"success": True, "message": "Scheduled broadcast deleted"})
            
    except Exception as e:
        logger.error(f"Error deleting scheduled broadcast: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scheduler/schedule', methods=['POST'])
def api_schedule_broadcast_old():
    """زمان‌بندی یک ارسال (قدیمی)"""
    try:
        data = request.get_json()
        scheduled_time = data.get('scheduled_time')
        platform = data.get('platform')
        scopes = data.get('scopes', [])
        content_text = data.get('content_text')
        content_type = data.get('content_type')
        content_data = data.get('content_data')
        is_recurring = data.get('is_recurring', False)
        recurring_pattern = data.get('recurring_pattern')
        
        if not scheduled_time or not platform or not scopes:
            return jsonify({"error": "scheduled_time, platform, and scopes are required"}), 400
        
        # اجرای async در thread
        def schedule_sync():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(schedule_broadcast(
                    scheduled_time, platform, scopes, content_text, 
                    content_type, content_data, is_recurring, recurring_pattern
                ))
            finally:
                loop.close()
        
        broadcast_id = schedule_sync()
        return jsonify({"success": True, "broadcast_id": broadcast_id})
    except Exception as e:
        logger.error(f"Error in api_schedule_broadcast: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scheduler/list', methods=['GET'])
def api_get_scheduler_list():
    """دریافت لیست ارسال‌های زمان‌بندی شده"""
    try:
        status = request.args.get('status')
        broadcasts = get_scheduled_broadcasts(status)
        return jsonify([dict(broadcast) for broadcast in broadcasts])
    except Exception as e:
        logger.error(f"Error in api_get_scheduled_broadcasts: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scheduler/cancel/<int:broadcast_id>', methods=['POST'])
def api_cancel_scheduled_broadcast(broadcast_id):
    """لغو ارسال زمان‌بندی شده"""
    try:
        cancel_scheduled_broadcast(broadcast_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in api_cancel_scheduled_broadcast: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scheduler/delete_multiple', methods=['POST'])
def api_delete_multiple_scheduled():
    """حذف چندگانه ارسال‌های زمان‌بندی شده"""
    try:
        data = request.get_json()
        broadcast_ids = data.get('broadcast_ids', [])
        
        if not broadcast_ids:
            return jsonify({"error": "هیچ ارسالی انتخاب نشده"}), 400
        
        deleted_count = 0
        for broadcast_id in broadcast_ids:
            try:
                # حذف از scheduler
                if scheduler:
                    try:
                        scheduler.remove_job(f"once_{broadcast_id}")
                    except:
                        pass
                    try:
                        scheduler.remove_job(f"recurring_{broadcast_id}")
                    except:
                        pass
                
                # حذف از دیتابیس
                db_execute("DELETE FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
                deleted_count += 1
                logger.info(f"Scheduled broadcast {broadcast_id} deleted")
            except Exception as e:
                logger.error(f"Error deleting broadcast {broadcast_id}: {e}")
                continue
        
        return jsonify({
            "success": True,
            "deleted_count": deleted_count,
            "total_requested": len(broadcast_ids)
        })
    except Exception as e:
        logger.error(f"Error in api_delete_multiple_scheduled: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/force-sync', methods=['POST'])
def api_force_sync():
    """اجبار سینک مجدد تمام چت‌ها از API"""
    try:
        data = request.get_json()
        platform = data.get('platform', 'all')  # 'telegram', 'bale', or 'all'
        
        def force_sync_sync():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if platform == 'all':
                    # سینک هر سه پلتفرم
                    loop.run_until_complete(discover_all_chats_from_api('telegram'))
                    loop.run_until_complete(discover_all_chats_from_api('bale'))
                    loop.run_until_complete(discover_all_chats_from_api('ita'))
                    return {"telegram": "synced", "bale": "synced", "ita": "synced"}
                else:
                    # سینک پلتفرم مشخص
                    loop.run_until_complete(discover_all_chats_from_api(platform))
                    return {platform: "synced"}
            finally:
                loop.close()
        
        result = force_sync_sync()
        logger.info(f"[Flask API] Force sync completed: {result}")
        return jsonify({"success": True, "result": result})
        
    except Exception as e:
        logger.error(f"Error in api_force_sync: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sync-chat', methods=['POST'])
def api_sync_chat():
    """سینک یک چت خاص از طریق API"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        chat_type = data.get('chat_type', 'group')
        name = data.get('name', '')
        username = data.get('username', '')
        
        if not chat_id or not platform:
            return jsonify({"error": "chat_id and platform are required"}), 400
        
        # ثبت چت
        register_chat(str(chat_id), chat_type, platform, name, username)
        
        logger.info(f"[Flask API] Manually synced chat {chat_id} for {platform}")
        return jsonify({"success": True, "message": f"Chat {chat_id} synced successfully for {platform}"})
        
    except Exception as e:
        logger.error(f"Error in api_sync_chat: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/restore-backup', methods=['POST'])
def api_restore_backup():
    """بازیابی چت‌ها از فایل backup"""
    try:
        restored_count = restore_chats_from_backup()
        return jsonify({"success": True, "restored_count": restored_count, "message": f"Restored {restored_count} chats from backup"})
        
    except Exception as e:
        logger.error(f"Error in api_restore_backup: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-chat-tags', methods=['POST'])
def api_update_chat_tags():
    """به‌روزرسانی تگ‌های یک چت"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        tags = data.get('tags', '')
        
        if not chat_id or not platform:
            return jsonify({"error": "chat_id and platform are required"}), 400
        
        success = update_chat_tags(chat_id, platform, tags)
        if success:
            return jsonify({"success": True, "message": f"Tags updated for chat {chat_id}"})
        else:
            return jsonify({"error": "Failed to update tags"}), 500
            
    except Exception as e:
        logger.error(f"Error in api_update_chat_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-chat-tags/<platform>/<chat_id>', methods=['GET'])
def api_get_chat_tags(platform: str, chat_id: str):
    """دریافت تگ‌های یک چت"""
    try:
        tags = get_chat_tags(chat_id, platform)
        return jsonify({"success": True, "tags": tags})
    except Exception as e:
        logger.error(f"Error in api_get_chat_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-all-tags', methods=['GET'])
def api_get_all_tags():
    """دریافت تمام تگ‌های موجود"""
    try:
        tags = get_all_tags()
        return jsonify({"success": True, "tags": tags})
    except Exception as e:
        logger.error(f"Error in api_get_all_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-chats-by-tags', methods=['POST'])
def api_get_chats_by_tags():
    """دریافت چت‌ها بر اساس تگ‌ها"""
    try:
        data = request.get_json()
        tags = data.get('tags', [])
        
        if not tags:
            return jsonify({"error": "tags are required"}), 400
        
        chats = get_chats_by_tags(tags)
        return jsonify({"success": True, "chats": chats})
    except Exception as e:
        logger.error(f"Error in api_get_chats_by_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/get-user-tag-status', methods=['GET'])
def api_get_user_tag_status():
    """دریافت وضعیت تگ‌گذاری کاربران"""
    try:
        platform = request.args.get('platform', 'all')
        
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            if platform == 'all':
                cur.execute("""
                    SELECT chat_id, platform, tags, created_at, name, username
                    FROM chats 
                    WHERE chat_type = 'private' AND tags IS NOT NULL AND tags != ''
                    ORDER BY created_at DESC
                """)
            else:
                cur.execute("""
                    SELECT chat_id, platform, tags, created_at, name, username
                    FROM chats 
                    WHERE chat_type = 'private' AND platform = ? AND tags IS NOT NULL AND tags != ''
                    ORDER BY created_at DESC
                """, (platform,))
            
            rows = cur.fetchall()
            
            users = []
            for row in rows:
                users.append({
                    'user_id': row[0],
                    'platform': row[1],
                    'has_selected_tags': bool(row[2] and row[2].strip()),
                    'selected_tags': row[2] or '',
                    'created_at': row[3],
                    'name': row[4] or 'نامشخص',
                    'username': row[5] or ''
                })
            
            return jsonify({
                'success': True,
                'users': users
            })
    except Exception as e:
        logger.error(f"Error getting user tag status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update-user-tags', methods=['POST'])
def api_update_user_tags():
    """به‌روزرسانی تگ‌های کاربر"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        platform = data.get('platform')
        tags = data.get('tags', '')
        
        if not user_id or not platform:
            return jsonify({
                'success': False,
                'error': 'user_id and platform are required'
            }), 400
        
        # به‌روزرسانی تگ‌ها در جدول chats (که قبلاً در update_user_tag_status انجام می‌شود)
        update_user_tag_status(str(user_id), platform, tags)
        
        return jsonify({
            'success': True,
            'message': 'تگ‌های کاربر با موفقیت به‌روزرسانی شد'
        })
    except Exception as e:
        logger.error(f"Error updating user tags: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cleanup-user-tag-status', methods=['POST'])
def api_cleanup_user_tag_status():
    """حذف جدول user_tag_status پس از انتقال داده‌ها"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # بررسی وجود جدول
            cur.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='user_tag_status'
            """)
            
            if cur.fetchone():
                # حذف جدول
                cur.execute("DROP TABLE user_tag_status")
                conn.commit()
                logger.info("✅ جدول user_tag_status حذف شد")
                
                return jsonify({
                    'success': True,
                    'message': 'جدول user_tag_status با موفقیت حذف شد'
                })
            else:
                return jsonify({
                    'success': True,
                    'message': 'جدول user_tag_status از قبل وجود نداشت'
                })
                
    except Exception as e:
        logger.error(f"Error cleaning up user_tag_status table: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export-tags', methods=['GET'])
def api_export_tags():
    """صادرات تگ‌ها به فایل JSON"""
    try:
        # دریافت تمام چت‌ها با تگ‌هایشان
        chats = db_fetchall("SELECT chat_id, platform, name, username, tags FROM chats WHERE tags IS NOT NULL AND tags != ''")
        
        # ساخت فایل JSON
        export_data = {
            "export_date": datetime.now().isoformat(),
            "chats": []
        }
        
        for chat in chats:
            export_data["chats"].append({
                "chat_id": chat['chat_id'],
                "platform": chat['platform'],
                "name": chat['name'],
                "username": chat['username'],
                "tags": chat['tags']
            })
        
        # ذخیره فایل
        export_file = "tags_export.json"
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return send_file(export_file, as_attachment=True, download_name=f"tags_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
    except Exception as e:
        logger.error(f"Error in api_export_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/import-tags', methods=['POST'])
def api_import_tags():
    """واردات تگ‌ها از فایل JSON"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({"error": "File must be a JSON file"}), 400
        
        # خواندن فایل
        import_data = json.load(file)
        
        if 'chats' not in import_data:
            return jsonify({"error": "Invalid file format"}), 400
        
        updated_count = 0
        for chat_data in import_data['chats']:
            chat_id = chat_data.get('chat_id')
            platform = chat_data.get('platform')
            tags = chat_data.get('tags', '')
            
            if chat_id and platform:
                success = update_chat_tags(chat_id, platform, tags)
                if success:
                    updated_count += 1
        
        return jsonify({"success": True, "updated_count": updated_count, "message": f"Updated tags for {updated_count} chats"})
        
    except Exception as e:
        logger.error(f"Error in api_import_tags: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/growth-stats/<platform>', methods=['GET'])
def api_growth_stats(platform: str):
    """دریافت آمار رشد برای یک پلتفرم"""
    try:
        days = request.args.get('days', 7, type=int)
        growth_stats = calculate_growth_stats(platform, days)
        return jsonify({"success": True, "growth_stats": growth_stats})
    except Exception as e:
        logger.error(f"Error in api_growth_stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/growth-report/<platform>', methods=['GET'])
def api_growth_report(platform: str):
    """تولید و دانلود گزارش رشد برای یک پلتفرم"""
    try:
        filepath = generate_growth_report(platform)
        if filepath and os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=f"growth_report_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        else:
            return jsonify({"error": "Failed to generate growth report"}), 500
    except Exception as e:
        logger.error(f"Error in api_growth_report: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/overall-growth-stats', methods=['GET'])
def api_overall_growth_stats():
    """دریافت آمار رشد کلی تمام پلتفرم‌ها"""
    try:
        days = request.args.get('days', 7, type=int)
        
        # دریافت آمار رشد برای هر پلتفرم
        telegram_growth = calculate_growth_stats('telegram', days)
        bale_growth = calculate_growth_stats('bale', days)
        ita_growth = calculate_growth_stats('ita', days)
        
        # محاسبه مجموع کل
        total_stats = {
            'telegram': telegram_growth.get('total', {}),
            'bale': bale_growth.get('total', {}),
            'ita': ita_growth.get('total', {}),
            'overall': {
                'current_members': (telegram_growth.get('total', {}).get('current_members', 0) or 0) + 
                                 (bale_growth.get('total', {}).get('current_members', 0) or 0) + 
                                 (ita_growth.get('total', {}).get('current_members', 0) or 0),
                'past_members': (telegram_growth.get('total', {}).get('past_members', 0) or 0) + 
                               (bale_growth.get('total', {}).get('past_members', 0) or 0) + 
                               (ita_growth.get('total', {}).get('past_members', 0) or 0),
                'current_chats': (telegram_growth.get('total', {}).get('current_chats', 0) or 0) + 
                                (bale_growth.get('total', {}).get('current_chats', 0) or 0) + 
                                (ita_growth.get('total', {}).get('current_chats', 0) or 0),
                'past_chats': (telegram_growth.get('total', {}).get('past_chats', 0) or 0) + 
                             (bale_growth.get('total', {}).get('past_chats', 0) or 0) + 
                             (ita_growth.get('total', {}).get('past_chats', 0) or 0)
            }
        }
        
        # محاسبه رشد کلی
        overall = total_stats['overall']
        overall['member_growth'] = overall['current_members'] - overall['past_members']
        overall['member_growth_pct'] = round((overall['member_growth'] / overall['past_members'] * 100) if overall['past_members'] > 0 else 0, 2)
        overall['chat_growth'] = overall['current_chats'] - overall['past_chats']
        overall['chat_growth_pct'] = round((overall['chat_growth'] / overall['past_chats'] * 100) if overall['past_chats'] > 0 else 0, 2)
        
        return jsonify({"success": True, "growth_stats": total_stats})
    except Exception as e:
        logger.error(f"Error in api_overall_growth_stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/test_logs', methods=['GET'])
def api_test_logs():
    """تست لاگ‌ها"""
    print("=== TEST LOGS ===")
    logger.info("=== TEST LOGS ===")
    logger.debug("DEBUG log test")
    logger.warning("WARNING log test")
    logger.error("ERROR log test")
    return jsonify({"message": "Logs tested"})

@app.route('/api/test_ita_member_count/<string:chat_id>', methods=['GET'])
def api_test_ita_member_count(chat_id: str):
    """
    تست دریافت تعداد اعضای چت از ایتا
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(test_ita_member_count(chat_id))
        loop.close()
        
        return jsonify({
            'success': True,
            'chat_id': chat_id,
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/force_update_ita_member_count/<string:chat_id>', methods=['POST'])
def api_force_update_ita_member_count(chat_id: str):
    """
    به‌روزرسانی اجباری تعداد اعضای یک چت ایتا
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(force_update_ita_member_count(chat_id))
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error force updating ITA member count: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update_all_ita_member_counts', methods=['POST'])
def api_update_all_ita_member_counts():
    """
    به‌روزرسانی تعداد اعضای تمام چت‌های ایتا
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(check_and_update_ita_member_counts())
        loop.close()
        
        return jsonify({
            'success': True,
            'message': 'All ITA member counts updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating all ITA member counts: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

async def check_and_update_ita_member_counts(is_daily_update: bool = False):
    """
    بررسی و به‌روزرسانی تعداد اعضای چت‌های ایتا
    این تابع به صورت دوره‌ای اجرا می‌شود
    
    Args:
        is_daily_update: اگر True باشد، این به‌روزرسانی روزانه است (ساعت 1 صبح)
    """
    try:
        logger.info("[ITA] 🔄 Starting periodic member count check...")
        
        # دریافت تمام چت‌های ایتا
        ita_chats = db_fetchall("SELECT chat_id, chat_type, name, username FROM chats WHERE platform = 'ita' AND is_active = 1")
        
        updated_count = 0
        total_count = len(ita_chats)
        
        for chat in ita_chats:
            chat_id = chat['chat_id']
            chat_type = chat['chat_type']
            chat_name = chat['name'] if chat['name'] else ''
            chat_username = chat['username'] if chat['username'] else ''
            
            try:
                logger.info(f"[ITA] 🔍 Checking chat: {chat_id} ({chat_name})")
                
                # دریافت تعداد اعضای فعلی از دیتابیس
                current_metrics = db_fetchone("""
                    SELECT members_count FROM chats_metrics 
                    WHERE chat_id = ? AND platform = 'ita' 
                    ORDER BY date_key DESC LIMIT 1
                """, (chat_id,))
                
                current_count = current_metrics['members_count'] if current_metrics else 0
                
                # تلاش برای دریافت تعداد جدید
                new_count = await get_ita_chat_member_count(chat_id)
                
                # مقایسه و به‌روزرسانی در صورت تغییر
                if new_count != current_count or is_daily_update:
                    date_key = time.strftime('%Y-%m-%d')
                    
                    # اگر به‌روزرسانی روزانه است، همیشه ذخیره کن
                    if is_daily_update:
                        db_execute("""
                            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count, is_daily_snapshot)
                            VALUES (?, 'ita', ?, ?, 1)
                        """, (chat_id, date_key, new_count))
                        logger.info(f"[ITA] 📅 Daily snapshot saved for {chat_id}: {new_count} members")
                    else:
                        # به‌روزرسانی دوره‌ای - فقط در صورت تغییر
                        db_execute("""
                            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count, is_daily_snapshot)
                            VALUES (?, 'ita', ?, ?, 0)
                        """, (chat_id, date_key, new_count))
                        logger.info(f"[ITA] ✅ Updated {chat_id}: {current_count} → {new_count} members")
                    
                    updated_count += 1
                else:
                    logger.debug(f"[ITA] ⏸️ No change for {chat_id}: {current_count} members")
                
                # کمی صبر بین درخواست‌ها
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"[ITA] ❌ Error checking chat {chat_id}: {e}")
        
        logger.info(f"[ITA] ✅ Periodic check completed: {updated_count}/{total_count} chats updated")
        
    except Exception as e:
        logger.error(f"[ITA] ❌ Error in periodic member count check: {e}")

async def force_update_ita_member_count(chat_id: str) -> dict:
    """
    به‌روزرسانی اجباری تعداد اعضای یک چت ایتا
    """
    try:
        logger.info(f"[ITA] 🔄 Force updating member count for {chat_id}")
        
        # دریافت تعداد فعلی
        current_metrics = db_fetchone("""
            SELECT members_count FROM chats_metrics 
            WHERE chat_id = ? AND platform = 'ita' 
            ORDER BY date_key DESC LIMIT 1
        """, (chat_id,))
        
        current_count = current_metrics['members_count'] if current_metrics else 0
        
        # دریافت تعداد جدید
        new_count = await get_ita_chat_member_count(chat_id)
        
        # به‌روزرسانی در دیتابیس
        date_key = time.strftime('%Y-%m-%d')
        db_execute("""
            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
            VALUES (?, 'ita', ?, ?)
        """, (chat_id, date_key, new_count))
        
        logger.info(f"[ITA] ✅ Force update completed: {chat_id} = {new_count} members")
        
        return {
            'success': True,
            'chat_id': chat_id,
            'old_count': current_count,
            'new_count': new_count,
            'updated': current_count != new_count
        }
        
    except Exception as e:
        logger.error(f"[ITA] ❌ Error in force update for {chat_id}: {e}")
        return {
            'success': False,
            'chat_id': chat_id,
            'error': str(e)
        }

@app.route('/api/update_ita_snapshots', methods=['POST'])
def api_update_ita_snapshots():
    """
    به‌روزرسانی snapshot های ایتا
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # دریافت تمام چت‌های ایتا
        ita_chats = db_fetchall("SELECT chat_id, chat_type FROM chats WHERE platform = 'ita'")
        
        for chat in ita_chats:
            chat_id = chat['chat_id']
            chat_type = chat['chat_type']
            
            # ایجاد snapshot برای هر چت
            loop.run_until_complete(create_chat_snapshot(chat_id, 'ita', chat_type))
        
        loop.close()
        
        return jsonify({
            'success': True,
            'message': f'Updated snapshots for {len(ita_chats)} Ita chats'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/check_ita_member_counts', methods=['POST'])
def api_check_ita_member_counts():
    """
    API endpoint برای بررسی دستی تعداد اعضای ایتا
    """
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(check_and_update_ita_member_counts())
        loop.close()
        
        return jsonify({
            'success': True,
            'message': 'Ita member count check completed'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/register_chat', methods=['POST'])
def api_register_chat():
    """
    API endpoint for registering a new chat.
    
    Request JSON format:
    {
        "chat_id": "123456789",      # Required - Chat ID (string)
        "chat_type": "channel",      # Required - Type: channel, group, private
        "platform": "telegram",      # Required - Platform: telegram, bale, ita
        "name": "Channel Name",      # Optional - Display name
        "username": "channel_user",  # Optional - Username
        "tags": "tag1,tag2"          # Optional - Comma-separated tags
    }
    
    Response:
    {
        "success": true/false,
        "message": "Status message",
        "chat_id": "123456789",
        "platform": "telegram"
    }
    """
    logger.info("===== CHAT REGISTRATION API CALL =====")
    return handle_chat_registration()

@app.route('/api/update_chat', methods=['POST'])
def api_update_chat():
    """
    API endpoint for updating an existing chat.
    Uses the same request/response format as register_chat.
    """
    logger.info("===== CHAT UPDATE API CALL =====")
    return handle_chat_registration(update=True)

def handle_chat_registration(update=False):
    """
    Handle chat registration or update.
    
    Args:
        update: Boolean indicating if this is an update operation
        
    Returns:
        JSON response with success/error details
    """
    request_id = str(uuid.uuid4())[:8]
    action = 'update' if update else 'registration'
    
    logger.info(f"[{request_id}] Starting chat {action} request")
    
    # Check content type
    if not request.is_json:
        error_msg = "Invalid content type. Expected application/json"
        logger.error(f"[{request_id}] {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg,
            'request_id': request_id
        }), 400
    
    # Get and log request data
    try:
        data = request.get_json()
        logger.info(f"[{request_id}] Received {action} data: {json.dumps(data, ensure_ascii=False)}")
    except Exception as e:
        error_msg = f"Invalid JSON data: {str(e)}"
        logger.error(f"[{request_id}] {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg,
            'request_id': request_id
        }), 400
    
    # Validate required fields
    required_fields = ['chat_id', 'chat_type', 'platform']
    for field in required_fields:
        if field not in data:
            error_msg = f"Missing required field: {field}"
            logger.error(f"[{request_id}] {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg,
                'request_id': request_id,
                'missing_field': field
            }), 400
    
    # Validate chat_type
    valid_chat_types = ['channel', 'group', 'private']
    chat_type = data['chat_type'].lower()
    if chat_type not in valid_chat_types:
        error_msg = f"Invalid chat_type: {chat_type}. Must be one of: {valid_chat_types}"
        logger.error(f"[{request_id}] {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg,
            'request_id': request_id,
            'valid_chat_types': valid_chat_types
        }), 400
    
    # Validate platform
    valid_platforms = ['telegram', 'bale', 'ita']
    platform = data['platform'].lower()
    if platform not in valid_platforms:
        error_msg = f"Invalid platform: {platform}. Must be one of: {valid_platforms}"
        logger.error(f"[{request_id}] {error_msg}")
        return jsonify({
            'success': False,
            'error': error_msg,
            'request_id': request_id,
            'valid_platforms': valid_platforms
        }), 400
    
    try:
        # Extract parameters with validation
        chat_id = str(data['chat_id']).strip()
        name = (data.get('name') or '').strip()
        username = (data.get('username') or '').lstrip('@').strip()
        tags = (data.get('tags') or '').strip()
        member_count = data.get('member_count', 0)
        
        logger.info(f"[{request_id}] Processing {action} for chat - ID: {chat_id}, Type: {chat_type}, Platform: {platform}")
        logger.info(f"[{request_id}] Additional info - Name: '{name}', Username: '{username}', Tags: '{tags}', Member Count: {member_count}")
        
        # Check for existing chat if this is an update
        existing_chat = None
        if update:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM chats WHERE chat_id = ? AND platform = ?",
                    (chat_id, platform)
                )
                existing_chat = cursor.fetchone()
                
                if not existing_chat:
                    error_msg = f"Chat not found for update - ID: {chat_id}, Platform: {platform}"
                    logger.error(f"[{request_id}] {error_msg}")
                    return jsonify({
                        'success': False,
                        'error': error_msg,
                        'request_id': request_id
                    }), 404
                
                logger.info(f"[{request_id}] Found existing chat for update: {dict(existing_chat)}")
        
        # Call the registration function
        logger.info(f"[{request_id}] Calling manual_register_chat function")
        success = manual_register_chat(
            chat_id=chat_id,
            chat_type=chat_type,
            platform=platform,
            name=name if name else None,
            username=username if username else None,
            tags=tags if tags else None,
            member_count=member_count
        )
        
        if success:
            result_msg = f"Successfully {action}ed chat: {chat_id} on {platform}"
            logger.info(f"[{request_id}] {result_msg}")
            
            # Get updated chat info
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM chats WHERE chat_id = ? AND platform = ?",
                    (chat_id, platform)
                )
                updated_chat = cursor.fetchone()
                
                if updated_chat:
                    logger.info(f"[{request_id}] Updated chat record: {dict(updated_chat)}")
                else:
                    logger.warning(f"[{request_id}] Could not fetch updated chat record")
            
            return jsonify({
                'success': True,
                'message': result_msg,
                'request_id': request_id,
                'chat_id': chat_id,
                'platform': platform,
                'action': action
            })
        else:
            error_msg = f"Failed to {action} chat: {chat_id} on {platform}"
            logger.error(f"[{request_id}] {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg,
                'request_id': request_id,
                'chat_id': chat_id,
                'platform': platform
            }), 500
            
    except Exception as e:
        error_msg = f"Error in chat {action}: {str(e)}"
        logger.error(f"[{request_id}] {error_msg}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}',
            'request_id': request_id,
            'chat_id': data.get('chat_id', 'unknown'),
            'platform': data.get('platform', 'unknown')
        }), 500

@app.route('/api/list_chats_v2', methods=['GET'])
def api_list_chats_v2():
    """
    API endpoint for listing registered chats with filters.
    This is an enhanced version with more filtering options.
    """
    try:
        # Get query parameters
        platform_filter = request.args.get('platform', 'all')
        type_filter = request.args.get('type', 'all')
        search_query = request.args.get('q', '').strip().lower()
        
        logger.info(f"Listing chats with filters - Platform: {platform_filter}, Type: {type_filter}, Search: {search_query}")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Build the query
            query = """
                SELECT 
                    chat_id, platform, chat_type, name, username, tags, 
                    created_at, last_active,
                    CASE 
                        WHEN chat_type = 'private' THEN 1
                        WHEN member_count IS NOT NULL AND member_count > 0 THEN member_count
                        ELSE 0
                    END as member_count
                FROM chats
                WHERE 1=1
            """
            
            params = []
            
            # Apply filters
            if platform_filter != 'all':
                query += " AND platform = ?"
                params.append(platform_filter)
                
            if type_filter != 'all':
                query += " AND chat_type = ?"
                params.append(type_filter)
                
            if search_query:
                query += " AND (chat_id LIKE ? OR name LIKE ? OR username LIKE ?)"
                search_term = f"%{search_query}%"
                params.extend([search_term, search_term, search_term])
            
            # Order by platform and name
            query += " ORDER BY created_at DESC, platform, LOWER(COALESCE(name, ''))"
            
            logger.debug(f"Executing query: {query} with params: {params}")
            cursor.execute(query, params)
            
            # Convert rows to list of dicts
            columns = [col[0] for col in cursor.description]
            chats = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.info(f"Found {len(chats)} matching chats")
            return jsonify(chats)
            
    except Exception as e:
        logger.error(f"Error listing chats: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Error listing chats: {str(e)}'
        }), 500

@app.route('/api/restore_chats', methods=['POST'])
def api_restore_chats():
    """
    API endpoint for restoring chats from backup database to main database.
    Use this only when main database is lost or corrupted.
    """
    logger.info("Restore chats API called - restoring from backup to main database")
    
    try:
        result = restore_chats_from_backup()
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Chats restored successfully from backup database'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to restore chats from backup database'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in restore chats API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/api/backup_chats', methods=['POST'])
def api_backup_chats():
    """
    API endpoint for updating backup database from main database.
    This creates/updates bot_database.db with current data from multi_bot_platform.db
    """
    logger.info("Backup chats API called - updating backup database from main database")
    
    try:
        result = backup_chats_to_backup_db()
        
        if result:
            return jsonify({
                'success': True,
                'message': 'Chats backed up successfully to backup database'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to backup chats to backup database'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in backup chats API: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/api/debug_chat_status/<platform>/<chat_id>', methods=['GET'])
def api_debug_chat_status(platform: str, chat_id: str):
    """
    Debug endpoint to check chat status in database
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check in main database
        cursor.execute(
            "SELECT * FROM chats WHERE chat_id = ? AND platform = ?",
            (chat_id, platform)
        )
        main_chat = cursor.fetchone()
        
        # Check in backup database
        backup_conn = sqlite3.connect('bot_database.db')
        backup_conn.row_factory = sqlite3.Row
        backup_cursor = backup_conn.cursor()
        
        backup_cursor.execute(
            "SELECT * FROM chats WHERE chat_id = ? AND platform = ?",
            (chat_id, platform)
        )
        backup_chat = backup_cursor.fetchone()
        
        conn.close()
        backup_conn.close()
        
        return jsonify({
            'success': True,
            'chat_id': chat_id,
            'platform': platform,
            'main_db_exists': main_chat is not None,
            'backup_db_exists': backup_chat is not None,
            'main_db_data': dict(main_chat) if main_chat else None,
            'backup_db_data': dict(backup_chat) if backup_chat else None
        })
        
    except Exception as e:
        logger.error(f"Error checking chat status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/delete_chat', methods=['POST'])
def api_delete_chat():
    """
    API endpoint for deleting a chat.
    """
    logger.info("Delete chat API called")
    
    # Check content type
    if not request.is_json:
        logger.error("Invalid content type. Expected application/json")
        return jsonify({
            'success': False,
            'error': 'Content-Type must be application/json'
        }), 400
    
    data = request.get_json()
    logger.info(f"Received delete request: {data}")
    
    # Validate required fields
    required_fields = ['chat_id', 'platform']
    for field in required_fields:
        if field not in data:
            logger.error(f"Missing required field: {field}")
            return jsonify({
                'success': False,
                'error': f'Missing required field: {field}'
            }), 400
    
    try:
        chat_id = str(data['chat_id']).strip()
        platform = data['platform']
        
        logger.info(f"Deleting chat - ID: {chat_id}, Platform: {platform}")
        
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # First, check if chat exists before deletion
            cursor.execute(
                "SELECT chat_id, platform, name FROM chats WHERE chat_id = ? AND platform = ?",
                (chat_id, platform)
            )
            existing_chat = cursor.fetchone()
            
            if not existing_chat:
                logger.warning(f"Chat not found for deletion: {chat_id} on {platform}")
                conn.close()
                return jsonify({
                    'success': False,
                    'error': 'Chat not found'
                })
            
            logger.info(f"Found chat to delete: {existing_chat['name']} (ID: {chat_id})")
            
            # Delete from chats table
            cursor.execute(
                "DELETE FROM chats WHERE chat_id = ? AND platform = ?",
                (chat_id, platform)
            )
            
            deleted_rows = cursor.rowcount
            logger.info(f"Deleted {deleted_rows} rows from chats table")
            
            # Also delete from chat_memberships to clean up (if table exists)
            try:
                cursor.execute(
                    "DELETE FROM chat_memberships WHERE chat_id = ? AND platform = ?",
                    (chat_id, platform)
                )
                logger.info(f"Cleaned up chat_memberships for chat {chat_id}")
            except Exception as e:
                logger.warning(f"Could not clean up chat_memberships (table may not exist): {e}")
                # Continue with deletion even if chat_members cleanup fails
            
            conn.commit()
            
            if deleted_rows > 0:
                logger.info(f"Successfully deleted chat: {chat_id} from {platform}")
                
                # Update backup database after deletion
                try:
                    backup_chats_to_backup_db()
                    logger.info(f"Backup updated after deleting chat {chat_id}")
                except Exception as e:
                    logger.warning(f"Backup update failed after deleting chat {chat_id}: {e}")
                
                conn.close()
                return jsonify({
                    'success': True,
                    'message': f'Chat {chat_id} deleted successfully from {platform}'
                })
            else:
                logger.warning(f"No rows were deleted for chat: {chat_id} on {platform}")
                conn.close()
                return jsonify({
                    'success': False,
                    'error': 'Failed to delete chat - no rows affected'
                })
                
        except Exception as e:
            logger.error(f"Error in database operations: {e}", exc_info=True)
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Database error: {str(e)}'
            }), 500

    except Exception as e:
        logger.error(f"Error deleting chat: {str(e)}", exc_info=True)
        try:
            if 'conn' in locals():
                conn.close()
        except:
            pass
        return jsonify({
            'success': False,
            'error': f'Error deleting chat: {str(e)}'
        }), 500

@app.route('/api/set_ita_member_count', methods=['POST'])
def api_set_ita_member_count():
    """
    تنظیم دستی تعداد اعضای چت ایتا
    """
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        member_count = data.get('member_count')
        
        if not chat_id or not member_count:
            return jsonify({
                'success': False,
                'error': 'chat_id and member_count are required'
            }), 400
        
        # ذخیره در جدول metrics
        date_key = time.strftime('%Y-%m-%d')
        db_execute("""
            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
            VALUES (?, 'ita', ?, ?)
        """, (chat_id, date_key, member_count))
        
        return jsonify({
            'success': True,
            'message': f'Member count for chat {chat_id} set to {member_count}',
            'chat_id': chat_id,
            'member_count': member_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/debug_register', methods=['POST'])
def api_debug_register():
    """تست ثبت با لاگ‌های بیشتر"""
    try:
        print("=== DEBUG REGISTER START ===")
        data = request.get_json()
        print(f"Request data: {data}")
        
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        
        print(f"Chat ID: {chat_id}, Platform: {platform}")
        
        # تست ثبت
        result = manual_register_chat(chat_id, 'channel', platform, 'Debug Test')
        print(f"Registration result: {result}")
        
        return jsonify({"success": result, "message": "Debug test completed"})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/register_ita_chat_full', methods=['POST'])
def api_register_ita_chat_full():
    """
    ثبت چت ایتا با دریافت اطلاعات کامل (نام، یوزرنیم، تعداد اعضا)
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "username_or_id",
        "chat_type": "channel",  // اختیاری
        "name": "نام کانال",      // اختیاری
        "username": "username"   // اختیاری
    }
    """
    try:
        logger.info("🚀 [Flask API] ITA full registration request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        chat_type = data.get('chat_type', 'channel')
        name = data.get('name')
        username = data.get('username')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Processing ITA full registration - chat_id: {chat_id}, type: {chat_type}, name: {name}, username: {username}")
        
        # ثبت چت با اطلاعات کامل
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username))
            loop.close()
            
            if success:
                logger.info(f"[Flask API] Successfully registered ITA chat {chat_id} with full info")
                return jsonify({
                    "success": True,
                    "message": f"ITA chat {chat_id} registered successfully with full information",
                    "chat_id": chat_id,
                    "platform": "ita"
                })
            else:
                logger.error(f"[Flask API] Failed to register ITA chat {chat_id}")
                return jsonify({
                    "success": False,
                    "error": "Failed to register ITA chat"
                }), 500
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA full registration: {e}")
            return jsonify({
                "success": False,
                "error": f"Registration failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA full registration: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/register_ita_smart', methods=['POST'])
def api_register_ita_smart():
    """
    ثبت چت ایتا با استفاده از روش‌های پیشرفته (شامل شناسه عددی و username)
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "username_or_numeric_id",
        "chat_type": "channel",  // اختیاری
        "name": "نام کانال",      // اختیاری
        "username": "username"   // اختیاری
    }
    """
    try:
        logger.info("🚀 [Flask API] ITA smart registration request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        chat_type = data.get('chat_type', 'channel')
        name = data.get('name')
        username = data.get('username')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Processing ITA smart registration - chat_id: {chat_id}, type: {chat_type}, name: {name}, username: {username}")
        
        # ثبت چت با روش‌های پیشرفته
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username))
            loop.close()
            
            if success:
                logger.info(f"[Flask API] Successfully registered ITA chat {chat_id} with smart analysis")
                return jsonify({
                    "success": True,
                    "message": f"ITA chat {chat_id} registered successfully with smart analysis",
                    "chat_id": chat_id,
                    "platform": "ita",
                    "method": "smart_analysis"
                })
            else:
                logger.error(f"[Flask API] Failed to register ITA chat {chat_id}")
                return jsonify({
                    "success": False,
                    "error": "Failed to register ITA chat"
                }), 500
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA smart registration: {e}")
            return jsonify({
                "success": False,
                "error": f"Registration failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA smart registration: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/register_ita_from_message', methods=['POST'])
def api_register_ita_from_message():
    """
    ثبت چت ایتا از اطلاعات پیام ارسالی (بدون ارسال پیام جدید)
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "message_data": {
            "chat": {
                "id": "chat_id",
                "title": "نام کانال",
                "username": "username",
                "type": "channel"
            }
        },
        "chat_type": "channel",  // اختیاری
        "name": "نام کانال",      // اختیاری
        "username": "username"   // اختیاری
    }
    """
    try:
        logger.info("📨 [Flask API] ITA registration from message request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        message_data = data.get('message_data')
        chat_type = data.get('chat_type', 'channel')
        name = data.get('name')
        username = data.get('username')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not message_data:
            error_msg = "message_data is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        chat_info = message_data.get('chat', {})
        if not chat_info.get('id'):
            error_msg = "chat.id is required in message_data"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        chat_id = str(chat_info.get('id'))
        
        logger.info(f"[Flask API] Processing ITA registration from message - chat_id: {chat_id}, type: {chat_type}, name: {name}, username: {username}")
        
        # ثبت چت از اطلاعات پیام
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username, message_data))
            loop.close()
            
            if success:
                logger.info(f"[Flask API] Successfully registered ITA chat {chat_id} from message data")
                return jsonify({
                    "success": True,
                    "message": f"ITA chat {chat_id} registered successfully from message data",
                    "chat_id": chat_id,
                    "platform": "ita",
                    "method": "message_extraction"
                })
            else:
                logger.error(f"[Flask API] Failed to register ITA chat {chat_id} from message data")
                return jsonify({
                    "success": False,
                    "error": "Failed to register ITA chat from message data"
                }), 500
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA registration from message: {e}")
            return jsonify({
                "success": False,
                "error": f"Registration failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA registration from message: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/register_ita_advanced_smart', methods=['POST'])
def api_register_ita_advanced_smart():
    """
    ثبت چت ایتا با استفاده از روش‌های advanced_smart_gui (شامل ارسال پیام برای شناسه‌های عددی)
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "username_or_numeric_id",
        "chat_type": "channel",  // اختیاری
        "name": "نام کانال",      // اختیاری
        "username": "username",   // اختیاری
        "allow_test_message": true  // اختیاری - اجازه ارسال پیام تست
    }
    """
    try:
        logger.info("🧠 [Flask API] ITA advanced smart registration request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        chat_type = data.get('chat_type', 'channel')
        name = data.get('name')
        username = data.get('username')
        allow_test_message = data.get('allow_test_message', True)
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Processing ITA advanced smart registration - chat_id: {chat_id}, type: {chat_type}, name: {name}, username: {username}, allow_test_message: {allow_test_message}")
        
        # ثبت چت با روش‌های پیشرفته
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if allow_test_message:
                # استفاده از روش advanced_smart_gui (شامل ارسال پیام)
                success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username))
            else:
                # استفاده از روش بدون ارسال پیام
                success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username))
            
            loop.close()
            
            if success:
                logger.info(f"[Flask API] Successfully registered ITA chat {chat_id} with advanced smart analysis")
                return jsonify({
                    "success": True,
                    "message": f"ITA chat {chat_id} registered successfully with advanced smart analysis",
                    "chat_id": chat_id,
                    "platform": "ita",
                    "method": "advanced_smart_gui_style"
                })
            else:
                logger.error(f"[Flask API] Failed to register ITA chat {chat_id}")
                return jsonify({
                    "success": False,
                    "error": "Failed to register ITA chat"
                }), 500
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA advanced smart registration: {e}")
            return jsonify({
                "success": False,
                "error": f"Registration failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA advanced smart registration: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/test_ita_detection', methods=['POST'])
def api_test_ita_detection():
    """
    تست روش‌های تشخیص ایتا برای یک چت
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "username_or_numeric_id"
    }
    """
    try:
        logger.info("🧪 [Flask API] ITA detection test request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Testing ITA detection for chat_id: {chat_id}")
        
        # تست روش‌های تشخیص
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            test_results = loop.run_until_complete(test_ita_smart_detection(chat_id))
            loop.close()
            
            logger.info(f"[Flask API] Detection test completed for {chat_id}")
            return jsonify({
                "success": True,
                "message": f"Detection test completed for {chat_id}",
                "chat_id": chat_id,
                "test_results": test_results
            })
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA detection test: {e}")
            return jsonify({
                "success": False,
                "error": f"Detection test failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA detection test: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/register_ita_from_sent_message', methods=['POST'])
def api_register_ita_from_sent_message():
    """
    ثبت چت ایتا از اطلاعات پیام ارسالی (بدون ارسال پیام جدید)
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "message_response": {
            "ok": true,
            "result": {
                "message_id": 123,
                "chat": {
                    "id": "chat_id",
                    "title": "نام کانال",
                    "username": "username",
                    "type": "channel"
                }
            }
        },
        "chat_type": "channel",  // اختیاری
        "name": "نام کانال",      // اختیاری
        "username": "username"   // اختیاری
    }
    """
    try:
        logger.info("📨 [Flask API] ITA registration from sent message request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        message_response = data.get('message_response')
        chat_type = data.get('chat_type', 'channel')
        name = data.get('name')
        username = data.get('username')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not message_response:
            error_msg = "message_response is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        if not message_response.get('ok'):
            error_msg = "Message was not sent successfully"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        result = message_response.get('result', {})
        chat_info = result.get('chat', {})
        if not chat_info.get('id'):
            error_msg = "chat.id is required in message_response.result"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        chat_id = str(chat_info.get('id'))
        
        logger.info(f"[Flask API] Processing ITA registration from sent message - chat_id: {chat_id}, type: {chat_type}, name: {name}, username: {username}")
        
        # ثبت چت از اطلاعات پیام ارسالی
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(register_ita_chat_with_full_info(chat_id, chat_type, name, username, message_response))
            loop.close()
            
            if success:
                logger.info(f"[Flask API] Successfully registered ITA chat {chat_id} from sent message")
                return jsonify({
                    "success": True,
                    "message": f"ITA chat {chat_id} registered successfully from sent message",
                    "chat_id": chat_id,
                    "platform": "ita",
                    "method": "sent_message_extraction"
                })
            else:
                logger.error(f"[Flask API] Failed to register ITA chat {chat_id} from sent message")
                return jsonify({
                    "success": False,
                    "error": "Failed to register ITA chat from sent message"
                }), 500
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA registration from sent message: {e}")
            return jsonify({
                "success": False,
                "error": f"Registration failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA registration from sent message: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/test_ita_advanced_smart', methods=['POST'])
def api_test_ita_advanced_smart():
    """
    تست روش‌های advanced_smart_gui برای تشخیص ایتا
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "username_or_numeric_id"
    }
    """
    try:
        logger.info("🧠 [Flask API] ITA advanced smart test request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Testing ITA advanced smart detection for chat_id: {chat_id}")
        
        # تست روش‌های تشخیص
        try:
            # استفاده از asyncio.run برای اجرای تابع async
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            test_results = loop.run_until_complete(test_ita_advanced_smart_gui_style(chat_id))
            loop.close()
            
            logger.info(f"[Flask API] Advanced smart detection test completed for {chat_id}")
            return jsonify({
                "success": True,
                "message": f"Advanced smart detection test completed for {chat_id}",
                "chat_id": chat_id,
                "test_results": test_results
            })
                
        except Exception as e:
            logger.error(f"[Flask API] Error in ITA advanced smart detection test: {e}")
            return jsonify({
                "success": False,
                "error": f"Advanced smart detection test failed: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error in ITA advanced smart detection test: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/sync_all_member_counts', methods=['POST'])
def api_sync_all_member_counts():
    """
    همگام‌سازی تعداد اعضای همه چت‌ها
    """
    try:
        logger.info("🔄 [Flask API] Syncing all member counts request received")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # دریافت همه چت‌ها
            cursor.execute("SELECT chat_id, platform, chat_type FROM chats WHERE chat_type != 'private'")
            chats = cursor.fetchall()
            
            updated_count = 0
            failed_count = 0
            
            for chat_id, platform, chat_type in chats:
                try:
                    # دریافت تعداد اعضا از API
                    member_count = asyncio.run(get_chat_member_count(str(chat_id), platform, chat_type))
                    
                    if member_count > 0:
                        # به‌روزرسانی در جدول chats
                        cursor.execute("""
                            UPDATE chats 
                            SET member_count = ?
                            WHERE chat_id = ? AND platform = ?
                        """, (member_count, str(chat_id), platform))
                        
                        # ذخیره در جدول metrics
                        date_key = time.strftime('%Y-%m-%d')
                        cursor.execute("""
                            INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                            VALUES (?, ?, ?, ?)
                        """, (str(chat_id), platform, date_key, member_count))
                        
                        updated_count += 1
                        logger.info(f"✅ Updated member count for {chat_id} ({platform}): {member_count}")
                    else:
                        logger.warning(f"⚠️ No members found for {chat_id} ({platform})")
                        failed_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ Failed to get member count for {chat_id} ({platform}): {e}")
                    failed_count += 1
                
                # کمی مکث بین درخواست‌ها
                time.sleep(0.5)
            
            conn.commit()
            
            logger.info(f"🔄 [Flask API] Member count sync completed: {updated_count} updated, {failed_count} failed")
            return jsonify({
                "success": True,
                "message": f"Member count sync completed: {updated_count} updated, {failed_count} failed",
                "updated_count": updated_count,
                "failed_count": failed_count,
                "total_chats": len(chats)
            })
            
    except Exception as e:
        logger.error(f"❌ [Flask API] Error syncing member counts: {e}")
        return jsonify({
            "success": False,
            "error": f"Error syncing member counts: {str(e)}"
        }), 500

@app.route('/api/update_chat_member_count', methods=['POST'])
def api_update_chat_member_count():
    """
    به‌روزرسانی تعداد اعضای چت
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "chat_id",
        "platform": "ita",
        "member_count": 1500
    }
    """
    try:
        logger.info("👥 [Flask API] Update chat member count request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        member_count = data.get('member_count')
        
        # اعتبارسنجی ورودی‌های اجباری
        if not chat_id:
            error_msg = "chat_id is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        if not platform:
            error_msg = "platform is required"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        if not member_count or not isinstance(member_count, int) or member_count < 0:
            error_msg = "member_count is required and must be a positive integer"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Updating member count for chat {chat_id} on {platform} to {member_count}")
        
        # به‌روزرسانی تعداد اعضا
        try:
            # ذخیره در جدول metrics
            date_key = time.strftime('%Y-%m-%d')
            db_execute("""
                INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                VALUES (?, ?, ?, ?)
            """, (str(chat_id), platform, date_key, member_count))
            
            # به‌روزرسانی در جدول chats (اگر فیلد member_count وجود دارد)
            try:
                db_execute("""
                    UPDATE chats 
                    SET member_count = ?
                    WHERE chat_id = ? AND platform = ?
                """, (member_count, str(chat_id), platform))
            except Exception as e:
                logger.warning(f"[Flask API] Could not update member_count in chats table: {e}")
            
            logger.info(f"[Flask API] Successfully updated member count for chat {chat_id}")
            return jsonify({
                "success": True,
                "message": f"Member count updated successfully for chat {chat_id}",
                "chat_id": chat_id,
                "platform": platform,
                "member_count": member_count
            })
                
        except Exception as e:
            logger.error(f"[Flask API] Error updating member count: {e}")
            return jsonify({
                "success": False,
                "error": f"Failed to update member count: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"[Flask API] Unexpected error updating member count: {e}")
        return jsonify({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/get_chats_with_member_count', methods=['GET'])
def api_get_chats_with_member_count():
    """
    دریافت لیست چت‌ها با تعداد اعضا
    
    پارامترهای اختیاری:
    - platform: فیلتر بر اساس پلتفرم (ita, tlg)
    - limit: تعداد رکوردها (پیش‌فرض: 100)
    - offset: شروع از رکورد (پیش‌فرض: 0)
    """
    try:
        logger.info("📋 [Flask API] Get chats with member count request received")
        
        # دریافت پارامترها
        platform = request.args.get('platform')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        logger.info(f"[Flask API] Getting chats with member count - platform: {platform}, limit: {limit}, offset: {offset}")
        
        # ساخت کوئری
        where_clause = ""
        params = []
        
        if platform:
            where_clause = "WHERE c.platform = ?"
            params.append(platform)
        
        query = f"""
            SELECT 
                c.chat_id,
                c.platform,
                c.name,
                c.username,
                c.chat_type,
                c.created_at,
                cm.members_count,
                cm.date_key as last_updated
            FROM chats c
            LEFT JOIN chats_metrics cm ON c.chat_id = cm.chat_id AND c.platform = cm.platform
            {where_clause}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """
        
        params.extend([limit, offset])
        
        # اجرای کوئری
        results = db_fetchall(query, params)
        
        # فرمت کردن نتایج
        chats = []
        for row in results:
            chat = {
                'chat_id': row[0],
                'platform': row[1],
                'name': row[2] or 'Unknown',
                'username': row[3] or 'None',
                'chat_type': row[4],
                'created_at': row[5],
                'member_count': row[6] if row[6] is not None else 'Unknown',
                'last_updated': row[7]
            }
            chats.append(chat)
        
        # شمارش کل رکوردها
        count_query = f"SELECT COUNT(*) FROM chats c {where_clause}"
        count_params = params[:-2] if platform else []
        total_count = db_fetchone(count_query, count_params)[0]
        
        logger.info(f"[Flask API] Retrieved {len(chats)} chats with member count")
        
        return jsonify({
            "success": True,
            "chats": chats,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        })
        
    except Exception as e:
        logger.error(f"[Flask API] Error getting chats with member count: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to get chats: {str(e)}"
        }), 500

@app.route('/api/check_chat_exists', methods=['POST'])
def api_check_chat_exists():
    """
    بررسی وجود چت در دیتابیس
    """
    try:
        logger.info("🔍 [Check Chat Exists] Request received")
        data = request.get_json(silent=True) or {}
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        
        logger.info(f"🔍 [Check Chat Exists] Data: chat_id={chat_id}, platform={platform}")
        
        if not chat_id or not platform:
            logger.warning("❌ [Check Chat Exists] Missing chat_id or platform")
            return jsonify({"exists": False, "error": "Missing chat_id or platform"}), 400
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id, platform, name, username, chat_type, is_active
                FROM chats 
                WHERE chat_id = ? AND platform = ?
            """, (str(chat_id), platform.lower()))
            
            existing_chat = cursor.fetchone()
            logger.info(f"🔍 [Check Chat Exists] Query result: {existing_chat}")
            
            if existing_chat:
                logger.info("✅ [Check Chat Exists] Chat exists")
                return jsonify({
                    "exists": True,
                    "chat": dict(existing_chat) if existing_chat else None
                })
            else:
                logger.info("❌ [Check Chat Exists] Chat does not exist")
                return jsonify({"exists": False})
                
    except Exception as e:
        logger.error(f"❌ [Check Chat Exists] Error: {str(e)}", exc_info=True)
        return jsonify({"exists": False, "error": str(e)}), 500

@app.route('/api/manual_register_chat', methods=['POST'])
def api_manual_register_chat():
    """
    ثبت دستی چت/کانال در دیتابیس
    
    درخواست باید به صورت JSON با فیلدهای زیر ارسال شود:
    {
        "chat_id": "123456789",       # شناسه عددی چت (الزامی)
        "chat_type": "channel",      # نوع چت: channel, group, private (پیش‌فرض: channel)
        "platform": "telegram",      # پلتفرم: telegram, bale, ita (پیش‌فرض: telegram)
        "name": "نام چت",            # نام چت (اختیاری)
        "username": "username"       # یوزرنیم چت (اختیاری)
    }
    
    پاسخ موفقیت‌آمیز:
    {
        "success": true,
        "message": "Chat 123456789 registered successfully for telegram",
        "chat_id": "123456789",
        "platform": "telegram",
        "type": "channel"
    }
    """
    try:
        logger.info("🚀 [Flask API] Manual register chat request received")
        
        # دریافت و اعتبارسنجی داده‌های ورودی
        if not request.is_json:
            error_msg = "Invalid request: Content-Type must be application/json"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
            
        data = request.get_json()
        logger.info(f"📥 [Flask API] Request data: {data}")
        
        # استخراج و اعتبارسنجی فیلدهای الزامی
        chat_id = data.get('chat_id')
        chat_type = data.get('chat_type', 'channel').lower()
        platform = data.get('platform', 'telegram').lower()
        name = data.get('name', '')
        username = data.get('username', '')
        member_count = data.get('member_count', 0)
        tags = data.get('tags', '')
        
        # اعتبارسنجی مقادیر ورودی
        if not chat_id:
            error_msg = "Missing required parameter: chat_id"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
            
        if chat_type not in ['channel', 'group', 'private', 'supergroup']:
            error_msg = f"Invalid chat_type: {chat_type}. Must be one of: channel, group, private"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
            
        if platform not in ['telegram', 'bale', 'ita']:
            error_msg = f"Invalid platform: {platform}. Must be one of: telegram, bale, ita"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        logger.info(f"[Flask API] Processing registration - chat_id: {chat_id}, platform: {platform}, type: {chat_type}, name: {name}")
        
        # ثبت چت در دیتابیس
        logger.info(f"[Flask API] Calling manual_register_chat function with params: chat_id={chat_id}, chat_type={chat_type}, platform={platform}, name={name}, username={username}, member_count={member_count}, tags={tags}")
        success = manual_register_chat(chat_id, chat_type, platform, name, username, tags, member_count)
        logger.info(f"[Flask API] manual_register_chat returned: {success}")
        
        if success:
            logger.info(f"[Flask API] Chat {chat_id} successfully registered for {platform}")
            return jsonify({
                "success": True,
                "message": f"Chat {chat_id} registered successfully for {platform}",
                "chat_id": chat_id,
                "platform": platform,
                "type": chat_type
            })
        else:
            error_msg = f"Failed to register chat {chat_id} for {platform}"
            logger.error(f"[Flask API] {error_msg}")
            return jsonify({
                "success": False,
                "error": error_msg,
                "message": "Check server logs for more details"
            }), 500
            
    except Exception as e:
        error_msg = f"Unexpected error in manual register chat: {str(e)}"
        logger.error(f"[Flask API] {error_msg}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": error_msg
        }), 500

@app.route('/api/analyze_chat', methods=['POST'])
def api_analyze_chat():
    """
    API endpoint to analyze chat information using smart detection
    """
    try:
        logger.info("🔍 [Analyze Chat] Request received")
        data = request.get_json()
        chat_id = data.get('chat_id')
        platform = data.get('platform')
        quick_mode = data.get('quick_mode', False)
        
        logger.info(f"🔍 [Analyze Chat] Data: chat_id={chat_id}, platform={platform}, quick_mode={quick_mode}")
        
        if not chat_id:
            return jsonify({"success": False, "error": "Missing chat_id"}), 400
        
        if not platform:
            return jsonify({"success": False, "error": "Missing platform"}), 400
        
        # Validate platform
        valid_platforms = ['telegram', 'bale', 'ita']
        if platform.lower() not in valid_platforms:
            return jsonify({"success": False, "error": f"Invalid platform. Must be one of: {valid_platforms}"}), 400
        
        # Analyze based on platform
        if platform.lower() == 'ita':
            result = asyncio.run(_get_ita_advanced_smart_info(chat_id))
        elif platform.lower() == 'telegram':
            result = asyncio.run(_get_telegram_chat_info(chat_id))
        elif platform.lower() == 'bale':
            result = asyncio.run(_get_bale_chat_info(chat_id))
        else:
            return jsonify({"success": False, "error": "Unsupported platform"}), 400
        
        if result.get('success'):
            logger.info(f"✅ [Analyze Chat] Success for {chat_id}: {result.get('method', 'unknown')}")
            return jsonify(result)
        else:
            logger.warning(f"❌ [Analyze Chat] Failed for {chat_id}: {result.get('error', 'unknown error')}")
            return jsonify(result)
            
    except Exception as e:
        logger.error(f"❌ [Analyze Chat] Error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Analysis failed: {str(e)}"
        }), 500

@app.route('/api/register_ita_chat', methods=['POST'])
def api_register_ita_chat():
    """
    API endpoint to manually register ITA chats for broadcasting
    """
    try:
        logger.info("📝 [Register ITA Chat] Request received")
        data = request.get_json()
        chat_id = data.get('chat_id')
        chat_type = data.get('chat_type', 'group')  # default to group
        name = data.get('name', '')
        username = data.get('username', '')
        tags = data.get('tags', '')
        
        logger.info(f"📝 [Register ITA Chat] Data: chat_id={chat_id}, type={chat_type}, name={name}")
        
        if not chat_id:
            return jsonify({"error": "Missing chat_id"}), 400
        
        # Validate chat_type
        valid_types = ['private', 'group', 'channel', 'supergroup']
        if chat_type not in valid_types:
            return jsonify({"error": f"Invalid chat_type. Must be one of: {valid_types}"}), 400
        
        # Try to get ITA chat info if name is not provided
        if not name:
            try:
                import asyncio
                import concurrent.futures
                
                def get_ita_info():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        result = loop.run_until_complete(get_ita_chat_info(str(chat_id)))
                        loop.close()
                        return result
                    except Exception as e:
                        logger.warning(f"Failed to get ITA chat info: {e}")
                        return None
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_ita_info)
                    ita_info = future.result(timeout=10)
                    
                    if ita_info and ita_info.get('title'):
                        name = ita_info['title']
                        logger.info(f"📝 [Register ITA Chat] Auto-retrieved name: {name}")
            except Exception as e:
                logger.warning(f"📝 [Register ITA Chat] Could not auto-retrieve name: {e}")
        
        # Register the chat
        success = register_chat(
            chat_id=str(chat_id),
            chat_type=chat_type,
            platform='ita',
            name=name,
            username=username,
            tags=tags
        )
        
        if success:
            logger.info(f"✅ [Register ITA Chat] Successfully registered ITA chat: {chat_id}")
            return jsonify({
                "success": True,
                "message": f"ITA chat {chat_id} registered successfully",
                "chat_id": chat_id,
                "platform": "ita",
                "chat_type": chat_type,
                "name": name
            })
        else:
            logger.error(f"❌ [Register ITA Chat] Failed to register ITA chat: {chat_id}")
            return jsonify({"error": "Failed to register ITA chat"}), 500
            
    except Exception as e:
        logger.error(f"Error registering ITA chat: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug_database', methods=['GET'])
def api_debug_database():
    """
    API endpoint to debug database state and check what's missing
    """
    try:
        logger.info("🔍 [Debug Database] Request received")
        
        # Check if database exists
        import os
        db_exists = os.path.exists(DB_FILE)
        
        result = {
            "database_exists": db_exists,
            "database_file": DB_FILE,
            "platforms": {}
        }
        
        if not db_exists:
            result["error"] = "Database file does not exist"
            return jsonify(result)
        
        # Check each platform
        platforms = ['telegram', 'bale', 'ita']
        
        for platform in platforms:
            try:
                # Count total chats
                total_chats = db_fetchone("SELECT COUNT(*) as count FROM chats WHERE platform = ?", (platform,))
                total_count = total_chats['count'] if total_chats else 0
                
                # Count active chats
                active_chats = db_fetchone("SELECT COUNT(*) as count FROM chats WHERE platform = ? AND is_active = 1", (platform,))
                active_count = active_chats['count'] if active_chats else 0
                
                # Count by chat type
                chat_types = db_fetchall("""
                    SELECT chat_type, COUNT(*) as count 
                    FROM chats 
                    WHERE platform = ? AND is_active = 1 
                    GROUP BY chat_type
                """, (platform,))
                
                chat_type_counts = {row['chat_type']: row['count'] for row in chat_types}
                
                # Get sample chats
                sample_chats = db_fetchall("""
                    SELECT chat_id, chat_type, name, username, is_active 
                    FROM chats 
                    WHERE platform = ? 
                    LIMIT 5
                """, (platform,))
                
                result["platforms"][platform] = {
                    "total_chats": total_count,
                    "active_chats": active_count,
                    "chat_types": chat_type_counts,
                    "sample_chats": [dict(row) for row in sample_chats]
                }
                
            except Exception as e:
                result["platforms"][platform] = {
                    "error": str(e)
                }
        
        # Check broadcast targets specifically
        result["broadcast_targets"] = {}
        for platform in platforms:
            try:
                targets = get_target_ids_by_scope(['private', 'group', 'channel'], platform)
                result["broadcast_targets"][platform] = {
                    scope: len(ids) for scope, ids in targets.items()
                }
            except Exception as e:
                result["broadcast_targets"][platform] = {"error": str(e)}
        
        logger.info(f"🔍 [Debug Database] Result: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error debugging database: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/force_update_ita_chat_names', methods=['POST'])
def api_force_update_ita_chat_names():
    """
    API endpoint to force update ITA chat names
    """
    try:
        import asyncio
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        updated_count = loop.run_until_complete(force_update_ita_chat_names())
        loop.close()
        
        return jsonify({
            "success": True,
            "message": f"Successfully updated {updated_count} ITA chat names",
            "updated_count": updated_count
        })
        
    except Exception as e:
        logger.error(f"Error in force update ITA chat names API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/debug_ita_sendmessage/<string:chat_id>', methods=['GET'])
def api_debug_ita_sendmessage(chat_id: str):
    """
    API endpoint to get ITA chat info without sending test message
    """
    try:
        # بررسی اطلاعات موجود در دیتابیس
        existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id,))
        
        if existing_chat:
            chat_info = {
                "chat_id": chat_id,
                "title": existing_chat.get('chat_title', ''),
                "username": existing_chat.get('chat_username', ''),
                "type": existing_chat.get('chat_type', 'channel'),
                "source": "database"
            }
        else:
            chat_info = {
                "chat_id": chat_id,
                "title": "",
                "username": "",
                "type": "channel",
                "source": "not_found"
            }
        
        return jsonify({
            "success": True,
            "message": f"Chat info retrieved for {chat_id} (no test message sent)",
            "chat_info": chat_info
        })
        
    except Exception as e:
        logger.error(f"Error in debug ITA chat info: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/get_ita_chat_title/<string:username>', methods=['GET'])
def api_get_ita_chat_title(username: str):
    """
    API endpoint to get ITA chat title from username
    """
    try:
        import asyncio
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        title = loop.run_until_complete(get_ita_chat_title_from_username(username))
        loop.close()
        
        return jsonify({
            "success": True,
            "username": username,
            "title": title,
            "message": f"Retrieved title for @{username}: {title}"
        })
        
    except Exception as e:
        logger.error(f"Error getting ITA chat title: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/update_ita_chat_names_batch', methods=['POST'])
def api_update_ita_chat_names_batch():
    """
    API endpoint to update all ITA chat names using username as title
    """
    try:
        # دریافت تمام چت‌های ایتا که نام ندارند یا نام خالی دارند
        ita_chats = db_fetchall("""
            SELECT chat_id, name, username 
            FROM chats 
            WHERE platform = 'ita' 
            AND (name IS NULL OR name = '' OR name LIKE 'کانال ایتا%')
            AND username IS NOT NULL AND username != ''
        """)
        
        updated_count = 0
        for chat in ita_chats:
            chat_id = chat['chat_id']
            username = chat['username']
            
            # استفاده از username به عنوان نام
            new_name = f"@{username}"
            
            # به‌روزرسانی نام در دیتابیس
            db_execute("""
                UPDATE chats 
                SET name = ?, last_active = datetime('now')
                WHERE chat_id = ? AND platform = 'ita'
            """, (new_name, chat_id))
            
            logger.info(f"[ITA Batch] Updated chat {chat_id}: {new_name}")
            updated_count += 1
        
        return jsonify({
            "success": True,
            "message": f"Successfully updated {updated_count} ITA chat names",
            "updated_count": updated_count
        })
        
    except Exception as e:
        logger.error(f"Error updating ITA chat names batch: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/update_ita_chat_name/<string:chat_id>', methods=['POST'])
def api_update_ita_chat_name(chat_id: str):
    """
    API endpoint to update a specific ITA chat name
    """
    try:
        import asyncio
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        chat_info = loop.run_until_complete(get_ita_chat_info_simple(chat_id))
        loop.close()
        
        if chat_info and chat_info.get('title'):
            # Update the database
            db_execute("""
                UPDATE chats 
                SET name = ?, username = ?, last_active = datetime('now')
                WHERE chat_id = ? AND platform = 'ita'
            """, (chat_info['title'], chat_info.get('username', ''), chat_id))
            
            return jsonify({
                "success": True,
                "message": f"Successfully updated ITA chat {chat_id}",
                "chat_info": chat_info
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Could not retrieve info for ITA chat {chat_id}"
            }), 404
        
    except Exception as e:
        logger.error(f"Error updating ITA chat name: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/list_ita_chats', methods=['GET'])
def api_list_ita_chats():
    """
    API endpoint to list all ITA chats in database
    """
    try:
        ita_chats = db_fetchall("""
            SELECT chat_id, name, username, chat_type, created_at, last_active, is_active
            FROM chats 
            WHERE platform = 'ita'
            ORDER BY created_at DESC
        """)
        
        return jsonify({
            "success": True,
            "chats": ita_chats,
            "count": len(ita_chats)
        })
        
    except Exception as e:
        logger.error(f"Error listing ITA chats: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/test_ita_chat_simple/<string:chat_id>', methods=['GET'])
def api_test_ita_chat_simple(chat_id: str):
    """
    API endpoint to test simple ITA chat info retrieval
    """
    try:
        import asyncio
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        chat_info = loop.run_until_complete(get_ita_chat_info_simple(chat_id))
        loop.close()
        
        if chat_info:
            return jsonify({
                "success": True,
                "chat_info": chat_info,
                "message": f"Successfully retrieved info for ITA chat {chat_id}"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"Failed to retrieve info for ITA chat {chat_id}"
            }), 404
        
    except Exception as e:
        logger.error(f"Error in test ITA chat simple API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/test_ita_api', methods=['POST'])
def api_test_ita_api():
    """
    API endpoint to test ITA API functionality
    """
    try:
        logger.info("🧪 [Test ITA API] Request received")
        data = request.get_json()
        chat_id = data.get('chat_id')
        test_message = data.get('test_message', 'Test message from multi-bot platform')
        
        if not chat_id:
            return jsonify({"error": "Missing chat_id"}), 400
        
        logger.info(f"🧪 [Test ITA API] Testing with chat_id: {chat_id}")
        
        # Test 1: Get chat info
        try:
            import asyncio
            import concurrent.futures
            
            def test_ita_functions():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Test get_ita_chat_info
                    chat_info = loop.run_until_complete(get_ita_chat_info(str(chat_id)))
                    
                    # Test send_ita_message
                    success, message_id = loop.run_until_complete(send_ita_message(str(chat_id), test_message))
                    
                    loop.close()
                    return {
                        "chat_info": chat_info,
                        "send_message": {"success": success, "message_id": message_id}
                    }
                except Exception as e:
                    logger.error(f"Error in ITA test: {e}")
                    return {"error": str(e)}
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(test_ita_functions)
                test_result = future.result(timeout=30)
            
            logger.info(f"🧪 [Test ITA API] Test result: {test_result}")
            
            return jsonify({
                "success": True,
                "chat_id": chat_id,
                "test_result": test_result,
                "message": "ITA API test completed"
            })
            
        except Exception as e:
            logger.error(f"Error testing ITA API: {e}")
            return jsonify({
                "success": False,
                "error": str(e),
                "message": "ITA API test failed"
            }), 500
            
    except Exception as e:
        logger.error(f"Error in test ITA API endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sync_telegram_channel/<string:chat_id>', methods=['POST'])
def api_sync_telegram_channel(chat_id: str):
    """
    API endpoint to manually sync a Telegram channel
    """
    try:
        import asyncio
        
        async def sync_channel():
            try:
                # بررسی اینکه آیا چت در دیتابیس موجود است
                existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'telegram'", (chat_id,))
                
                if not existing_chat:
                    return {"success": False, "error": "Chat not found in database"}
                
                # دریافت اطلاعات چت از API
                chat_info = await telegram_app.bot.get_chat(int(chat_id))
                chat_name = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                chat_username = getattr(chat_info, 'username', None)
                
                # بررسی وضعیت ربات در کانال
                try:
                    bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                    bot_status = bot_member.status
                except Exception as e:
                    bot_status = "unknown"
                    logger.warning(f"Could not get bot status in channel {chat_id}: {e}")
                
                # به‌روزرسانی اطلاعات چت
                success = register_chat(
                    chat_id=str(chat_id),
                    chat_type=chat_info.type,
                    platform='telegram',
                    name=chat_name,
                    username=chat_username
                )
                
                return {
                    "success": success,
                    "chat_id": chat_id,
                    "chat_name": chat_name,
                    "chat_username": chat_username,
                    "bot_status": bot_status,
                    "message": f"Channel {chat_id} synced successfully" if success else "Failed to sync channel"
                }
                
            except Exception as e:
                logger.error(f"Error syncing Telegram channel {chat_id}: {e}")
                return {"success": False, "error": str(e)}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(sync_channel())
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in sync Telegram channel API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scan_telegram_channels', methods=['POST'])
def api_scan_telegram_channels():
    """
    API endpoint to scan all Telegram channels and register them manually
    This is useful for channels where the bot was added as admin after messages were sent
    """
    try:
        import asyncio
        
        async def scan_channels():
            try:
                logger.info("🔍 [Scan Channels] Starting Telegram channels scan")
                
                # دریافت تمام کانال‌های تلگرام از دیتابیس
                channels = db_fetchall("""
                    SELECT chat_id, chat_title, chat_username, chat_type 
                    FROM chats 
                    WHERE platform = 'telegram' AND chat_type = 'channel'
                    ORDER BY chat_id
                """)
                
                if not channels:
                    return {
                        "success": True,
                        "scanned_count": 0,
                        "registered_count": 0,
                        "message": "No Telegram channels found in database"
                    }
                
                logger.info(f"🔍 [Scan Channels] Found {len(channels)} channels to scan")
                
                scanned_count = 0
                registered_count = 0
                results = []
                
                for channel in channels:
                    chat_id = str(channel['chat_id'])
                    chat_title = channel['chat_title'] or ''
                    chat_username = channel['chat_username'] or ''
                    
                    try:
                        # دریافت اطلاعات چت از API
                        chat_info = await telegram_app.bot.get_chat(int(chat_id))
                        api_title = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                        api_username = getattr(chat_info, 'username', None) or ''
                        
                        # بررسی وضعیت ربات در کانال
                        bot_status = "unknown"
                        try:
                            bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                            bot_status = bot_member.status
                        except Exception as e:
                            logger.warning(f"Could not get bot status in channel {chat_id}: {e}")
                        
                        # به‌روزرسانی اطلاعات چت
                        success = register_chat(
                            chat_id=chat_id,
                            chat_type=chat_info.type,
                            platform='telegram',
                            name=api_title,
                            username=api_username
                        )
                        
                        scanned_count += 1
                        if success:
                            registered_count += 1
                        
                        results.append({
                            "chat_id": chat_id,
                            "old_title": chat_title,
                            "new_title": api_title,
                            "old_username": chat_username,
                            "new_username": api_username,
                            "bot_status": bot_status,
                            "success": success
                        })
                        
                        logger.info(f"🔍 [Scan Channels] Channel {chat_id}: {api_title} (@{api_username}) - Bot status: {bot_status}")
                        
                        # تاخیر کوتاه برای جلوگیری از rate limit
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Error scanning channel {chat_id}: {e}")
                        results.append({
                            "chat_id": chat_id,
                            "error": str(e),
                            "success": False
                        })
                
                return {
                    "success": True,
                    "scanned_count": scanned_count,
                    "registered_count": registered_count,
                    "results": results,
                    "message": f"Scanned {scanned_count} channels, registered {registered_count} successfully"
                }
                
            except Exception as e:
                logger.error(f"Error in scan channels: {e}")
                return {"success": False, "error": str(e)}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(scan_channels())
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in scan Telegram channels API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/add_telegram_channel', methods=['POST'])
def api_add_telegram_channel():
    """
    API endpoint to manually add a Telegram channel to the database
    This is useful for channels where the bot was added as admin after messages were sent
    """
    try:
        import asyncio
        
        data = request.get_json()
        chat_id = data.get('chat_id')
        chat_title = data.get('chat_title', '')
        chat_username = data.get('chat_username', '')
        
        if not chat_id:
            return jsonify({
                "success": False,
                "error": "chat_id is required"
            }), 400
        
        async def add_channel():
            try:
                logger.info(f"📢 [Add Channel] Adding Telegram channel {chat_id}")
                
                # بررسی اینکه آیا چت در دیتابیس موجود است
                existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'telegram'", (chat_id,))
                
                if existing_chat:
                    return {
                        "success": False,
                        "error": "Channel already exists in database",
                        "existing_chat": dict(existing_chat)
                    }
                
                # دریافت اطلاعات چت از API
                try:
                    chat_info = await telegram_app.bot.get_chat(int(chat_id))
                    api_title = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                    api_username = getattr(chat_info, 'username', None) or ''
                    api_type = chat_info.type
                except Exception as e:
                    logger.warning(f"Could not get chat info from API for {chat_id}: {e}")
                    # استفاده از اطلاعات ارائه شده توسط کاربر
                    api_title = chat_title
                    api_username = chat_username
                    api_type = 'channel'
                
                # بررسی وضعیت ربات در کانال
                bot_status = "unknown"
                try:
                    bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                    bot_status = bot_member.status
                except Exception as e:
                    logger.warning(f"Could not get bot status in channel {chat_id}: {e}")
                
                # ثبت چت در دیتابیس
                success = register_chat(
                    chat_id=str(chat_id),
                    chat_type=api_type,
                    platform='telegram',
                    name=api_title,
                    username=api_username
                )
                
                if success:
                    logger.info(f"📢 [Add Channel] Successfully added channel {chat_id}: {api_title} (@{api_username})")
                    return {
                        "success": True,
                        "chat_id": chat_id,
                        "chat_title": api_title,
                        "chat_username": api_username,
                        "chat_type": api_type,
                        "bot_status": bot_status,
                        "message": f"Channel {chat_id} added successfully"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to register channel in database"
                    }
                
            except Exception as e:
                logger.error(f"Error adding Telegram channel {chat_id}: {e}")
                return {"success": False, "error": str(e)}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(add_channel())
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in add Telegram channel API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/force_register_telegram_channel/<string:chat_id>', methods=['POST'])
def api_force_register_telegram_channel(chat_id: str):
    """
    API endpoint to force register a Telegram channel
    This will register the channel even if bot doesn't receive messages from it
    """
    try:
        import asyncio
        
        async def force_register_channel():
            try:
                logger.info(f"🔧 [Force Register] Force registering Telegram channel {chat_id}")
                
                # دریافت اطلاعات چت از API
                try:
                    chat_info = await telegram_app.bot.get_chat(int(chat_id))
                    chat_name = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                    chat_username = getattr(chat_info, 'username', None) or ''
                    chat_type = chat_info.type
                except Exception as e:
                    logger.warning(f"Could not get chat info from API for {chat_id}: {e}")
                    return {
                        "success": False,
                        "error": f"Could not get chat info: {str(e)}"
                    }
                
                # بررسی وضعیت ربات در کانال
                bot_status = "unknown"
                try:
                    bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                    bot_status = bot_member.status
                except Exception as e:
                    logger.warning(f"Could not get bot status in channel {chat_id}: {e}")
                
                # ثبت چت در دیتابیس
                success = register_chat(
                    chat_id=str(chat_id),
                    chat_type=chat_type,
                    platform='telegram',
                    name=chat_name,
                    username=chat_username
                )
                
                if success:
                    logger.info(f"🔧 [Force Register] Successfully force registered channel {chat_id}: {chat_name} (@{chat_username})")
                    return {
                        "success": True,
                        "chat_id": chat_id,
                        "chat_title": chat_name,
                        "chat_username": chat_username,
                        "chat_type": chat_type,
                        "bot_status": bot_status,
                        "message": f"Channel {chat_id} force registered successfully"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to register channel in database"
                    }
                
            except Exception as e:
                logger.error(f"Error force registering Telegram channel {chat_id}: {e}")
                return {"success": False, "error": str(e)}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(force_register_channel())
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in force register Telegram channel API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/monitor_telegram_channels', methods=['POST'])
def api_monitor_telegram_channels():
    """
    API endpoint to monitor all Telegram channels where bot is admin
    This will check channels and register them if they're not in database
    """
    try:
        import asyncio
        
        async def monitor_channels():
            try:
                logger.info("🔍 [Monitor Channels] Starting Telegram channels monitoring")
                
                # دریافت تمام کانال‌های تلگرام از دیتابیس
                channels = db_fetchall("""
                    SELECT chat_id, chat_title, chat_username, chat_type 
                    FROM chats 
                    WHERE platform = 'telegram' AND chat_type = 'channel'
                    ORDER BY chat_id
                """)
                
                if not channels:
                    return {
                        "success": True,
                        "monitored_count": 0,
                        "registered_count": 0,
                        "message": "No Telegram channels found in database"
                    }
                
                logger.info(f"🔍 [Monitor Channels] Found {len(channels)} channels to monitor")
                
                monitored_count = 0
                registered_count = 0
                results = []
                
                for channel in channels:
                    chat_id = str(channel['chat_id'])
                    chat_title = channel['chat_title'] or ''
                    chat_username = channel['chat_username'] or ''
                    
                    try:
                        # بررسی وضعیت ربات در کانال
                        bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                        bot_status = bot_member.status
                        
                        if bot_status in ['administrator', 'creator']:
                            # ربات ادمین است، بررسی اینکه آیا کانال در دیتابیس موجود است
                            existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'telegram'", (chat_id,))
                            
                            if not existing_chat:
                                # کانال در دیتابیس موجود نیست، آن را ثبت کن
                                chat_info = await telegram_app.bot.get_chat(int(chat_id))
                                api_title = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                                api_username = getattr(chat_info, 'username', None) or ''
                                
                                success = register_chat(
                                    chat_id=chat_id,
                                    chat_type=chat_info.type,
                                    platform='telegram',
                                    name=api_title,
                                    username=api_username
                                )
                                
                                if success:
                                    registered_count += 1
                                    logger.info(f"🔍 [Monitor Channels] Registered missing channel {chat_id}: {api_title} (@{api_username})")
                                
                                results.append({
                                    "chat_id": chat_id,
                                    "action": "registered",
                                    "chat_title": api_title,
                                    "chat_username": api_username,
                                    "bot_status": bot_status,
                                    "success": success
                                })
                            else:
                                # کانال در دیتابیس موجود است
                                results.append({
                                    "chat_id": chat_id,
                                    "action": "already_exists",
                                    "chat_title": chat_title,
                                    "chat_username": chat_username,
                                    "bot_status": bot_status,
                                    "success": True
                                })
                        else:
                            # ربات ادمین نیست
                            results.append({
                                "chat_id": chat_id,
                                "action": "not_admin",
                                "chat_title": chat_title,
                                "chat_username": chat_username,
                                "bot_status": bot_status,
                                "success": False
                            })
                        
                        monitored_count += 1
                        
                        # تاخیر کوتاه برای جلوگیری از rate limit
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Error monitoring channel {chat_id}: {e}")
                        results.append({
                            "chat_id": chat_id,
                            "action": "error",
                            "error": str(e),
                            "success": False
                        })
                
                return {
                    "success": True,
                    "monitored_count": monitored_count,
                    "registered_count": registered_count,
                    "results": results,
                    "message": f"Monitored {monitored_count} channels, registered {registered_count} missing channels"
                }
                
            except Exception as e:
                logger.error(f"Error in monitor channels: {e}")
                return {"success": False, "error": str(e)}
        
        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(monitor_channels())
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in monitor Telegram channels API: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/start_channel_monitoring', methods=['POST'])
def api_start_channel_monitoring():
    """
    API endpoint to start periodic monitoring of Telegram channels
    This will check channels every 5 minutes and register missing ones
    """
    try:
        import asyncio
        import threading
        import time
        
        def start_monitoring():
            async def monitor_channels_periodic():
                while True:
                    try:
                        logger.info("🔍 [Periodic Monitor] Starting periodic channel monitoring")
                        
                        # دریافت تمام کانال‌های تلگرام از دیتابیس
                        channels = db_fetchall("""
                            SELECT chat_id, chat_title, chat_username, chat_type 
                            FROM chats 
                            WHERE platform = 'telegram' AND chat_type = 'channel'
                            ORDER BY chat_id
                        """)
                        
                        if channels:
                            logger.info(f"🔍 [Periodic Monitor] Found {len(channels)} channels to monitor")
                            
                            for channel in channels:
                                chat_id = str(channel['chat_id'])
                                chat_title = channel['chat_title'] or ''
                                chat_username = channel['chat_username'] or ''
                                
                                try:
                                    # بررسی وضعیت ربات در کانال
                                    bot_member = await telegram_app.bot.get_chat_member(int(chat_id), telegram_app.bot.id)
                                    bot_status = bot_member.status
                                    
                                    if bot_status in ['administrator', 'creator']:
                                        # بررسی اینکه آیا کانال در دیتابیس موجود است
                                        existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'telegram'", (chat_id,))
                                        
                                        if not existing_chat:
                                            # کانال در دیتابیس موجود نیست، آن را ثبت کن
                                            chat_info = await telegram_app.bot.get_chat(int(chat_id))
                                            api_title = getattr(chat_info, 'title', None) or getattr(chat_info, 'first_name', None) or ''
                                            api_username = getattr(chat_info, 'username', None) or ''
                                            
                                            success = register_chat(
                                                chat_id=chat_id,
                                                chat_type=chat_info.type,
                                                platform='telegram',
                                                name=api_title,
                                                username=api_username
                                            )
                                            
                                            if success:
                                                logger.info(f"🔍 [Periodic Monitor] Registered missing channel {chat_id}: {api_title} (@{api_username})")
                                        
                                        # تاخیر کوتاه برای جلوگیری از rate limit
                                        await asyncio.sleep(0.5)
                                        
                                except Exception as e:
                                    logger.warning(f"Error in periodic monitoring channel {chat_id}: {e}")
                        
                        # تاخیر 5 دقیقه
                        await asyncio.sleep(300)  # 5 minutes
                        
                    except Exception as e:
                        logger.error(f"Error in periodic monitoring: {e}")
                        await asyncio.sleep(60)  # 1 minute delay on error
            
            # اجرای نظارت دوره‌ای در thread جداگانه
            def run_monitoring():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(monitor_channels_periodic())
                loop.close()
            
            monitoring_thread = threading.Thread(target=run_monitoring, daemon=True)
            monitoring_thread.start()
            
            return {
                "success": True,
                "message": "Channel monitoring started successfully",
                "monitoring_interval": "5 minutes"
            }
        
        result = start_monitoring()
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error starting channel monitoring: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/clear_all_database', methods=['POST'])
def api_clear_all_database():
    """
    API endpoint to clear all data from all database tables
    """
    try:
        logger.info("🗑️ [Clear Database] Request received")
        
        # Check if database exists
        import os
        if not os.path.exists(DB_FILE):
            return jsonify({"error": "Database file does not exist"}), 404
        
        # List of all tables to clear
        tables_to_clear = [
            'chats',
            'broadcast_batches', 
            'sent_messages',
            'chats_metrics',
            'channel_posts_stats',
            'unique_members',
            'chat_memberships',
            'scheduled_broadcasts',
            'broadcast_dedupe'
        ]
        
        cleared_tables = []
        errors = []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for table in tables_to_clear:
                try:
                    # Check if table exists
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    if cursor.fetchone():
                        # Clear table
                        cursor.execute(f"DELETE FROM {table}")
                        cleared_tables.append(table)
                        logger.info(f"🗑️ [Clear Database] Cleared table: {table}")
                    else:
                        logger.info(f"🗑️ [Clear Database] Table {table} does not exist, skipping")
                except Exception as e:
                    error_msg = f"Error clearing table {table}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"🗑️ [Clear Database] {error_msg}")
            
            # Commit all changes
            conn.commit()
            
            # Reset auto-increment counters
            for table in cleared_tables:
                try:
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
                except Exception as e:
                    logger.warning(f"Could not reset sequence for {table}: {e}")
            
            conn.commit()
        
        result = {
            "success": True,
            "message": "Database cleared successfully",
            "cleared_tables": cleared_tables,
            "total_cleared": len(cleared_tables)
        }
        
        if errors:
            result["errors"] = errors
            result["warning"] = f"Some tables had errors: {len(errors)} errors"
        
        logger.info(f"🗑️ [Clear Database] Result: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/reset_database', methods=['POST'])
def api_reset_database():
    """
    API endpoint to completely reset the database (delete and recreate)
    """
    try:
        logger.info("🔄 [Reset Database] Request received")
        
        import os
        
        # Check if database exists
        if os.path.exists(DB_FILE):
            # Delete the database file
            os.remove(DB_FILE)
            logger.info(f"🔄 [Reset Database] Deleted database file: {DB_FILE}")
        
        # Recreate the database by calling init_db
        init_db()
        logger.info("🔄 [Reset Database] Recreated database with fresh tables")
        
        result = {
            "success": True,
            "message": "Database reset successfully",
            "database_file": DB_FILE,
            "action": "deleted_and_recreated"
        }
        
        logger.info(f"🔄 [Reset Database] Result: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/list_chats', methods=['GET'])
def api_list_chats():
    """
    لیست کردن تمام چت‌های ثبت شده در دیتابیس
    """
    try:
        platform = request.args.get('platform', 'all')
        
        if platform == 'all':
            query = "SELECT chat_id, chat_type, platform, name, username, created_at, last_active, is_active FROM chats ORDER BY created_at DESC, platform, chat_type, name"
            params = ()
        else:
            query = "SELECT chat_id, chat_type, platform, name, username, created_at, last_active, is_active FROM chats WHERE platform = ? ORDER BY created_at DESC, chat_type, name"
            params = (platform,)
        
        rows = db_fetchall(query, params)
        
        chats = []
        for row in rows:
            # For private chats, set member count to 1
            member_count = 1 if row['chat_type'] == 'private' else 0
            chats.append({
                "chat_id": row['chat_id'],
                "chat_type": row['chat_type'],
                "platform": row['platform'],
                "name": row['name'] or f"کانال {row['platform']} {row['chat_id']}",
                "username": row['username'] or '',
                "created_at": row['created_at'],
                "last_active": row['last_active'],
                "is_active": row['is_active'],
                "member_count": member_count
            })
        
        return jsonify({
            "success": True,
            "chats": chats,
            "total": len(chats),
            "platform": platform
        })
        
    except Exception as e:
        logger.error(f"Error in list chats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/clear-cache', methods=['POST'])
def api_clear_cache():
    """پاک کردن کش و سینک مجدد"""
    try:
        data = request.get_json()
        platform = data.get('platform', 'all')
        
        # پاک کردن webhook تلگرام برای اطمینان از polling
        if platform in ['all', 'telegram']:
            try:
                import requests
                # Use actual token from config
                telegram_token = TELEGRAM_BOT_TOKEN
                webhook_url = f"https://api.telegram.org/bot{telegram_token}/deleteWebhook"
                response = requests.post(webhook_url, timeout=10)
                if response.status_code == 200:
                    logger.info("[Flask API] Telegram webhook cleared")
            except Exception as e:
                logger.warning(f"Could not clear Telegram webhook: {e}")
        
        # اجرای force sync
        def clear_and_sync():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if platform == 'all':
                    loop.run_until_complete(discover_all_chats_from_api('telegram'))
                    loop.run_until_complete(discover_all_chats_from_api('bale'))
                    loop.run_until_complete(discover_all_chats_from_api('ita'))
                    return {"telegram": "cleared_and_synced", "bale": "synced", "ita": "synced"}
                else:
                    loop.run_until_complete(discover_all_chats_from_api(platform))
                    return {platform: "cleared_and_synced"}
            finally:
                loop.close()
        
        result = clear_and_sync()
        logger.info(f"[Flask API] Cache cleared and sync completed: {result}")
        return jsonify({"success": True, "result": result})
        
    except Exception as e:
        logger.error(f"Error in api_clear_cache: {e}")
        return jsonify({"error": str(e)}), 500


def run_flask():
    logger.info("Starting Flask on http://0.0.0.0:5010")
    app.run(host='0.0.0.0', port=5010, debug=False)

# =================================================================
# --- Shared Handlers ---
# =================================================================
async def promote_user_in_telegram_chats_async(promoter_id: int, target_user_id: int, context: TelegramContextTypes.DEFAULT_TYPE):
    rows = db_fetchall("SELECT chat_id FROM chats WHERE chat_type IN ('group','channel') AND platform='telegram'")
    success, fail = 0, 0
    for r in rows:
        try:
            await context.bot.promote_chat_member(
                chat_id=int(r['chat_id']), user_id=target_user_id,
                can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=True,
                can_restrict_members=True, can_promote_members=False, 
                can_change_info=True, can_invite_users=True, can_pin_messages=True
            )
            success += 1
        except Exception as e:
            logger.warning(f"[Telegram] Promote failed for chat {r['chat_id']}: {e}")
            fail += 1
        await asyncio.sleep(0.1)
    final_text = f"✅ عملیات افزودن ادمین کامل شد.\nموفق: {success}\nناموفق: {fail}"
    await context.bot.send_message(promoter_id, final_text)
    await context.bot.send_message(promoter_id, "چه کاری می‌خواهید انجام دهید؟", reply_markup=build_telegram_main_menu())
    logger.info(f"[Telegram] Admin promotion for {target_user_id} completed. Success: {success}, Failed: {fail}")


async def tele_post_init(application: TelegramApplication):
    global telegram_app, telegram_bot_loop
    telegram_app = application
    telegram_bot_loop = asyncio.get_running_loop()
    logger.info(f"[Telegram] Bot initialized and ready.")
    # فعال‌سازی برنامه‌ریز ثبت روزانه اعضا
    asyncio.create_task(metrics_post_init(application, 'telegram'))

async def bale_post_init(application: TelegramApplication):
    global bale_app, bale_bot_loop
    bale_app = application
    bale_bot_loop = asyncio.get_running_loop()
    logger.info(f"[Bale] Bot initialized and ready.")
    # فعال‌سازی برنامه‌ریز ثبت روزانه اعضا
    asyncio.create_task(metrics_post_init(application, 'bale'))

async def start_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str, owner_id: int):
    user, chat = update.effective_user, update.effective_chat
    if user and chat and chat.type == ChatType.PRIVATE:
        uname = getattr(chat, 'username', None)
        fname = getattr(chat, 'first_name', None) or ''
        register_chat(str(user.id), "private", platform, name=fname, username=uname)
        if user.id == owner_id:
            (user_state if platform == 'telegram' else bale_user_state).pop(f"{platform}:{user.id}", None)
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await update.message.reply_text(f"سلام ادمین گرامی! به پنل جامع مدیریت {platform} خوش آمدید.", reply_markup=menu_builder())
            logger.info(f"[{platform}] Admin {user.id} received /start message with menu. Chat type from API: {chat.type}")
        else:
            # بررسی وضعیت تگ‌گذاری کاربر
            has_selected_tags = check_user_tag_status(str(user.id), platform)
            
            if not has_selected_tags:
                # کاربر جدید - درخواست انتخاب تگ
                welcome_msg = f"""🎉 سلام {fname}! به ربات خوش آمدید!

📋 برای دریافت پیام‌های مناسب، لطفاً از تگ‌های زیر چندتایی انتخاب کنید:

🔢 تگ‌های موجود: 1 تا 22
✅ می‌توانید چندین تگ انتخاب کنید
🎯 این تگ‌ها برای ارسال پیام‌های مرتبط به شما استفاده می‌شود

لطفاً تگ‌های مورد نظر خود را انتخاب کنید:"""
                
                keyboard = build_tag_selection_keyboard(platform)
                await update.message.reply_text(welcome_msg, reply_markup=keyboard)
                
                # ذخیره وضعیت انتخاب تگ در user_state
                current_user_state = user_state if platform == 'telegram' else bale_user_state
                current_user_state[f"{platform}:{user.id}"] = {
                    'state': 'selecting_tags',
                    'selected_tags': []
                }
                
                logger.info(f"[{platform}] New user {user.id} started tag selection process")
            else:
                # کاربر قبلاً تگ‌ها را انتخاب کرده
                await update.message.reply_text("شما قبلاً تگ‌های خود را انتخاب کرده‌اید. برای تغییر تگ‌ها با ادمین تماس بگیرید.")
            
            # ارسال اطلاعیه به ادمین برای کاربر جدید
            notification_msg = f"👤 کاربر جدید ربات را استارت کرد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {user.id}\n👤 نام: {fname}\n🔗 یوزرنیم: @{uname}" if uname else f"👤 کاربر جدید ربات را استارت کرد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {user.id}\n👤 نام: {fname}"
            await send_admin_notification(notification_msg, platform)
            
            logger.info(f"[{platform}] User {user.id} registered from /start command. Chat type from API: {chat.type}")

async def chat_member_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str):
    if update.my_chat_member:
        chat, new_member_status = update.my_chat_member.chat, update.my_chat_member.new_chat_member.status
        if new_member_status in ['member', 'administrator']:
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
            chat_username = getattr(chat, 'username', None)
            register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
            
            # ارسال اطلاعیه به ادمین برای اضافه شدن ربات به گروه/کانال
            chat_type_name = "گروه" if chat.type in ['group', 'supergroup'] else "کانال"
            notification_msg = f"📢 ربات به {chat_type_name} جدید اضافه شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}\n🔗 یوزرنیم: @{chat_username}" if chat_username else f"📢 ربات به {chat_type_name} جدید اضافه شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}"
            await send_admin_notification(notification_msg, platform)
            
            logger.info(f"[{platform}] Bot added/promoted in chat {chat.id}. API chat type: {chat.type}. Registered.")
        elif new_member_status in ['left', 'kicked']:
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
            chat_username = getattr(chat, 'username', None)
            
            # ارسال اطلاعیه به ادمین برای حذف ربات از گروه/کانال
            chat_type_name = "گروه" if chat.type in ['group', 'supergroup'] else "کانال"
            removal_reason = "اخراج شد" if new_member_status == 'kicked' else "خروج کرد"
            notification_msg = f"❌ ربات از {chat_type_name} {removal_reason}:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}\n🔗 یوزرنیم: @{chat_username}" if chat_username else f"❌ ربات از {chat_type_name} {removal_reason}:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}"
            await send_admin_notification(notification_msg, platform)
            
            await delete_user_completely(str(chat.id), platform)
            logger.info(f"[{platform}] Bot left/kicked from chat {chat.id}. Removed from DB.")

async def sync_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str, owner_id: int):
    user, chat = update.effective_user, update.effective_chat
    if user and chat and user.id == owner_id:
        # جلوگیری از پردازش مکرر
        sync_key = f"{platform}_{chat.id}_{user.id}"
        if hasattr(sync_handler_base, '_processing'):
            if not hasattr(sync_handler_base, '_processing'):
                sync_handler_base._processing = set()
            if sync_key in sync_handler_base._processing:
                logger.debug(f"[{platform}] Sync already processing for {sync_key}, skipping")
                return
            sync_handler_base._processing.add(sync_key)
        else:
            sync_handler_base._processing = {sync_key}
        
        try:
            register_chat(str(chat.id), chat.type, platform)
            chat_name = chat.title or chat.first_name or ''
            reply_text_escaped = escape_markdown_v2(f"✅ چت '{chat_name}' در پلتفرم {platform} ثبت/به‌روزرسانی شد.")
            await update.message.reply_text(reply_text_escaped, parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"[{platform}] Admin {user.id} manually synced chat {chat.id}. API chat type: {chat.type}")
        except Exception as e:
            logger.error(f"Error in sync handler: {e}")
            await update.message.reply_text("❌ خطا در همگام‌سازی چت. لطفاً دوباره تلاش کنید.")
        finally:
            # حذف از لیست پردازش
            if hasattr(sync_handler_base, '_processing'):
                sync_handler_base._processing.discard(sync_key)

async def export_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str, owner_id: int):
    user = update.effective_user
    if not user or user.id != owner_id: return
    
    await update.message.reply_text(f"⏳ در حال ساخت گزارش اکسل برای {platform}...")
    rows = db_fetchall(f"SELECT chat_id, chat_type FROM chats WHERE platform='{platform}'")
    report_data = []
    
    for r in rows:
        cid_str, ctype_db = r['chat_id'], r['chat_type']
        try:
            if platform == 'ita':
                # ایتا از API مستقیم استفاده می‌کند
                chat_info = await get_ita_chat_info(cid_str)
                if chat_info:
                    members = await get_ita_chat_member_count(cid_str)
                    report_data.append({"ID": cid_str, "Title": chat_info.get('title', '') or (f"{chat_info.get('first_name', '')} {chat_info.get('last_name', '')}".strip()), 
                                      "Type": ctype_db, "Members": members, "Username": chat_info.get('username', '')})
                else:
                    report_data.append({"ID": cid_str, "Title": "Error: Could not get chat info", "Type": ctype_db, "Members": 1, "Username": ""})
            else:
                cid = int(cid_str)
            chat_info = await context.bot.get_chat(cid)
            
            logger.info(f"[{platform} Export] Checking chat {cid_str}, DB type: {ctype_db}, API type from get_chat: {chat_info.type}")

            if chat_info.type == ChatType.PRIVATE:
                # برای کاربران خصوصی، تعداد اعضا همیشه 1 است
                members = 1
            else:
                try: 
                    members = await context.bot.get_chat_member_count(cid)
                    # اگر تعداد اعضا صفر است، آن را به یک تبدیل کن
                    if members == 0:
                        members = 1
                except Exception as ex: 
                    logger.warning(f"[{platform} Export] Could not get member count for chat {cid_str} (API type: {chat_info.type}): {ex}")
                    members = 1
            
            report_data.append({"ID": chat_info.id, "Title": chat_info.title or (f"{chat_info.first_name or ''} {chat_info.last_name or ''}".strip()), 
                                 "Type": CHAT_TYPE_DISPLAY_NAMES.get(chat_info.type, chat_info.type), 
                                 "Members": members, "Username": (f"@{chat_info.username}" if chat_info.username else "N/A")})
        except Exception as e:
            logger.warning(f"[{platform} Export] Could not fetch chat info for {cid_str}: {e}")
        await asyncio.sleep(0.05)
    
    if not report_data:
        await update.message.reply_text(f"❌ هیچ چتی برای گزارش {platform} یافت نشد.")
        return

    # ایجاد دیتافریم اصلی برای لیست چت‌ها
    df_chats = pd.DataFrame(report_data)
    
    # ایجاد دیتافریم برای ارسال‌های انبوه
    broadcast_data = []
    sql = f"""
    SELECT b.batch_id, b.scope, b.content_preview, b.timestamp,
           COUNT(s.message_id) as total_sent,
           SUM(CASE WHEN c.chat_type = 'private' THEN 1 ELSE 0 END) as private_cnt,
           SUM(CASE WHEN c.chat_type = 'group' THEN 1 ELSE 0 END) as group_cnt,
           SUM(CASE WHEN c.chat_type = 'channel' THEN 1 ELSE 0 END) as channel_cnt,
           b.platform as platform  -- Explicitly specify the platform column from broadcast_batches
    FROM broadcast_batches b
    LEFT JOIN sent_messages s ON b.batch_id = s.batch_id
    LEFT JOIN chats c ON s.chat_id = c.chat_id AND b.platform = c.platform
    WHERE b.platform = '{platform}'
    GROUP BY b.batch_id, b.scope, b.content_preview, b.timestamp, b.platform
    ORDER BY b.timestamp DESC
    """
    rows_broadcasts = db_fetchall(sql)
    
    for r in rows_broadcasts:
        tstamp = r['timestamp']
        date_display = tstamp
        if jdatetime and tstamp:
            try:
                y, m, d, hh, mm, ss = map(int, [tstamp[0:4], tstamp[5:7], tstamp[8:10], tstamp[11:13], tstamp[14:16], tstamp[17:19]])
                jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                date_display = jdt.strftime('%Y/%m/%d %H:%M')
            except Exception: pass
        broadcast_data.append({
            'شناسه دسته': r['batch_id'], 'تاریخ': date_display, 'مقصدها': r['scope'],
            'پیش‌نمایش محتوا': r['content_preview'], 'تعداد کل ارسال': r['total_sent'] or 0,
            'کاربران': r['private_cnt'] or 0, 'گروه‌ها': r['group_cnt'] or 0, 'کانال‌ها': r['channel_cnt'] or 0
        })
    
    df_broadcasts = pd.DataFrame(broadcast_data) if broadcast_data else pd.DataFrame(columns=['شناسه دسته','تاریخ','مقصدها','پیش‌نمایش محتوا','تعداد کل ارسال','کاربران','گروه‌ها','کانال‌ها'])
    
    # ایجاد فایل اکسل با چندین شیت
    file_path = f"{platform}_report.xlsx"
    try:
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df_chats.to_excel(writer, sheet_name="لیست چت‌ها", index=False)
            df_broadcasts.to_excel(writer, sheet_name="گزارش ارسال انبوه", index=False)
            
        # ارسال فایل با timeout بیشتر
        try:
            await asyncio.wait_for(
                update.message.reply_document(open(file_path, 'rb'), caption=f"✅ گزارش جامع چت‌های {platform}"),
                timeout=120  # 2 دقیقه timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout while sending {platform} report file")
            await update.message.reply_text("❌ خطا در ارسال فایل: timeout. لطفاً دوباره تلاش کنید.")
            return
        except Exception as e:
            logger.error(f"Error sending {platform} report file: {e}")
            await update.message.reply_text(f"❌ خطا در ارسال فایل: {str(e)}")
            return
        logger.info(f"[{platform}] Admin {user.id} exported chat report.")
    except Exception as e:
        logger.error(f"[{platform} Export] Failed to create/send Excel report: {e}", exc_info=True)
        await update.message.reply_text(f"❌ خطا در ساخت/ارسال گزارش: {e}")
    finally:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

async def button_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str, owner_id: int):
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    
    try:
        await query.answer()
    except (BadRequest, RuntimeError, Exception) as e:
        # Silently ignore timeout errors and event loop errors to reduce log noise
        if any(keyword in str(e).lower() for keyword in ["too old", "timeout", "event loop is closed", "network error"]):
            logger.debug(f"[{platform}] Ignoring callback query error: {e}")
        else:
            logger.warning(f"[{platform}] Failed to answer callback query: {e}")

    data = query.data
    current_user_state = user_state if platform == 'telegram' else bale_user_state
    key = f"{platform}:{user_id}"
    
    # مدیریت انتخاب تگ‌ها برای کاربران عادی
    if data.startswith("select_tag_"):
        tag_number = data.split("_")[-1]
        user_state_data = current_user_state.get(key, {})
        
        if user_state_data.get('state') == 'selecting_tags':
            selected_tags = user_state_data.get('selected_tags', [])
            if tag_number in selected_tags:
                # حذف تگ اگر قبلاً انتخاب شده
                selected_tags.remove(tag_number)
                await query.answer(f"تگ {tag_number} حذف شد")
            else:
                # اضافه کردن تگ
                selected_tags.append(tag_number)
                await query.answer(f"تگ {tag_number} اضافه شد")
            
            # به‌روزرسانی state
            current_user_state[key]['selected_tags'] = selected_tags
            
            # نمایش وضعیت فعلی
            status_msg = f"تگ‌های انتخاب شده: {', '.join(selected_tags) if selected_tags else 'هیچ'}"
            await query.edit_message_text(
                query.message.text + f"\n\n📋 {status_msg}",
                reply_markup=query.message.reply_markup
            )
            return
    
    elif data == "confirm_tags":
        user_state_data = current_user_state.get(key, {})
        if user_state_data.get('state') == 'selecting_tags':
            selected_tags = user_state_data.get('selected_tags', [])
            
            if not selected_tags:
                await query.answer("لطفاً حداقل یک تگ انتخاب کنید", show_alert=True)
                return
            
            # ذخیره تگ‌ها در دیتابیس
            tags_string = ','.join(selected_tags)
            update_user_tag_status(str(user_id), platform, tags_string)
            
            # به‌روزرسانی تگ‌ها در جدول chats
            register_chat(str(user_id), "private", platform, tags=tags_string)
            
            # پاک کردن state
            current_user_state.pop(key, None)
            
            await query.edit_message_text(
                f"✅ تگ‌های شما با موفقیت ثبت شد!\n\n"
                f"📋 تگ‌های انتخاب شده: {', '.join(selected_tags)}\n\n"
                f"🎯 از این پس پیام‌های مرتبط با این تگ‌ها را دریافت خواهید کرد.\n\n"
                f"برای تغییر تگ‌ها با ادمین تماس بگیرید."
            )
            
            # اطلاع به ادمین
            notification_msg = f"✅ کاربر تگ‌های خود را انتخاب کرد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {user_id}\n🏷️ تگ‌ها: {tags_string}"
            await send_admin_notification(notification_msg, platform)
            
            logger.info(f"[{platform}] User {user_id} completed tag selection: {tags_string}")
            return
    
    # فقط ادمین می‌تواند از سایر دکمه‌ها استفاده کند
    if user_id != owner_id: return

    logger.info(f"[{platform}] Debug - Callback handler start: key={key}, data={data}, state_before={list(current_user_state.get(key, {}).keys())}")

    if data.startswith("menu_"): 
        logger.info(f"[{platform}] Debug - Clearing state for menu callback: {data}")
        current_user_state.pop(key, None)
    
    try:
        if data == "menu_list":
            # استفاده از تابع جدید برای تولید آمار یکسان
            text = generate_unified_chat_stats()
            
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await query.edit_message_text(text, reply_markup=menu_builder())
        
        elif data == "menu_delete_history":
            # نمایش تاریخچه برای هر دو پلتفرم تا بتوانید از هر ربات، حذف را اجرا کنید
            rows = db_fetchall(
                """
                SELECT batch_id, scope, strftime('%y/%m/%d %H:%M', timestamp) as ts,
                       content_preview, platform
                FROM broadcast_batches
                ORDER BY timestamp DESC
                LIMIT 10
                """
            )
            
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            if not rows:
                await query.edit_message_text("هیچ ارسال اخیری یافت نشد.", reply_markup=menu_builder())
                return
                
            platform_emoji = {
                'telegram': '📨',
                'bale': '💬'
            }
            
            buttons = [
                [InlineKeyboardButton(
                    f"{platform_emoji.get(r['platform'], '📌')} {r['scope']} ({r['content_preview'][:30]}{'...' if len(r['content_preview']) > 30 else ''} - {r['ts']})",
                    callback_data=f"view_batch_{r['batch_id']}"
                )]
                for r in rows
            ]
            buttons.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main")])
            await query.edit_message_text(
                "📋 تاریخچه ارسال‌ها\n\nبرای مشاهده جزئیات و حذف، روی هر آیتم کلیک کنید.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif data.startswith("view_batch_"):
            batch_id = int(data.split("_")[-1])
            batch = db_fetchone("""
                SELECT batch_id, platform, scope, content_preview, 
                       strftime('%Y-%m-%d %H:%M', timestamp) as ts,
                       (SELECT COUNT(*) FROM sent_messages WHERE batch_id = ?) as message_count
                FROM broadcast_batches 
                WHERE batch_id = ?
            """, (batch_id, batch_id))
            
            if batch and hasattr(batch, 'keys'):
                batch = {key: batch[key] for key in batch.keys()}
                message_count = batch.get('message_count', 0)
            else:
                await query.answer("❌ خطا: اطلاعات ارسال یافت نشد", show_alert=True)
                return
            
            if batch['platform'] == 'telegram':
                platform_name = 'تلگرام'
            elif batch['platform'] == 'bale':
                platform_name = 'بله'
            elif batch['platform'] == 'ita':
                platform_name = 'ایتا'
            else:
                platform_name = batch['platform']
            
            text = (
                f"📝 *جزئیات ارسال*\n"
                f"• پلتفرم: {platform_name}\n"
                f"• محدوده: {batch['scope']}\n"
                f"• تعداد پیام: {message_count}\n"
                f"• تاریخ: {batch['ts']}\n"
                f"• محتوا: {batch['content_preview'][:100]}{'...' if len(batch['content_preview']) > 100 else ''}"
            )
            
            buttons = [
                [
                    InlineKeyboardButton("❌ حذف این ارسال", callback_data=f"confirm_delete_{batch_id}"),
                    InlineKeyboardButton("🔙 بازگشت", callback_data="menu_delete_history")
                ]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif data.startswith("confirm_delete_"):
            batch_id = int(data.split("_")[-1])
            batch_info = db_fetchall("SELECT platform FROM broadcast_batches WHERE batch_id = ?", (batch_id,))
            if not batch_info:
                await query.answer("❌ ارسال مورد نظر یافت نشد یا قبلاً حذف شده است.", show_alert=True)
                return
                
            buttons = [
                [
                    InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"delete_batch_{batch_id}"),
                    InlineKeyboardButton("❌ خیر، انصراف", callback_data=f"view_batch_{batch_id}")
                ]
            ]
            
            await query.edit_message_text(
                "⚠️ آیا از حذف این ارسال اطمینان دارید؟\n\nاین عمل قابل بازگشت نیست.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        elif data.startswith("delete_scheduled_"):
            try:
                await query.answer()
            except Exception as e:
                logger.warning(f"Error answering callback query: {e}")
                
            # Parse broadcast_id from callback data (format: delete_scheduled_<broadcast_id>)
            broadcast_id = int(data.split('_')[2])
            
            # دریافت اطلاعات ارسال زمان‌بندی شده
            broadcast_info = db_fetchone("""
                SELECT * FROM scheduled_broadcasts WHERE id = ? AND status = 'pending'
            """, (broadcast_id,))
            
            if not broadcast_info:
                try:
                    await query.answer("❌ ارسال زمان‌بندی شده یافت نشد یا قبلاً اجرا شده است.", show_alert=True)
                except Exception as e:
                    logger.warning(f"Failed to answer callback query: {e}")
                return
            
            # حذف از scheduler
            if scheduler:
                try:
                    scheduler.remove_job(f"once_{broadcast_id}")
                    logger.info(f"Removed scheduled job once_{broadcast_id}")
                except Exception as e:
                    logger.warning(f"Failed to remove scheduled job once_{broadcast_id}: {e}")
            
            # حذف از دیتابیس
            db_execute("DELETE FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
            
            # نمایش پیام موفقیت
            await query.edit_message_text(
                "✅ ارسال زمان‌بندی شده با موفقیت حذف شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main")]])
            )
            
        elif data.startswith("delete_completed_"):
            try:
                await query.answer()
            except Exception as e:
                logger.warning(f"Error answering callback query: {e}")
            
            # Parse broadcast_id from callback data (format: delete_completed_<broadcast_id>)
            broadcast_id = int(data.split('_')[2])
            
            # حذف از دیتابیس
            db_execute("DELETE FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
            
            # نمایش پیام موفقیت
            await query.edit_message_text(
                "✅ گزارش ارسال انجام شده حذف شد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main")]])
            )
            
        elif data.startswith("delete_batch_"):
            try:
                await query.answer()
            except Exception as e:
                logger.warning(f"Error answering callback query: {e}")
                
            # Parse batch_id and platform from callback data (format: delete_batch_<batch_id>_<platform>)
            parts = data.split('_')
            if len(parts) >= 4:  # delete_batch_<id>_<platform>
                batch_id = int(parts[2])
                batch_platform = parts[3]
            else:
                # Fallback for old format
                batch_id = int(parts[-1])
                batch_platform = None
                
            batch_info = db_fetchall("""
                SELECT b.platform, b.content_preview, b.batch_id, 
                       COUNT(s.message_id) as message_count
                FROM broadcast_batches b
                LEFT JOIN sent_messages s ON b.batch_id = s.batch_id
                WHERE b.batch_id = ?
                GROUP BY b.batch_id
            """, (batch_id,))
            
            if not batch_info:
                await query.answer("❌ ارسال مورد نظر یافت نشد یا قبلاً حذف شده است.", show_alert=True)
                return
                
            # تبدیل sqlite3.Row به dict برای دسترسی ایمن به کلیدها
            batch = dict(batch_info[0])
            batch_platform = batch['platform']
            message_count = batch.get('message_count', 0)
            # اجازه حذف از هر ربات (Route کردن به اپلیکیشن صحیح بر اساس batch_platform)
            
            if batch_platform == 'telegram':
                platform_name = 'تلگرام'
            elif batch_platform == 'bale':
                platform_name = 'بله'
            elif batch_platform == 'ita':
                platform_name = 'ایتا'
            else:
                platform_name = batch_platform
            content_preview = batch.get('content_preview', '-') or '-'
            # پیام فعلی را به حالت شروع عملیات تغییر می‌دهیم
            await query.edit_message_text(
                f"🗑 عملیات حذف برای {platform_name} آغاز شد.\n\n"
                f"محتوا: {content_preview}\n"
                f"نتیجه به‌زودی در همین پیام نمایش داده می‌شود."
            )
            
            app_target = telegram_app if batch_platform == 'telegram' else bale_app
            loop_target = telegram_bot_loop if batch_platform == 'telegram' else bale_bot_loop
            
            if not app_target or not loop_target:
                error_msg = f"❌ ربات {platform_name} در حال حاضر فعال نیست."
                await query.edit_message_text(error_msg)
                return
            
            # اجرای حذف در پس‌زمینه و ارسال نتیجه به ادمین، بدون قفل کردن ربات
            try:
                admin_id = query.from_user.id
                msg_chat_id = query.message.chat.id
                msg_id = query.message.message_id
                current_loop = asyncio.get_running_loop()
                async def edit_result_message(res_ok: dict=None, err: Exception=None):
                    if err is not None:
                        # Get platform name for error message
                        platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا'}
                        error_platform_name = platform_names.get(batch_platform, batch_platform)
                        err_text = (
                            f"❌ خطا در حذف از {error_platform_name}: {err}\n\n"
                            f"محتوا: {content_preview}"
                        )
                        await context.bot.edit_message_text(
                            chat_id=msg_chat_id,
                            message_id=msg_id,
                            text=err_text,
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("📋 بازگشت به تاریخچه", callback_data="menu_delete_history")],
                                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu_main")]
                            ])
                        )
                        return
                    deleted = res_ok.get('deleted', 0)
                    failed = res_ok.get('failed', 0)
                    # Update the original message with new button states
                    # Get the original message text
                    original_msg = query.message.text
                    
                    # Create updated keyboard with deleted status
                    updated_keyboard = []
                    platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا'}
                    
                    # We need to regenerate all buttons for this message
                    # First, let's find all batch IDs that were created for this broadcast
                    # We'll look for batches created around the same time as this one
                    
                    # Get the current batch info to find related batches
                    current_batch_info = db_fetchone("SELECT timestamp FROM broadcast_batches WHERE batch_id = ?", (batch_id,))
                    if current_batch_info:
                        # Find all batches created within 1 minute of this one (same broadcast)
                        related_batches = db_fetchall("""
                            SELECT batch_id, platform, is_deleted 
                            FROM broadcast_batches 
                            WHERE timestamp BETWEEN datetime(?, '-1 minute') AND datetime(?, '+1 minute')
                            ORDER BY batch_id
                        """, (current_batch_info['timestamp'], current_batch_info['timestamp']))
                        
                        # Create buttons for all related batches
                        for batch in related_batches:
                            batch_id_val = batch['batch_id']
                            batch_platform_val = batch['platform']
                            is_deleted_val = batch['is_deleted']
                            
                            platform_name = platform_names.get(batch_platform_val, batch_platform_val)
                            
                            if is_deleted_val == 1:
                                # This batch is deleted
                                updated_keyboard.append([InlineKeyboardButton(f"✅ حذف شده - {platform_name}", callback_data="noop")])
                            else:
                                # This batch is still active
                                updated_keyboard.append([InlineKeyboardButton(f"🗑 حذف ارسال {platform_name}", callback_data=f"delete_batch_{batch_id_val}_{batch_platform_val}")])
                    
                    # If we couldn't find related batches, fall back to the current batch only
                    if not updated_keyboard:
                        platform_name = platform_names.get(batch_platform, batch_platform)
                        updated_keyboard.append([InlineKeyboardButton(f"✅ حذف شده - {platform_name}", callback_data="noop")])
                    
                    # Update the message with new button state
                    await context.bot.edit_message_text(
                        chat_id=msg_chat_id,
                        message_id=msg_id,
                        text=original_msg,
                        reply_markup=InlineKeyboardMarkup(updated_keyboard)
                    )

                if loop_target is current_loop:
                    async def run_same_loop():
                        try:
                            res = await delete_messages_async(app_target, batch_id, batch_platform)
                            await edit_result_message(res_ok=res)
                        except Exception as e:
                            logger.error(f"Error in same-loop delete: {e}", exc_info=True)
                            await edit_result_message(err=e)
                    asyncio.create_task(run_same_loop())
                else:
                    fut = asyncio.run_coroutine_threadsafe(
                        delete_messages_async(app_target, batch_id, batch_platform),
                        loop_target
                    )
                    async def wait_other_loop():
                        try:
                            loop_local = asyncio.get_running_loop()
                            res = await loop_local.run_in_executor(None, lambda: fut.result(300))
                            await edit_result_message(res_ok=res)
                        except Exception as e:
                            logger.error(f"Error waiting other-loop delete: {e}", exc_info=True)
                            await edit_result_message(err=e)
                    asyncio.create_task(wait_other_loop())
            except Exception as e:
                logger.error(f"Error scheduling delete background task: {e}", exc_info=True)
                await context.bot.send_message(query.from_user.id, f"❌ خطا در زمان‌بندی حذف: {e}")

        # شاخه refresh_batch حذف شد چون نتیجه نهایی را همان لحظه نمایش می‌دهیم
        
        # بخش menu_export حذف شد و دکمه‌ها مستقیماً به منوی اصلی منتقل شدند

        elif data == "comprehensive_report_start":
            # درخواست انتخاب پلتفرم برای گزارش جامع
            platform_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 تلگرام", callback_data="comprehensive_report_platform_telegram")],
                [InlineKeyboardButton("💬 بله", callback_data="comprehensive_report_platform_bale")],
                [InlineKeyboardButton("📱 ایتا", callback_data="comprehensive_report_platform_ita")],
                [InlineKeyboardButton("🔄 هر دو (تلگرام + بله)", callback_data="comprehensive_report_platform_both")],
                [InlineKeyboardButton("🌐 همه (تلگرام + بله + ایتا)", callback_data="comprehensive_report_platform_all")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")]
            ])
            await query.edit_message_text("گزارش جامع برای کدام پلتفرم ساخته شود؟", reply_markup=platform_kb)

        elif data.startswith("comprehensive_report_platform_"):
            choice = data.split("_")[-1]

            async def generate_comprehensive_report(selected_platforms: list):
                await query.edit_message_text(f"⏳ در حال ساخت گزارش جامع برای پلتفرم(های): {', '.join(selected_platforms)}. این عملیات ممکن است کمی طول بکشد...")

                # --- شیت ۱: لیست چت‌ها ---
                df_chats = pd.DataFrame()
                rows_all = []
                async def fetch_live_info(pf: str, cid) -> dict:
                    info = {"members": None, "name": None, "username": None}
                    try:
                        if pf == 'ita':
                            # برای ایتا از دیتابیس اطلاعات را می‌گیریم
                            chat_id_str = str(cid) if cid is not None else None
                            if chat_id_str:
                                chat_info = db_fetchone("SELECT name, username FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id_str,))
                                if chat_info:
                                    info["name"] = chat_info['name']
                                    info["username"] = chat_info['username']
                                
                                # اگر نام موجود نیست یا خالی است، سعی می‌کنیم آن را به‌روزرسانی کنیم
                                if not info["name"] or not info["username"] or (info["name"] and info["name"].strip() == "") or (info["username"] and info["username"].strip() == ""):
                                    try:
                                        # استفاده از تابع بهبود یافته get_ita_chat_info
                                        chat_info_from_api = await get_ita_chat_info(chat_id_str)
                                        if chat_info_from_api:
                                            # به‌روزرسانی دیتابیس با اطلاعات جدید
                                            await update_ita_chat_info_from_response(chat_id_str, chat_info_from_api)
                                            # دریافت اطلاعات به‌روزرسانی شده
                                            updated_chat = db_fetchone("SELECT name, username FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id_str,))
                                            if updated_chat:
                                                info["name"] = updated_chat['name'] or info["name"]
                                                info["username"] = updated_chat['username'] or info["username"]
                                    except Exception as e:
                                        logger.warning(f"[ITA] Failed to update chat info for {chat_id_str}: {e}")
                                
                                # تعداد اعضا از metrics
                                member_count = await get_ita_chat_member_count(chat_id_str)
                                info["members"] = member_count
                            else:
                                # اگر cid None است، اطلاعات پیش‌فرض برمی‌گردانیم
                                info["members"] = 1
                        else:
                            app_obj = telegram_app if pf == 'telegram' else bale_app
                        loop_obj = telegram_bot_loop if pf == 'telegram' else bale_bot_loop
                        if not app_obj or not loop_obj or cid is None: return info
                        fut_info = asyncio.run_coroutine_threadsafe(app_obj.bot.get_chat(cid), loop_obj)
                        loop_local = asyncio.get_running_loop()
                        chat_obj = await loop_local.run_in_executor(None, lambda: fut_info.result(timeout=10))
                        info["name"] = getattr(chat_obj, 'title', None) or getattr(chat_obj, 'first_name', None) or None
                        info["username"] = getattr(chat_obj, 'username', None)
                        chat_type = getattr(chat_obj, 'type', None)
                        if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                            fut_cnt = asyncio.run_coroutine_threadsafe(app_obj.bot.get_chat_member_count(cid), loop_obj)
                            member_count = await loop_local.run_in_executor(None, lambda: fut_cnt.result(timeout=10))
                            # اگر تعداد اعضا صفر است، آن را به یک تبدیل کن
                            if member_count == 0:
                                member_count = 1
                            info["members"] = member_count
                        elif chat_type == ChatType.PRIVATE:
                            # برای کاربران خصوصی، تعداد اعضا همیشه 1 است
                            info["members"] = 1
                    except Exception: pass
                    return info

                for pf in selected_platforms:
                    db_rows = db_fetchall("SELECT chat_id, chat_type, name, username, created_at FROM chats WHERE platform= ?", (pf,))
                    for r in db_rows:
                        cid_str = r['chat_id']
                        cid = int(cid_str) if str(cid_str).lstrip('-').isdigit() else None
                        name_db, user_db, created_at = r['name'], r['username'], r['created_at']
                        live = await fetch_live_info(pf, cid) if cid is not None else {"members": None, "name": None, "username": None}
                        name_final = live.get('name') or name_db or ''
                        username_final = live.get('username') or user_db or ''
                        link = ''
                        if username_final:
                            if pf == 'telegram':
                                link = f"https://t.me/{username_final}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/{username_final}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/{username_final}"
                        date_display = created_at or ''
                        if created_at and jdatetime:
                            try:
                                y, m, d = int(created_at[0:4]), int(created_at[5:7]), int(created_at[8:10])
                                hh, mm, ss = int(created_at[11:13]), int(created_at[14:16]), int(created_at[17:19])
                                jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                                date_display = jdt.strftime('%Y/%m/%d %H:%M:%S')
                            except Exception: pass
                        # اگر لینک خالی است، از شناسه چت استفاده کن
                        if not link and cid_str:
                            if pf == 'telegram':
                                link = f"https://t.me/c/{cid_str.replace('-100', '')}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/c/{cid_str}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/c/{cid_str}"
                        
                        # دریافت تگ‌های چت
                        chat_tags = get_chat_tags(cid_str, pf) or 'ندارد'
                        
                        # محاسبه تعداد اعضا - برای کاربران خصوصی مقدار 1 در نظر بگیر
                        member_count = live.get('members') or 0
                        if r['chat_type'] == 'private' and member_count == 0:
                            member_count = 1
                        
                        rows_all.append({
                            'پلتفرم': 'تلگرام' if pf == 'telegram' else ('بله' if pf == 'bale' else 'ایتا'),
                            'شناسه چت': cid_str, 'نوع چت': r['chat_type'], 'نام': name_final,
                            'نام‌کاربری': username_final or 'ندارد', 'لینک': link or 'ندارد', 
                            'تگ‌ها': chat_tags, 'تعداد اعضا': member_count,
                            'تاریخ ثبت': date_display, '_sort': created_at or ''
                        })
                if rows_all:
                    df_chats = pd.DataFrame(rows_all)
                    if '_sort' in df_chats.columns: df_chats = df_chats.sort_values(by=['_sort'], ascending=False)
                    df_chats = df_chats[['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تگ‌ها','تعداد اعضا','تاریخ ثبت']]
                else:
                    df_chats = pd.DataFrame(columns=['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تگ‌ها','تعداد اعضا','تاریخ ثبت'])

                # --- شیت ۲: گزارش ارسال‌ها ---
                df_broadcasts = pd.DataFrame()
                q_platforms = ' AND b.platform IN ({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else ''
                params = selected_platforms
                sql = f"""
                SELECT b.platform, b.batch_id, b.scope, b.content_preview, b.timestamp,
                       COUNT(s.message_id) as total_sent,
                       SUM(CASE WHEN c.chat_type = 'private' THEN 1 ELSE 0 END) as private_cnt,
                       SUM(CASE WHEN c.chat_type = 'group' THEN 1 ELSE 0 END) as group_cnt,
                       SUM(CASE WHEN c.chat_type = 'channel' THEN 1 ELSE 0 END) as channel_cnt
                FROM broadcast_batches b
                LEFT JOIN sent_messages s ON b.batch_id = s.batch_id
                LEFT JOIN chats c ON s.chat_id = c.chat_id AND b.platform = c.platform
                WHERE 1=1 {q_platforms}
                GROUP BY b.batch_id, b.platform, b.scope, b.content_preview, b.timestamp
                ORDER BY b.timestamp DESC
                """
                try:
                    rows_broadcasts = db_fetchall(sql, tuple(params))
                except Exception as e:
                    logger.error(f"Error fetching broadcast data: {e}")
                    rows_broadcasts = []
                broadcast_data = []
                if rows_broadcasts:
                    for r in rows_broadcasts:
                        tstamp = r['timestamp']
                        date_display = tstamp
                        if jdatetime and tstamp:
                            try:
                                y, m, d, hh, mm, ss = map(int, [tstamp[0:4], tstamp[5:7], tstamp[8:10], tstamp[11:13], tstamp[14:16], tstamp[17:19]])
                                jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                                date_display = jdt.strftime('%Y/%m/%d %H:%M')
                            except Exception: pass
                        platform_name = {
                            'telegram': 'تلگرام',
                            'bale': 'بله',
                            'ita': 'ایتا'
                        }.get(r['platform'], r['platform'])
                        broadcast_data.append({
                            'پلتفرم': platform_name,
                            'شناسه دسته': r['batch_id'], 'تاریخ': date_display, 'مقصدها': r['scope'] or 'ندارد',
                            'پیش‌نمایش محتوا': r['content_preview'] or 'ندارد', 'تعداد کل ارسال': r['total_sent'] or 0,
                            'کاربران': r['private_cnt'] or 0, 'گروه‌ها': r['group_cnt'] or 0, 'کانال‌ها': r['channel_cnt'] or 0,
                            '_sort': tstamp
                        })
                    df_broadcasts = pd.DataFrame(broadcast_data)
                    if '_sort' in df_broadcasts.columns: df_broadcasts = df_broadcasts.sort_values(by=['_sort'], ascending=False)
                    df_broadcasts = df_broadcasts[['پلتفرم','شناسه دسته','تاریخ','مقصدها','پیش‌نمایش محتوا','تعداد کل ارسال','کاربران','گروه‌ها','کانال‌ها']]
                else:
                    df_broadcasts = pd.DataFrame(columns=['پلتفرم','شناسه دسته','تاریخ','مقصدها','پیش‌نمایش محتوا','تعداد کل ارسال','کاربران','گروه‌ها','کانال‌ها'])

                # --- شیت ۳: آمار روزانه اعضا ---
                df_daily_pivot = pd.DataFrame()
                q_platforms_daily = ' AND m.platform IN ({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else ''
                params_daily = selected_platforms
                sql_daily = f"""
                SELECT m.platform, m.chat_id, m.date_key, m.members_count,
                       c.chat_type, c.name, c.username
                FROM chats_metrics m
                LEFT JOIN chats c ON c.chat_id=m.chat_id AND c.platform=m.platform
                WHERE 1=1 {q_platforms_daily} AND c.chat_type != 'private'
                """
                try:
                    rows_daily = db_fetchall(sql_daily, tuple(params_daily))
                except Exception as e:
                    logger.error(f"Error fetching daily data: {e}")
                    rows_daily = []
                daily_data = []
                if rows_daily:
                    for r in rows_daily:
                        pf = r['platform']
                        uname, nm = r['username'] or '', r['name'] or ''
                        if not (nm and uname):
                            # تبدیل chat_id به عدد فقط اگر ممکن باشد
                            cid = None
                            try:
                                cid = int(r['chat_id']) if str(r['chat_id']).lstrip('-').isdigit() else None
                            except (ValueError, TypeError):
                                cid = None
                            
                            live_info = await fetch_live_info(pf, cid)
                            nm = nm or live_info.get('name')
                            uname = uname or live_info.get('username')
                        link = ''
                        if uname:
                            if pf == 'telegram':
                                link = f"https://t.me/{uname}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/{uname}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/{uname}"
                        else:
                            # اگر username نداریم، از chat_id استفاده کن
                            if pf == 'telegram':
                                link = f"https://t.me/c/{r['chat_id'].replace('-100', '')}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/c/{r['chat_id']}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/c/{r['chat_id']}"
                        date_display = r['date_key']
                        if jdatetime: 
                            try:
                                y,m,d = map(int, r['date_key'].split('-'))
                                date_display = jdatetime.date.fromgregorian(year=y, month=m, day=d).strftime('%Y/%m/%d')
                            except Exception: pass
                        # دریافت تگ‌های چت
                        chat_tags = get_chat_tags(r['chat_id'], pf) or 'ندارد'
                        
                        daily_data.append({
                            'پلتفرم': 'تلگرام' if pf=='telegram' else ('بله' if pf=='bale' else 'ایتا'), 'شناسه چت': r['chat_id'], 'نوع چت': r['chat_type'],
                            'نام': nm or 'ندارد', 'نام‌کاربری': uname or 'ندارد', 'لینک': link or 'ندارد', 'تگ‌ها': chat_tags, 'تاریخ': date_display,
                            'تعداد اعضا': r['members_count'], '_date_key': r['date_key']
                        })
                    df_daily_raw = pd.DataFrame(daily_data)
                    if not df_daily_raw.empty:
                        # ابتدا اطلاعات چت‌ها را از دیتابیس دریافت کن
                        chat_info_map = {}
                        for pf in selected_platforms:
                            chat_rows = db_fetchall("SELECT chat_id, name, username FROM chats WHERE platform = ?", (pf,))
                            for chat_row in chat_rows:
                                chat_info_map[f"{pf}_{chat_row['chat_id']}"] = {
                                    'name': chat_row['name'] or 'ندارد',
                                    'username': chat_row['username'] or 'ندارد'
                                }
                        
                        # به‌روزرسانی اطلاعات چت‌ها در daily_data
                        for i, row in df_daily_raw.iterrows():
                            chat_key = f"{row['پلتفرم'].lower().replace('تلگرام', 'telegram').replace('بله', 'bale').replace('ایتا', 'ita')}_{row['شناسه چت']}"
                            if chat_key in chat_info_map:
                                df_daily_raw.at[i, 'نام'] = chat_info_map[chat_key]['name']
                                df_daily_raw.at[i, 'نام‌کاربری'] = chat_info_map[chat_key]['username']
                                
                                # ساخت لینک بر اساس username
                                pf = row['پلتفرم'].lower().replace('تلگرام', 'telegram').replace('بله', 'bale').replace('ایتا', 'ita')
                                username = chat_info_map[chat_key]['username']
                                if username and username != 'ندارد':
                                    if pf == 'telegram':
                                        df_daily_raw.at[i, 'لینک'] = f"https://t.me/{username}"
                                    elif pf == 'bale':
                                        df_daily_raw.at[i, 'لینک'] = f"https://ble.ir/{username}"
                                    elif pf == 'ita':
                                        df_daily_raw.at[i, 'لینک'] = f"https://eitaa.com/{username}"
                                else:
                                    # اگر username نداریم، از chat_id استفاده کن
                                    chat_id = row['شناسه چت']
                                    if pf == 'telegram':
                                        df_daily_raw.at[i, 'لینک'] = f"https://t.me/c/{chat_id.replace('-100', '')}"
                                    elif pf == 'bale':
                                        df_daily_raw.at[i, 'لینک'] = f"https://ble.ir/c/{chat_id}"
                                    elif pf == 'ita':
                                        df_daily_raw.at[i, 'لینک'] = f"https://eitaa.com/c/{chat_id}"
                        
                        idx_cols = ['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تگ‌ها']
                        pivot = df_daily_raw.pivot_table(index=idx_cols, columns='_date_key', values='تعداد اعضا', aggfunc='last')
                        pivot = pivot.reindex(sorted(pivot.columns, reverse=True), axis=1)
                        date_map = df_daily_raw.drop_duplicates('_date_key').set_index('_date_key')['تاریخ'].to_dict()
                        pivot.rename(columns=date_map, inplace=True)
                        df_daily_pivot = pivot.reset_index()
                else:
                    df_daily_pivot = pd.DataFrame(columns=['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک'])

                # --- شیت ۴: تحلیل رشد ---
                df_growth = pd.DataFrame()
                
                q_platforms_growth = '({})'.format(','.join('?'*len(selected_platforms))) if selected_platforms else '()'
                params_growth = selected_platforms

                # محاسبه تاریخ شروع و پایان برای تحلیل رشد (30 روز گذشته)
                from datetime import datetime as dt, timedelta
                end_date = dt.now().strftime('%Y-%m-%d')
                start_date = (dt.now() - timedelta(days=30)).strftime('%Y-%m-%d')
                
                sql_growth = f"""
                WITH rng AS (
                  SELECT chat_id, platform,
                         MIN(date_key) AS d_start,
                         MAX(date_key) AS d_end
                  FROM chats_metrics
                  WHERE date_key BETWEEN ? AND ? AND platform IN {q_platforms_growth}
                  GROUP BY chat_id, platform
                ),
                s AS (
                  SELECT m.chat_id, m.platform, m.members_count AS start_members
                  FROM chats_metrics m
                  JOIN rng ON rng.chat_id=m.chat_id AND rng.platform=m.platform AND rng.d_start=m.date_key
                ),
                e AS (
                  SELECT m.chat_id, m.platform, m.members_count AS end_members
                  FROM chats_metrics m
                  JOIN rng ON rng.chat_id=m.chat_id AND rng.platform=m.platform AND rng.d_end=m.date_key
                )
                SELECT r.platform, r.chat_id, r.d_start, r.d_end,
                       s.start_members, e.end_members,
                       c.chat_type, c.name, c.username
                FROM rng r
                LEFT JOIN s ON s.chat_id=r.chat_id AND s.platform=r.platform
                LEFT JOIN e ON e.chat_id=r.chat_id AND e.platform=r.platform
                LEFT JOIN chats c ON c.chat_id=r.chat_id AND c.platform=r.platform
                WHERE c.is_active = 1 AND c.chat_type != 'private'
                """
                # اضافه کردن تاریخ‌ها به پارامترها
                params_growth_with_dates = [start_date, end_date] + params_growth
                try:
                    rows_growth = db_fetchall(sql_growth, tuple(params_growth_with_dates))
                except Exception as e:
                    logger.error(f"Error fetching growth data: {e}")
                    rows_growth = []
                growth_data = []
                if rows_growth:
                    for r in rows_growth:
                        pf = r['platform']
                        uname, nm = r['username'] or '', r['name'] or ''
                        if not (nm and uname):
                            # تبدیل chat_id به عدد فقط اگر ممکن باشد
                            cid = None
                            try:
                                cid = int(r['chat_id']) if str(r['chat_id']).lstrip('-').isdigit() else None
                            except (ValueError, TypeError):
                                cid = None
                            
                            live_info = await fetch_live_info(pf, cid)
                            nm = nm or live_info.get('name')
                            uname = uname or live_info.get('username')
                        link = ''
                        if uname:
                            if pf == 'telegram':
                                link = f"https://t.me/{uname}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/{uname}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/{uname}"
                        else:
                            # اگر username نداریم، از chat_id استفاده کن
                            if pf == 'telegram':
                                link = f"https://t.me/c/{r['chat_id'].replace('-100', '')}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/c/{r['chat_id']}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/c/{r['chat_id']}"
                        start_m, end_m = r['start_members'] or 0, r['end_members'] or 0
                        growth = end_m - start_m
                        growth_pct = (growth / start_m * 100.0) if start_m > 0 else (100.0 if end_m > 0 else 0.0)
                        
                        # محاسبه تعداد روزها بین تاریخ شروع و پایان
                        try:
                            start_date = dt.strptime(r['d_start'], '%Y-%m-%d')
                            end_date = dt.strptime(r['d_end'], '%Y-%m-%d')
                            days = (end_date - start_date).days + 1  # +1 برای شامل کردن روز آخر
                        except Exception:
                            days = 1  # در صورت خطا، حداقل 1 روز در نظر بگیر
                        
                        avg_daily = growth / float(days) if days > 0 else 0
                        start_disp, end_disp = r['d_start'], r['d_end']
                        if jdatetime:
                            try:
                                y,m,d = map(int, r['d_start'].split('-'))
                                start_disp = jdatetime.date.fromgregorian(year=y, month=m, day=d).strftime('%Y/%m/%d')
                                y,m,d = map(int, r['d_end'].split('-'))
                                end_disp = jdatetime.date.fromgregorian(year=y, month=m, day=d).strftime('%Y/%m/%d')
                            except Exception: pass
                        # دریافت تگ‌های چت
                        chat_tags = get_chat_tags(r['chat_id'], pf) or 'ندارد'
                        
                        growth_data.append({
                            'پلتفرم': 'تلگرام' if pf=='telegram' else ('بله' if pf=='bale' else 'ایتا'), 'شناسه چت': r['chat_id'], 'نوع چت': r['chat_type'],
                            'نام': nm or 'ندارد', 'نام‌کاربری': uname or 'ندارد', 'لینک': link or 'ندارد', 'تگ‌ها': chat_tags, 'اعضا در شروع': start_m, 'اعضا در پایان': end_m,
                            'رشد خالص': growth, 'رشد درصدی': round(growth_pct, 2), 'میانگین رشد روزانه': round(avg_daily, 2),
                            'تاریخ شروع': start_disp, 'تاریخ پایان': end_disp
                        })
                    df_growth = pd.DataFrame(growth_data)
                    if not df_growth.empty:
                        # به‌روزرسانی اطلاعات چت‌ها در growth_data
                        chat_info_map = {}
                        for pf in selected_platforms:
                            chat_rows = db_fetchall("SELECT chat_id, name, username FROM chats WHERE platform = ?", (pf,))
                            for chat_row in chat_rows:
                                chat_info_map[f"{pf}_{chat_row['chat_id']}"] = {
                                    'name': chat_row['name'] or 'ندارد',
                                    'username': chat_row['username'] or 'ندارد'
                                }
                        
                        # به‌روزرسانی اطلاعات چت‌ها در df_growth
                        for i, row in df_growth.iterrows():
                            chat_key = f"{row['پلتفرم'].lower().replace('تلگرام', 'telegram').replace('بله', 'bale').replace('ایتا', 'ita')}_{row['شناسه چت']}"
                            if chat_key in chat_info_map:
                                df_growth.at[i, 'نام'] = chat_info_map[chat_key]['name']
                                df_growth.at[i, 'نام‌کاربری'] = chat_info_map[chat_key]['username']
                                
                                # ساخت لینک بر اساس username
                                pf = row['پلتفرم'].lower().replace('تلگرام', 'telegram').replace('بله', 'bale').replace('ایتا', 'ita')
                                username = chat_info_map[chat_key]['username']
                                if username and username != 'ندارد':
                                    if pf == 'telegram':
                                        df_growth.at[i, 'لینک'] = f"https://t.me/{username}"
                                    elif pf == 'bale':
                                        df_growth.at[i, 'لینک'] = f"https://ble.ir/{username}"
                                    elif pf == 'ita':
                                        df_growth.at[i, 'لینک'] = f"https://eitaa.com/{username}"
                                else:
                                    # اگر username نداریم، از chat_id استفاده کن
                                    chat_id = row['شناسه چت']
                                    if pf == 'telegram':
                                        df_growth.at[i, 'لینک'] = f"https://t.me/c/{chat_id.replace('-100', '')}"
                                    elif pf == 'bale':
                                        df_growth.at[i, 'لینک'] = f"https://ble.ir/c/{chat_id}"
                                    elif pf == 'ita':
                                        df_growth.at[i, 'لینک'] = f"https://eitaa.com/c/{chat_id}"
                        
                        df_growth = df_growth.sort_values(by=['رشد خالص'], ascending=False)
                else:
                    df_growth = pd.DataFrame(columns=['پلتفرم', 'شناسه چت', 'نوع چت', 'نام', 'نام‌کاربری', 'لینک', 'اعضا در شروع', 'اعضا در پایان', 'رشد خالص', 'رشد درصدی', 'میانگین رشد روزانه', 'تاریخ شروع', 'تاریخ پایان'])

                # --- نوشتن فایل نهایی ---
                file_path = None
                try:
                    ts = int(time.time())
                    # استفاده از مسیر مطلق برای اطمینان
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    file_path = os.path.join(current_dir, f"comprehensive_report_{'_'.join(selected_platforms)}_{ts}.xlsx")
                    
                    logger.info(f"Creating Excel file at: {file_path}")
                    
                    # --- شیت ۵: آمار ربات‌ها ---
                    df_bot_stats = generate_bot_statistics_sheet(selected_platforms)
                    
                    # --- شیت ۶: آمار روزانه ربات‌ها ---
                    df_daily_bot_stats = generate_daily_bot_statistics_sheet(selected_platforms)
                    
                    # ساخت فایل Excel
                    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                        df_chats.to_excel(writer, sheet_name="لیست چت‌ها", index=False)
                        df_broadcasts.to_excel(writer, sheet_name="گزارش ارسال انبوه", index=False)
                        df_daily_pivot.to_excel(writer, sheet_name="آمار روزانه اعضا", index=False)
                        df_growth.to_excel(writer, sheet_name="تحلیل رشد", index=False)
                        df_bot_stats.to_excel(writer, sheet_name="آمار ربات‌ها", index=False)
                        df_daily_bot_stats.to_excel(writer, sheet_name="آمار روزانه ربات‌ها", index=False)
                    
                    logger.info(f"Excel file created successfully: {file_path}")

                    # بررسی وجود فایل قبل از ارسال
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        logger.info(f"File exists with size: {file_size} bytes")

                    await query.edit_message_text("✅ گزارش مختصر آماده شد. در حال ارسال فایل...")
                    
                    # ارسال فایل با timeout بیشتر
                    try:
                        with open(file_path, 'rb') as file:
                            await asyncio.wait_for(
                                context.bot.send_document(
                                    chat_id=query.from_user.id, 
                                    document=file, 
                                    caption="گزارش مختصر عملکرد"
                                ),
                                timeout=120  # 2 دقیقه timeout
                            )
                    except asyncio.TimeoutError:
                        logger.error("Timeout while sending comprehensive report file")
                        await query.edit_message_text("❌ خطا در ارسال فایل: timeout. لطفاً دوباره تلاش کنید.")
                        return
                    except Exception as e:
                        logger.error(f"Error sending comprehensive report file: {e}")
                        await query.edit_message_text(f"❌ خطا در ارسال فایل: {str(e)}")
                        return
                    
                    # ارسال منوی اصلی
                    menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
                    await context.bot.send_message(query.from_user.id, "منوی اصلی:", reply_markup=menu_builder())
                    
                    logger.info("Excel file sent successfully")
                    # حذف else اضافی و انتقال شرط به بالا
                    if not os.path.exists(file_path):
                        logger.error(f"File was not created: {file_path}")
                        await query.edit_message_text("❌ فایل Excel ساخته نشد. لطفاً دوباره تلاش کنید.")
                        return
                except Exception as e:
                    logger.error(f"Error in comprehensive report generation: {e}", exc_info=True)
                    await query.edit_message_text(f"❌ خطا در ساخت/ارسال گزارش جامع: {e}")
                finally:
                    # پاک کردن فایل بعد از ارسال موفق
                    try:
                        if file_path and os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Temporary file removed: {file_path}")
                    except Exception as e:
                        logger.warning(f"Could not remove temporary file {file_path}: {e}")


            async def export_compose_and_send(selected_platforms: list):
                # ساخت گزارش تجمیعی برای یک یا هر دو پلتفرم بدون نیاز به متدهای خصوصی PTB
                rows_all = []
                # کمکی: دریافت اطلاعات زنده چت (نام/یوزرنیم/تعداد اعضا) از لوپ همان پلتفرم به شکل ایمن
                async def fetch_live_info(pf: str, cid) -> dict:
                    info = {"members": None, "name": None, "username": None}
                    try:
                        if pf == 'ita':
                            # برای ایتا از دیتابیس اطلاعات را می‌گیریم
                            chat_id_str = str(cid) if cid is not None else None
                            if chat_id_str:
                                chat_info = db_fetchone("SELECT name, username FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id_str,))
                                if chat_info:
                                    info["name"] = chat_info['name']
                                    info["username"] = chat_info['username']
                                
                                # اگر نام موجود نیست یا خالی است، سعی می‌کنیم آن را به‌روزرسانی کنیم
                                if not info["name"] or not info["username"] or (info["name"] and info["name"].strip() == "") or (info["username"] and info["username"].strip() == ""):
                                    try:
                                        # استفاده از تابع بهبود یافته get_ita_chat_info
                                        chat_info_from_api = await get_ita_chat_info(chat_id_str)
                                        if chat_info_from_api:
                                            # به‌روزرسانی دیتابیس با اطلاعات جدید
                                            await update_ita_chat_info_from_response(chat_id_str, chat_info_from_api)
                                            # دریافت اطلاعات به‌روزرسانی شده
                                            updated_chat = db_fetchone("SELECT name, username FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id_str,))
                                            if updated_chat:
                                                info["name"] = updated_chat['name'] or info["name"]
                                                info["username"] = updated_chat['username'] or info["username"]
                                    except Exception as e:
                                        logger.warning(f"[ITA] Failed to update chat info for {chat_id_str}: {e}")
                                
                                # تعداد اعضا از metrics
                                member_count = await get_ita_chat_member_count(chat_id_str)
                                info["members"] = member_count
                            else:
                                # اگر cid None است، اطلاعات پیش‌فرض برمی‌گردانیم
                                info["members"] = 1
                        else:
                            app_obj = telegram_app if pf == 'telegram' else bale_app
                        loop_obj = telegram_bot_loop if pf == 'telegram' else bale_bot_loop
                        if not app_obj or not loop_obj or cid is None:
                            return info
                        # get_chat
                        fut_info = asyncio.run_coroutine_threadsafe(app_obj.bot.get_chat(cid), loop_obj)
                        loop_local = asyncio.get_running_loop()
                        chat_obj = await loop_local.run_in_executor(None, lambda: fut_info.result(timeout=10))
                        info["name"] = getattr(chat_obj, 'title', None) or getattr(chat_obj, 'first_name', None) or None
                        info["username"] = getattr(chat_obj, 'username', None)
                        # تلاش برای شمارش اعضا برای گروه/سوپرگروه/کانال
                        if getattr(chat_obj, 'type', None) in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                            fut_cnt = asyncio.run_coroutine_threadsafe(app_obj.bot.get_chat_member_count(cid), loop_obj)
                            member_count = await loop_local.run_in_executor(None, lambda: fut_cnt.result(timeout=10))
                            # اگر تعداد اعضا صفر است، آن را به یک تبدیل کن
                            if member_count == 0:
                                member_count = 1
                            info["members"] = member_count
                    except Exception:
                        pass
                    return info
                for pf in selected_platforms:
                    db_rows = db_fetchall("SELECT chat_id, chat_type, name, username, created_at FROM chats WHERE platform= ?", (pf,))
                    for r in db_rows:
                        cid_str = r['chat_id']
                        cid = int(cid_str) if str(cid_str).lstrip('-').isdigit() else None
                        name_db = r['name'] if 'name' in r.keys() else None
                        user_db = r['username'] if 'username' in r.keys() else None
                        created_at = r['created_at'] if 'created_at' in r.keys() else None
                        # تلاش برای دریافت اطلاعات زنده
                        live = await fetch_live_info(pf, cid) if cid is not None else {"members": None, "name": None, "username": None}
                        name_final = live.get('name') or name_db or ''
                        username_final = live.get('username') or user_db or ''
                        if username_final and isinstance(username_final, bytes): username_final = username_final.decode('utf-8', errors='ignore')
                        # ساخت لینک نمایشی
                        link = ''
                        if username_final:
                            if pf == 'telegram':
                                link = f"https://t.me/{username_final}"
                            elif pf == 'bale':
                                link = f"https://ble.ir/{username_final}"
                            elif pf == 'ita':
                                link = f"https://eitaa.com/{username_final}"
                        # تبدیل تاریخ به نمایش واحد فارسی
                        date_display = created_at or ''
                        if created_at and jdatetime:
                            try:
                                y, m, d = int(created_at[0:4]), int(created_at[5:7]), int(created_at[8:10])
                                hh, mm, ss = int(created_at[11:13]), int(created_at[14:16]), int(created_at[17:19])
                                jdt = jdatetime.datetime.fromgregorian(year=y, month=m, day=d, hour=hh, minute=mm, second=ss)
                                date_display = jdt.strftime('%Y/%m/%d %H:%M:%S')
                            except Exception:
                                date_display = created_at
                        # محاسبه مقدار خام برای سورت
                        sort_raw = created_at or ''
                        rows_all.append({
                            'پلتفرم': 'تلگرام' if pf == 'telegram' else ('بله' if pf == 'bale' else 'ایتا'),
                            'شناسه چت': cid_str,
                            'نوع چت': r['chat_type'],
                            'نام': name_final,
                            'نام‌کاربری': username_final,
                            'لینک': link,
                            'تعداد اعضا': live.get('members'),
                            'تاریخ ثبت': date_display,
                            '_sort': sort_raw
                        })
                if not rows_all:
                    await query.edit_message_text("هیچ چتی برای ساخت گزارش یافت نشد.")
                    return
                # ساخت DataFrame و فایل اکسل موقت
                try:
                    df = pd.DataFrame(rows_all)
                    # مرتب‌سازی و انتخاب ستون‌ها با عناوین فارسی
                    if '_sort' in df.columns:
                        df = df.sort_values(by=['_sort'], ascending=False)
                    cols = ['پلتفرم','شناسه چت','نوع چت','نام','نام‌کاربری','لینک','تعداد اعضا','تاریخ ثبت']
                    df = df[cols]
                    ts = int(time.time())
                    file_path = os.path.join(os.getcwd(), f"chats_report_{'both' if len(selected_platforms)>1 else selected_platforms[0]}_{ts}.xlsx")
                    df.to_excel(file_path, index=False, engine='openpyxl')
                    await query.edit_message_text("✅ گزارش آماده شد. در حال ارسال فایل...")
                    await context.bot.send_document(chat_id=query.from_user.id, document=open(file_path, 'rb'), caption="گزارش چت‌ها")
                    # منوی اصلی پس از ارسال فایل
                    menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
                    await context.bot.send_message(query.from_user.id, "منوی اصلی:", reply_markup=menu_builder())
                except Exception as e:
                    await query.edit_message_text(f"❌ خطا در ساخت/ارسال گزارش: {e}")
                finally:
                    try:
                        if 'file_path' in locals() and os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception:
                        pass

            # اجرای گزارش بر اساس انتخاب کاربر
            if choice == 'telegram':
                await generate_comprehensive_report(['telegram'])
            elif choice == 'bale':
                await generate_comprehensive_report(['bale'])
            elif choice == 'ita':
                await generate_comprehensive_report(['ita'])
            elif choice == 'both':
                await generate_comprehensive_report(['telegram', 'bale'])
            elif choice == 'all':
                await generate_comprehensive_report(['telegram', 'bale', 'ita'])
            else:
                await generate_comprehensive_report(['telegram', 'bale'])

        elif data == "menu_about":
            help_text = f"💡 راهنمای جامع ربات {platform}\n\n"
            help_text += "📋 دستورات اصلی:\n"
            help_text += "• /start - نمایش منوی اصلی\n"
            help_text += "• /sync - ثبت دستی گروه/کانال\n"
            help_text += "• /export - دریافت خروجی اکسل\n\n"
            if platform == 'telegram':
                help_text += "ℹ️ نکته: افزودن ادمین در تلگرام فقط در گروه‌هایی که ربات ادمین است ممکن است."
            else:
                help_text += "ℹ️ نکته: در بله، افزودن ادمین از طریق ربات در حال حاضر پشتیبانی نمی‌شود."
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await query.edit_message_text(help_text, reply_markup=menu_builder())
        
        elif data == "menu_admin_panel":
            if platform == 'telegram':
                admin_menu = InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن ادمین جدید به چت‌ها", callback_data="admin_add_start")],[InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu_main")]])
                await query.edit_message_text("👑 پنل مدیریت ادمین تلگرام", reply_markup=admin_menu)
            else:
                await query.edit_message_text(escape_markdown_v2("👑 پنل مدیریت ادمین بله\n\n*نکته:* قابلیت افزودن ادمین (promote_chat_member) از طریق ربات در بله فعلاً پشتیبانی نمی‌شود."), reply_markup=build_bale_main_menu(), parse_mode=ParseMode.MARKDOWN_V2)
        
        elif data == "admin_add_start":
            if platform == 'telegram':
                current_user_state[key] = {'status': 'awaiting_admin_id'}
                prompt_msg = await query.edit_message_text("لطفا شناسه عددی کاربر را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 لغو", callback_data="menu_main")]]))
                current_user_state[key]['prompt_msg_id'] = prompt_msg.message_id
            else:
                await query.edit_message_text(escape_markdown_v2("❌ این قابلیت برای بله پشتیبانی نمی‌شود."), reply_markup=build_bale_main_menu(), parse_mode=ParseMode.MARKDOWN_V2)
        
        elif data == "menu_broadcast":
            context.user_data['selected_scopes'] = []
            # مرحله انتخاب پلتفرم را اضافه می‌کنیم
            await query.edit_message_text("1/4: پلتفرم مقصد را انتخاب کنید:", reply_markup=build_platform_select_keyboard())
            return
        elif data.startswith("select_platform_"):
            # ذخیره انتخاب پلتفرم در state
            platform_choice = data.split("_")[-1]
            current_user_state[key] = current_user_state.get(key, {})
            current_user_state[key]['target_platform'] = platform_choice
            # بعد از انتخاب پلتفرم، به انتخاب scope برو
            keyboard_builder = generate_scope_keyboard_telegram if platform == 'telegram' else generate_scope_keyboard_bale
            await query.edit_message_text("2/4: مقصدها را انتخاب کنید:", reply_markup=keyboard_builder([]))
            return
        elif data == "select_all_scopes":
            selected = ["private", "group", "channel"]
            context.user_data['selected_scopes'] = selected
            keyboard_builder = generate_scope_keyboard_telegram if platform == 'telegram' else generate_scope_keyboard_bale
            await query.edit_message_text("2/4: مقصدها را انتخاب کنید:", reply_markup=keyboard_builder(selected))
            return
        elif data.startswith("togglescope_"):
            scope = data.split("_", 1)[1]
            selected = context.user_data.get('selected_scopes', [])
            if scope in selected: selected.remove(scope)
            else: selected.append(scope)
            context.user_data['selected_scopes'] = selected
            keyboard_builder = generate_scope_keyboard_telegram if platform == 'telegram' else generate_scope_keyboard_bale
            await query.edit_message_text("2/4: مقصدها را انتخاب کنید:", reply_markup=keyboard_builder(selected))
            return
        elif data == "confirm_scope":
            selected_scopes = context.user_data.get('selected_scopes', [])
            if not selected_scopes: await query.answer("لطفا حداقل یک مقصد انتخاب کنید!", show_alert=True); return
            current_user_state[key] = current_user_state.get(key, {})
            current_user_state[key]['status'] = 'awaiting_content'
            current_user_state[key]['scopes'] = selected_scopes
            scope_names = ", ".join([CHAT_TYPE_DISPLAY_NAMES.get(s, s) for s in selected_scopes])
            prompt_msg = await query.edit_message_text(f"3/4: مقصدها: *{escape_markdown_v2(scope_names)}*\n\nاکنون محتوا را ارسال کنید:", parse_mode=ParseMode.MARKDOWN_V2)
            current_user_state[key]['prompt_msg_id'] = prompt_msg.message_id
            return
        
        elif data == "confirm_broadcast_proceed":
            state = current_user_state.get(key, {})
            info = state.get('broadcast_info', {})
            logger.info(f"[{platform}] Debug - key: {key}, state keys: {list(state.keys())}, info keys: {list(info.keys()) if info else 'None'}")
            if not info or not any([info.get('text'), info.get('image_path'), info.get('video_path'), info.get('document_path')]):
                menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
                await query.edit_message_text("❌ خطای داخلی: محتوای پیام یافت نشد.", reply_markup=menu_builder()); return
            
            # نمایش منوی زمان‌بندی
            preview = info.get('preview_content', info.get('content_preview', '-'))
            if preview and len(preview) > 100:
                preview = preview[:97] + "..."
            
            scope_names = ", ".join([CHAT_TYPE_DISPLAY_NAMES.get(s, s) for s in info.get('scopes', [])])
            scheduling_text = f"4/4: زمان ارسال را انتخاب کنید:\n\n📝 محتوا: {preview}\n🎯 مقصد: {scope_names}\n\nزمان ارسال را انتخاب کنید:"
            
            await query.edit_message_text(scheduling_text, reply_markup=build_scheduling_keyboard())
            return
        
        # منطق زمان‌بندی ارسال
        elif data == "schedule_now":
            await execute_scheduled_broadcast(context, platform, user_id, 0)  # 0 = همین الان
            return
            
        elif data == "schedule_1h":
            await execute_scheduled_broadcast(context, platform, user_id, 3600)  # 1 ساعت
            return
            
        elif data == "schedule_2h":
            await execute_scheduled_broadcast(context, platform, user_id, 7200)  # 2 ساعت
            return
            
        elif data == "schedule_1d":
            await execute_scheduled_broadcast(context, platform, user_id, 86400)  # 1 روز
            return
            
        elif data == "schedule_custom":
            # درخواست تاریخ و زمان شمسی
            current_user_state[key] = current_user_state.get(key, {})
            current_user_state[key]['status'] = 'awaiting_custom_datetime'
            # ایجاد پیام با زمان فعلی
            iran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(iran_tz)
            current_persian_time = format_persian_datetime(now)
            current_time_str = current_persian_time.replace('/', '/').replace(' ', ' ')
            
            await query.edit_message_text(f"📅 لطفاً تاریخ و زمان شمسی را وارد کنید:\n\nفرمت: {current_time_str}\n\nمثال: {current_time_str}")
            return
        
        elif data == "menu_scheduling_queue":
            await query.edit_message_text("📅 صف انتشار:", reply_markup=build_scheduling_queue_keyboard())
            return
        
        elif data.startswith("queue_"):
            await show_scheduling_queue(context, platform, user_id, data)
            return
        
        elif data.startswith("cancel_scheduled_"):
            broadcast_id = int(data.split("_")[-1])
            cancel_scheduled_broadcast(broadcast_id)
            await query.edit_message_text(f"✅ پست {broadcast_id} لغو شد.")
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await context.bot.send_message(user_id, "چه کاری می‌خواهید انجام دهید؟", reply_markup=menu_builder())
            return
        
        elif data in ["broadcast_cancel", "menu_main"]:
            current_user_state.pop(key, None)
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await query.edit_message_text("عملیات لغو شد.", reply_markup=menu_builder())

    except BadRequest as e:
        if "Message is not modified" not in str(e): logger.error(f"[{platform} Callback] BadRequest: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"[{platform} Callback] Error processing callback '{data}': {e}", exc_info=True)

async def message_handler_base(update: TelegramUpdate, context: TelegramContextTypes.DEFAULT_TYPE, platform: str, owner_id: int):
    user, chat, msg = update.effective_user, update.effective_chat, update.message

    if not msg: 
        logger.debug(f"[{platform}] Received an update without a message object. Skipping.")
        return

    current_user_state = user_state if platform == 'telegram' else bale_user_state
    key = f"{platform}:{user.id}" if user else None

    # Handling bot being added to group (new_chat_members)
    if msg.new_chat_members:
        bot_info = await context.bot.get_me()
        if any(member.id == bot_info.id for member in msg.new_chat_members):
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
            chat_username = getattr(chat, 'username', None)
            register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
            await safe_reply_text(msg, f"✅ ربات با موفقیت به گروه {platform} اضافه و در سیستم ثبت شد.")
            
            # ارسال اطلاعیه به ادمین برای اضافه شدن ربات به گروه/کانال
            chat_type_name = "گروه" if chat.type in ['group', 'supergroup'] else "کانال"
            notification_msg = f"📢 ربات به {chat_type_name} جدید اضافه شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}\n🔗 یوزرنیم: @{chat_username}" if chat_username else f"📢 ربات به {chat_type_name} جدید اضافه شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}"
            await send_admin_notification(notification_msg, platform)
            
            logger.info(f"[{platform}] Bot added to group {chat.id} and registered. API chat type: {chat.type}")
            return
    
    # ثبت خودکار چت‌های گروه/کانال در هر پیام
    if chat and chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
        chat_username = getattr(chat, 'username', None)
        
        # ثبت چت با لاگ‌گیری بهتر
        try:
            success = register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
            if success:
                logger.info(f"[{platform}] Successfully registered chat {chat.id} ({chat.type}) - Name: {chat_name}, Username: {chat_username}")
            else:
                logger.error(f"[{platform}] Failed to register chat {chat.id} ({chat.type})")
        except Exception as e:
            logger.error(f"[{platform}] Error registering chat {chat.id}: {e}")
        
        # برای کانال‌ها، بررسی اضافی انجام دهیم
        if chat.type == ChatType.CHANNEL:
            logger.info(f"[{platform}] Channel message received - ID: {chat.id}, Name: {chat_name}")
            # بررسی اینکه آیا ربات در کانال ادمین است یا نه
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status in ['administrator', 'creator']:
                    logger.info(f"[{platform}] Bot is admin in channel {chat.id}")
                else:
                    logger.warning(f"[{platform}] Bot is not admin in channel {chat.id} - status: {bot_member.status}")
            except Exception as e:
                logger.warning(f"[{platform}] Could not check bot status in channel {chat.id}: {e}")
    
    # نظارت بر تغییرات کانال‌ها (برای کانال‌هایی که ربات ادمین است)
    if chat and chat.type == ChatType.CHANNEL:
        try:
            # بررسی اینکه آیا ربات در کانال ادمین است
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status in ['administrator', 'creator']:
                # بررسی اینکه آیا کانال در دیتابیس موجود است
                existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = ?", (str(chat.id), platform))
                
                if not existing_chat:
                    # کانال در دیتابیس موجود نیست، آن را ثبت کن
                    chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
                    chat_username = getattr(chat, 'username', None)
                    
                    success = register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
                    if success:
                        logger.info(f"[{platform}] Auto-registered channel {chat.id} - Name: {chat_name}, Username: {chat_username}")
                        
                        # ارسال اطلاعیه به ادمین
                        notification_msg = f"📢 کانال جدید به صورت خودکار ثبت شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}\n🔗 یوزرنیم: @{chat_username}" if chat_username else f"📢 کانال جدید به صورت خودکار ثبت شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}"
                        await send_admin_notification(notification_msg, platform)
                    else:
                        logger.error(f"[{platform}] Failed to auto-register channel {chat.id}")
                else:
                    # کانال در دیتابیس موجود است، اطلاعات آن را به‌روزرسانی کن
                    chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
                    chat_username = getattr(chat, 'username', None)
                    
                    success = register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
                    if success:
                        logger.info(f"[{platform}] Updated channel info {chat.id} - Name: {chat_name}, Username: {chat_username}")
        except Exception as e:
            logger.warning(f"[{platform}] Error monitoring channel {chat.id}: {e}")
    
    # نظارت دوره‌ای بر کانال‌های تلگرام (هر 5 دقیقه)
    # تفاوت بین بله و تلگرام: بله پیام‌های کانال را دریافت می‌کند، تلگرام نه
    if platform == 'telegram' and chat and chat.type == ChatType.CHANNEL:
        try:
            # بررسی اینکه آیا ربات در کانال ادمین است
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status in ['administrator', 'creator']:
                # بررسی اینکه آیا کانال در دیتابیس موجود است
                existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = ?", (str(chat.id), platform))
                
                if not existing_chat:
                    # کانال در دیتابیس موجود نیست، آن را ثبت کن
                    chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or ''
                    chat_username = getattr(chat, 'username', None)
                    
                    success = register_chat(str(chat.id), chat.type, platform, name=chat_name, username=chat_username)
                    if success:
                        logger.info(f"[{platform}] Periodic check - Auto-registered channel {chat.id} - Name: {chat_name}, Username: {chat_username}")
                        
                        # ارسال اطلاعیه به ادمین
                        notification_msg = f"📢 کانال جدید در نظارت دوره‌ای ثبت شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}\n🔗 یوزرنیم: @{chat_username}" if chat_username else f"📢 کانال جدید در نظارت دوره‌ای ثبت شد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {chat.id}\n📝 نام: {chat_name}"
                        await send_admin_notification(notification_msg, platform)
                    else:
                        logger.error(f"[{platform}] Periodic check - Failed to auto-register channel {chat.id}")
        except Exception as e:
            logger.warning(f"[{platform}] Error in periodic channel monitoring {chat.id}: {e}")

    # Admin message handling (private chat)
    if user and chat and chat.type == ChatType.PRIVATE and user.id == owner_id:
        
        # Delete previous prompt message if exists
        if key and current_user_state.get(key) and current_user_state[key].get('prompt_msg_id'):
            try: await context.bot.delete_message(user.id, current_user_state[key]['prompt_msg_id'])
            except Exception: pass

        state = current_user_state.get(key)
        
        # Admin ID input for promotion (Telegram only)
        if state and state.get('status') == 'awaiting_admin_id':
            if platform == 'telegram':
                if not msg.text or not msg.text.isdigit():
                    await safe_reply_text(msg, "❌ شناسه نامعتبر. فقط عدد ارسال کنید.", reply_markup=build_telegram_main_menu()); return
                target_user_id = int(msg.text)
                await msg.delete()
                current_user_state.pop(key, None)
                await context.bot.send_message(user.id, f"⏳ درخواست افزودن ادمین برای `{target_user_id}` ثبت شد.", parse_mode=ParseMode.MARKDOWN_V2)
                asyncio.create_task(promote_user_in_telegram_chats_async(user.id, target_user_id, context))
                return
            else: # Admin promotion not supported for Bale
                await safe_reply_text(msg, escape_markdown_v2("❌ این قابلیت برای بله پشتیبانی نمی‌شود\\."), reply_markup=build_bale_main_menu(), parse_mode=ParseMode.MARKDOWN_V2)
                current_user_state.pop(key, None)
                return

        # Content input for broadcast
        if state and state.get('status') == 'awaiting_content':
            content_text = msg.text or msg.caption
            content_image_id = msg.photo[-1].file_id if msg.photo else None
            content_video_id = msg.video.file_id if msg.video else None
            content_document_id = msg.document.file_id if msg.document else None
            content_audio_id = msg.audio.file_id if msg.audio else None
            
            # لاگ‌گذاری برای دیباگ
            logger.info(f"[{platform}] Content analysis - text: {bool(content_text)}, photo: {bool(content_image_id)}, video: {bool(content_video_id)}, document: {bool(content_document_id)}, audio: {bool(content_audio_id)}")
            if msg.document:
                logger.info(f"[{platform}] Document details - file_id: {msg.document.file_id}, file_name: {msg.document.file_name}, mime_type: {getattr(msg.document, 'mime_type', 'unknown')}")
            if msg.audio:
                logger.info(f"[{platform}] Audio details - file_id: {msg.audio.file_id}, file_name: {getattr(msg.audio, 'file_name', 'unknown')}, mime_type: {getattr(msg.audio, 'mime_type', 'unknown')}")
            if content_text:
                logger.info(f"[{platform}] Content text: {content_text[:100]}...")
            
            # Get file content if media exists
            file_content = None
            file_type = None
            file_name = None
            
            if content_image_id:
                file_type = 'photo'
                file_content = await get_file_content(platform, content_image_id)
                file_name = 'image.jpg'
            elif content_video_id:
                file_type = 'video'
                file_content = await get_file_content(platform, content_video_id)
                file_name = 'video.mp4'
            elif content_document_id:
                file_type = 'document'
                file_content = await get_file_content(platform, content_document_id)
                # بهبود تشخیص نام فایل برای فایل‌های document
                if msg.document.file_name:
                    file_name = msg.document.file_name
                else:
                    # تشخیص نوع فایل از محتوا
                    detected_ext = detect_file_extension_from_content(file_content.getvalue()) if file_content else '.bin'
                    file_name = f"document{detected_ext}"
                    logger.info(f"[{platform}] Detected file extension: {detected_ext} for document without filename")
            elif content_audio_id:
                file_type = 'document'  # Treat audio as document for sending
                file_content = await get_file_content(platform, content_audio_id)
                # بهبود تشخیص نام فایل برای فایل‌های audio
                if hasattr(msg.audio, 'file_name') and msg.audio.file_name:
                    file_name = msg.audio.file_name
                else:
                    # تشخیص نوع فایل از محتوا
                    detected_ext = detect_file_extension_from_content(file_content.getvalue()) if file_content else '.mp3'
                    file_name = f"audio{detected_ext}"
                    logger.info(f"[{platform}] Detected file extension: {detected_ext} for audio without filename")
            
            # Save file content to a temporary file if needed
            temp_file_path = None
            if file_content and file_type:
                os.makedirs('temp', exist_ok=True)
                if not file_name:
                    detected_ext = detect_file_extension_from_content(file_content.getvalue())
                    file_name = f"document{detected_ext if detected_ext else '.bin'}"
                # استفاده از تابع create_temp_file_with_cleanup برای نام‌گذاری بهتر
                temp_file_path = create_temp_file_with_cleanup(file_content.getvalue(), file_name, f"mbot_{platform}_")
                logger.info(f"Created temp file: {temp_file_path} for {file_name}")
                
                # بررسی صحت فایل ایجاد شده
                if os.path.exists(temp_file_path) and os.path.getsize(temp_file_path) > 0:
                    logger.info(f"[{platform}] Temp file created successfully: {temp_file_path} (size: {os.path.getsize(temp_file_path)} bytes)")
                else:
                    logger.error(f"[{platform}] Failed to create temp file: {temp_file_path}")
                    temp_file_path = None
            
            # بررسی آیا پیام فوروارد شده است
            is_forwarded = bool(msg.forward_from_chat and msg.forward_from_message_id)
            forward_chat_id = str(msg.forward_from_chat.id) if msg.forward_from_chat else None
            forward_message_id = msg.forward_from_message_id if msg.forward_from_message_id else None

            is_pure_text = bool(content_text and not any([content_image_id, content_video_id, content_document_id, content_audio_id, is_forwarded]))
            is_media = any([content_image_id, content_video_id, content_document_id, content_audio_id])
            
            logger.info(f"[{platform}] Content analysis - is_pure_text: {is_pure_text}, is_media: {is_media}, is_forwarded: {is_forwarded}")
            logger.info(f"[{platform}] Content details - text: {bool(content_text)}, image: {bool(content_image_id)}, video: {bool(content_video_id)}, document: {bool(content_document_id)}")

            target_platform = state.get('target_platform', 'both')  # Default to both platforms
            logger.info(f"[{platform}] Target platform for broadcast: {target_platform}")
            logger.info(f"[{platform}] State: {state}")
            scopes = state['scopes']
            logger.info(f"[{platform}] Scopes: {scopes}")
            
            # تعیین پیش‌نمایش محتوا
            if is_forwarded:
                preview = f"فوروارد از پیام {forward_message_id}"
                if content_text:
                    preview += f" (متن: {content_text[:30]}{'...' if len(content_text) > 30 else ''})"
            elif is_pure_text:
                preview = (content_text[:30] + ("..." if len(content_text) > 30 else "")) if content_text else "-"
            elif content_image_id:
                preview = "[عکس]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
            elif content_video_id:
                preview = "[ویدیو]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
            elif content_document_id:
                preview = "[فایل]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
            elif content_audio_id:
                preview = "[فایل صوتی]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
            else:
                preview = "[بدون محتوا]"

            # ذخیره اطلاعات برای زمان‌بندی
            current_user_state[key] = current_user_state.get(key, {})
            current_user_state[key]['broadcast_info'] = {
                'text': content_text,
                'image_path': temp_file_path if content_image_id else None,
                'video_path': temp_file_path if content_video_id else None,
                'document_path': temp_file_path if content_document_id or content_audio_id else None,
                'scopes': scopes,
                'target_platform': target_platform,
                'preview_content': preview,
                'original_media_name': file_name,
                'forward_from_chat_id': forward_chat_id if is_forwarded else None,
                'forward_from_message_id': forward_message_id if is_forwarded else None,
                # ذخیره فایل temp اصلی برای cleanup بعدی
                'original_temp_file': temp_file_path,
                # ذخیره file_id اصلی برای recovery
                'original_file_id': content_image_id or content_video_id or content_document_id or content_audio_id
            }
            logger.info(f"[{platform}] Debug - Stored broadcast_info for key: {key}, content: {content_text[:50] if content_text else 'None'}...")

            # نمایش منوی تأیید و زمان‌بندی
            scope_names = ", ".join([CHAT_TYPE_DISPLAY_NAMES.get(s, s) for s in scopes])
            platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا', 'both': 'تلگرام + بله', 'all': 'همه پلتفرم‌ها'}
            platform_display = platform_names.get(target_platform, target_platform)
            
            confirmation_text = f"3/4: تأیید نهایی:\n\n📝 محتوا: {preview}\n🎯 مقصد: {scope_names}\n📱 پلتفرم: {platform_display}\n\nآیا می‌خواهید ادامه دهید؟"
            
            keyboard = [
                [InlineKeyboardButton("✅ تأیید و ادامه", callback_data="confirm_broadcast_proceed")],
                [InlineKeyboardButton("🔙 لغو", callback_data="broadcast_cancel")]
            ]
            
            await msg.reply_text(confirmation_text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

            async def send_to_platform_async(send_platform_name):
                if send_platform_name == 'telegram':
                    send_app = telegram_app
                    send_owner_id = OWNER_ID
                elif send_platform_name == 'bale':
                    send_app = bale_app
                    send_owner_id = BALE_OWNER_ID
                elif send_platform_name == 'ita':
                    send_app = None  # ایتا از API مستقیم استفاده می‌کند
                    send_owner_id = ITA_OWNER_ID
                else:
                    logger.error(f"[{platform}] Unknown platform: {send_platform_name}")
                    return {'sent': 0, 'failed': 0, 'batch_id': None, 'platform': send_platform_name, 'content_preview': None}
                
                send_final_targets = {cid for scope in scopes for cid in get_target_ids_by_scope([scope], send_platform_name)[scope] if str(cid) != str(send_owner_id)}
                logger.info(f"[{platform}] Found {len(send_final_targets)} targets for {send_platform_name}: {send_final_targets}")
                
                if not send_final_targets:
                    logger.warning(f"[{platform}] No targets found for {send_platform_name}")
                    return {'sent': 0, 'failed': 0, 'batch_id': None, 'platform': send_platform_name, 'content_preview': None}

                # Dedupe guard per (platform, content) to avoid repeated multi-sends
                dedupe_key = build_broadcast_key(
                    send_platform_name,
                    content_text,
                    content_image_id,
                    content_video_id,
                    content_document_id,
                    forward_chat_id,
                    forward_message_id,
                    platform  # source platform
                )
                if is_duplicate_broadcast(dedupe_key):
                    logger.info(f"[{send_platform_name}] Duplicate broadcast detected within TTL. Skipping.")
                    return {'sent': 0, 'failed': 0, 'batch_id': None, 'platform': send_platform_name, 'content_preview': 'duplicate-skipped'}
                
                # Prioritize media types: photo > video > document > audio
                media_photo = content_image_id if content_image_id else None
                media_video = content_video_id if content_video_id and not media_photo else None
                media_document = content_document_id if content_document_id and not media_photo and not media_video else None
                media_audio = content_audio_id if content_audio_id and not media_photo and not media_video and not media_document else None
                
                # Use temp file path for documents if available
                if media_document and temp_file_path:
                    media_document = temp_file_path
                    logger.info(f"[{send_platform_name}] Using temp file path for document: {temp_file_path}")
                elif media_document:
                    logger.info(f"[{send_platform_name}] Using document ID for document: {media_document}")
                
                # Use temp file path for audio if available
                if media_audio and temp_file_path:
                    media_audio = temp_file_path
                    logger.info(f"[{send_platform_name}] Using temp file path for audio: {temp_file_path}")
                elif media_audio:
                    logger.info(f"[{send_platform_name}] Using audio ID for audio: {media_audio}")
                
                # برای cross-platform، فایل موقت را کپی کنیم تا پاک نشود
                cross_platform_temp_file = None
                logger.info(f"[{send_platform_name}] Cross-platform check - media_photo: {bool(media_photo)}, media_video: {bool(media_video)}, media_document: {bool(media_document)}, media_audio: {bool(media_audio)}, temp_file_path: {bool(temp_file_path)}, send_platform_name: {send_platform_name}, platform: {platform}")
                
                if (media_document or media_audio) and temp_file_path and send_platform_name != platform:
                    logger.info(f"[{send_platform_name}] Creating cross-platform temp file from: {temp_file_path}")
                    try:
                        import shutil
                        cross_platform_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(temp_file_path)[1], prefix=f"mbot_{send_platform_name}_")
                        shutil.copy2(temp_file_path, cross_platform_temp_file.name)
                        if media_document:
                            media_document = cross_platform_temp_file.name
                        if media_audio:
                            media_audio = cross_platform_temp_file.name
                        logger.info(f"[{send_platform_name}] Created cross-platform temp file: {cross_platform_temp_file.name}")
                    except Exception as e:
                        logger.error(f"[{send_platform_name}] Failed to create cross-platform temp file: {e}")
                else:
                    logger.info(f"[{send_platform_name}] Skipping cross-platform temp file creation - conditions not met")
                
                # تعیین source_platform برای cross-platform file transfer
                has_media = bool(media_photo or media_video or media_document or media_audio)
                source_platform = platform if has_media else None
                logger.info(f"[{send_platform_name}] Source platform determination - has_media: {has_media}, source_platform: {source_platform}")
                
                # استخراج نام فایل اصلی برای پیام‌های فوروارد و غیر فوروارد
                original_media_name = None
                if msg:
                    if is_forwarded:
                        # برای پیام‌های فوروارد، نام فایل از پیام اصلی استخراج می‌شود
                        if msg.document:
                            original_media_name = msg.document.file_name
                        elif msg.audio and hasattr(msg.audio, 'file_name'):
                            original_media_name = msg.audio.file_name
                        elif msg.photo:
                            # برای عکس‌ها، نام فایل از caption یا نام پیش‌فرض
                            original_media_name = "image.jpg"
                        elif msg.video:
                            # برای ویدئوها، نام فایل از caption یا نام پیش‌فرض
                            original_media_name = "video.mp4"
                    else:
                        # برای پیام‌های غیر فوروارد
                        if msg.document:
                            original_media_name = msg.document.file_name
                        elif msg.audio and hasattr(msg.audio, 'file_name'):
                            original_media_name = msg.audio.file_name
                        elif getattr(msg, 'effective_attachment', None) and getattr(msg.effective_attachment, 'file_name', None):
                            original_media_name = os.path.basename(msg.effective_attachment.file_name)

                kwargs = {
                    'app': send_app,
                    'scopes': scopes,
                    'platform': send_platform_name,
                    'owner_id': send_owner_id,
                    'text': content_text,
                    'photo_path': media_photo,
                    'video_path': media_video,
                    'document_path': media_document or media_audio,  # Use audio as document
                    'forward_from_chat_id': forward_chat_id if is_forwarded else None,
                    'forward_from_message_id': forward_message_id if is_forwarded else None,
                    'source_platform': source_platform,
                    'original_media_name': original_media_name,
                }
                
                try:
                    result = await perform_broadcast_async(**kwargs)
                    result['platform'] = send_platform_name
                    
                    # پاک کردن فایل موقت cross-platform
                    if cross_platform_temp_file and os.path.exists(cross_platform_temp_file.name):
                        try:
                            os.unlink(cross_platform_temp_file.name)
                            logger.info(f"[{send_platform_name}] Cleaned up cross-platform temp file: {cross_platform_temp_file.name}")
                        except Exception as e:
                            logger.warning(f"[{send_platform_name}] Failed to cleanup cross-platform temp file: {e}")
                    
                    # تعیین پیش‌نمایش محتوا
                    if is_forwarded:
                        preview = f"فوروارد از پیام {forward_message_id}"
                        if content_text:
                            preview += f" (متن: {content_text[:30]}{'...' if len(content_text) > 30 else ''})"
                    elif is_pure_text:
                        preview = (content_text[:30] + ("..." if len(content_text) > 30 else "")) if content_text else "-"
                    elif content_image_id:
                        preview = "[عکس]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
                    elif content_video_id:
                        preview = "[ویدیو]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
                    elif content_document_id:
                        preview = "[فایل]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
                    elif content_audio_id:
                        preview = "[فایل صوتی]" + (f" (کپشن: {content_text[:30]}{'...' if content_text and len(content_text) > 30 else ''})" if content_text else "")
                    else:
                        preview = "[بدون محتوا]"
                        
                    result['content_preview'] = preview
                    return result
                    
                except Exception as e:
                    logger.error(f"Error in send_to_platform_async for {send_platform_name}: {e}", exc_info=True)
                    return {
                        'sent': 0, 
                        'failed': len(send_final_targets), 
                        'batch_id': None, 
                        'platform': send_platform_name, 
                        'content_preview': f"خطا در ارسال: {str(e)[:100]}",
                        'error': str(e)
                    }


        # اگر منتظر کپشن هستیم
        if state and state.get('status') == 'awaiting_caption':
            pending_media = state.get('pending_media')
            if not pending_media:
                await msg.reply_text("❌ خطای داخلی: اطلاعات فایل یافت نشد. لطفاً دوباره تلاش کنید.")
                current_user_state.pop(key, None)
                return
            caption = msg.text
            scopes = pending_media['scopes']
            final_targets = {cid for scope in scopes for cid in get_target_ids_by_scope([scope], platform)[scope] if int(cid) != owner_id}
            for target_id in final_targets:
                try:
                    if pending_media['image_id']:
                        await context.bot.send_photo(chat_id=int(target_id), photo=pending_media['image_id'], caption=caption)
                    elif pending_media['video_id']:
                        await context.bot.send_video(chat_id=int(target_id), video=pending_media['video_id'], caption=caption)
                    elif pending_media['document_id']:
                        await context.bot.send_document(chat_id=int(target_id), document=pending_media['document_id'], caption=caption)
                except Exception as e:
                    logger.warning(f"[{platform}] Failed to send media to {target_id}: {e}")
            await msg.reply_text("✅ فایل به همه مقصدها ارسال شد.")
            current_user_state.pop(key, None)
            return
        
        # پردازش تاریخ و زمان شمسی برای زمان‌بندی
        if state and state.get('status') == 'awaiting_custom_datetime':
            if not msg.text:
                await msg.reply_text("❌ لطفاً تاریخ و زمان را به صورت متن وارد کنید.\n\nمثال: 1403/07/15 14:30")
                return
            
            # تجزیه تاریخ شمسی
            parsed_datetime = parse_persian_datetime(msg.text.strip())
            if not parsed_datetime:
                await msg.reply_text("❌ فرمت تاریخ نامعتبر است.\n\nلطفاً فرمت صحیح را وارد کنید:\n1403/07/15 14:30")
                return
            
            # بررسی که تاریخ در آینده باشد
            iran_tz = pytz.timezone('Asia/Tehran')
            now = datetime.now(iran_tz)
            
            # اطمینان از اینکه هر دو datetime timezone دارند
            if parsed_datetime.tzinfo is None:
                parsed_datetime = iran_tz.localize(parsed_datetime)
            if now.tzinfo is None:
                now = iran_tz.localize(now)
            
            if parsed_datetime <= now:
                await msg.reply_text("❌ تاریخ باید در آینده باشد.\n\nلطفاً تاریخ و زمانی بعد از الان وارد کنید.")
                return
            
            # محاسبه تاخیر بر حسب ثانیه
            delay_seconds = int((parsed_datetime - now).total_seconds())
            
            # ذخیره زمان انتخابی کاربر در state
            current_user_state[key]['selected_datetime'] = parsed_datetime
            
            # اجرای زمان‌بندی
            await execute_scheduled_broadcast(context, platform, user.id, delay_seconds)
            current_user_state.pop(key, None)
            return
        
        # Admin Echo / Fallback for other messages/commands
        if msg.text:
            if msg.text.startswith('/'): 
                menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
                await msg.reply_text(escape_markdown_v2("دستور نامعتبر یا عملیات در حال انجام\\. لطفاً از منو استفاده کنید\\."), reply_markup=menu_builder(), parse_mode=ParseMode.MARKDOWN_V2)
                return
            else:
                await msg.reply_text(escape_markdown_v2(f"پیام شما دریافت شد: {msg.text}\n\nبرای مدیریت، لطفاً از منو استفاده کنید\\."), parse_mode=ParseMode.MARKDOWN_V2)
                menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
                await msg.reply_text("چه کاری می‌خواهید انجام دهید؟", reply_markup=menu_builder())
                return
        elif msg.photo or msg.video or msg.document or msg.sticker:
             await msg.reply_text("پیام رسانه‌ای شما دریافت شد. لطفاً برای ارسال انبوه از طریق منوی 'ارسال انبوه' اقدام کرده و محتوای لازم را ارسال کنید.")
             return

    # Non-admin private message handling
    if user and chat and chat.type == ChatType.PRIVATE and user.id != owner_id:
        uname = getattr(chat, 'username', None)
        fname = getattr(chat, 'first_name', None) or ''
        register_chat(str(chat.id), "private", platform, name=fname, username=uname)
        if msg.text:
            await msg.reply_text(f"✅ پیام شما دریافت شد: {msg.text}")
        else:
            await msg.reply_text("✅ پیام شما دریافت شد. لطفاً برای هماهنگی بیشتر با ادمین ربات تماس بگیرید.")
        
        # ارسال اطلاعیه به ادمین برای پیام کاربر غیر ادمین
        message_preview = msg.text[:50] + "..." if msg.text and len(msg.text) > 50 else msg.text or "پیام رسانه‌ای"
        notification_msg = f"💬 کاربر غیر ادمین پیام فرستاد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {user.id}\n👤 نام: {fname}\n🔗 یوزرنیم: @{uname}\n📝 پیام: {message_preview}" if uname else f"💬 کاربر غیر ادمین پیام فرستاد:\n\n📱 پلتفرم: {platform}\n🆔 شناسه: {user.id}\n👤 نام: {fname}\n📝 پیام: {message_preview}"
        await send_admin_notification(notification_msg, platform)
        
        logger.info(f"[{platform}] Non-admin user {user.id} sent message, replied acknowledgement. Chat type: {chat.type}")
        return

async def handle_rate_limit_with_backoff(func, *args, max_retries=3, **kwargs):
    """
    تابع کمکی برای مدیریت rate limiting با exponential backoff
    """
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except RetryAfter as e:
            if attempt == max_retries - 1:
                logger.error(f"Rate limit exceeded after {max_retries} attempts")
                raise
            
            wait_time = min(e.retry_after + (2 ** attempt), 60)  # Cap at 60 seconds
            logger.warning(f"Rate limit hit, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
        except Exception as e:
            # For other exceptions, don't retry
            raise e

async def send_with_concurrency_control(semaphore, func, *args, **kwargs):
    """
    تابع کمکی برای ارسال با کنترل همزمانی
    """
    async with semaphore:
        try:
            return await handle_rate_limit_with_backoff(func, *args, **kwargs)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.error(f"Event loop is closed during send operation: {e}")
                # تلاش برای استفاده از Event Loop اصلی تلگرام
                try:
                    logger.info("Attempting to use Telegram's main Event Loop...")
                    # بررسی وجود Event Loop اصلی تلگرام
                    if 'telegram_bot_loop' in globals() and telegram_bot_loop and not telegram_bot_loop.is_closed():
                        # استفاده از Event Loop اصلی تلگرام
                        future = asyncio.run_coroutine_threadsafe(
                            handle_rate_limit_with_backoff(func, *args, **kwargs),
                            telegram_bot_loop
                        )
                        return future.result(timeout=30)
                    else:
                        logger.error("Telegram Event Loop is not available")
                        # تلاش برای ایجاد Event Loop جدید
                        logger.info("Attempting to create new Event Loop...")
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(handle_rate_limit_with_backoff(func, *args, **kwargs))
                            return result
                        finally:
                            new_loop.close()
                except Exception as loop_error:
                    logger.error(f"Failed to use Telegram Event Loop: {loop_error}")
                    raise e
            else:
                raise e

async def safe_reply_text(msg, text, **kwargs):
    """
    تابع کمکی برای ارسال reply_text با exception handling
    """
    try:
        await msg.reply_text(text, **kwargs)
    except (RuntimeError, Exception) as e:
        # Silently ignore event loop errors and network errors
        if any(keyword in str(e).lower() for keyword in ["event loop is closed", "network error", "future attached to different loop"]):
            logger.debug(f"Ignoring reply_text error: {e}")
        else:
            logger.warning(f"Failed to send reply_text: {e}")

def create_temp_file_with_cleanup(file_content: bytes, original_filename: str, prefix: str = "mbot_tmp_") -> str:
    """
    ایجاد فایل موقت با cleanup خودکار
    """
    # تشخیص پسوند فایل
    import os
    file_ext = os.path.splitext(original_filename)[1] if original_filename else '.tmp'
    
    # ایجاد فایل موقت با نام ساده
    temp_file = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=file_ext)
    temp_file.write(file_content)
    temp_file.close()
    
    # ثبت فایل برای cleanup بعدی
    if not hasattr(create_temp_file_with_cleanup, 'temp_files'):
        create_temp_file_with_cleanup.temp_files = set()
    create_temp_file_with_cleanup.temp_files.add(temp_file.name)
    
    return temp_file.name

def cleanup_temp_files():
    """
    پاکسازی فایل‌های موقت
    """
    if hasattr(create_temp_file_with_cleanup, 'temp_files'):
        for temp_file_path in create_temp_file_with_cleanup.temp_files.copy():
            try:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                create_temp_file_with_cleanup.temp_files.discard(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_file_path}: {e}")

def parse_persian_datetime(persian_datetime_str: str) -> Optional[datetime]:
    """
    تبدیل تاریخ و زمان شمسی به میلادی
    فرمت ورودی: 1403/07/15 14:30
    """
    try:
        # حذف فاصله‌های اضافی
        persian_datetime_str = persian_datetime_str.strip()
        
        # تشخیص فرمت تاریخ و زمان
        if ' ' in persian_datetime_str:
            date_part, time_part = persian_datetime_str.split(' ', 1)
        else:
            date_part = persian_datetime_str
            time_part = "00:00"
        
        # تجزیه تاریخ شمسی
        date_parts = date_part.split('/')
        if len(date_parts) != 3:
            return None
        
        year, month, day = map(int, date_parts)
        
        # تجزیه زمان
        time_parts = time_part.split(':')
        if len(time_parts) == 2:
            hour, minute = map(int, time_parts)
            second = 0
        elif len(time_parts) == 3:
            hour, minute, second = map(int, time_parts)
        else:
            return None
        
        # تبدیل تاریخ شمسی به میلادی
        if not jdatetime:
            logger.error("jdatetime library not available for Persian date parsing")
            return None
        
        persian_date = jdatetime.date(year, month, day)
        gregorian_date = persian_date.togregorian()
        
        # ایجاد datetime میلادی با timezone ایران
        if pytz:
            iran_tz = pytz.timezone('Asia/Tehran')
            gregorian_datetime = iran_tz.localize(datetime.combine(gregorian_date, datetime.min.time().replace(hour=hour, minute=minute, second=second)))
        else:
            gregorian_datetime = datetime.combine(gregorian_date, datetime.min.time().replace(hour=hour, minute=minute, second=second))
        
        return gregorian_datetime
        
    except Exception as e:
        logger.error(f"Error parsing Persian datetime '{persian_datetime_str}': {e}")
        return None

def format_persian_datetime(dt: datetime) -> str:
    """
    تبدیل datetime میلادی به فرمت شمسی
    """
    try:
        # تبدیل به timezone ایران
        if pytz:
            iran_tz = pytz.timezone('Asia/Tehran')
        if dt.tzinfo is None:
            dt = iran_tz.localize(dt)
        else:
            dt = dt.astimezone(iran_tz)
        
        # تبدیل به تاریخ شمسی
        if jdatetime:
            # تبدیل datetime به تاریخ شمسی
            persian_date = jdatetime.datetime.fromgregorian(datetime=dt)
            return persian_date.strftime('%Y/%m/%d %H:%M')
        else:
            return dt.strftime('%Y-%m-%d %H:%M')
        
    except Exception as e:
        logger.error(f"Error formatting Persian datetime: {e}")
        return dt.strftime('%Y-%m-%d %H:%M')

async def execute_scheduled_broadcast(context, platform: str, user_id: int, delay_seconds: int):
    """
    اجرای ارسال زمان‌بندی شده
    """
    try:
        # بررسی وجود event loop
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                logger.error(f"Event loop is closed for execute_scheduled_broadcast. user_id: {user_id}, platform: {platform}")
                return
        except RuntimeError:
            logger.error(f"No event loop available for execute_scheduled_broadcast. user_id: {user_id}, platform: {platform}")
            return
        
        # بررسی وجود context
        if not context or not hasattr(context, 'bot'):
            logger.error(f"No context available for execute_scheduled_broadcast. user_id: {user_id}, platform: {platform}")
            return
        
        # بررسی delay_seconds - اگر 0 باشد، ارسال فوری انجام می‌شود
        if delay_seconds == 0:
            logger.info(f"Immediate broadcast requested for user_id: {user_id}, platform: {platform}")
        else:
            logger.info(f"Scheduled broadcast requested for user_id: {user_id}, platform: {platform}, delay: {delay_seconds}s")
        current_user_state = user_state if platform == 'telegram' else bale_user_state
        key = f"{platform}:{user_id}"
        state = current_user_state.get(key, {})
        info = state.get('broadcast_info', {})
        if not info:
            if context and hasattr(context, 'bot'):
                await context.bot.send_message(user_id, "❌ خطا: اطلاعات ارسال یافت نشد.")
            else:
                logger.error(f"❌ خطا: اطلاعات ارسال یافت نشد برای user_id: {user_id}")
            return
        
        target_app = telegram_app if platform == 'telegram' else bale_app
        target_owner_id = OWNER_ID if platform == 'telegram' else BALE_OWNER_ID
        
        if delay_seconds == 0:
            # ارسال فوری
            if context and hasattr(context, 'bot'):
                await context.bot.send_message(user_id, "⏳ ارسال آغاز شد...")
            else:
                logger.info(f"⏳ ارسال آغاز شد برای user_id: {user_id}")
            
            # Handle multi-platform sending - فقط اگر context موجود باشد
            if context and hasattr(context, 'bot'):
                target_platform = info.get('target_platform', 'both')
                results = []
                
                # Execute broadcasts in order: Ita first (to copy files before they're cleaned up), then others
                if target_platform in ['ita', 'all']:
                    logger.info(f"[{platform}] Starting Ita broadcast with scopes: {info['scopes']}")
                    result = await perform_broadcast_async(None, scopes=info['scopes'], platform='ita', 
                                                   text=info.get('text'), photo_path=info.get('image_path'), 
                                                   video_path=info.get('video_path'), document_path=info.get('document_path'), 
                                                           owner_id=ITA_OWNER_ID, original_media_name=info.get('original_media_name'),
                                                           forward_from_chat_id=info.get('forward_from_chat_id'),
                                                           forward_from_message_id=info.get('forward_from_message_id'),
                                                           source_platform=platform, original_file_id=info.get('original_file_id'))
                    logger.info(f"[{platform}] Ita broadcast result: {result}")
                    results.append(result)
                
                if target_platform in ['telegram', 'both', 'all']:
                    result = await perform_broadcast_async(telegram_app, scopes=info['scopes'], platform='telegram', 
                                                           text=info.get('text'), photo_path=info.get('image_path'), 
                                                           video_path=info.get('video_path'), document_path=info.get('document_path'), 
                                                           owner_id=OWNER_ID, original_media_name=info.get('original_media_name'),
                                                           forward_from_chat_id=info.get('forward_from_chat_id'),
                                                           forward_from_message_id=info.get('forward_from_message_id'),
                                                           source_platform=platform, original_file_id=info.get('original_file_id'))
                    results.append(result)
                
                if target_platform in ['bale', 'both', 'all']:
                    result = await perform_broadcast_async(bale_app, scopes=info['scopes'], platform='bale', 
                                                           text=info.get('text'), photo_path=info.get('image_path'), 
                                                           video_path=info.get('video_path'), document_path=info.get('document_path'), 
                                                           owner_id=BALE_OWNER_ID, original_media_name=info.get('original_media_name'),
                                                           forward_from_chat_id=info.get('forward_from_chat_id'),
                                                           forward_from_message_id=info.get('forward_from_message_id'),
                                                           source_platform=platform, original_file_id=info.get('original_file_id'))
                    results.append(result)
            else:
                # اگر context موجود نیست، ارسال فوری انجام نده
                logger.warning(f"⏳ ارسال فوری برای user_id: {user_id} لغو شد - context موجود نیست")
                return
            
            # Clean up original temp files after all broadcasts are complete
            await cleanup_original_temp_files(info)
            
            # Combine results
            total_sent = sum(r.get('sent', 0) for r in results)
            total_failed = sum(r.get('failed', 0) for r in results)
            
            keyboard = []
            platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا'}
            
            for result in results:
                if result.get('batch_id'):
                    platform_name = platform_names.get(result.get('platform', ''), result.get('platform', ''))
                    batch_id = result['batch_id']
                    
                    # بررسی وضعیت حذف
                    batch_info = db_fetchone("SELECT is_deleted FROM broadcast_batches WHERE batch_id = ?", (batch_id,))
                    if batch_info and batch_info['is_deleted'] == 1:
                        keyboard.append([InlineKeyboardButton(f"✅ حذف شده - {platform_name}", callback_data="noop")])
                    else:
                        keyboard.append([InlineKeyboardButton(f"🗑 حذف ارسال {platform_name}", callback_data=f"delete_batch_{batch_id}_{result.get('platform', '')}")])
            
            preview = info.get('preview_content', info.get('content_preview', '-'))
            if preview and len(preview) > 100:
                preview = preview[:97] + "..."
            
            # Format platform names for display
            platform_names = []
            if target_platform in ['telegram', 'both', 'all']:
                platform_names.append('تلگرام')
            if target_platform in ['bale', 'both', 'all']:
                platform_names.append('بله')
            if target_platform in ['ita', 'all']:
                platform_names.append('ایتا')
            
            platform_display = ' + '.join(platform_names)
            
            if context and hasattr(context, 'bot'):
                # تولید آمار تفصیلی برای ارسال فوری
                detailed_stats = generate_detailed_stats_report(results)
                
                # محاسبه تعداد کل چت‌های هدف از نتایج
                total_target_chats = sum(
                    sum(scope_stats.get('sent', 0) + scope_stats.get('failed', 0) 
                        for scope_stats in result.get('detailed_results', {}).values())
                    for result in results
                )
                
                
                report_text = f"✅ ارسال کامل شد.\n\n📱 پلتفرم: {platform_display}\n🎯 چت‌های هدف: {total_target_chats}\n✅ موفق: {total_sent}\n❌ ناموفق: {total_failed}\n\n{detailed_stats}\n\n📝 محتوا: {preview}"
                
                await context.bot.send_message(user_id, report_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                logger.info(f"✅ ارسال کامل شد برای user_id: {user_id}, موفق: {total_sent}, ناموفق: {total_failed}")
        else:
            # ارسال زمان‌بندی شده
            iran_tz = pytz.timezone('Asia/Tehran')
            # استفاده از زمان انتخابی کاربر اگر موجود باشد، در غیر این صورت محاسبه از delay_seconds
            if 'selected_datetime' in state:
                scheduled_time = state['selected_datetime']
            else:
                scheduled_time = datetime.now(iran_tz) + timedelta(seconds=delay_seconds)
            
            # ذخیره در دیتابیس
            broadcast_id = schedule_broadcast(
                scheduled_time=scheduled_time,
                platform=info.get('target_platform', platform),  # استفاده از target_platform به جای platform
                scopes=info['scopes'],
                content_text=info.get('text'),
                content_type='text' if info.get('text') else ('photo' if info.get('image_path') else ('video' if info.get('video_path') else 'document')),
                content_data=json.dumps({
                    'text': info.get('text'),
                    'image_path': info.get('image_path'),
                    'video_path': info.get('video_path'),
                    'document_path': info.get('document_path'),
                    'original_media_name': info.get('original_media_name')
                })
            )
            
            # برنامه‌ریزی در APScheduler - این کار در schedule_broadcast انجام می‌شود
            
            preview = info.get('preview_content', info.get('content_preview', '-'))
            if preview and len(preview) > 100:
                preview = preview[:97] + "..."
            
            persian_time = format_persian_datetime(scheduled_time)
            
            # ایجاد keyboard برای بازخورد
            keyboard = []
            keyboard.append([InlineKeyboardButton("🗑 حذف ارسال زمان‌بندی شده", callback_data=f"delete_scheduled_{broadcast_id}")])
            
            if context and hasattr(context, 'bot'):
                sent_message = await context.bot.send_message(user_id, escape_markdown_v2(f"✅ پست زمان‌بندی شد!\n\n📝 محتوا: {preview}\n⏰ زمان ارسال: {persian_time}\n🆔 شناسه: {broadcast_id}"), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
                # ذخیره message_id در دیتابیس
                db_execute("UPDATE scheduled_broadcasts SET notification_message_id = ? WHERE id = ?", (sent_message.message_id, broadcast_id))
            else:
                logger.info(f"✅ پست زمان‌بندی شد برای user_id: {user_id}, شناسه: {broadcast_id}, زمان: {persian_time}")
        
        # پاک کردن اطلاعات از current_user_state
        if key in current_user_state and 'broadcast_info' in current_user_state[key]:
            current_user_state[key].pop('broadcast_info', None)
        
        # بازگشت به منوی اصلی
        if context and hasattr(context, 'bot'):
            menu_builder = build_telegram_main_menu if platform == 'telegram' else build_bale_main_menu
            await context.bot.send_message(user_id, "چه کاری می‌خواهید انجام دهید؟", reply_markup=menu_builder())
        else:
            logger.info(f"منوی اصلی برای user_id: {user_id}")
        
    except Exception as e:
        logger.error(f"Error in execute_scheduled_broadcast: {e}")
        # بررسی وجود event loop قبل از ارسال پیام خطا
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            if loop.is_closed():
                logger.error(f"Event loop is closed, cannot send error message to user_id: {user_id}")
                return
        except RuntimeError:
            logger.error(f"No event loop available, cannot send error message to user_id: {user_id}")
            return
        
        if context and hasattr(context, 'bot'):
            try:
                await context.bot.send_message(user_id, f"❌ خطا در ارسال: {str(e)}")
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")
        else:
            logger.error(f"❌ خطا در ارسال برای user_id: {user_id}: {str(e)}")

async def show_scheduling_queue(context, platform: str, user_id: int, queue_type: str):
    """
    نمایش صف انتشار
    """
    try:
        # تعریف فیلترهای تاریخ
        now = datetime.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)
        week_end = today + timedelta(days=7)
        
        if queue_type == "queue_today":
            filter_condition = "DATE(scheduled_time) = DATE('now')"
            title = "📅 پست‌های امروز:"
        elif queue_type == "queue_tomorrow":
            filter_condition = "DATE(scheduled_time) = DATE('now', '+1 day')"
            title = "📅 پست‌های فردا:"
        elif queue_type == "queue_day_after":
            filter_condition = "DATE(scheduled_time) = DATE('now', '+2 days')"
            title = "📅 پست‌های دو روز بعد:"
        elif queue_type == "queue_this_week":
            filter_condition = "scheduled_time BETWEEN datetime('now') AND datetime('now', '+7 days')"
            title = "📅 پست‌های این هفته:"
        else:  # queue_all
            filter_condition = "scheduled_time >= datetime('now')"
            title = "📋 کل لیست انتشار:"
        
        # دریافت پست‌های زمان‌بندی شده
        scheduled_posts = db_fetchall(f"""
            SELECT id, scheduled_time, platform, scopes, content_text, content_type, status
            FROM scheduled_broadcasts 
            WHERE {filter_condition} AND status = 'pending'
            ORDER BY scheduled_time ASC
        """)
        
        if not scheduled_posts:
            await context.bot.send_message(user_id, f"{title}\n\n📭 هیچ پستی در این بازه زمانی وجود ندارد.")
            return
        
        # ساخت متن گزارش
        report_text = f"{title}\n\n"
        for post in scheduled_posts:
            post_id = post['id']
            scheduled_time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S')
            persian_time = format_persian_datetime(scheduled_time)
            platform_name = 'تلگرام' if post['platform'] == 'telegram' else ('بله' if post['platform'] == 'bale' else 'ایتا')
            scopes = json.loads(post['scopes']) if post['scopes'] else []
            scope_names = ", ".join([CHAT_TYPE_DISPLAY_NAMES.get(s, s) for s in scopes])
            content_preview = post['content_text'][:50] + "..." if post['content_text'] and len(post['content_text']) > 50 else (post['content_text'] or f"فایل {post['content_type']}")
            
            report_text += f"🆔 {post_id}\n"
            report_text += f"⏰ {persian_time}\n"
            report_text += f"📱 {platform_name}\n"
            report_text += f"🎯 {scope_names}\n"
            report_text += f"📝 {content_preview}\n"
            report_text += f"❌ لغو\n\n"
        
        # اضافه کردن دکمه‌های لغو
        keyboard = []
        for post in scheduled_posts[:10]:  # حداکثر 10 دکمه
            keyboard.append([InlineKeyboardButton(f"❌ لغو پست {post['id']}", callback_data=f"cancel_scheduled_{post['id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_main")])
        
        await context.bot.send_message(user_id, report_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"Error in show_scheduling_queue: {e}")
        await context.bot.send_message(user_id, f"❌ خطا در نمایش صف: {str(e)}")

# Async database functions to prevent blocking
async def async_db_execute(query: str, params: tuple = ()):
    """
    اجرای کوئری دیتابیس به صورت async
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, db_execute, query, params)

async def async_db_fetchone(query: str, params: tuple = ()):
    """
    دریافت یک رکورد از دیتابیس به صورت async
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, db_fetchone, query, params)

async def async_db_fetchall(query: str, params: tuple = ()):
    """
    دریافت تمام رکوردها از دیتابیس به صورت async
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, db_fetchall, query, params)

# =================================================================
# --- Segmentation Functions ---
# =================================================================

def get_chats_by_segmentation(platform: str = None, chat_type: str = None, 
                             tags: str = None, is_active: bool = None, 
                             days_since_active: int = None) -> List[Dict]:
    """
    دریافت چت‌ها بر اساس معیارهای segmentation
    """
    conditions = []
    params = []
    
    if platform:
        conditions.append("platform = ?")
        params.append(platform)
    
    if chat_type:
        conditions.append("chat_type = ?")
        params.append(chat_type)
    
    if tags:
        conditions.append("tags LIKE ?")
        params.append(f"%{tags}%")
    
    if is_active is not None:
        conditions.append("is_active = ?")
        params.append(1 if is_active else 0)
    
    if days_since_active is not None:
        conditions.append("last_active < datetime('now', '-{} days')".format(days_since_active))
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
        SELECT chat_id, platform, chat_type, name, username, 
               last_active, tags, is_active, created_at
        FROM chats 
        WHERE {where_clause}
        ORDER BY last_active DESC
    """
    
    return db_fetchall(query, tuple(params))

def update_chat_tags(chat_id: str, platform: str, tags: str):
    """
    به‌روزرسانی تگ‌های یک چت
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE chats SET tags = ? WHERE chat_id = ? AND platform = ?", 
                         (tags, chat_id, platform))
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"DB Execute Error in update_chat_tags: {e}")
        return False

def update_chat_activity(chat_id: str, platform: str):
    """
    به‌روزرسانی زمان آخرین فعالیت یک چت
    """
    db_execute("UPDATE chats SET last_active = datetime('now'), is_active = 1 WHERE chat_id = ? AND platform = ?", 
               (chat_id, platform))

def deactivate_chat(chat_id: str, platform: str):
    """
    غیرفعال کردن یک چت
    """
    db_execute("UPDATE chats SET is_active = 0 WHERE chat_id = ? AND platform = ?", 
               (chat_id, platform))

# =================================================================
# --- Scheduler Functions ---
# =================================================================

def init_scheduler():
    """
    راه‌اندازی scheduler به صورت همگام (sync)
    """
    global scheduler
    # از BackgroundScheduler استفاده می‌کنیم
    scheduler = BackgroundScheduler()
    scheduler.start()
    logger.info("BackgroundScheduler initialized and started")

def schedule_broadcast(scheduled_time, platform: str, scopes: List[str], 
                           content_text: str = None, content_type: str = None, 
                           content_data: str = None, is_recurring: bool = False, 
                           recurring_pattern: str = None) -> int:
    """
    زمان‌بندی یک ارسال
    """
    # تبدیل scheduled_time به datetime object اگر string است
    if isinstance(scheduled_time, str):
        scheduled_datetime = parse_persian_datetime(scheduled_time)
        if not scheduled_datetime:
            raise ValueError(f"Invalid scheduled time format: {scheduled_time}")
    else:
        scheduled_datetime = scheduled_time
    
    # ذخیره در دیتابیس
    broadcast_id = db_execute("""
        INSERT INTO scheduled_broadcasts 
        (scheduled_time, platform, scopes, content_text, content_type, content_data, is_recurring, recurring_pattern)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (scheduled_datetime.isoformat(), platform, json.dumps(scopes), content_text, content_type, content_data, 
          is_recurring, recurring_pattern))
    
    # اضافه کردن به scheduler
    if scheduler:
        if is_recurring and recurring_pattern:
            # ارسال دوره‌ای
            trigger = CronTrigger.from_crontab(recurring_pattern)
            scheduler.add_job(
                execute_scheduled_broadcast_job,
                trigger=trigger,
                args=[broadcast_id],
                id=f"recurring_{broadcast_id}",
                replace_existing=True
            )
        else:
            # ارسال یکباره
            scheduler.add_job(
                execute_scheduled_broadcast_job,
                trigger=DateTrigger(run_date=scheduled_datetime),
                args=[broadcast_id],
                id=f"once_{broadcast_id}",
                replace_existing=True
            )
    
    logger.info(f"Scheduled broadcast {broadcast_id} for {scheduled_time}")
    return broadcast_id

async def execute_scheduled_broadcast_from_db(broadcast_id: int, app):
    """
    اجرای ارسال زمان‌بندی شده از دیتابیس.
    این تابع همیشه در Event Loop اصلی ربات اجرا می‌شود.
    """
    logger.info(f"[Async Job] Executing broadcast from DB for id: {broadcast_id}")
    try:
        # دریافت اطلاعات از دیتابیس به صورت async
        broadcast = await async_db_fetchone(
            "SELECT * FROM scheduled_broadcasts WHERE id = ? AND status = 'pending'", (broadcast_id,)
        )
        
        if not broadcast:
            logger.warning(f"Scheduled broadcast {broadcast_id} not found or already executed.")
            return
        
        # به‌روزرسانی وضعیت به 'در حال اجرا'
        await async_db_execute("UPDATE scheduled_broadcasts SET status = 'executing' WHERE id = ?", (broadcast_id,))
        
        # بررسی scopes
        try:
            scopes = json.loads(broadcast['scopes']) if 'scopes' in broadcast.keys() else []
        except json.JSONDecodeError:
            scopes = []
        
        # بررسی content_data و content_text
        content_data = {}
        content_text = broadcast['content_text'] if 'content_text' in broadcast.keys() else (broadcast['message'] if 'message' in broadcast.keys() else '')
        
        if broadcast['content_data'] if 'content_data' in broadcast.keys() else None:
            try:
                # اگر string است، JSON parse کن
                if isinstance(broadcast['content_data'], str):
                    if broadcast['content_data'].strip():
                        try:
                            content_data = json.loads(broadcast['content_data'])
                        except json.JSONDecodeError:
                            # اگر JSON نیست، به عنوان text در نظر بگیر
                            content_data = {'text': broadcast['content_data']}
                # اگر dict است، مستقیماً استفاده کن
                elif isinstance(broadcast['content_data'], dict):
                    content_data = broadcast['content_data']
                # اگر int یا سایر انواع است، به dict تبدیل کن
                else:
                    content_data = {'text': str(broadcast['content_data'])}
            except (json.JSONDecodeError, TypeError):
                # اگر JSON نیست، به عنوان string در نظر بگیر
                content_data = {'text': str(broadcast['content_data'])}
        
        # اگر content_data خالی است اما content_text وجود دارد، بررسی کن که آیا مسیر فایل است
        if not content_data and content_text:
            # بررسی اینکه آیا content_text مسیر فایل است
            if content_text and (content_text.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')) or 
                               content_text.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')) or
                               content_text.endswith(('.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac'))):
                # اگر مسیر فایل است، آن را به عنوان رسانه تشخیص بده
                if content_text.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    content_data = {'image_path': content_text}
                elif content_text.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                    content_data = {'video_path': content_text}
                else:
                    content_data = {'document_path': content_text}
            else:
                # اگر مسیر فایل نیست، به عنوان متن در نظر بگیر
                content_data = {'text': content_text}
        
        # بررسی اضافی: اگر content_data یک string است و مسیر فایل است
        if isinstance(content_data, str) and content_data:
            if content_data.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                content_data = {'image_path': content_data}
            elif content_data.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                content_data = {'video_path': content_data}
            elif content_data.endswith(('.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac')):
                content_data = {'document_path': content_data}
            else:
                content_data = {'text': content_data}
        
        # بررسی اضافی: اگر content_data یک dict است و دارای کلید text با مسیر فایل است
        if isinstance(content_data, dict) and 'text' in content_data:
            text_value = content_data['text']
            if text_value and isinstance(text_value, str):
                if text_value.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                    content_data = {'image_path': text_value}
                elif text_value.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
                    content_data = {'video_path': text_value}
                elif text_value.endswith(('.pdf', '.doc', '.docx', '.txt', '.zip', '.rar', '.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac')):
                    content_data = {'document_path': text_value}
                # اگر مسیر فایل نیست، content_data را تغییر نده
        
        # <<< START CHANGE: Correctly handle local file paths for all platforms >>>
        
        platforms_to_send = []
        
        # بررسی platforms (JSON array) به جای platform (single value)
        if 'platforms' in broadcast.keys() and broadcast['platforms']:
            try:
                platforms_to_send = json.loads(broadcast['platforms'])
                logger.info(f"[Scheduled Broadcast {broadcast_id}] Using platforms field: {platforms_to_send}")
            except json.JSONDecodeError:
                # اگر JSON نیست، به عنوان single platform در نظر بگیر
                platforms_to_send = [broadcast['platforms']]
                logger.info(f"[Scheduled Broadcast {broadcast_id}] Using platforms as single value: {platforms_to_send}")
        else:
            # fallback به platform field اگر platforms وجود نداشت
            target_platform = broadcast['platform'] if 'platform' in broadcast.keys() else 'telegram'
            logger.info(f"[Scheduled Broadcast {broadcast_id}] Using platform field as fallback: {target_platform}")
            if target_platform and target_platform.strip():
                try:
                    # اگر JSON است، آن را parse کن
                    if target_platform.startswith('[') or target_platform.startswith('{'):
                        platforms_to_send = json.loads(target_platform)
                    else:
                        platforms_to_send = [target_platform]
                except json.JSONDecodeError:
                    platforms_to_send = [target_platform]
            else:
                platforms_to_send = ['telegram']  # default
        
        logger.info(f"[Scheduled Broadcast {broadcast_id}] Final platforms_to_send: {platforms_to_send}")

        results = []
        
        # Extract file paths once
        photo_path = content_data.get('image_path') if isinstance(content_data, dict) else None
        video_path = content_data.get('video_path') if isinstance(content_data, dict) else None
        document_path = content_data.get('document_path') if isinstance(content_data, dict) else None
        
        # لاگ برای دیباگ
        logger.info(f"[Scheduled Broadcast {broadcast_id}] Content analysis:")
        logger.info(f"  - content_text: {content_text}")
        logger.info(f"  - content_data: {content_data}")
        logger.info(f"  - content_data type: {type(content_data)}")
        logger.info(f"  - photo_path: {photo_path}")
        logger.info(f"  - video_path: {video_path}")
        logger.info(f"  - document_path: {document_path}")
        
        # بررسی وجود فایل‌ها
        if photo_path:
            logger.info(f"  - photo_path exists: {os.path.exists(photo_path)}")
        if video_path:
            logger.info(f"  - video_path exists: {os.path.exists(video_path)}")
        if document_path:
            logger.info(f"  - document_path exists: {os.path.exists(document_path)}")
        
        # لاگ اضافی برای دیباگ
        logger.info(f"[Scheduled Broadcast {broadcast_id}] After processing:")
        logger.info(f"  - Final content_data: {content_data}")
        logger.info(f"  - Final photo_path: {photo_path}")
        logger.info(f"  - Final video_path: {video_path}")
        logger.info(f"  - Final document_path: {document_path}")
        
        # The source platform is where the content originated, useful for cross-platform file_id transfers
        # For scheduled tasks, the file is already local, so we don't need a source_platform for download.
        # We pass the original media name for better presentation.
        original_media_name = content_data.get('original_media_name') if isinstance(content_data, dict) else None
        
        # اگر original_media_name وجود ندارد، از نام فایل اصلی استخراج کن
        if not original_media_name:
            if document_path and os.path.exists(document_path):
                # استخراج نام فایل اصلی از مسیر فایل زماندار
                temp_filename = os.path.basename(document_path)
                # اگر فایل زماندار است، نام اصلی را استخراج کن
                if temp_filename.startswith('scheduled_') and '_' in temp_filename:
                    # فرمت: scheduled_uuid_originalname.ext
                    parts = temp_filename.split('_', 2)  # فقط 2 بار split کن
                    if len(parts) >= 3:
                        original_media_name = parts[2]  # نام اصلی بعد از UUID
                        logger.info(f"[Scheduled Broadcast {broadcast_id}] Extracted original filename from scheduled file: {original_media_name}")
                    else:
                        original_media_name = temp_filename
                        logger.info(f"[Scheduled Broadcast {broadcast_id}] Using scheduled filename as is: {original_media_name}")
                else:
                    original_media_name = temp_filename
                    logger.info(f"[Scheduled Broadcast {broadcast_id}] Using filename as is: {original_media_name}")
            elif photo_path and os.path.exists(photo_path):
                original_media_name = os.path.basename(photo_path)
                logger.info(f"[Scheduled Broadcast {broadcast_id}] Extracted original_media_name from photo_path: {original_media_name}")
            elif video_path and os.path.exists(video_path):
                original_media_name = os.path.basename(video_path)
                logger.info(f"[Scheduled Broadcast {broadcast_id}] Extracted original_media_name from video_path: {original_media_name}")
        
        logger.info(f"[Scheduled Broadcast {broadcast_id}] Final original_media_name: {original_media_name}")
        
        # Copy temp files for each platform to prevent cleanup conflicts
        import shutil
        import tempfile
        
        platform_files = {}
        for platform in platforms_to_send:
            platform_files[platform] = {
                'photo_path': photo_path,
                'video_path': video_path,
                'document_path': document_path
            }
            
            # Copy photo file if it exists
            if photo_path:
                logger.info(f"[Platform {platform}] Checking photo file: {photo_path}")
                logger.info(f"[Platform {platform}] File exists: {os.path.exists(photo_path)}")
                if os.path.exists(photo_path):
                    logger.info(f"Copying photo temp file for {platform}: {photo_path}")
                    temp_dir = tempfile.gettempdir()
                    original_filename = os.path.basename(photo_path)
                    temp_file = os.path.join(temp_dir, f"mbot_{platform}_photo_{os.urandom(8).hex()}_{original_filename}")
                    shutil.copy2(photo_path, temp_file)
                    platform_files[platform]['photo_path'] = temp_file
                    logger.info(f"Copied photo temp file for {platform}: {temp_file}")
                else:
                    logger.warning(f"[Platform {platform}] Photo file not found: {photo_path}")
                    platform_files[platform]['photo_path'] = None
            
            # Copy video file if it exists
            if video_path:
                logger.info(f"[Platform {platform}] Checking video file: {video_path}")
                logger.info(f"[Platform {platform}] File exists: {os.path.exists(video_path)}")
                if os.path.exists(video_path):
                    logger.info(f"Copying video temp file for {platform}: {video_path}")
                    temp_dir = tempfile.gettempdir()
                    original_filename = os.path.basename(video_path)
                    temp_file = os.path.join(temp_dir, f"mbot_{platform}_video_{os.urandom(8).hex()}_{original_filename}")
                    shutil.copy2(video_path, temp_file)
                    platform_files[platform]['video_path'] = temp_file
                    logger.info(f"Copied video temp file for {platform}: {temp_file}")
                else:
                    logger.warning(f"[Platform {platform}] Video file not found: {video_path}")
                    platform_files[platform]['video_path'] = None
            
            # Copy document file if it exists
            if document_path:
                logger.info(f"[Platform {platform}] Checking document file: {document_path}")
                logger.info(f"[Platform {platform}] File exists: {os.path.exists(document_path)}")
                if os.path.exists(document_path):
                    logger.info(f"Copying document temp file for {platform}: {document_path}")
                    temp_dir = tempfile.gettempdir()
                    original_filename = os.path.basename(document_path)
                    # حفظ پسوند فایل اصلی
                    file_ext = os.path.splitext(original_filename)[1]
                    temp_file = os.path.join(temp_dir, f"mbot_{platform}_document_{os.urandom(8).hex()}_{original_filename}")
                    shutil.copy2(document_path, temp_file)
                    platform_files[platform]['document_path'] = temp_file
                    logger.info(f"Copied document temp file for {platform}: {temp_file}")
                else:
                    logger.warning(f"[Platform {platform}] Document file not found: {document_path}")
                    platform_files[platform]['document_path'] = None
        
        # Prepare broadcast arguments
        # اگر content_data دارای image_path است، text را از content_text بگیر
        text_for_broadcast = None
        if isinstance(content_data, dict) and 'image_path' in content_data:
            # اگر عکس داریم، از content_text به عنوان کپشن استفاده کن
            text_for_broadcast = content_text if content_text else None
        elif isinstance(content_data, dict) and 'video_path' in content_data:
            # اگر ویدیو داریم، از content_text به عنوان کپشن استفاده کن
            text_for_broadcast = content_text if content_text else None
        elif isinstance(content_data, dict) and 'document_path' in content_data:
            # اگر مستند داریم، از content_text به عنوان کپشن استفاده کن
            text_for_broadcast = content_text if content_text else None
        elif isinstance(content_data, dict) and 'text' in content_data:
            # اگر فقط متن داریم
            text_for_broadcast = content_data.get('text')
        else:
            # اگر content_data خالی است، از content_text استفاده کن
            text_for_broadcast = content_text if content_text else None
        
        # لاگ text_for_broadcast
        logger.info(f"[Scheduled Broadcast {broadcast_id}] text_for_broadcast: {text_for_broadcast}")
        
        common_kwargs = {
            'scopes': scopes,
            'text': text_for_broadcast,
            'original_media_name': original_media_name,
            'forward_from_chat_id': content_data.get('forward_from_chat_id') if isinstance(content_data, dict) else None,
            'forward_from_message_id': content_data.get('forward_from_message_id') if isinstance(content_data, dict) else None,
            # Since files are local, we don't need a source_platform for downloading
            'source_platform': None,
            'original_file_id': content_data.get('original_file_id') if isinstance(content_data, dict) else None
        }

        # تولید content_preview برای تاریخچه
        preview_content = ""
        if photo_path:
            preview_content = f"تصویر: {os.path.basename(photo_path)}" + (f" (کپشن: {text_for_broadcast[:50]}{'...' if text_for_broadcast and len(text_for_broadcast)>50 else ''})" if text_for_broadcast else "")
        elif video_path:
            preview_content = f"ویدئو: {os.path.basename(video_path)}" + (f" (کپشن: {text_for_broadcast[:50]}{'...' if text_for_broadcast and len(text_for_broadcast)>50 else ''})" if text_for_broadcast else "")
        elif document_path:
            preview_content = f"فایل: {os.path.basename(document_path)}" + (f" (کپشن: {text_for_broadcast[:50]}{'...' if text_for_broadcast and len(text_for_broadcast)>50 else ''})" if text_for_broadcast else "")
        elif text_for_broadcast:
            preview_content = text_for_broadcast[:100]
        else:
            preview_content = "ارسال زماندار"
        
        logger.info(f"[Scheduled Broadcast {broadcast_id}] Preview content: {preview_content}")

        # Execute broadcasts in order: Ita first (to copy files before they're cleaned up), then others
        if 'ita' in platforms_to_send:
            logger.info(f"Executing scheduled broadcast for Ita...")
            ita_kwargs = common_kwargs.copy()
            ita_kwargs.update(platform_files['ita'])
            result_ita = await perform_broadcast_async(
                app=None, platform='ita', owner_id=ITA_OWNER_ID, **ita_kwargs
            )
            result_ita['platform'] = 'ita'
            result_ita['preview_content'] = preview_content
            results.append(result_ita)

        if 'telegram' in platforms_to_send and telegram_app:
            logger.info(f"Executing scheduled broadcast for Telegram...")
            telegram_kwargs = common_kwargs.copy()
            telegram_kwargs.update(platform_files['telegram'])
            result_telegram = await perform_broadcast_async(
                app=telegram_app, platform='telegram', owner_id=OWNER_ID, **telegram_kwargs
            )
            result_telegram['platform'] = 'telegram'
            result_telegram['preview_content'] = preview_content
            results.append(result_telegram)

        if 'bale' in platforms_to_send and bale_app:
            logger.info(f"Executing scheduled broadcast for Bale...")
            bale_kwargs = common_kwargs.copy()
            bale_kwargs.update(platform_files['bale'])
            result_bale = await perform_broadcast_async(
                app=bale_app, platform='bale', owner_id=BALE_OWNER_ID, **bale_kwargs
            )
            result_bale['platform'] = 'bale'
            result_bale['preview_content'] = preview_content
            results.append(result_bale)
            
        # The temp files are cleaned up within each perform_broadcast_async call now, so no need to clean here.

        # محاسبه آمار دقیق‌تر
        total_sent = sum(r.get('sent', 0) for r in results)
        total_failed = sum(r.get('failed', 0) for r in results)
        
        # محاسبه تعداد چت‌های هدف برای هر پلتفرم (بدون ادمین‌ها)
        target_chats = {}
        for r in results:
            platform = r.get('platform', 'unknown')
            if platform in ['telegram', 'bale', 'ita']:
                # تعداد واقعی چت‌های هدف از detailed_results
                detailed_results = r.get('detailed_results', {})
                target_count = sum(
                    scope_stats.get('sent', 0) + scope_stats.get('failed', 0) 
                    for scope_stats in detailed_results.values()
                )
                target_chats[platform] = target_count
                

        result = {
            'sent': total_sent,
            'failed': total_failed,
            'platform_results': results,
            'target_chats': target_chats,
            'total_target_chats': sum(target_chats.values())
        }
        
        # <<< END CHANGE >>>
        
        # به‌روزرسانی وضعیت نهایی
        status = 'completed' if result.get('sent', 0) > 0 else 'failed'
        await async_db_execute(
            "UPDATE scheduled_broadcasts SET status = ?, executed_at = datetime('now') WHERE id = ?",
            (status, broadcast_id)
        )
        
        logger.info(f"Scheduled broadcast {broadcast_id} executed. Status: {status}. Sent: {result.get('sent', 0)}")
        
        # ذخیره نتایج ارسال در تاریخچه (اگر ارسال موفق بوده)
        if status == 'completed' and result.get('sent', 0) > 0:
            try:
                # ایجاد preview از محتوا
                content_preview = content_text if content_text else "ارسال زماندار"
                if len(content_preview) > 50:
                    content_preview = content_preview[:47] + "..."
                
                # ذخیره در broadcast_batches
                scope_str = ",".join(scopes) if scopes else "scheduled"
                platform_str = ",".join(platforms_to_send) if platforms_to_send else "telegram"
                
                # دریافت تمام پیام‌های ارسال شده از نتایج
                all_sent_messages = []
                if 'platform_results' in result:
                    for platform_result in result['platform_results']:
                        platform = platform_result.get('platform', '')
                        sent_messages = platform_result.get('sent_messages', [])
                        for chat_id, message_id in sent_messages:
                            all_sent_messages.append((chat_id, message_id))
                
                # ذخیره در دیتابیس
                if all_sent_messages:
                    batch_id = await async_save_broadcast_to_db(scope_str, content_preview, platform_str, all_sent_messages)
                    logger.info(f"Scheduled broadcast {broadcast_id} results saved to history with batch_id: {batch_id}")
                else:
                    logger.warning(f"No sent messages to save for scheduled broadcast {broadcast_id}")
                    
            except Exception as save_error:
                logger.error(f"Failed to save scheduled broadcast {broadcast_id} to history: {save_error}")
        
        # ارسال گزارش موفقیت به کاربر (اگر context موجود باشد)
        if status == 'completed' and result.get('sent', 0) > 0:
            # پیدا کردن message_id پیام زمان‌بندی شده
            notification_info = await async_db_fetchone("SELECT notification_message_id FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
            if notification_info and notification_info['notification_message_id']:
                # پیدا کردن کاربر از دیتابیس - اولین کاربر بله
                user_info = await async_db_fetchone("SELECT * FROM chats WHERE chat_type = 'private' AND platform = 'bale' ORDER BY created_at DESC LIMIT 1")
                if user_info:
                    user_id = int(user_info['chat_id'])
                    message_id = notification_info['notification_message_id']
                    try:
                        # ادیت پیام قبلی به گزارش موفقیت
                        if bale_app and bale_bot_loop:
                            # ایجاد keyboard برای حذف هر پلتفرم
                            keyboard = []
                            
                            # اگر نتایج پلتفرم‌ها موجود باشد، دکمه‌های جداگانه ایجاد کن
                            if 'platform_results' in result:
                                platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا'}
                                for platform_result in result['platform_results']:
                                    if platform_result.get('batch_id'):
                                        platform = platform_result.get('platform', '')
                                        platform_name = platform_names.get(platform, platform)
                                        batch_id = platform_result['batch_id']
                                        
                                        # بررسی وضعیت حذف
                                        batch_info = await async_db_fetchone("SELECT is_deleted FROM broadcast_batches WHERE batch_id = ?", (batch_id,))
                                        if batch_info and batch_info['is_deleted'] == 1:
                                            keyboard.append([InlineKeyboardButton(f"✅ حذف شده - {platform_name}", callback_data="noop")])
                                        else:
                                            keyboard.append([InlineKeyboardButton(f"🗑 حذف از {platform_name}", callback_data=f"delete_batch_{batch_id}_{platform}")])
                            else:
                                # fallback برای پلتفرم‌های خاص
                                keyboard.append([InlineKeyboardButton("🗑 حذف ارسال‌های انجام شده", callback_data=f"delete_completed_{broadcast_id}")])
                            
                            # ایجاد گزارش شبیه ارسال فوری
                            if 'platform_results' in result:
                                platform_names = []
                                for platform_result in result['platform_results']:
                                    platform = platform_result.get('platform', '')
                                    if platform == 'telegram':
                                        platform_names.append('تلگرام')
                                    elif platform == 'bale':
                                        platform_names.append('بله')
                                    elif platform == 'ita':
                                        platform_names.append('ایتا')
                                
                                platform_display = ' + '.join(platform_names)
                                
                                # دریافت محتوا از دیتابیس
                                content_info = await async_db_fetchone("SELECT content_text FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
                                preview = content_info['content_text'] if content_info and content_info['content_text'] else ''
                                if preview and len(preview) > 50:
                                    preview = preview[:47] + "..."
                                
                                # نمایش آمار دقیق‌تر
                                total_target = result.get('total_target_chats', 0)
                                total_sent = result.get('sent', 0)
                                total_failed = result.get('failed', 0)
                                platform_results = result.get('platform_results', [])
                                
                                # تولید آمار تفصیلی
                                detailed_stats = generate_detailed_stats_report(platform_results)
                                
                                report_text = f"✅ ارسال زمان‌بندی کامل شد.\n\n📱 پلتفرم: {platform_display}\n🎯 چت‌های هدف: {total_target}\n✅ موفق: {total_sent}\n❌ ناموفق: {total_failed}\n\n{detailed_stats}\n\n📝 محتوا: {preview}"
                            else:
                                # fallback برای پلتفرم‌های خاص
                                report_text = f"✅ ارسال زمان‌بندی کامل شد.\n\n✅ موفق: {result.get('sent', 0)}\n❌ ناموفق: {result.get('failed', 0)}\n🆔 شناسه: {broadcast_id}"
                            
                            coro = bale_app.bot.edit_message_text(
                                chat_id=user_id,
                                message_id=message_id,
                                text=report_text,
                                reply_markup=InlineKeyboardMarkup(keyboard)
                            )
                            asyncio.run_coroutine_threadsafe(coro, bale_bot_loop)
                            logger.info(f"Success report edited for user {user_id} for broadcast {broadcast_id}")
                    except Exception as send_error:
                        logger.error(f"Failed to edit success report for user {user_id}: {send_error}")
                        # اگر ادیت ناموفق بود، پیام جدید ارسال کن
                        try:
                            if bale_app and bale_bot_loop:
                                # ایجاد گزارش fallback شبیه ارسال فوری
                                if 'platform_results' in result:
                                    platform_names = []
                                    for platform_result in result['platform_results']:
                                        platform = platform_result.get('platform', '')
                                        if platform == 'telegram':
                                            platform_names.append('تلگرام')
                                        elif platform == 'bale':
                                            platform_names.append('بله')
                                        elif platform == 'ita':
                                            platform_names.append('ایتا')
                                    
                                    platform_display = ' + '.join(platform_names)
                                    
                                    # دریافت محتوا از دیتابیس
                                    content_info = await async_db_fetchone("SELECT content_text FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))
                                    preview = content_info['content_text'] if content_info and content_info['content_text'] else ''
                                    if preview and len(preview) > 50:
                                        preview = preview[:47] + "..."
                                    
                                    # نمایش آمار دقیق‌تر
                                    total_target = result.get('total_target_chats', 0)
                                    total_sent = result.get('sent', 0)
                                    total_failed = result.get('failed', 0)
                                    platform_results = result.get('platform_results', [])
                                    
                                    # تولید آمار تفصیلی
                                    detailed_stats = generate_detailed_stats_report(platform_results)
                                    
                                    fallback_text = f"✅ ارسال زمان‌بندی کامل شد.\n\n📱 پلتفرم: {platform_display}\n🎯 چت‌های هدف: {total_target}\n✅ موفق: {total_sent}\n❌ ناموفق: {total_failed}\n\n{detailed_stats}\n\n📝 محتوا: {preview}"
                                else:
                                    fallback_text = f"✅ ارسال زمان‌بندی کامل شد.\n\n✅ موفق: {result.get('sent', 0)}\n❌ ناموفق: {result.get('failed', 0)}\n🆔 شناسه: {broadcast_id}"
                                
                                coro = bale_app.bot.send_message(user_id, fallback_text)
                                asyncio.run_coroutine_threadsafe(coro, bale_bot_loop)
                                logger.info(f"Success report sent as new message to user {user_id} for broadcast {broadcast_id}")
                        except Exception as fallback_error:
                            logger.error(f"Failed to send fallback success report to user {user_id}: {fallback_error}")
        
    except Exception as e:
        logger.error(f"Error executing scheduled broadcast {broadcast_id} from DB: {e}", exc_info=True)
        await async_db_execute(
            "UPDATE scheduled_broadcasts SET status = 'failed', executed_at = datetime('now') WHERE id = ?",
            (broadcast_id,)
        )

def execute_scheduled_broadcast_job(broadcast_id: int):
    """
    تابع wrapper برای اجرای ارسال زمان‌بندی شده توسط APScheduler.
    این تابع Sync است و وظیفه آن ارسال Coroutine به Event Loop صحیح است.
    """
    logger.info(f"[Scheduler Job] Starting job for broadcast_id: {broadcast_id}")
    try:
        # ۱. اطلاعات ارسال را به صورت همگام (sync) از دیتابیس بخوان
        broadcast = db_fetchone("SELECT * FROM scheduled_broadcasts WHERE id = ?", (broadcast_id,))

        if not broadcast:
            logger.warning(f"[Scheduler Job] Broadcast {broadcast_id} not found in DB. Maybe it was cancelled.")
            return

        platform = broadcast['platform']
        
        # ۲. لوپ و اپلیکیشن ربات مقصد را پیدا کن
        target_loop = None
        target_app = None
        
        # بررسی platforms field برای multi-platform broadcasts
        platforms = []
        if 'platforms' in broadcast.keys() and broadcast['platforms']:
            try:
                platforms = json.loads(broadcast['platforms'])
            except json.JSONDecodeError:
                platforms = [broadcast['platforms']]
        
        # اگر چندین پلتفرم انتخاب شده، از اولین پلتفرم برای انتخاب event loop استفاده کن
        if len(platforms) > 1:
            platform = platforms[0]  # استفاده از اولین پلتفرم برای انتخاب event loop
            logger.info(f"[Scheduler Job] Multi-platform broadcast detected, using first platform for event loop: {platform}")
        
        if platform == 'telegram':
            target_loop = telegram_bot_loop
            target_app = telegram_app
        elif platform == 'bale':
            target_loop = bale_bot_loop
            target_app = bale_app
        elif platform == 'all':
            # برای 'all'، از بله استفاده می‌کنیم چون در execute_scheduled_broadcast_from_db خودش همه پلتفرم‌ها را handle می‌کند
            target_loop = bale_bot_loop
            target_app = bale_app
        # پلتفرم‌های دیگر در اینجا اضافه شوند
        
        if not target_loop or not target_app:
            logger.error(f"[Scheduler Job] Could not find a running event loop or app for platform: {platform}. Broadcast {broadcast_id} will be marked as failed.")
            db_execute("UPDATE scheduled_broadcasts SET status = 'failed' WHERE id = ?", (broadcast_id,))
            return
            
        # ۳. تابع async را به صورت امن به لوپ در حال اجرای ربات ارسال کن
        # این کار با asyncio.run_coroutine_threadsafe انجام می‌شود
        coro = execute_scheduled_broadcast_from_db(broadcast_id, target_app)
        asyncio.run_coroutine_threadsafe(coro, target_loop)
        
        logger.info(f"[Scheduler Job] Coroutine for broadcast {broadcast_id} successfully submitted to {platform}'s event loop.")

    except Exception as e:
        logger.error(f"Error in execute_scheduled_broadcast_job for broadcast {broadcast_id}: {e}", exc_info=True)
        # در صورت بروز خطا، وضعیت ارسال را در دیتابیس failed ثبت کن
        db_execute("UPDATE scheduled_broadcasts SET status = 'failed' WHERE id = ?", (broadcast_id,))

def cancel_scheduled_broadcast(broadcast_id: int):
    """
    لغو ارسال زمان‌بندی شده
    """
    try:
        # حذف از scheduler
        if scheduler:
            try:
                scheduler.remove_job(f"once_{broadcast_id}")
            except:
                pass  # Job ممکن است وجود نداشته باشد
            try:
                scheduler.remove_job(f"recurring_{broadcast_id}")
            except:
                pass  # Job ممکن است وجود نداشته باشد
        
        # به‌روزرسانی در دیتابیس
        db_execute("UPDATE scheduled_broadcasts SET status = 'cancelled' WHERE id = ?", (broadcast_id,))
        logger.info(f"Scheduled broadcast {broadcast_id} cancelled")
    except Exception as e:
        logger.error(f"Error cancelling scheduled broadcast {broadcast_id}: {e}")
        raise

def get_scheduled_broadcasts(status: str = None) -> List[Dict]:
    """
    دریافت لیست ارسال‌های زمان‌بندی شده
    """
    try:
        if status:
            result = db_fetchall("""
                SELECT * FROM scheduled_broadcasts 
                WHERE status = ? 
                ORDER BY scheduled_time ASC
            """, (status,))
        else:
            result = db_fetchall("""
                SELECT * FROM scheduled_broadcasts 
                ORDER BY scheduled_time ASC
            """)
        
        logger.info(f"get_scheduled_broadcasts: Found {len(result)} broadcasts with status={status}")
        return result
    except Exception as e:
        logger.error(f"Error in get_scheduled_broadcasts: {e}")
        return []

async def download_file_to_temp(platform: str, file_id: str, original_filename: str = None) -> Optional[str]:
    """
    دانلود فایل به فایل موقت با مدیریت بهتر حافظه
    """
    global telegram_app, bale_app, telegram_bot_loop, bale_bot_loop
    
    if platform == 'telegram':
        bot_instance = telegram_app.bot if telegram_app else None
        source_loop = telegram_bot_loop
    elif platform == 'bale':
        bot_instance = bale_app.bot if bale_app else None
        source_loop = bale_bot_loop
    else:
        return None
        
    if not bot_instance or not source_loop:
        logger.error(f"[{platform}] Bot instance or loop not available for file download")
        return None
    
    try:
        logger.info(f"[{platform}] Downloading file_id: {file_id} to temp file")
        
        async def download_to_temp():
            file = await bot_instance.get_file(file_id)
            
            # ایجاد فایل موقت
            file_ext = os.path.splitext(original_filename)[1] if original_filename else '.tmp'
            temp_file = tempfile.NamedTemporaryFile(delete=False, prefix=f"mbot_{platform}_", suffix=file_ext)
            temp_path = temp_file.name
            temp_file.close()
            
            # دانلود مستقیم به فایل
            if platform == 'bale' and hasattr(file, 'file_path') and file.file_path:
                if file.file_path.startswith('https://api.telegram.org/'):
                    corrected_path = file.file_path.replace('https://api.telegram.org/', 'https://tapi.bale.ai/')
                    
                    def sync_download():
                        response = requests.get(corrected_path, timeout=120, stream=True)
                        if response.status_code == 200:
                            with open(temp_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            return temp_path
                        else:
                            raise Exception(f"HTTP {response.status_code}")
                    
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, sync_download)
                    return temp_path
            
            # دانلود عادی
            await file.download_to_drive(temp_path)
            return temp_path
            
        # اجرا در لوپ مناسب
        if source_loop != asyncio.get_running_loop():
            future = asyncio.run_coroutine_threadsafe(download_to_temp(), source_loop)
            temp_path = future.result(timeout=180)
        else:
            temp_path = await download_to_temp()
            
        logger.info(f"[{platform}] File downloaded to temp: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Error downloading file {file_id} from {platform}: {e}")
        return None

async def error_handler_base(update: object, context: TelegramContextTypes.DEFAULT_TYPE, platform: str) -> None:
    error = context.error
    if "Conflict" in str(error) and "getUpdates" in str(error):
        logger.warning(f"[{platform}] Conflict detected - another bot instance may be running. This is usually not critical.")
        return
    logger.error(f"[{platform}] Exception while handling update:", exc_info=error)

# =================================================================
# --- Telegram Bot Setup ---
# =================================================================
def run_telegram_bot():
    global telegram_app, telegram_bot_loop
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    telegram_bot_loop = loop  # تنظیم global event loop برای thread-safe execution
    try:
        app = TelegramApplication.builder().token(TELEGRAM_BOT_TOKEN).post_init(tele_post_init).build()
        
        app.add_error_handler(lambda u, c: error_handler_base(u, c, 'telegram'))
        app.add_handler(CommandHandler("start", lambda u, c: start_handler_base(u, c, 'telegram', OWNER_ID)))
        app.add_handler(CommandHandler("sync", lambda u, c: sync_handler_base(u, c, 'telegram', OWNER_ID)))
        app.add_handler(CommandHandler("export", lambda u, c: export_handler_base(u, c, 'telegram', OWNER_ID)))
        app.add_handler(ChatMemberHandler(lambda u, c: chat_member_handler_base(u, c, 'telegram')))
        app.add_handler(CallbackQueryHandler(lambda u, c: button_handler_base(u, c, 'telegram', OWNER_ID)))
        app.add_handler(MessageHandler(filters.ALL, lambda u, c: message_handler_base(u, c, 'telegram', OWNER_ID))) 

        logger.info("[Telegram] Polling for updates starting...")
        # اضافه کردن تنظیمات برای حل مشکل Conflict
        app.run_polling(drop_pending_updates=True, allowed_updates=['message', 'callback_query', 'my_chat_member'], stop_signals=None)
    except Exception as e:
        if "Conflict" in str(e):
            logger.warning("[Telegram] Conflict detected - another bot instance may be running. Retrying in 5 seconds...")
            time.sleep(5)
            try:
                app.run_polling(drop_pending_updates=True, allowed_updates=['message', 'callback_query', 'my_chat_member'], stop_signals=None)
            except Exception as retry_error:
                logger.critical(f"[Telegram] Critical error during retry: {retry_error}", exc_info=True)
        else:
            logger.critical(f"[Telegram] Critical error during bot execution: {e}", exc_info=True)
    finally:
        if loop and not loop.is_closed(): loop.close()
        logger.info("[Telegram] Bot stopped.")

def restart_telegram_bot():
    """
    تابع برای restart کردن Telegram bot در صورت بسته شدن Event Loop
    """
    global telegram_app, telegram_bot_loop
    try:
        logger.info("[Telegram] Restarting bot due to Event Loop closure...")
        
        # بستن Event Loop قبلی اگر باز است
        if telegram_bot_loop and not telegram_bot_loop.is_closed():
            telegram_bot_loop.close()
        
        # ایجاد Event Loop جدید
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        telegram_bot_loop = new_loop
        
        # ایجاد Application جدید
        telegram_app = TelegramApplication.builder().token(TELEGRAM_BOT_TOKEN).post_init(tele_post_init).build()
        
        # اضافه کردن handlers
        telegram_app.add_error_handler(lambda u, c: error_handler_base(u, c, 'telegram'))
        telegram_app.add_handler(CommandHandler("start", lambda u, c: start_handler_base(u, c, 'telegram', OWNER_ID)))
        telegram_app.add_handler(CommandHandler("sync", lambda u, c: sync_handler_base(u, c, 'telegram', OWNER_ID)))
        telegram_app.add_handler(CommandHandler("export", lambda u, c: export_handler_base(u, c, 'telegram', OWNER_ID)))
        telegram_app.add_handler(ChatMemberHandler(lambda u, c: chat_member_handler_base(u, c, 'telegram')))
        telegram_app.add_handler(CallbackQueryHandler(lambda u, c: button_handler_base(u, c, 'telegram', OWNER_ID)))
        telegram_app.add_handler(MessageHandler(filters.ALL, lambda u, c: message_handler_base(u, c, 'telegram', OWNER_ID)))
        
        logger.info("[Telegram] Bot restarted successfully")
        return True
        
    except Exception as e:
        logger.error(f"[Telegram] Failed to restart bot: {e}")
        return False

# =================================================================
# --- Bale Bot Setup (using python-telegram-bot with Bale API) ---
# =================================================================
def run_bale_bot():
    global bale_app, bale_bot_loop
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    bale_bot_loop = loop  # تنظیم global event loop برای thread-safe execution
    try:
        app = TelegramApplication.builder().token(BALE_BOT_TOKEN).base_url(BALE_API_BASE_URL).post_init(bale_post_init).build()
        
        app.add_error_handler(lambda u, c: error_handler_base(u, c, 'bale'))
        app.add_handler(CommandHandler("start", lambda u, c: start_handler_base(u, c, 'bale', BALE_OWNER_ID)))
        app.add_handler(CommandHandler("sync", lambda u, c: sync_handler_base(u, c, 'bale', BALE_OWNER_ID)))
        app.add_handler(CommandHandler("export", lambda u, c: export_handler_base(u, c, 'bale', BALE_OWNER_ID)))
        app.add_handler(ChatMemberHandler(lambda u, c: chat_member_handler_base(u, c, 'bale')))
        app.add_handler(CallbackQueryHandler(lambda u, c: button_handler_base(u, c, 'bale', BALE_OWNER_ID)))
        app.add_handler(MessageHandler(filters.ALL, lambda u, c: message_handler_base(u, c, 'bale', BALE_OWNER_ID)))

        logger.info("[Bale] Polling for updates starting...")
        app.run_polling(stop_signals=None)
    except Exception as e:
        logger.critical(f"[Bale] Critical error during bot execution: {e}", exc_info=True)
    finally:
        if loop and not loop.is_closed(): loop.close()
        logger.info("[Bale] Bot stopped.")


# =================================================================
# --- Metrics: Daily members snapshot ---
# =================================================================
async def capture_daily_members_snapshot_for_platform(pf: str):
    """Capture members count for all chats of a platform once per day (date_key=YYYY-MM-DD)."""
    app_obj = telegram_app if pf == 'telegram' else bale_app
    loop_obj = telegram_bot_loop if pf == 'telegram' else bale_bot_loop
    if not app_obj or not loop_obj:
        logger.warning(f"[{pf}] capture_daily_members_snapshot skipped: app/loop not ready")
        return
    date_key = time.strftime('%Y-%m-%d')
    # فقط چت‌هایی که private نیستند را در نظر بگیریم
    rows = db_fetchall("SELECT chat_id, chat_type FROM chats WHERE platform=? AND chat_type != 'private'", (pf,))
    for r in rows:
        cid_str, ctype = r['chat_id'], r['chat_type']
        try:
            # اگر قبلاً امروز ذخیره شده، رد شود
            exists = db_fetchone("SELECT 1 FROM chats_metrics WHERE chat_id=? AND platform=? AND date_key=?", (cid_str, pf, date_key))
            if exists: continue
            # تلاش برای شمارش اعضا برای گروه/سوپرگروه/کانال
            cid = int(cid_str)
            try:
                members = await asyncio.wait_for(app_obj.bot.get_chat_member_count(cid), timeout=10)
            except Exception as e:
                # Silently ignore event loop errors and network errors
                if any(keyword in str(e).lower() for keyword in ["event loop is closed", "network error", "timeout"]):
                    logger.debug(f"[{pf}] Ignoring member count error for {cid_str}: {e}")
                else:
                    logger.debug(f"[{pf}] get_chat_member_count failed for {cid_str}: {e}")
                continue
            try:
                db_execute("INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count) VALUES (?, ?, ?, ?)", (cid_str, pf, date_key, int(members)))
            except Exception as e:
                logger.warning(f"[{pf}] Failed to insert metrics for {cid_str}: {e}")
        except Exception as e:
            logger.debug(f"[{pf}] get_chat_member_count failed for {cid_str}: {e}")
        # کمی مکث بین درخواست‌ها برای جلوگیری از حساسیت پیام‌رسان
        await asyncio.sleep(0.2 + random.random()*0.3)

async def schedule_ita_member_check_task():
    """
    برنامه‌ریزی بررسی دوره‌ای تعداد اعضای ایتا
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = AsyncIOScheduler()
        
        # بررسی روزانه ساعت 1 صبح (برای آمار روزانه)
        scheduler.add_job(
            lambda: asyncio.run(check_and_update_ita_member_counts(is_daily_update=True)),
            'cron',
            hour=1,
            minute=0,
            id='ita_daily_member_check',
            replace_existing=True
        )
        
        # بررسی اضافی هر 12 ساعت (کاهش فرکانس برای کاهش خطر)
        scheduler.add_job(
            check_and_update_ita_member_counts,
            'interval',
            hours=12,
            id='ita_periodic_member_check',
            replace_existing=True
        )
        
        # زمان‌بندی به‌روزرسانی آمار بازدید پست‌ها (هر 6 ساعت - کاهش فرکانس)
        scheduler.add_job(
            lambda: asyncio.run(update_channel_posts_views(None, 'telegram')),
            'interval',
            hours=6,
            id='update_telegram_posts_views',
            replace_existing=True
        )
        
        scheduler.add_job(
            lambda: asyncio.run(update_channel_posts_views(None, 'bale')),
            'interval',
            hours=6,
            id='update_bale_posts_views',
            replace_existing=True
        )
        
        scheduler.add_job(
            lambda: asyncio.run(update_channel_posts_views(None, 'ita')),
            'interval',
            hours=6,
            id='update_ita_posts_views',
            replace_existing=True
        )
        
        # ذخیره snapshot روزانه آمار ربات‌ها (ساعت 1:05 صبح)
        scheduler.add_job(
            save_daily_bot_statistics_snapshot,
            'cron',
            hour=1,
            minute=5,
            id='daily_bot_statistics_snapshot',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("[ITA] Scheduled periodic member count check every 6 hours")
        logger.info("[SNAPSHOT] Scheduled daily bot statistics snapshot at 1:05 AM")
        
    except Exception as e:
        logger.error(f"[ITA] Error scheduling member count check: {e}")

async def schedule_daily_metrics_task(pf: str):
    """Schedule a task to run at 00:01 local time every day."""
    while True:
        try:
            # محاسبه تاخیر تا 01:00 روز بعد به همراه جیتر تصادفی برای کاهش ریسک
            now = time.localtime()
            # ثانیه های تا نیمه شب
            secs_today = now.tm_hour*3600 + now.tm_min*60 + now.tm_sec
            # هدف: 01:00 فردا => 25*3600 - secs_today
            target = 25*3600 - secs_today
            jitter = int(random.uniform(30, 300))  # 30 تا 300 ثانیه جیتر
            delay = target + jitter
            await asyncio.sleep(delay)
            await capture_daily_members_snapshot_for_platform(pf)
        except Exception as e:
            logger.error(f"[{pf}] Error in daily metrics scheduler: {e}")
            await asyncio.sleep(3600)

async def metrics_post_init(application: "TelegramApplication", pf: str):
    """Run once on bot ready: capture today's snapshot if missing, then schedule daily task."""
    # ثبت امروز اگر موجود نیست
    try:
        date_key = time.strftime('%Y-%m-%d')
        has_any = db_fetchone("SELECT 1 FROM chats_metrics WHERE platform=? AND date_key=? LIMIT 1", (pf, date_key))
        if not has_any:
            await capture_daily_members_snapshot_for_platform(pf)
    except Exception as e:
        logger.warning(f"[{pf}] initial daily snapshot failed: {e}")
    # زمان‌بندی برای هر روز 00:01
    asyncio.create_task(schedule_daily_metrics_task(pf))

# =================================================================
# --- اجرای اصلی ---
# =================================================================

def run_flask():
    """Run the Flask web server"""
    try:
        logger.info("Starting Flask server...")
        app.run(host='0.0.0.0', port=5010, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask server error: {e}")


def main():
    """تابع اصلی اجرای برنامه"""
    try:
        init_db()
        
        # راه‌اندازی scheduler
        init_scheduler()  # فراخوانی مستقیم و همگام
        
        threads = []

        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()

        if TELEGRAM_BOT_TOKEN and len(TELEGRAM_BOT_TOKEN) > 10:
            tele_thread = Thread(target=run_telegram_bot)
            threads.append(tele_thread)
            logger.info("Telegram bot configured and added to threads.")
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not set or invalid. Telegram bot will not run.")

        if BALE_BOT_TOKEN and len(BALE_BOT_TOKEN) > 10:
            bale_thread = Thread(target=run_bale_bot)
            threads.append(bale_thread)
            logger.info("Bale bot configured and added to threads.")
        else:
            logger.warning("BALE_BOT_TOKEN not set or invalid. Bale bot will not run.")

        if not threads:
            logger.critical("No bot services were configured to run. Exiting application.")
            return
            
        # Start all threads
        for t in threads:
            t.start()
            
        logger.info("All services (Flask + Bots) started. Main thread is now waiting for bot threads to complete (press Ctrl+C to stop).")
        
        # Start Ita member count check scheduler
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(schedule_ita_member_check_task())
            logger.info("Ita member count check scheduler started")
        except Exception as e:
            logger.error(f"Failed to start Ita member count check scheduler: {e}")
        
        # Wait for all threads to complete
        for t in threads:
            t.join()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Application received shutdown signal (Ctrl+C/System Exit). Shutting down gracefully.")
    except Exception as e:
        logger.critical(f"Main application execution error: {e}", exc_info=True)
    finally:
        print("\nApplication stopped. Goodbye!")


def save_chat_to_backup(chat_id: str, chat_type: str, platform: str, name: str = None, username: str = None, tags: str = None):
    """ذخیره اطلاعات چت در فایل backup"""
    try:
        backup_file = "chats_backup.json"
        current_time = datetime.now().isoformat()
        
        # خواندن فایل backup موجود
        if os.path.exists(backup_file):
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        else:
            backup_data = {}
        
        # اضافه کردن چت جدید
        chat_key = f"{platform}_{chat_id}"
        backup_data[chat_key] = {
            "chat_id": chat_id,
            "platform": platform,
            "chat_type": chat_type,
            "name": name,
            "username": username,
            "tags": tags or "",
            "last_updated": current_time
        }
        
        # ذخیره فایل backup
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[Backup] Saved chat {chat_id} ({platform}) to backup file")
        
    except Exception as e:
        logger.error(f"Error saving chat to backup: {e}")


def get_chat_tags(chat_id: str, platform: str):
    """دریافت تگ‌های یک چت"""
    try:
        result = db_fetchone("SELECT tags FROM chats WHERE chat_id = ? AND platform = ?", (chat_id, platform))
        return result['tags'] if result and result['tags'] else ""
    except Exception as e:
        logger.error(f"Error getting chat tags: {e}")
        return ""

def get_all_tags():
    """دریافت تمام تگ‌های موجود"""
    try:
        results = db_fetchall("SELECT DISTINCT tags FROM chats WHERE tags IS NOT NULL AND tags != ''")
        all_tags = set()
        for result in results:
            if result['tags']:
                tags = [tag.strip() for tag in result['tags'].split(',') if tag.strip()]
                all_tags.update(tags)
        return sorted(list(all_tags))
    except Exception as e:
        logger.error(f"Error getting all tags: {e}")
        return []

def get_chats_by_tags(tags: list):
    """دریافت چت‌ها بر اساس تگ‌ها"""
    try:
        if not tags:
            return []
        
        # ساخت query برای جستجوی تگ‌ها
        tag_conditions = []
        params = []
        for tag in tags:
            tag_conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        
        query = f"SELECT * FROM chats WHERE {' OR '.join(tag_conditions)}"
        results = db_fetchall(query, params)
        
        # فیلتر کردن نتایج برای اطمینان از وجود تگ
        filtered_results = []
        for result in results:
            chat_tags = [t.strip() for t in result['tags'].split(',') if t.strip()] if result['tags'] else []
            if any(tag in chat_tags for tag in tags):
                filtered_results.append(result)
        
        return filtered_results
    except Exception as e:
        logger.error(f"Error getting chats by tags: {e}")
        return []

def calculate_growth_stats(platform: str, days: int = 7):
    """محاسبه آمار رشد برای یک پلتفرم"""
    try:
        # دریافت آمار فعلی
        current_date = datetime.now().strftime('%Y-%m-%d')
        past_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # آمار فعلی
        current_stats = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members, COUNT(*) as chat_count
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = ? AND c.is_active = 1 AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = m.chat_id AND platform = m.platform
            )
            GROUP BY c.chat_type
        """, (platform,))
        
        # آمار گذشته
        past_stats = db_fetchall("""
            SELECT c.chat_type, SUM(m.members_count) as total_members, COUNT(*) as chat_count
            FROM chats_metrics m
            JOIN chats c ON c.chat_id = m.chat_id AND c.platform = m.platform
            WHERE m.platform = ? AND c.is_active = 1 AND m.date_key = (
                SELECT MAX(date_key) FROM chats_metrics 
                WHERE chat_id = m.chat_id AND platform = m.platform AND date_key <= ?
            )
            GROUP BY c.chat_type
        """, (platform, past_date))
        
        # تبدیل به dictionary
        current_dict = {r['chat_type']: {'members': r['total_members'], 'chats': r['chat_count']} for r in current_stats}
        past_dict = {r['chat_type']: {'members': r['total_members'], 'chats': r['chat_count']} for r in past_stats}
        
        # محاسبه رشد
        growth_stats = {}
        for chat_type in ['private', 'group', 'channel']:
            current_members = current_dict.get(chat_type, {}).get('members', 0) or 0
            past_members = past_dict.get(chat_type, {}).get('members', 0) or 0
            current_chats = current_dict.get(chat_type, {}).get('chats', 0) or 0
            past_chats = past_dict.get(chat_type, {}).get('chats', 0) or 0
            
            member_growth = current_members - past_members
            member_growth_pct = (member_growth / past_members * 100) if past_members > 0 else 0
            chat_growth = current_chats - past_chats
            chat_growth_pct = (chat_growth / past_chats * 100) if past_chats > 0 else 0
            
            growth_stats[chat_type] = {
                'current_members': current_members,
                'past_members': past_members,
                'member_growth': member_growth,
                'member_growth_pct': round(member_growth_pct, 2),
                'current_chats': current_chats,
                'past_chats': past_chats,
                'chat_growth': chat_growth,
                'chat_growth_pct': round(chat_growth_pct, 2)
            }
        
        # محاسبه مجموع
        total_current_members = sum(current_dict.get(ct, {}).get('members', 0) or 0 for ct in ['private', 'group', 'channel'])
        total_past_members = sum(past_dict.get(ct, {}).get('members', 0) or 0 for ct in ['private', 'group', 'channel'])
        total_current_chats = sum(current_dict.get(ct, {}).get('chats', 0) or 0 for ct in ['private', 'group', 'channel'])
        total_past_chats = sum(past_dict.get(ct, {}).get('chats', 0) or 0 for ct in ['private', 'group', 'channel'])
        
        total_member_growth = total_current_members - total_past_members
        total_member_growth_pct = (total_member_growth / total_past_members * 100) if total_past_members > 0 else 0
        total_chat_growth = total_current_chats - total_past_chats
        total_chat_growth_pct = (total_chat_growth / total_past_chats * 100) if total_past_chats > 0 else 0
        
        growth_stats['total'] = {
            'current_members': total_current_members,
            'past_members': total_past_members,
            'member_growth': total_member_growth,
            'member_growth_pct': round(total_member_growth_pct, 2),
            'current_chats': total_current_chats,
            'past_chats': total_past_chats,
            'chat_growth': total_chat_growth,
            'chat_growth_pct': round(total_chat_growth_pct, 2)
        }
        
        return growth_stats
    except Exception as e:
        logger.error(f"Error calculating growth stats for {platform}: {e}")
        return {}

def save_daily_bot_statistics_snapshot():
    """ذخیره snapshot روزانه آمار ربات‌ها"""
    try:
        from datetime import datetime
        
        # دریافت آمار فعلی
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # تبدیل تاریخ به شمسی
        try:
            import jdatetime
            jdt = jdatetime.datetime.fromgregorian(date=datetime.now().date())
            current_date_jalali = jdt.strftime('%Y/%m/%d')
        except ImportError:
            current_date_jalali = current_date
        
        # آمار تمام پلتفرم‌ها
        platforms = ['telegram', 'bale', 'ita']
        snapshot_data = {
            'date': current_date,
            'date_jalali': current_date_jalali,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'platforms': {}
        }
        
        for platform in platforms:
            # آمار چت‌ها
            chat_counts = db_fetchall("""
                SELECT chat_type, COUNT(*) as count
                FROM chats 
                WHERE platform = ? AND is_active = 1
                GROUP BY chat_type
            """, (platform,))
            
            chat_counts_dict = {r['chat_type']: r['count'] for r in chat_counts}
            
            # آمار اعضا (از snapshot روزانه)
            member_stats = db_fetchall("""
                SELECT c.chat_type, 
                       COALESCE(SUM(m.members_count), 0) as total_members
                FROM chats c
                LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                    AND m.date_key = (
                        SELECT MAX(date_key) FROM chats_metrics 
                        WHERE chat_id = c.chat_id AND platform = c.platform 
                        AND is_daily_snapshot = 1
                    )
                WHERE c.platform = ? AND c.is_active = 1
                GROUP BY c.chat_type
            """, (platform,))
            
            # اگر snapshot روزانه موجود نیست، از آخرین metrics استفاده کن
            if not any(r['total_members'] > 0 for r in member_stats):
                member_stats = db_fetchall("""
                    SELECT c.chat_type, 
                           COALESCE(SUM(m.members_count), 0) as total_members
                    FROM chats c
                    LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                        AND m.date_key = (
                            SELECT MAX(date_key) FROM chats_metrics 
                            WHERE chat_id = c.chat_id AND platform = c.platform
                        )
                    WHERE c.platform = ? AND c.is_active = 1 AND c.chat_type != 'private'
                    GROUP BY c.chat_type
                """, (platform,))
            
            member_stats_dict = {r['chat_type']: r['total_members'] for r in member_stats}
            
            # اگر metrics خالی است، از تعداد چت‌ها استفاده کن (هر چت = 1 عضو)
            if not any(member_stats_dict.values()):
                member_stats_dict = {chat_type: count for chat_type, count in chat_counts_dict.items()}
            
            # تبدیل صفر به یک برای گزارش یکپارچه
            for chat_type in member_stats_dict:
                if member_stats_dict[chat_type] == 0:
                    member_stats_dict[chat_type] = 1
            
            # ذخیره آمار پلتفرم
            snapshot_data['platforms'][platform] = {
                'chats': chat_counts_dict,
                'members': member_stats_dict,
                'total_chats': sum(chat_counts_dict.values()),
                'total_members': sum(member_stats_dict.values())
            }
        
        # محاسبه مجموع کل
        total_chats = sum(data['total_chats'] for data in snapshot_data['platforms'].values())
        total_members = sum(data['total_members'] for data in snapshot_data['platforms'].values())
        
        snapshot_data['totals'] = {
            'total_chats': total_chats,
            'total_members': total_members
        }
        
        # ذخیره در فایل JSON
        import json
        import os
        
        snapshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
        os.makedirs(snapshots_dir, exist_ok=True)
        
        snapshot_file = os.path.join(snapshots_dir, f'bot_statistics_{current_date}.json')
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Daily bot statistics snapshot saved: {snapshot_file}")
        return snapshot_data
        
    except Exception as e:
        logger.error(f"Error saving daily bot statistics snapshot: {e}")
        return None

def generate_bot_statistics_sheet(selected_platforms: list):
    """تولید شیت آمار ربات‌ها برای فایل اکسل"""
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        
        # دریافت آمار فعلی (snapshot روزانه ساعت 1 صبح)
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        # تبدیل تاریخ به شمسی
        try:
            import jdatetime
            jdt = jdatetime.datetime.fromgregorian(date=datetime.now().date())
            current_date_jalali = jdt.strftime('%Y/%m/%d')
        except ImportError:
            current_date_jalali = current_date
        
        # ساخت داده‌های آمار
        stats_data = []
        
        for platform in selected_platforms:
            platform_name = 'تلگرام' if platform == 'telegram' else ('بله' if platform == 'bale' else 'ایتا')
            
            # آمار چت‌ها
            chat_counts = db_fetchall("""
                SELECT chat_type, COUNT(*) as count
                FROM chats 
                WHERE platform = ? AND is_active = 1
                GROUP BY chat_type
            """, (platform,))
            
            chat_counts_dict = {r['chat_type']: r['count'] for r in chat_counts}
            
            # آمار اعضا (از snapshot روزانه)
            member_stats = db_fetchall("""
                SELECT c.chat_type, 
                       COALESCE(SUM(m.members_count), 0) as total_members,
                       COUNT(DISTINCT c.chat_id) as chat_count
                FROM chats c
                LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                    AND m.date_key = (
                        SELECT MAX(date_key) FROM chats_metrics 
                        WHERE chat_id = c.chat_id AND platform = c.platform 
                        AND is_daily_snapshot = 1
                    )
                WHERE c.platform = ? AND c.is_active = 1
                GROUP BY c.chat_type
            """, (platform,))
            
            # اگر snapshot روزانه موجود نیست، از آخرین metrics استفاده کن
            if not any(r['total_members'] > 0 for r in member_stats):
                member_stats = db_fetchall("""
                    SELECT c.chat_type, 
                           COALESCE(SUM(m.members_count), 0) as total_members,
                           COUNT(DISTINCT c.chat_id) as chat_count
                    FROM chats c
                    LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                        AND m.date_key = (
                            SELECT MAX(date_key) FROM chats_metrics 
                            WHERE chat_id = c.chat_id AND platform = c.platform
                        )
                    WHERE c.platform = ? AND c.is_active = 1
                    GROUP BY c.chat_type
                """, (platform,))
            
            member_stats_dict = {r['chat_type']: r['total_members'] for r in member_stats}
            
            # اگر metrics خالی است، از تعداد چت‌ها استفاده کن (هر چت = 1 عضو)
            if not any(member_stats_dict.values()):
                member_stats_dict = {chat_type: count for chat_type, count in chat_counts_dict.items()}
            
            # تبدیل صفر به یک برای گزارش یکپارچه
            for chat_type in member_stats_dict:
                if member_stats_dict[chat_type] == 0:
                    member_stats_dict[chat_type] = 1
            
            # آمار تفصیلی
            private_chats = chat_counts_dict.get('private', 0)
            group_chats = chat_counts_dict.get('group', 0)
            channel_chats = chat_counts_dict.get('channel', 0)
            total_chats = private_chats + group_chats + channel_chats
            
            private_members = member_stats_dict.get('private', 0)
            group_members = member_stats_dict.get('group', 0)
            channel_members = member_stats_dict.get('channel', 0)
            total_members = private_members + group_members + channel_members
            
            # اضافه کردن ردیف‌های آمار
            stats_data.extend([
                {
                    'پلتفرم': platform_name,
                    'نوع': 'کاربران',
                    'تعداد چت': private_chats,
                    'تعداد اعضا': private_members,
                    'میانگین اعضا': round(private_members / private_chats, 1) if private_chats > 0 else 0
                },
                {
                    'پلتفرم': platform_name,
                    'نوع': 'گروه‌ها',
                    'تعداد چت': group_chats,
                    'تعداد اعضا': group_members,
                    'میانگین اعضا': round(group_members / group_chats, 1) if group_chats > 0 else 0
                },
                {
                    'پلتفرم': platform_name,
                    'نوع': 'کانال‌ها',
                    'تعداد چت': channel_chats,
                    'تعداد اعضا': channel_members,
                    'میانگین اعضا': round(channel_members / channel_chats, 1) if channel_chats > 0 else 0
                },
                {
                    'پلتفرم': platform_name,
                    'نوع': 'مجموع',
                    'تعداد چت': total_chats,
                    'تعداد اعضا': total_members,
                    'میانگین اعضا': round(total_members / total_chats, 1) if total_chats > 0 else 0
                }
            ])
        
        # محاسبه مجموع کل
        if len(selected_platforms) > 1:
            total_private_chats = sum(chat_counts_dict.get('private', 0) for chat_counts_dict in [
                {r['chat_type']: r['count'] for r in db_fetchall("SELECT chat_type, COUNT(*) as count FROM chats WHERE platform = ? AND is_active = 1 GROUP BY chat_type", (p,))}
                for p in selected_platforms
            ])
            
            total_group_chats = sum(chat_counts_dict.get('group', 0) for chat_counts_dict in [
                {r['chat_type']: r['count'] for r in db_fetchall("SELECT chat_type, COUNT(*) as count FROM chats WHERE platform = ? AND is_active = 1 GROUP BY chat_type", (p,))}
                for p in selected_platforms
            ])
            
            total_channel_chats = sum(chat_counts_dict.get('channel', 0) for chat_counts_dict in [
                {r['chat_type']: r['count'] for r in db_fetchall("SELECT chat_type, COUNT(*) as count FROM chats WHERE platform = ? AND is_active = 1 GROUP BY chat_type", (p,))}
                for p in selected_platforms
            ])
            
            total_all_chats = total_private_chats + total_group_chats + total_channel_chats
            
            # محاسبه مجموع اعضا
            total_private_members = sum(member_stats_dict.get('private', 0) for member_stats_dict in [
                {r['chat_type']: r['total_members'] for r in db_fetchall("""
                    SELECT c.chat_type, COALESCE(SUM(m.members_count), 0) as total_members
                    FROM chats c
                    LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                        AND m.date_key = (SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = c.chat_id AND platform = c.platform)
                    WHERE c.platform = ? AND c.is_active = 1
                    GROUP BY c.chat_type
                """, (p,))}
                for p in selected_platforms
            ])
            
            total_group_members = sum(member_stats_dict.get('group', 0) for member_stats_dict in [
                {r['chat_type']: r['total_members'] for r in db_fetchall("""
                    SELECT c.chat_type, COALESCE(SUM(m.members_count), 0) as total_members
                    FROM chats c
                    LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                        AND m.date_key = (SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = c.chat_id AND platform = c.platform)
                    WHERE c.platform = ? AND c.is_active = 1
                    GROUP BY c.chat_type
                """, (p,))}
                for p in selected_platforms
            ])
            
            total_channel_members = sum(member_stats_dict.get('channel', 0) for member_stats_dict in [
                {r['chat_type']: r['total_members'] for r in db_fetchall("""
                    SELECT c.chat_type, COALESCE(SUM(m.members_count), 0) as total_members
                    FROM chats c
                    LEFT JOIN chats_metrics m ON c.chat_id = m.chat_id AND c.platform = m.platform
                        AND m.date_key = (SELECT MAX(date_key) FROM chats_metrics WHERE chat_id = c.chat_id AND platform = c.platform)
                    WHERE c.platform = ? AND c.is_active = 1
                    GROUP BY c.chat_type
                """, (p,))}
                for p in selected_platforms
            ])
            
            total_all_members = total_private_members + total_group_members + total_channel_members
            
            # اضافه کردن ردیف مجموع کل
            stats_data.extend([
                {
                    'پلتفرم': 'مجموع کل',
                    'نوع': 'کاربران',
                    'تعداد چت': total_private_chats,
                    'تعداد اعضا': total_private_members,
                    'میانگین اعضا': round(total_private_members / total_private_chats, 1) if total_private_chats > 0 else 0
                },
                {
                    'پلتفرم': 'مجموع کل',
                    'نوع': 'گروه‌ها',
                    'تعداد چت': total_group_chats,
                    'تعداد اعضا': total_group_members,
                    'میانگین اعضا': round(total_group_members / total_group_chats, 1) if total_group_chats > 0 else 0
                },
                {
                    'پلتفرم': 'مجموع کل',
                    'نوع': 'کانال‌ها',
                    'تعداد چت': total_channel_chats,
                    'تعداد اعضا': total_channel_members,
                    'میانگین اعضا': round(total_channel_members / total_channel_chats, 1) if total_channel_chats > 0 else 0
                },
                {
                    'پلتفرم': 'مجموع کل',
                    'نوع': 'مجموع',
                    'تعداد چت': total_all_chats,
                    'تعداد اعضا': total_all_members,
                    'میانگین اعضا': round(total_all_members / total_all_chats, 1) if total_all_chats > 0 else 0
                }
            ])
        
        # ایجاد DataFrame
        df = pd.DataFrame(stats_data)
        
        # اضافه کردن اطلاعات اضافی
        df['تاریخ گزارش'] = current_date_jalali
        df['ساعت گزارش'] = '01:00 (Snapshot روزانه)'
        
        return df
        
    except Exception as e:
        logger.error(f"Error generating bot statistics sheet: {e}")
        # بازگرداندن DataFrame خالی در صورت خطا
        return pd.DataFrame(columns=['پلتفرم', 'نوع', 'تعداد چت', 'تعداد اعضا', 'میانگین اعضا', 'تاریخ گزارش', 'ساعت گزارش'])

def generate_daily_bot_statistics_sheet(selected_platforms: list):
    """تولید شیت آمار روزانه ربات‌ها با ساختار pivot table"""
    try:
        import pandas as pd
        from datetime import datetime, timedelta
        import json
        import os
        
        # دریافت تمام snapshot های موجود
        snapshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'snapshots')
        
        if not os.path.exists(snapshots_dir):
            logger.warning("Snapshots directory not found")
            return pd.DataFrame(columns=['پلتفرم - نوع', 'نوع آمار'])
        
        # خواندن تمام فایل‌های snapshot
        snapshot_files = []
        for filename in os.listdir(snapshots_dir):
            if filename.startswith('bot_statistics_') and filename.endswith('.json'):
                date_str = filename.replace('bot_statistics_', '').replace('.json', '')
                file_path = os.path.join(snapshots_dir, filename)
                snapshot_files.append((date_str, file_path))
        
        # مرتب‌سازی بر اساس تاریخ (جدیدترین اول)
        snapshot_files.sort(key=lambda x: x[0], reverse=True)
        
        if not snapshot_files:
            logger.warning("No snapshot files found")
            return pd.DataFrame(columns=['پلتفرم - نوع', 'نوع آمار'])
        
        # خواندن داده‌های snapshot ها
        snapshots_data = {}
        for date_str, file_path in snapshot_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    snapshots_data[date_str] = data
            except Exception as e:
                logger.warning(f"Error reading snapshot {file_path}: {e}")
                continue
        
        # تبدیل تاریخ‌ها به شمسی
        try:
            import jdatetime
            jalali_dates = {}
            for date_str in snapshots_data.keys():
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    jdt = jdatetime.datetime.fromgregorian(date=date_obj)
                    jalali_dates[date_str] = jdt.strftime('%Y/%m/%d')
                except:
                    jalali_dates[date_str] = date_str
        except ImportError:
            jalali_dates = {date_str: date_str for date_str in snapshots_data.keys()}
        
        # ساخت ردیف‌های داده
        rows_data = []
        
        # تعریف ترتیب پلتفرم‌ها و نوع‌ها
        platforms_order = ['telegram', 'bale', 'ita']
        platform_names = {'telegram': 'تلگرام', 'bale': 'بله', 'ita': 'ایتا'}
        chat_types_order = ['private', 'group', 'channel', 'total']
        chat_type_names = {'private': 'کاربران', 'group': 'گروه‌ها', 'channel': 'کانال‌ها', 'total': 'مجموع'}
        
        # ساخت ردیف‌ها برای هر پلتفرم
        for platform in platforms_order:
            if platform not in selected_platforms:
                continue
                
            platform_name = platform_names[platform]
            
            # ردیف‌های تعداد چت
            for chat_type in chat_types_order:
                if chat_type == 'total':
                    row_data = {
                        'پلتفرم - نوع': f'{platform_name} - مجموع',
                        'نوع آمار': 'تعداد چت'
                    }
                else:
                    row_data = {
                        'پلتفرم - نوع': f'{platform_name} - {chat_type_names[chat_type]}',
                        'نوع آمار': 'تعداد چت'
                    }
                
                # اضافه کردن ستون‌های روزانه
                for date_str in sorted(snapshots_data.keys(), reverse=True):
                    jalali_date = jalali_dates[date_str]
                    snapshot = snapshots_data[date_str]
                    
                    if platform in snapshot.get('platforms', {}):
                        platform_data = snapshot['platforms'][platform]
                        
                        if chat_type == 'total':
                            value = platform_data.get('total_chats', 0)
                        else:
                            value = platform_data.get('chats', {}).get(chat_type, 0)
                    else:
                        value = 0
                    
                    row_data[jalali_date] = value
                
                rows_data.append(row_data)
        
        # ردیف‌های تعداد اعضا
        for platform in platforms_order:
            if platform not in selected_platforms:
                continue
                
            platform_name = platform_names[platform]
            
            for chat_type in chat_types_order:
                if chat_type == 'total':
                    row_data = {
                        'پلتفرم - نوع': f'{platform_name} - مجموع',
                        'نوع آمار': 'تعداد اعضا'
                    }
                else:
                    row_data = {
                        'پلتفرم - نوع': f'{platform_name} - {chat_type_names[chat_type]}',
                        'نوع آمار': 'تعداد اعضا'
                    }
                
                # اضافه کردن ستون‌های روزانه
                for date_str in sorted(snapshots_data.keys(), reverse=True):
                    jalali_date = jalali_dates[date_str]
                    snapshot = snapshots_data[date_str]
                    
                    if platform in snapshot.get('platforms', {}):
                        platform_data = snapshot['platforms'][platform]
                        
                        if chat_type == 'total':
                            value = platform_data.get('total_members', 0)
                        else:
                            value = platform_data.get('members', {}).get(chat_type, 0)
                    else:
                        value = 0
                    
                    row_data[jalali_date] = value
                
                rows_data.append(row_data)
        
        # ردیف‌های مجموع کل (اگر بیش از یک پلتفرم انتخاب شده)
        if len(selected_platforms) > 1:
            # ردیف‌های مجموع کل - تعداد چت
            for chat_type in chat_types_order:
                if chat_type == 'total':
                    row_data = {
                        'پلتفرم - نوع': 'مجموع کل - مجموع',
                        'نوع آمار': 'تعداد چت'
                    }
                else:
                    row_data = {
                        'پلتفرم - نوع': f'مجموع کل - {chat_type_names[chat_type]}',
                        'نوع آمار': 'تعداد چت'
                    }
                
                # اضافه کردن ستون‌های روزانه
                for date_str in sorted(snapshots_data.keys(), reverse=True):
                    jalali_date = jalali_dates[date_str]
                    snapshot = snapshots_data[date_str]
                    
                    total_value = 0
                    for platform in selected_platforms:
                        if platform in snapshot.get('platforms', {}):
                            platform_data = snapshot['platforms'][platform]
                            
                            if chat_type == 'total':
                                value = platform_data.get('total_chats', 0)
                            else:
                                value = platform_data.get('chats', {}).get(chat_type, 0)
                            
                            total_value += value
                    
                    row_data[jalali_date] = total_value
                
                rows_data.append(row_data)
            
            # ردیف‌های مجموع کل - تعداد اعضا
            for chat_type in chat_types_order:
                if chat_type == 'total':
                    row_data = {
                        'پلتفرم - نوع': 'مجموع کل - مجموع',
                        'نوع آمار': 'تعداد اعضا'
                    }
                else:
                    row_data = {
                        'پلتفرم - نوع': f'مجموع کل - {chat_type_names[chat_type]}',
                        'نوع آمار': 'تعداد اعضا'
                    }
                
                # اضافه کردن ستون‌های روزانه
                for date_str in sorted(snapshots_data.keys(), reverse=True):
                    jalali_date = jalali_dates[date_str]
                    snapshot = snapshots_data[date_str]
                    
                    total_value = 0
                    for platform in selected_platforms:
                        if platform in snapshot.get('platforms', {}):
                            platform_data = snapshot['platforms'][platform]
                            
                            if chat_type == 'total':
                                value = platform_data.get('total_members', 0)
                            else:
                                value = platform_data.get('members', {}).get(chat_type, 0)
                            
                            total_value += value
                    
                    row_data[jalali_date] = total_value
                
                rows_data.append(row_data)
        
        # ایجاد DataFrame
        df = pd.DataFrame(rows_data)
        
        return df
        
    except Exception as e:
        logger.error(f"Error generating daily bot statistics sheet: {e}")
        # بازگرداندن DataFrame خالی در صورت خطا
        return pd.DataFrame(columns=['پلتفرم - نوع', 'نوع آمار'])

def generate_growth_report(platform: str):
    """تولید گزارش رشد برای یک پلتفرم"""
    try:
        import pandas as pd
        from datetime import datetime
        
        # دریافت آمار رشد
        growth_stats = calculate_growth_stats(platform, 7)
        
        if not growth_stats:
            return None
        
        # ساخت DataFrame
        data = []
        for chat_type, stats in growth_stats.items():
            if chat_type == 'total':
                continue
                
            data.append({
                'نوع چت': 'کاربران' if chat_type == 'private' else ('گروه‌ها' if chat_type == 'group' else 'کانال‌ها'),
                'تعداد چت فعلی': stats['current_chats'],
                'تعداد چت گذشته': stats['past_chats'],
                'رشد تعداد چت': stats['chat_growth'],
                'درصد رشد چت': f"{stats['chat_growth_pct']}%",
                'تعداد اعضای فعلی': stats['current_members'],
                'تعداد اعضای گذشته': stats['past_members'],
                'رشد تعداد اعضا': stats['member_growth'],
                'درصد رشد اعضا': f"{stats['member_growth_pct']}%"
            })
        
        # اضافه کردن مجموع
        total_stats = growth_stats.get('total', {})
        data.append({
            'نوع چت': 'مجموع',
            'تعداد چت فعلی': total_stats.get('current_chats', 0),
            'تعداد چت گذشته': total_stats.get('past_chats', 0),
            'رشد تعداد چت': total_stats.get('chat_growth', 0),
            'درصد رشد چت': f"{total_stats.get('chat_growth_pct', 0)}%",
            'تعداد اعضای فعلی': total_stats.get('current_members', 0),
            'تعداد اعضای گذشته': total_stats.get('past_members', 0),
            'رشد تعداد اعضا': total_stats.get('member_growth', 0),
            'درصد رشد اعضا': f"{total_stats.get('member_growth_pct', 0)}%"
        })
        
        df = pd.DataFrame(data)
        
        # ذخیره فایل Excel
        filename = f"growth_report_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='گزارش رشد', index=False)
            
            # تنظیم عرض ستون‌ها
            worksheet = writer.sheets['گزارش رشد']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        return filepath
    except Exception as e:
        logger.error(f"Error generating growth report for {platform}: {e}")
        return None

def restore_chats_from_backup():
    """بازیابی چت‌ها از فایل backup"""
    try:
        backup_file = "chats_backup.json"
        if not os.path.exists(backup_file):
            logger.info("[Backup] No backup file found")
            return 0
        
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        restored_count = 0
        for chat_key, chat_info in backup_data.items():
            try:
                register_chat(
                    chat_info["chat_id"],
                    chat_info["chat_type"],
                    chat_info["platform"],
                    chat_info.get("name"),
                    chat_info.get("username"),
                    chat_info.get("tags")
                )
                restored_count += 1
            except Exception as e:
                logger.error(f"Error restoring chat {chat_key}: {e}")
        
        logger.info(f"[Backup] Restored {restored_count} chats from backup")
        return restored_count
        
    except Exception as e:
        logger.error(f"Error restoring chats from backup: {e}")
        return 0

def auto_daily_stats_collection(max_retries: int = 3):
    """
    ذخیره‌سازی خودکار آمار روزانه با قابلیت تلاش مجدد
    
    Args:
        max_retries: حداکثر تعداد تلاش برای دریافت آمار هر چت
    
    Returns:
        تعداد چت‌هایی که با موفقیت آمارگیری شدند
    """
    import asyncio
    from datetime import datetime, timedelta
    import time
    
    logger.info("📊 [Auto Stats] Starting daily stats collection...")
    
    try:
        # دریافت تمام چت‌های فعال
        active_chats = db_fetchall("""
            SELECT chat_id, platform, chat_type, name 
            FROM chats 
            WHERE is_active = 1
            ORDER BY created_at DESC, platform, chat_type
        """)
        
        if not active_chats:
            logger.warning("⚠️ [Auto Stats] No active chats found for stats collection")
            return 0
            
        total_chats = len(active_chats)
        collected_count = 0
        failed_count = 0
        
        logger.info(f"🔍 [Auto Stats] Found {total_chats} active chats to process")
        
        for index, chat in enumerate(active_chats, 1):
            chat_id = chat['chat_id']
            platform = chat['platform']
            chat_type = chat['chat_type']
            chat_name = chat.get('name', 'Unnamed')
            
            logger.info(f"🔄 [{index}/{total_chats}] Processing {chat_name} ({chat_id} - {platform})")
            
            for attempt in range(1, max_retries + 1):
                try:
                    # دریافت تعداد اعضا با تاخیر بین تلاش‌ها
                    if attempt > 1:
                        retry_delay = 5 * attempt  # تاخیر تصاعدی
                        logger.warning(f"   ⏳ Attempt {attempt}/{max_retries} after {retry_delay}s delay...")
                        time.sleep(retry_delay)
                    
                    member_count = asyncio.run(get_chat_member_count(chat_id, platform, chat_type))
                    
                    # ذخیره در جدول metrics
                    date_key = datetime.now().strftime('%Y-%m-%d')
                    db_execute("""
                        INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                        VALUES (?, ?, ?, ?)
                    """, (chat_id, platform, date_key, member_count))
                    
                    collected_count += 1
                    logger.info(f"✅ Successfully collected stats for {chat_name} ({platform}): {member_count} members")
                    break  # در صورت موفقیت از حلقه تلاش‌ها خارج می‌شویم
                    
                except Exception as e:
                    if attempt == max_retries:
                        failed_count += 1
                        logger.error(f"❌ Failed to collect stats for {chat_name} after {max_retries} attempts: {str(e)}")
                    else:
                        logger.warning(f"⚠️ Attempt {attempt} failed for {chat_name}: {str(e)}")
        
        # ثبت خلاصه عملیات
        success_rate = (collected_count / total_chats * 100) if total_chats > 0 else 0
        logger.info(f"📊 [Auto Stats] Collection completed! "
                   f"Success: {collected_count}, Failed: {failed_count}, "
                   f"Success rate: {success_rate:.1f}%")
        
        # ارسال اعلان به ادمین در صورت خطا
        if failed_count > 0:
            error_msg = (f"⚠️ Daily stats collection completed with {failed_count} failures. "
                        f"Success rate: {success_rate:.1f}%")
            try:
                send_admin_notification(error_msg, platform="telegram")  # یا پلتفرم دلخواه دیگر
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
        
        return collected_count
        
    except Exception as e:
        error_msg = f"❌ Critical error in auto daily stats collection: {str(e)}"
        logger.error(error_msg, exc_info=True)
        try:
            send_admin_notification(error_msg, platform="telegram")  # یا پلتفرم دلخواه دیگر
        except Exception as notify_err:
            logger.error(f"Failed to send critical error notification: {notify_err}")
        return 0

def schedule_daily_stats():
    """
    برنامه‌ریزی ذخیره‌سازی خودکار آمار روزانه
    
    این تابع یک scheduler جداگانه برای جمع‌آوری آمار روزانه راه‌اندازی می‌کند.
    زمان پیش‌فرض: هر روز ساعت 3:00 بامداد
    """
    import schedule
    import time
    import threading
    from datetime import datetime
    
    def run_scheduler():
        # تنظیم زمان ذخیره‌سازی (ساعت 3 بامداد)
        schedule_time = "03:00"
        schedule.every().day.at(schedule_time).do(
            lambda: auto_daily_stats_collection(max_retries=3)
        )
        
        logger.info(f"⏰ [Scheduler] Daily stats collection scheduled for {schedule_time} (local time)")
        
        try:
            # محاسبه زمان باقی‌مانده تا اجرای بعدی
            now = datetime.now()
            next_run = datetime.strptime(
                f"{now.strftime('%Y-%m-%d')} {schedule_time}", 
                "%Y-%m-%d %H:%M"
            )
            if now > next_run:
                next_run = next_run + timedelta(days=1)
            
            time_until_next = (next_run - now).total_seconds()
            logger.info(f"⏳ [Scheduler] Next run in {time_until_next/3600:.1f} hours")
        except Exception as e:
            logger.warning(f"⚠️ [Scheduler] Could not calculate next run time: {e}")
        
        # حلقه اصلی scheduler
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                logger.error(f"❌ [Scheduler] Error in scheduled task: {e}", exc_info=True)
                # در صورت بروز خطا، 5 دقیقه صبر می‌کنیم و دوباره تلاش می‌کنیم
                time.sleep(300)
            else:
                time.sleep(60)  # چک کردن هر دقیقه
    
    # اجرای scheduler در thread جداگانه
    try:
        scheduler_thread = threading.Thread(
            target=run_scheduler, 
            name="StatsScheduler",
            daemon=True
        )
        scheduler_thread.start()
        logger.info("🚀 [Scheduler] Daily stats scheduler started successfully")
        return True
    except Exception as e:
        logger.critical(f"❌ [Scheduler] Failed to start scheduler: {e}", exc_info=True)
        return False

def start_application():
    """
    تابع اصلی برای راه‌اندازی برنامه و سرویس‌های جانبی
    """
    # راه‌اندازی scheduler
    if not schedule_daily_stats():
        logger.warning("⚠️ Could not start stats scheduler. Some features may not work as expected.")
    
    # سایر تنظیمات راه‌اندازی
    logger.info("✅ Application services initialized successfully")

async def register_ita_chat_with_full_info(chat_id: str, chat_type: str = 'channel', name: str = None, username: str = None, message_data: dict = None) -> bool:
    """
    ثبت چت ایتا با دریافت اطلاعات کامل از روش‌های مختلف (بدون ارسال پیام)
    """
    try:
        logger.info(f"[ITA] Starting full registration for chat {chat_id}")
        
        # روش 1: استفاده از اطلاعات پیام ارسالی (اگر موجود باشد)
        if message_data:
            message_info = await get_ita_chat_info_from_message(message_data)
            if message_info.get('success'):
                data = message_info.get('data', {})
                final_name = name or data.get('name', '') or data.get('title', '')
                final_username = username or data.get('username', '')
                final_type = chat_type or data.get('type', 'channel')
                
                logger.info(f"[ITA] Message info for {chat_id}: name={final_name}, username={final_username}, type={final_type}")
                
                # ثبت در دیتابیس
                success = register_chat(
                    chat_id=str(chat_id),
                    chat_type=final_type,
                    platform='ita',
                    name=final_name,
                    username=final_username
                )
                
                if success:
                    logger.info(f"[ITA] Registered chat from message data: {chat_id}")
                    return success
        
        # روش 2: استفاده از کدهای advanced_smart_gui برای تشخیص پیشرفته
        advanced_info = await _get_ita_info_advanced_smart_gui_style(chat_id)
        
        if advanced_info and advanced_info.get('success'):
            # استفاده از اطلاعات دریافت شده از روش پیشرفته
            data = advanced_info.get('data', {})
            final_name = name or data.get('name', '') or data.get('title', '')
            final_username = username or data.get('username', '')
            final_type = chat_type or ('channel' if data.get('is_channel') else 'group')
            member_count = data.get('users', 0)
            
            logger.info(f"[ITA] Advanced info for {chat_id}: name={final_name}, username={final_username}, type={final_type}, members={member_count}")
            
            # ثبت در دیتابیس
            success = register_chat(
                chat_id=str(chat_id),
                chat_type=final_type,
                platform='ita',
                name=final_name,
                username=final_username
            )
            
            if success and member_count > 0:
                # ذخیره تعداد اعضا در جدول metrics
                date_key = time.strftime('%Y-%m-%d')
                db_execute("""
                    INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                    VALUES (?, 'ita', ?, ?)
                """, (str(chat_id), date_key, member_count))
                logger.info(f"[ITA] Saved member count {member_count} for chat {chat_id}")
            
            return success
        
        # روش 3: استفاده از روش‌های قبلی (بدون ارسال پیام)
        chat_info = await get_ita_chat_info(chat_id)
        
        if chat_info:
            # استفاده از اطلاعات دریافت شده
            final_name = name or chat_info.get('title', '') or chat_info.get('first_name', '')
            final_username = username or chat_info.get('username', '')
            final_type = chat_type or chat_info.get('type', 'channel')
            
            # دریافت تعداد اعضا (بدون ارسال پیام)
            member_count = await get_ita_chat_member_count(chat_id)
            
            logger.info(f"[ITA] Standard info for {chat_id}: name={final_name}, username={final_username}, type={final_type}, members={member_count}")
            
            # ثبت در دیتابیس
            success = register_chat(
                chat_id=str(chat_id),
                chat_type=final_type,
                platform='ita',
                name=final_name,
                username=final_username
            )
            
            if success and member_count > 0:
                # ذخیره تعداد اعضا در جدول metrics
                date_key = time.strftime('%Y-%m-%d')
                db_execute("""
                    INSERT OR REPLACE INTO chats_metrics (chat_id, platform, date_key, members_count)
                    VALUES (?, 'ita', ?, ?)
                """, (str(chat_id), date_key, member_count))
                logger.info(f"[ITA] Saved member count {member_count} for chat {chat_id}")
            
            return success
        else:
            # اگر اطلاعات دریافت نشد، با اطلاعات ارائه شده ثبت کن
            logger.warning(f"[ITA] Could not get full info for {chat_id}, using provided info")
            return register_chat(
                chat_id=str(chat_id),
                chat_type=chat_type,
                platform='ita',
                name=name,
                username=username
            )
            
    except Exception as e:
        logger.error(f"[ITA] Error in full registration for {chat_id}: {e}")
        return False

async def _get_telegram_chat_info(chat_id: str) -> dict:
    """
    دریافت اطلاعات چت تلگرام
    """
    try:
        logger.info(f"[Telegram] Analyzing chat: {chat_id}")
        
        # For now, return basic info - can be enhanced with Telegram API
        return {
            'success': True,
            'data': {
                'id': chat_id,
                'name': f'Telegram Chat {chat_id}',
                'username': None,
                'users': 'Unknown',
                'type': 'unknown',
                'title': f'Telegram Chat {chat_id}',
                'description': 'Not available',
                'verified': False,
                'image_url': None,
                'is_channel': False,
                'is_group': True,
                'is_private': False,
                'method': 'telegram_basic'
            }
        }
    except Exception as e:
        logger.error(f"[Telegram] Error analyzing {chat_id}: {e}")
        return {'success': False, 'error': str(e)}

async def _get_bale_chat_info(chat_id: str) -> dict:
    """
    دریافت اطلاعات چت بله
    """
    try:
        logger.info(f"[Bale] Analyzing chat: {chat_id}")
        
        # For now, return basic info - can be enhanced with Bale API
        return {
            'success': True,
            'data': {
                'id': chat_id,
                'name': f'Bale Chat {chat_id}',
                'username': None,
                'users': 'Unknown',
                'type': 'unknown',
                'title': f'Bale Chat {chat_id}',
                'description': 'Not available',
                'verified': False,
                'image_url': None,
                'is_channel': False,
                'is_group': True,
                'is_private': False,
                'method': 'bale_basic'
            }
        }
    except Exception as e:
        logger.error(f"[Bale] Error analyzing {chat_id}: {e}")
        return {'success': False, 'error': str(e)}

async def _get_ita_advanced_smart_info(chat_id: str) -> dict:
    """
    دریافت اطلاعات چت ایتا با استفاده از روش‌های پیشرفته (بر اساس advanced_smart_gui)
    """
    try:
        logger.info(f"[ITA] Advanced smart analysis for {chat_id}")
        
        # روش 1: استفاده از Eitaa kit (برای username ها و شناسه‌های عددی)
        kit_result = await _get_ita_kit_info(chat_id)
        if kit_result.get('success'):
            logger.info(f"[ITA] Eitaa kit success for {chat_id}")
            return kit_result
        
        # روش 2: استفاده از scraping پیشرفته (بدون ارسال پیام)
        scraping_result = await _scrape_ita_chat_info(chat_id)
        if scraping_result:
            logger.info(f"[ITA] Advanced scraping success for {chat_id}")
            return {
                'success': True,
                'data': scraping_result,
                'method': 'advanced_scraping'
            }
        
        # روش 3: استفاده از API های عمومی (بدون ارسال پیام)
        public_result = await _get_ita_public_chat_info(chat_id)
        if public_result:
            logger.info(f"[ITA] Public API success for {chat_id}")
            return {
                'success': True,
                'data': public_result,
                'method': 'public_api'
            }
        
        # روش 4: استفاده از روش‌های پیشرفته scraping
        advanced_result = await _get_ita_advanced_info(chat_id)
        if advanced_result:
            logger.info(f"[ITA] Advanced methods success for {chat_id}")
            return {
                'success': True,
                'data': advanced_result,
                'method': 'advanced_methods'
            }
        
        logger.warning(f"[ITA] All methods failed for {chat_id}")
        return {'success': False, 'error': 'No method succeeded'}
        
    except Exception as e:
        logger.error(f"[ITA] Error in advanced smart analysis: {e}")
        return {'success': False, 'error': str(e)}

async def _get_ita_kit_info(chat_id: str) -> dict:
    """
    دریافت اطلاعات از Eitaa kit (برای username ها و شناسه‌های عددی)
    """
    try:
        # حذف @ از ابتدای chat_id
        clean_id = chat_id.lstrip('@')
        
        # تلاش برای استفاده از Eitaa kit
        try:
            from eitaa import Eitaa
            
            # اگر chat_id عددی است، ابتدا سعی کنیم آن را به username تبدیل کنیم
            if clean_id.isdigit() or clean_id.startswith('-'):
                logger.info(f"[ITA] Trying to get info for numeric ID: {clean_id}")
                # برای شناسه‌های عددی، از روش‌های دیگر استفاده می‌کنیم
                return {'success': False, 'error': 'Numeric ID not supported by Eitaa kit'}
            
            # برای username ها
            logger.info(f"[ITA] Trying Eitaa kit for username: {clean_id}")
            info = Eitaa.get_info(clean_id)
            
            if info:
                formatted_data = {
                    'id': clean_id,
                    'name': info.get('name', 'Unknown'),
                    'users': info.get('users', 'Unknown'),
                    'type': 'channel' if info.get('is_channel') else 'group',
                    'username': f"@{clean_id}",
                    'title': info.get('name', 'Unknown'),
                    'description': info.get('description', 'None'),
                    'verified': info.get('is_verified', False),
                    'image_url': info.get('image_url', 'None'),
                    'is_channel': info.get('is_channel', False),
                    'is_group': not info.get('is_channel', True),
                    'is_private': False
                }
                
                logger.info(f"[ITA] Eitaa kit success: {formatted_data['name']} ({formatted_data['users']} members)")
                
                return {
                    'success': True,
                    'data': formatted_data,
                    'method': 'eitaa_kit'
                }
            else:
                return {'success': False, 'error': 'No info returned from Eitaa kit'}
            
        except ImportError:
            logger.warning("[ITA] Eitaa kit not available - install with: pip install eitaa")
            return {'success': False, 'error': 'Eitaa kit not available'}
        except Exception as e:
            logger.warning(f"[ITA] Eitaa kit error: {e}")
            return {'success': False, 'error': str(e)}
            
    except Exception as e:
        logger.error(f"[ITA] Error in kit info: {e}")
        return {'success': False, 'error': str(e)}

async def _send_ita_test_message(chat_id: str) -> dict:
    """
    دریافت اطلاعات چت بدون ارسال پیام تست
    """
    try:
        logger.info(f"[ITA Test] Getting chat info for {chat_id} without sending test message")
        
        # بررسی اطلاعات موجود در دیتابیس
        existing_chat = db_fetchone("SELECT * FROM chats WHERE chat_id = ? AND platform = 'ita'", (chat_id,))
        
        if existing_chat:
            formatted_data = {
                'id': chat_id,
                'name': existing_chat.get('chat_title', ''),
                'users': 'Unknown (not available via API)',
                'type': existing_chat.get('chat_type', 'channel'),
                'username': f"@{existing_chat.get('chat_username', '')}" if existing_chat.get('chat_username') else "None",
                'title': existing_chat.get('chat_title', ''),
                'description': 'Not available via API',
                'verified': 'Unknown (not available via API)',
                'image_url': 'Not available via API',
                'is_channel': existing_chat.get('chat_type') in ['channel', 'supergroup'],
                'is_group': existing_chat.get('chat_type') in ['group', 'supergroup'],
                'is_private': existing_chat.get('chat_type') == 'private'
            }
            
            return {
                'success': True,
                'data': formatted_data,
                'method': 'database_only'
            }
        else:
            return {
                'success': False, 
                'error': f'No chat info found for {chat_id} in database'
            }
            
    except Exception as e:
        logger.error(f"[ITA] Error in test message: {e}")
        return {'success': False, 'error': str(e)}

async def _get_ita_info_advanced_smart_gui_style(chat_id: str) -> dict:
    """
    دریافت اطلاعات چت ایتا با استفاده از روش‌های advanced_smart_gui
    """
    try:
        logger.info(f"[ITA] Advanced smart GUI style analysis for {chat_id}")
        
        # روش 1: Eitaa kit (برای username ها)
        if not chat_id.isdigit() and not chat_id.startswith('-'):
            kit_result = await _get_ita_kit_info(chat_id)
            if kit_result.get('success'):
                return kit_result
        
        # روش 2: استفاده از اطلاعات پیام ارسالی (بدون ارسال پیام جدید)
        # این روش فقط برای زمانی است که پیام ارسال شده و اطلاعات چت موجود باشد
        
        # روش 3: scraping پیشرفته
        scraping_result = await _scrape_ita_chat_info(chat_id)
        if scraping_result:
            return {
                'success': True,
                'data': scraping_result,
                'method': 'advanced_scraping'
            }
        
        # روش 4: API های عمومی
        public_result = await _get_ita_public_chat_info(chat_id)
        if public_result:
            return {
                'success': True,
                'data': public_result,
                'method': 'public_api'
            }
        
        return {'success': False, 'error': 'All methods failed'}
        
    except Exception as e:
        logger.error(f"[ITA] Error in advanced smart GUI style analysis: {e}")
        return {'success': False, 'error': str(e)}

async def get_ita_chat_info_from_message(message_data: dict) -> dict:
    """
    دریافت اطلاعات چت ایتا از پیام ارسالی (بدون ارسال پیام جدید)
    """
    try:
        logger.info(f"[ITA] Extracting chat info from message data")
        
        # استخراج اطلاعات چت از پیام
        chat_info = message_data.get('chat', {})
        if not chat_info:
            return {'success': False, 'error': 'No chat info in message'}
        
        # فرمت کردن اطلاعات
        formatted_data = {
            'id': str(chat_info.get('id', '')),
            'name': chat_info.get('title', chat_info.get('first_name', 'Unknown')),
            'users': 'Unknown (not available from message)',
            'type': chat_info.get('type', 'unknown'),
            'username': f"@{chat_info.get('username', 'None')}" if chat_info.get('username') else "None",
            'title': chat_info.get('title', chat_info.get('first_name', 'Unknown')),
            'description': 'Not available from message',
            'verified': 'Unknown (not available from message)',
            'image_url': 'Not available from message',
            'is_channel': chat_info.get('type') in ['channel', 'supergroup'],
            'is_group': chat_info.get('type') in ['group', 'supergroup'],
            'is_private': chat_info.get('type') == 'private'
        }
        
        logger.info(f"[ITA] Extracted chat info: {formatted_data['name']} ({formatted_data['type']})")
        
        # اگر username دریافت شد، سعی کنیم اطلاعات بیشتری از kit بگیریم
        if chat_info.get('username'):
            username = chat_info.get('username')
            logger.info(f"[ITA] Found username from message: {username}, trying kit")
            kit_result = await _get_ita_kit_info(username)
            if kit_result.get('success'):
                # ترکیب اطلاعات
                kit_data = kit_result.get('data', {})
                formatted_data.update({
                    'name': kit_data.get('name', formatted_data['name']),
                    'users': kit_data.get('users', formatted_data['users']),
                    'description': kit_data.get('description', formatted_data['description']),
                    'verified': kit_data.get('verified', formatted_data['verified']),
                    'image_url': kit_data.get('image_url', formatted_data['image_url']),
                    'is_channel': kit_data.get('is_channel', formatted_data['is_channel']),
                    'is_group': kit_data.get('is_group', formatted_data['is_group'])
                })
                logger.info(f"[ITA] Enhanced with kit info: {formatted_data['name']} ({formatted_data['users']} members)")
        
        return {
            'success': True,
            'data': formatted_data,
            'method': 'message_extraction'
        }
        
    except Exception as e:
        logger.error(f"[ITA] Error extracting chat info from message: {e}")
        return {'success': False, 'error': str(e)}

async def test_ita_smart_detection(chat_id: str) -> dict:
    """
    تست روش‌های پیشرفته تشخیص ایتا (بدون ارسال پیام)
    """
    try:
        logger.info(f"[ITA] Testing smart detection for {chat_id}")
        
        # تست روش‌های مختلف
        results = {
            'chat_id': chat_id,
            'methods_tested': [],
            'successful_methods': [],
            'final_result': None
        }
        
        # تست 1: Eitaa kit (برای username ها)
        if not chat_id.isdigit() and not chat_id.startswith('-'):
            logger.info(f"[ITA] Testing Eitaa kit for {chat_id}")
            kit_result = await _get_ita_kit_info(chat_id)
            results['methods_tested'].append('eitaa_kit')
            if kit_result.get('success'):
                results['successful_methods'].append('eitaa_kit')
                results['final_result'] = kit_result
                logger.info(f"[ITA] Eitaa kit success for {chat_id}")
                return results
        
        # تست 2: روش‌های scraping پیشرفته
        logger.info(f"[ITA] Testing advanced scraping for {chat_id}")
        scraping_result = await _scrape_ita_chat_info(chat_id)
        results['methods_tested'].append('advanced_scraping')
        if scraping_result:
            results['successful_methods'].append('advanced_scraping')
            results['final_result'] = {
                'success': True,
                'data': scraping_result,
                'method': 'advanced_scraping'
            }
            logger.info(f"[ITA] Advanced scraping success for {chat_id}")
            return results
        
        # تست 3: API های عمومی
        logger.info(f"[ITA] Testing public API for {chat_id}")
        public_result = await _get_ita_public_chat_info(chat_id)
        results['methods_tested'].append('public_api')
        if public_result:
            results['successful_methods'].append('public_api')
            results['final_result'] = {
                'success': True,
                'data': public_result,
                'method': 'public_api'
            }
            logger.info(f"[ITA] Public API success for {chat_id}")
            return results
        
        # تست 4: روش‌های پیشرفته
        logger.info(f"[ITA] Testing advanced methods for {chat_id}")
        advanced_result = await _get_ita_advanced_info(chat_id)
        results['methods_tested'].append('advanced_methods')
        if advanced_result:
            results['successful_methods'].append('advanced_methods')
            results['final_result'] = {
                'success': True,
                'data': advanced_result,
                'method': 'advanced_methods'
            }
            logger.info(f"[ITA] Advanced methods success for {chat_id}")
            return results
        
        logger.warning(f"[ITA] All non-intrusive methods failed for {chat_id}")
        return results
        
    except Exception as e:
        logger.error(f"[ITA] Error in smart detection test: {e}")
        return {
            'chat_id': chat_id,
            'error': str(e),
            'methods_tested': [],
            'successful_methods': [],
            'final_result': None
        }

async def test_ita_advanced_smart_gui_style(chat_id: str) -> dict:
    """
    تست روش‌های advanced_smart_gui برای تشخیص ایتا
    """
    try:
        logger.info(f"[ITA] Testing advanced smart GUI style detection for {chat_id}")
        
        # تست روش‌های مختلف
        results = {
            'chat_id': chat_id,
            'methods_tested': [],
            'successful_methods': [],
            'final_result': None
        }
        
        # تست 1: Eitaa kit (برای username ها)
        if not chat_id.isdigit() and not chat_id.startswith('-'):
            logger.info(f"[ITA] Testing Eitaa kit for {chat_id}")
            kit_result = await _get_ita_kit_info(chat_id)
            results['methods_tested'].append('eitaa_kit')
            if kit_result.get('success'):
                results['successful_methods'].append('eitaa_kit')
                results['final_result'] = kit_result
                logger.info(f"[ITA] Eitaa kit success for {chat_id}")
                return results
        
        # تست 2: استفاده از اطلاعات پیام ارسالی (بدون ارسال پیام جدید)
        # این تست فقط برای زمانی است که پیام ارسال شده و اطلاعات چت موجود باشد
        
        # تست 3: روش‌های scraping پیشرفته
        logger.info(f"[ITA] Testing advanced scraping for {chat_id}")
        scraping_result = await _scrape_ita_chat_info(chat_id)
        results['methods_tested'].append('advanced_scraping')
        if scraping_result:
            results['successful_methods'].append('advanced_scraping')
            results['final_result'] = {
                'success': True,
                'data': scraping_result,
                'method': 'advanced_scraping'
            }
            logger.info(f"[ITA] Advanced scraping success for {chat_id}")
            return results
        
        # تست 4: API های عمومی
        logger.info(f"[ITA] Testing public API for {chat_id}")
        public_result = await _get_ita_public_chat_info(chat_id)
        results['methods_tested'].append('public_api')
        if public_result:
            results['successful_methods'].append('public_api')
            results['final_result'] = {
                'success': True,
                'data': public_result,
                'method': 'public_api'
            }
            logger.info(f"[ITA] Public API success for {chat_id}")
            return results
        
        logger.warning(f"[ITA] All advanced smart GUI methods failed for {chat_id}")
        return results
        
    except Exception as e:
        logger.error(f"[ITA] Error in advanced smart GUI style test: {e}")
        return {
            'chat_id': chat_id,
            'error': str(e),
            'methods_tested': [],
            'successful_methods': [],
            'final_result': None
        }

# راه‌اندازی سرویس‌ها در شروع برنامه
if __name__ == "__main__":
    # Initialize logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('app.log', encoding='utf-8')
        ]
    )
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting application...")
        
        # Initialize backup system on startup
        try:
            logger.info("Initializing backup system...")
            backup_chats_to_backup_db()
            logger.info("✅ Backup system initialized - bot_database.db updated from main database")
        except Exception as e:
            logger.warning(f"⚠️ Backup system initialization failed: {e}")
        
        main()
    except Exception as e:
        logger.critical(f"Application failed to start: {e}", exc_info=True)
        raise
else:
    # When imported as a module
    logger = logging.getLogger(__name__)
    logger.info("Application module imported")
