import os
from flask import Flask, request, render_template, jsonify
from config import Config
from app.extensions import db, migrate, login_manager, bcrypt, socketio, babel, csrf, limiter


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
    limiter.init_app(app)

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

    @app.errorhandler(429)
    def rate_limit_error(e):
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'status': 'error',
                            'message': 'Too many requests. Please wait and try again.'}), 429
        return render_template('errors/rate_limited.html'), 429

    return app


def _run_schema_migrations(db):
    """Idempotent schema migrations — safe to run on every startup."""
    stmts = [
        # users: new columns
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS unsubscribe_token VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS newsletter_unsubscribed BOOLEAN DEFAULT FALSE",

        # abuse_logs table (in case db.create_all() didn't run or missed it)
        """CREATE TABLE IF NOT EXISTS abuse_logs (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(45) NOT NULL,
            user_id INTEGER REFERENCES users(id),
            event_type VARCHAR(50) NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_abuse_logs_ip ON abuse_logs(ip_address)",
        "CREATE INDEX IF NOT EXISTS ix_abuse_logs_event ON abuse_logs(event_type)",
        "CREATE INDEX IF NOT EXISTS ix_abuse_logs_created ON abuse_logs(created_at)",

        # ip_bans table
        """CREATE TABLE IF NOT EXISTS ip_bans (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(45) NOT NULL UNIQUE,
            reason VARCHAR(200),
            banned_by_id INTEGER REFERENCES users(id),
            banned_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,
            is_permanent BOOLEAN NOT NULL DEFAULT FALSE,
            notes TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS ix_ip_bans_ip ON ip_bans(ip_address)",

        # newsletters table
        """CREATE TABLE IF NOT EXISTS newsletters (
            id SERIAL PRIMARY KEY,
            subject_en VARCHAR(200),
            subject_hi VARCHAR(200),
            content_en TEXT,
            content_hi TEXT,
            theme VARCHAR(30) NOT NULL DEFAULT 'classic',
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            recipient_count INTEGER DEFAULT 0,
            sent_at TIMESTAMP,
            sent_by_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW()
        )""",
    ]
    for sql in stmts:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()