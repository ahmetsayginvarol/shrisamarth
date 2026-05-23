import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.extensions import db
from app.models import (User, Bus, Voyage, Booking,
    RouteStop, ActivityLog, Notification,
    PasswordResetToken,
    EmailVerificationToken, Newsletter, IpBan, AbuseLog,
    SeatLock)
from sqlalchemy import text

# Optional models — may not exist in all deployments
try:
    from app.models import DriverLocation
except ImportError:
    DriverLocation = None

try:
    from app.models import PassengerProfile
except ImportError:
    PassengerProfile = None

app = create_app()

with app.app_context():
    print("Starting production cleanup...")
    print("=" * 50)

    # Safety check — confirm before proceeding
    confirm = input(
        "This will delete ALL demo data.\n"
        "Type 'yes i am sure' to continue: "
    )
    if confirm != 'yes i am sure':
        print("Aborted.")
        exit(0)

    # Delete in correct order (foreign keys)
    print("Deleting bookings...")
    Booking.query.delete()

    print("Deleting seat locks...")
    SeatLock.query.delete()

    print("Deleting route stops...")
    RouteStop.query.delete()

    print("Deleting voyages...")
    Voyage.query.delete()

    print("Deleting buses...")
    Bus.query.delete()

    print("Deleting activity logs...")
    ActivityLog.query.delete()

    print("Deleting notifications...")
    Notification.query.delete()

    if DriverLocation is not None:
        print("Deleting driver locations...")
        DriverLocation.query.delete()

    if PassengerProfile is not None:
        print("Deleting passenger profiles...")
        PassengerProfile.query.delete()

    print("Deleting password reset tokens...")
    PasswordResetToken.query.delete()

    print("Deleting email verification tokens...")
    EmailVerificationToken.query.delete()

    print("Deleting newsletters (drafts)...")
    Newsletter.query.filter_by(status='draft').delete()

    print("Deleting IP bans and abuse logs...")
    IpBan.query.delete()
    AbuseLog.query.delete()

    # Delete all non-admin users
    print("Deleting test users (keeping admin)...")
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        print("ERROR: No admin user found! Aborting.")
        db.session.rollback()
        exit(1)

    # Delete all users except admin
    User.query.filter(User.id != admin.id).delete()

    db.session.commit()
    print("All demo data deleted.")

    # Reset sequences (PostgreSQL)
    print("Resetting sequences...")
    sequences = [
        'buses_id_seq', 'voyages_id_seq',
        'bookings_id_seq', 'route_stops_id_seq',
        'activity_log_id_seq', 'newsletters_id_seq',
    ]
    for seq in sequences:
        try:
            db.session.execute(text(f"ALTER SEQUENCE {seq} RESTART WITH 1"))
        except Exception:
            pass
    db.session.commit()

    # Print admin account details
    print("\nAdmin account kept:")
    print(f"  Username: {admin.username}")
    print(f"  Role: {admin.role}")
    print(f"  Email: {admin.email or 'not set'}")

    print("\n" + "=" * 50)
    print("CLEANUP COMPLETE")
    print("=" * 50)
    print("\nNext steps for the client:")
    print("1. Log in at shrisamarth.in/auth/login")
    print("2. Go to Admin → Users → change admin password")
    print("3. Go to Admin → Buses → add your buses")
    print("4. Go to Admin → Voyages → create your routes")
    print("5. Go to Admin → Homepage → update contact info")
    print("6. Test a booking end-to-end")
    print("\nThe system is ready for real operation.")
