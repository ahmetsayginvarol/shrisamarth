import json
from flask import request
from flask_login import current_user
from app.extensions import db

EVENT_TYPES = {
    'register':           'Registered account',
    'login':              'Logged in',
    'logout':             'Logged out',
    'booking_created':    'Booked a ticket',
    'booking_cancelled':  'Cancelled booking',
    'profile_updated':    'Updated profile',
    'password_changed':   'Changed password',
    'email_verified':     'Email address verified',
    'password_reset':     'Password reset via email',
    'account_deactivated': 'Account deactivated',
}

EVENT_ICONS = {
    'register':           '🎉',
    'login':              '🔓',
    'logout':             '🔒',
    'booking_created':    '🎫',
    'booking_cancelled':  '❌',
    'profile_updated':    '✏️',
    'password_changed':   '🔑',
    'email_verified':     '✅',
    'password_reset':     '🔑',
    'account_deactivated': '🚫',
}


def log_user_activity(user_id, event_type, description, metadata=None,
                      performed_by_id=None, ip=None):
    """Log a user-facing activity event for a customer account."""
    from app.models import UserActivityLog

    if ip is None:
        try:
            forwarded_for = request.headers.get('X-Forwarded-For')
            ip = forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr
        except RuntimeError:
            ip = None

    if performed_by_id is None:
        try:
            if current_user.is_authenticated:
                performed_by_id = current_user.id
        except RuntimeError:
            pass

    entry = UserActivityLog(
        user_id=user_id,
        event_type=event_type,
        description=description,
        metadata_json=json.dumps(metadata) if metadata else None,
        ip_address=ip,
        performed_by_id=performed_by_id,
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
