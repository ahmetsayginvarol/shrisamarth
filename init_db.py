"""Initialize database — safe to run repeatedly."""
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    # Create any tables that don't exist yet
    db.create_all()

    # Add new columns that db.create_all() won't add to existing tables
    inspector = inspect(db.engine)

    # Check bookings table for group_booking_code
    columns = [c['name'] for c in inspector.get_columns('bookings')]
    if 'group_booking_code' not in columns:
        db.session.execute(text(
            'ALTER TABLE bookings ADD COLUMN group_booking_code VARCHAR(30)'
        ))
        db.session.commit()
        print("  Added group_booking_code column")

    # Check activity_log table exists (might be missing on older deploys)
    tables = inspector.get_table_names()
    if 'activity_log' not in tables:
        db.create_all()
        print("  Created activity_log table")

    print("Database initialized successfully.")