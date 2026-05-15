from flask import request
from flask_login import current_user
from app.extensions import db
from app.models import ActivityLog


def log_activity(action, description, target_type=None, target_id=None):
    """Log a user action to the activity log."""
    entry = ActivityLog(
        user_id=current_user.id if current_user and current_user.is_authenticated else None,
        action=action,
        description=description,
        target_type=target_type,
        target_id=target_id,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()