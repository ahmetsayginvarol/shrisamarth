import os
from flask import Flask, redirect, url_for
from flask_login import current_user

from config import Config
from app.extensions import db, migrate, login_manager, bcrypt, socketio, babel


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Make sure instance folder exists (for SQLite dev DB)
    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)
    babel.init_app(app)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(staff_bp, url_prefix='/staff')

    # Root route — sends people where they belong
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('staff.dashboard'))
        return redirect(url_for('auth.login'))

    # Make sure models are imported so migrations detect them
    from app import models  # noqa: F401

    return app