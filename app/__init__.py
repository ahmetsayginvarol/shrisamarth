import os
from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, bcrypt, socketio, babel, csrf


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(app)
    babel.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.staff.routes import staff_bp
    from app.admin.routes import admin_bp
    from app.customer.routes import customer_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(staff_bp, url_prefix='/staff')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(customer_bp)  # root — no prefix

    from app.verify.routes import verify_bp
    app.register_blueprint(verify_bp)
    csrf.exempt(verify_bp)

    # Import models so migrations detect them
    from app import models  # noqa: F401

    with app.app_context():
        db.create_all()
        _run_schema_migrations(db)

    @app.context_processor
    def inject_domain():
        return {'APP_DOMAIN': app.config['APP_DOMAIN']}

    return app


def _run_schema_migrations(db):
    """Add new columns to existing tables that db.create_all() won't touch."""
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP",
    ]
    for sql in stmts:
        try:
            db.session.execute(db.text(sql))
        except Exception:
            db.session.rollback()
    db.session.commit()