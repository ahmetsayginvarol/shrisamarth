from flask import request
from flask_login import current_user
from app.extensions import db
from app.models import ActivityLog


def log_activity(action, description, target_type=None, target_id=None):
    """Log a user action to the activity log."""
    if request:
        forwarded_for = request.headers.get('X-Forwarded-For')
        ip = forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr
    else:
        ip = None

    entry = ActivityLog(
        user_id=current_user.id if current_user and current_user.is_authenticated else None,
        action=action,
        description=description,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip,
    )
    db.session.add(entry)
    db.session.commit()


def notify_staff(title, message, link=None, booking_id=None, passenger_phone=None, urgent=False, user_ids=None):
    """Create a notification for staff users.

    user_ids: list of specific user IDs to notify. If None, notifies all active
              admin and reservation users (broadcast).
    """
    from app.models import Notification, User
    from app.extensions import socketio

    try:
        if user_ids is not None:
            staff_users = User.query.filter(
                User.id.in_(user_ids),
                User.is_active_account == True
            ).all()
        else:
            staff_users = User.query.filter(
                User.role.in_(['admin', 'reservation']),
                User.is_active_account == True
            ).all()

        for u in staff_users:
            n = Notification(
                user_id=u.id,
                title=title,
                message=message,
                link=link,
                booking_id=booking_id,
                passenger_phone=passenger_phone,
            )
            db.session.add(n)

        db.session.commit()

        # Real-time: emit unread count per user
        for u in staff_users:
            count = Notification.query.filter_by(user_id=u.id, is_read=False).count()
            socketio.emit('new_notification', {'count': count, 'title': title})

        if urgent:
            try:
                from flask import current_app
                from app.push import send_push_to_admins
                send_push_to_admins(
                    current_app._get_current_object(),
                    title, message, link,
                    user_ids=user_ids,
                )
            except Exception:
                pass
    except Exception as e:
        # Don't let notification failures break booking flow
        db.session.rollback()
        import sys
        print(f"notify_staff error: {e}", file=sys.stderr)