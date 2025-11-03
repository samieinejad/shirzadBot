"""
Database utilities and helpers
"""

import sqlite3
import logging
from functools import wraps
from pathlib import Path

logger = logging.getLogger(__name__)

# This will be set from app config
DB_FILE = None

def _get_db_file():
    """Get DB file path - lazy loading from config"""
    global DB_FILE
    if DB_FILE is None:
        try:
            import config
            DB_FILE = getattr(config, 'DB_FILE', 'multi_bot_platform.db')
        except:
            DB_FILE = 'multi_bot_platform.db'
    return DB_FILE

def set_db_file(db_path):
    """Set the database file path"""
    global DB_FILE
    DB_FILE = db_path

def get_db_connection():
    """Get database connection with optimized settings"""
    db_file = _get_db_file()
    logger.debug(f"[DB] Connecting to database: {db_file}")
    conn = sqlite3.connect(db_file, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Optimize for concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    
    logger.debug("[DB] Database connection established")
    return conn

def db_execute(query, params=None):
    """Execute a database query"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.error(f"[DB] Error executing query: {e}")
        raise

def db_fetchone(query, params=None):
    """Fetch one row from database"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return dict(cursor.fetchone()) if cursor.rowcount > 0 else None
    except Exception as e:
        logger.error(f"[DB] Error fetching one: {e}")
        return None

def db_fetchall(query, params=None):
    """Fetch all rows from database"""
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[DB] Error fetching all: {e}")
        return []

def db_transaction(queries):
    """Execute multiple queries in a transaction"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for query, params in queries:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"[DB] Transaction error: {e}")
        return False

def db_close_all():
    """Close all database connections (for cleanup)"""
    # SQLite connections are closed automatically when using context manager
    pass

