"""Initialize database — safe to run repeatedly."""
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    if not existing_tables:
        # Fresh database — create everything
        db.create_all()
        print("  Created all tables from scratch")
    else:
        # Tables exist — only add missing columns
        print(f"  Found {len(existing_tables)} existing tables")

        # Add group_booking_code to bookings if missing
        if 'bookings' in existing_tables:
            columns = [c['name'] for c in inspector.get_columns('bookings')]
            if 'group_booking_code' not in columns:
                db.session.execute(text(
                    'ALTER TABLE bookings ADD COLUMN group_booking_code VARCHAR(30)'
                ))
                db.session.commit()
                print("  Added group_booking_code column")

        # Create activity_log table if missing
        if 'activity_log' not in existing_tables:
            db.session.execute(text('''
                CREATE TABLE activity_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    action VARCHAR(50) NOT NULL,
                    description TEXT NOT NULL,
                    target_type VARCHAR(30),
                    target_id INTEGER,
                    ip_address VARCHAR(45),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            db.session.commit()
            print("  Created activity_log table")

    print("Database initialized successfully.")