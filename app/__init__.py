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
    dialect = db.engine.dialect.name  # 'postgresql' or 'sqlite'

    if dialect == 'postgresql':
        alter_stmts = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS unsubscribe_token VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS newsletter_unsubscribed BOOLEAN DEFAULT FALSE",
            "ALTER TABLE route_stops ADD COLUMN IF NOT EXISTS fare_override NUMERIC(10,2) DEFAULT NULL",
            "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS booking_type VARCHAR(20) DEFAULT 'staff'",
        ]
    else:
        # SQLite: no IF NOT EXISTS for ALTER TABLE — catch duplicate-column errors
        alter_stmts = [
            "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 1",
            "ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP",
            "ALTER TABLE users ADD COLUMN unsubscribe_token VARCHAR(64)",
            "ALTER TABLE users ADD COLUMN newsletter_unsubscribed BOOLEAN DEFAULT 0",
            "ALTER TABLE route_stops ADD COLUMN fare_override NUMERIC(10,2) DEFAULT NULL",
            "ALTER TABLE bookings ADD COLUMN booking_type VARCHAR(20) DEFAULT 'staff'",
        ]

    for sql in alter_stmts:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

    if dialect == 'postgresql':
        pg_stmts = [
            # abuse_logs
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
            # ip_bans
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
            # newsletters
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
            # financial_entries
            """CREATE TABLE IF NOT EXISTS financial_entries (
                id SERIAL PRIMARY KEY,
                entry_type VARCHAR(10) NOT NULL,
                category VARCHAR(50) NOT NULL,
                amount NUMERIC(10,2) NOT NULL,
                description TEXT,
                entry_date DATE NOT NULL,
                created_by_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS ix_financial_entries_date ON financial_entries(entry_date)",
            "CREATE INDEX IF NOT EXISTS ix_financial_entries_type ON financial_entries(entry_type)",
            # user_activity_log
            """CREATE TABLE IF NOT EXISTS user_activity_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_type VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                metadata_json TEXT,
                ip_address VARCHAR(45),
                performed_by_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            "CREATE INDEX IF NOT EXISTS ix_user_activity_log_user ON user_activity_log(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_user_activity_log_type ON user_activity_log(event_type)",
            "CREATE INDEX IF NOT EXISTS ix_user_activity_log_created ON user_activity_log(created_at)",
            # cash_collections
            """CREATE TABLE IF NOT EXISTS cash_collections (
                id SERIAL PRIMARY KEY,
                voyage_id INTEGER NOT NULL REFERENCES voyages(id),
                booking_id INTEGER REFERENCES bookings(id),
                driver_id INTEGER NOT NULL REFERENCES users(id),
                passenger_name VARCHAR(120) NOT NULL,
                passenger_phone VARCHAR(20),
                seat_id VARCHAR(8),
                boarding_point VARCHAR(80),
                dropping_point VARCHAR(80),
                amount NUMERIC(10,2) NOT NULL,
                is_walkin BOOLEAN NOT NULL DEFAULT FALSE,
                collected_at TIMESTAMP DEFAULT NOW(),
                notes TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS ix_cash_collections_voyage ON cash_collections(voyage_id)",
            "CREATE INDEX IF NOT EXISTS ix_cash_collections_driver ON cash_collections(driver_id)",
            # trip_reports
            """CREATE TABLE IF NOT EXISTS trip_reports (
                id SERIAL PRIMARY KEY,
                voyage_id INTEGER NOT NULL REFERENCES voyages(id),
                driver_id INTEGER NOT NULL REFERENCES users(id),
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                total_collected NUMERIC(10,2) DEFAULT 0,
                walkin_count INTEGER DEFAULT 0,
                notes TEXT,
                submitted_at TIMESTAMP DEFAULT NOW(),
                reviewed_by_id INTEGER REFERENCES users(id),
                reviewed_at TIMESTAMP,
                review_notes TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS ix_trip_reports_voyage ON trip_reports(voyage_id)",
            "CREATE INDEX IF NOT EXISTS ix_trip_reports_status ON trip_reports(status)",
        ]
        for sql in pg_stmts:
            try:
                db.session.execute(db.text(sql))
                db.session.commit()
            except Exception:
                db.session.rollback()
            db.session.rollback()