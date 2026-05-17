"""Initialize database — safe to run repeatedly."""
from sqlalchemy import inspect, text
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    dialect = db.engine.dialect.name

    if not existing_tables:
        # Fresh database — create everything
        db.create_all()
        print("  Created all tables from scratch")
    else:
        print(f"  Found {len(existing_tables)} existing tables")

        # Add phone / gender to users if missing
        if 'users' in existing_tables:
            user_cols = [c['name'] for c in inspector.get_columns('users')]
            if 'phone' not in user_cols:
                db.session.execute(text('ALTER TABLE users ADD COLUMN phone VARCHAR(20)'))
                db.session.commit()
                print("  Added phone column to users")
            if 'gender' not in user_cols:
                db.session.execute(text('ALTER TABLE users ADD COLUMN gender VARCHAR(1)'))
                db.session.commit()
                print("  Added gender column to users")
            if 'credit_balance' not in user_cols:
                db.session.execute(text('ALTER TABLE users ADD COLUMN credit_balance NUMERIC(10,2) NOT NULL DEFAULT 0'))
                db.session.commit()
                print("  Added credit_balance column to users")

        # Add group_booking_code to bookings if missing
        if 'bookings' in existing_tables:
            columns = [c['name'] for c in inspector.get_columns('bookings')]
            if 'group_booking_code' not in columns:
                db.session.execute(text(
                    'ALTER TABLE bookings ADD COLUMN group_booking_code VARCHAR(30)'
                ))
                db.session.commit()
                print("  Added group_booking_code column")
            if 'passenger_email' not in columns:
                db.session.execute(text(
                    'ALTER TABLE bookings ADD COLUMN passenger_email VARCHAR(120)'
                ))
                db.session.commit()
                print("  Added passenger_email column")
            if 'boarded_at' not in columns:
                db.session.execute(text('ALTER TABLE bookings ADD COLUMN boarded_at TIMESTAMP'))
                db.session.commit()
                print("  Added boarded_at column to bookings")
            if 'boarded_by_id' not in columns:
                db.session.execute(text('ALTER TABLE bookings ADD COLUMN boarded_by_id INTEGER'))
                db.session.commit()
                print("  Added boarded_by_id column to bookings")

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

        # Create seat_locks table if missing
        if 'seat_locks' not in existing_tables:
            if dialect == 'postgresql':
                sql = """
                    CREATE TABLE seat_locks (
                        id          SERIAL PRIMARY KEY,
                        voyage_id   INTEGER NOT NULL REFERENCES voyages(id),
                        seat_id     VARCHAR(8) NOT NULL,
                        session_id  VARCHAR(64) NOT NULL,
                        locked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at  TIMESTAMP NOT NULL
                    )
                """
            else:
                sql = """
                    CREATE TABLE seat_locks (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        voyage_id   INTEGER NOT NULL REFERENCES voyages(id),
                        seat_id     VARCHAR(8) NOT NULL,
                        session_id  VARCHAR(64) NOT NULL,
                        locked_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at  TIMESTAMP NOT NULL
                    )
                """
            db.session.execute(text(sql))
            db.session.commit()
            print(f"  Created seat_locks table ({dialect})")

        # Create notifications table if missing
        if 'notifications' not in existing_tables:
            if dialect == 'postgresql':
                sql = """
                    CREATE TABLE notifications (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        title VARCHAR(120) NOT NULL,
                        message TEXT NOT NULL,
                        link VARCHAR(500),
                        booking_id INTEGER REFERENCES bookings(id),
                        passenger_phone VARCHAR(20),
                        is_read BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            else:
                sql = """
                    CREATE TABLE notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        title VARCHAR(120) NOT NULL,
                        message TEXT NOT NULL,
                        link VARCHAR(500),
                        booking_id INTEGER REFERENCES bookings(id),
                        passenger_phone VARCHAR(20),
                        is_read INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            db.session.execute(text(sql))
            db.session.commit()
            print(f"  Created notifications table ({dialect})")

        # Add recurrence_group to voyages if missing
        if 'voyages' in existing_tables:
            voyage_cols = [c['name'] for c in inspector.get_columns('voyages')]
            if 'recurrence_group' not in voyage_cols:
                db.session.execute(text('ALTER TABLE voyages ADD COLUMN recurrence_group VARCHAR(30)'))
                db.session.commit()
                print("  Added recurrence_group column to voyages")

        # Create route_stops table if missing
        if 'route_stops' not in existing_tables:
            if dialect == 'postgresql':
                sql = """
                    CREATE TABLE route_stops (
                        id          SERIAL PRIMARY KEY,
                        voyage_id   INTEGER NOT NULL REFERENCES voyages(id) ON DELETE CASCADE,
                        stop_name   VARCHAR(80) NOT NULL,
                        stop_type   VARCHAR(10) NOT NULL,
                        stop_time   VARCHAR(5),
                        stop_order  INTEGER NOT NULL DEFAULT 0
                    )
                """
            else:
                sql = """
                    CREATE TABLE route_stops (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        voyage_id   INTEGER NOT NULL REFERENCES voyages(id) ON DELETE CASCADE,
                        stop_name   VARCHAR(80) NOT NULL,
                        stop_type   VARCHAR(10) NOT NULL,
                        stop_time   VARCHAR(5),
                        stop_order  INTEGER NOT NULL DEFAULT 0
                    )
                """
            db.session.execute(text(sql))
            db.session.commit()
            print(f"  Created route_stops table ({dialect})")

    print("Database initialized successfully.")
