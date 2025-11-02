"""
Flask application factory
Creates and configures the Flask app instance
"""

from flask import Flask
import logging
import os
from pathlib import Path

# This will be populated when app is created
app = None

def create_app(config_name='development'):
    """Create and configure Flask application"""
    global app
    
    from app import settings
    
    app = Flask(__name__, 
                instance_path=os.path.join(os.path.abspath(os.path.dirname(__file__)), '..'),
                static_folder='../static',
                template_folder='../templates')
    
    # Load configuration
    app.config['SECRET_KEY'] = settings.Settings.SECRET_KEY
    app.config['UPLOAD_FOLDER'] = settings.Settings.UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = settings.Settings.MAX_CONTENT_LENGTH
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Initialize database
    initialize_database(app)
    
    # Setup app context
    setup_context(app)
    
    return app

def setup_logging(app):
    """Setup logging configuration"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("werkzeug").setLevel(logging.INFO)

def register_blueprints(app):
    """Register Flask blueprints"""
    # Import blueprints here to avoid circular imports
    from app.routes import auth, admin, api
    
    app.register_blueprint(auth.bp, url_prefix='/api/auth')
    app.register_blueprint(admin.bp, url_prefix='/api/admin')
    app.register_blueprint(api.bp, url_prefix='/api')

def initialize_database(app):
    """Initialize database"""
    # Set DB file for utilities
    from app.utils import database
    database.set_db_file(app.config['DB_FILE'])
    
    # Import and run DB initialization
    # This will be done from the main app.py for now
    pass

def setup_context(app):
    """Setup application context"""
    @app.before_request
    def before_request():
        """Run before each request"""
        pass
    
    @app.after_request
    def after_request(response):
        """Run after each request"""
        return response
    
    @app.teardown_appcontext
    def close_db(error):
        """Close database connections"""
        from app.utils import database
        database.db_close_all()

