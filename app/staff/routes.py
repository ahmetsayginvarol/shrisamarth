from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from app.models import Voyage, Booking

staff_bp = Blueprint('staff', __name__, template_folder='../templates/staff')


@staff_bp.before_request
@login_required
def restrict_to_staff():
    """Only staff roles can access /staff/*."""
    if not current_user.has_role('admin', 'reservation', 'driver'):
        abort(403)


@staff_bp.route('/')
@staff_bp.route('/dashboard')
def dashboard():
    # For now, grab the next scheduled voyage. Later we'll add a voyage picker.
    voyage = (Voyage.query
              .filter_by(status='scheduled')
              .order_by(Voyage.departure_at.asc())
              .first())

    bookings = []
    if voyage:
        bookings = Booking.query.filter_by(voyage_id=voyage.id, status='confirmed').all()

    # Build a dict {seat_id: booking} for the template
    seat_map = {b.seat_id: b for b in bookings}

    return render_template(
        'staff/dashboard.html',
        voyage=voyage,
        seat_map=seat_map,
        role=current_user.role,
    )