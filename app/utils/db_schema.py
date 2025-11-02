"""
Database schema initialization and migrations
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

def init_database_schema(conn):
    """Initialize database schema with all tables"""
    
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    
    # Create tables
    _create_chat_tables(conn)
    _create_broadcast_tables(conn)
    _create_metrics_tables(conn)
    _create_user_tables(conn)
    _create_indexes(conn)
    
    # Run migrations
    _migrate_schema(conn)
    
    conn.commit()
    logger.info("✅ Database schema initialized")

def _create_chat_tables(conn):
    """Create chat-related tables"""
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
    
    conn.execute('''CREATE TABLE IF NOT EXISTS chats_metrics (
        chat_id TEXT, platform TEXT, date_key TEXT, 
        members_count INTEGER, is_daily_snapshot BOOLEAN DEFAULT 0, 
        PRIMARY KEY (chat_id, platform, date_key)
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS unique_members (
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
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS chat_memberships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        chat_type TEXT NOT NULL,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, platform, chat_id)
    )''')

def _create_broadcast_tables(conn):
    """Create broadcast-related tables"""
    conn.execute('''CREATE TABLE IF NOT EXISTS broadcast_batches (
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        scope TEXT NOT NULL, 
        platform TEXT, 
        content_preview TEXT, 
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        is_deleted INTEGER DEFAULT 0
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS sent_messages (
        message_id TEXT, 
        chat_id TEXT, 
        batch_id INTEGER, 
        FOREIGN KEY(batch_id) REFERENCES broadcast_batches(batch_id) ON DELETE CASCADE
    )''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS broadcast_dedupe (
        key TEXT PRIMARY KEY,
        created_at INTEGER
    )''')
    
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

def _create_metrics_tables(conn):
    """Create metrics and analytics tables"""
    conn.execute('''CREATE TABLE IF NOT EXISTS channel_posts_stats (
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
    )''')

def _create_user_tables(conn):
    """Create user authentication and billing tables"""
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mobile TEXT UNIQUE NOT NULL,
        full_name TEXT,
        is_verified INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
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

def _create_indexes(conn):
    """Create database indexes for performance"""
    try:
        # Chat indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_platform_type ON chats(platform, chat_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_last_active ON chats(last_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_tags ON chats(tags)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_is_active ON chats(is_active)")
        
        # Metrics indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_metrics_date ON chats_metrics(date_key)")
        
        # Broadcast indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_broadcast_batches_timestamp ON broadcast_batches(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_messages_batch ON sent_messages(batch_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_broadcasts_time ON scheduled_broadcasts(scheduled_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_broadcasts_status ON scheduled_broadcasts(status)")
        
        # User indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_otp_mobile ON user_otp_codes(mobile)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_billing_user ON user_billing(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_billing_ref ON user_billing(payping_ref_id)")
        
    except sqlite3.Error as e:
        logger.warning(f"Index creation warning: {e}")

def _migrate_schema(conn):
    """Run database migrations for existing databases"""
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info('chats')").fetchall()]
        
        # Chat migrations
        _add_column_if_not_exists(conn, 'chats', 'created_at', 'TEXT', cols)
        _add_column_if_not_exists(conn, 'chats', 'name', 'TEXT', cols)
        _add_column_if_not_exists(conn, 'chats', 'username', 'TEXT', cols)
        _add_column_if_not_exists(conn, 'chats', 'tags', "TEXT DEFAULT ''", cols)
        _add_column_if_not_exists(conn, 'chats', 'last_active', 'TIMESTAMP', cols)
        _add_column_if_not_exists(conn, 'chats', 'is_active', 'INTEGER DEFAULT 1', cols)
        _add_column_if_not_exists(conn, 'chats', 'member_count', 'INTEGER', cols)
        _add_column_if_not_exists(conn, 'chats', 'description', 'TEXT', cols)
        _add_column_if_not_exists(conn, 'chats', 'invite_link', 'TEXT', cols)
        
        # Scheduled broadcasts migrations
        scheduled_cols = [r[1] for r in conn.execute("PRAGMA table_info('scheduled_broadcasts')").fetchall()]
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'title', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'message', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'platforms', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'platform', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'scopes', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'solar_date', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'send_to_tagged', 'BOOLEAN DEFAULT 0', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'tag_filter', 'TEXT DEFAULT ""', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'content_type', 'TEXT DEFAULT "text"', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'content_data', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'pin_message', 'BOOLEAN DEFAULT 0', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'content_text', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'is_recurring', 'INTEGER DEFAULT 0', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'recurring_pattern', 'TEXT', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'executed_at', 'TIMESTAMP', scheduled_cols)
        _add_column_if_not_exists(conn, 'scheduled_broadcasts', 'notification_message_id', 'INTEGER', scheduled_cols)
        
        # Metrics migrations
        metrics_cols = [r[1] for r in conn.execute("PRAGMA table_info('chats_metrics')").fetchall()]
        _add_column_if_not_exists(conn, 'chats_metrics', 'is_daily_snapshot', 'BOOLEAN DEFAULT 0', metrics_cols)
        
        # Broadcast batches migrations
        batch_cols = [r[1] for r in conn.execute("PRAGMA table_info('broadcast_batches')").fetchall()]
        _add_column_if_not_exists(conn, 'broadcast_batches', 'is_deleted', 'INTEGER DEFAULT 0', batch_cols)
        
        # User migrations
        user_cols = [r[1] for r in conn.execute("PRAGMA table_info('users')").fetchall()]
        _add_column_if_not_exists(conn, 'users', 'is_admin', 'INTEGER DEFAULT 0', user_cols)
        
    except sqlite3.Error as e:
        logger.warning(f"Migration warning: {e}")

def _add_column_if_not_exists(conn, table, column, definition, existing_columns):
    """Add column to table if it doesn't exist"""
    if column not in existing_columns:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info(f"Added {column} column to {table} table")
        except sqlite3.Error as e:
            logger.warning(f"Failed to add column {column} to {table}: {e}")

