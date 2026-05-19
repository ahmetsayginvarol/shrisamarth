from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db, socketio
from app.models import Booking
from app.logging import log_activity

verify_bp = Blueprint('verify', __name__)

OPERATOR_PHONE = '+91 98765 43210'


@verify_bp.route('/verify/<booking_code>')
def verify(booking_code):
    booking = Booking.query.filter_by(booking_code=booking_code).first()
    if not booking:
        booking = Booking.query.filter_by(
            group_booking_code=booking_code, status='confirmed'
        ).first()

    want_json = request.args.get('format') == 'json'

    if not booking or booking.status != 'confirmed':
        if want_json:
            return jsonify({'state': 'invalid'})
        return render_template('verify/verify.html', state='invalid',
                               operator_phone=OPERATOR_PHONE)

    voyage = booking.voyage
    is_group = bool(booking.group_booking_code)

    if is_group:
        group_bookings = Booking.query.filter_by(
            group_booking_code=booking.group_booking_code, status='confirmed'
        ).all()
        seat_display = ', '.join(sorted(b.seat_id for b in group_bookings))
    else:
        seat_display = booking.seat_id

    balance_due = float(booking.balance_due or 0)

    from flask_login import current_user
    show_amount = (current_user.is_authenticated and
                   current_user.has_role('admin', 'reservation', 'driver'))

    state = 'boarded' if booking.boarded_at else 'valid'

    ctx = {
        'state': state,
        'booking_code': booking.booking_code,
        'group_booking_code': booking.group_booking_code,
        'passenger_name': booking.passenger_name,
        'seat_display': seat_display,
        'is_group': is_group,
        'route': f"{voyage.origin} → {voyage.destination}",
        'departure': voyage.departure_at.strftime('%d %b %Y · %H:%M'),
        'boarding_point': booking.boarding_point,
        'dropping_point': booking.dropping_point,
        'bus_registration': voyage.bus.registration,
        'has_balance': balance_due > 0,
        'balance_due': balance_due if show_amount else None,
        'boarded_at': booking.boarded_at.strftime('%H:%M') if booking.boarded_at else None,
        'gender': booking.gender,
    }

    if want_json:
        return jsonify(ctx)
    return render_template('verify/verify.html', operator_phone=OPERATOR_PHONE, **ctx)


@verify_bp.route('/verify/<booking_code>/board', methods=['POST'])
def mark_boarded(booking_code):
    # Try individual booking code first, then group code
    booking = Booking.query.filter_by(
        booking_code=booking_code, status='confirmed'
    ).first()

    is_group_scan = False
    group_bookings = []

    if not booking:
        # Could be a group booking code
        group_bookings = Booking.query.filter_by(
            group_booking_code=booking_code, status='confirmed'
        ).all()
        if not group_bookings:
            return jsonify({'status': 'error', 'message': 'Booking not found'}), 404
        booking = group_bookings[0]
        is_group_scan = True

    if not is_group_scan:
        group_bookings = [booking]

    now = datetime.utcnow()
    all_boarded = all(b.boarded_at for b in group_bookings)

    if all_boarded:
        return jsonify({
            'status': 'already_boarded',
            'boarded_at': group_bookings[0].boarded_at.strftime('%H:%M'),
        })

    voyage = booking.voyage
    for b in group_bookings:
        if not b.boarded_at:
            b.boarded_at = now
    db.session.commit()

    for b in group_bookings:
        log_activity('passenger_boarded',
                     f'Passenger {b.passenger_name} boarded seat {b.seat_id} on {voyage.origin}→{voyage.destination}',
                     'booking', b.id)
        socketio.emit('passenger_boarded', {
            'voyage_id': voyage.id,
            'seat_id': b.seat_id,
            'booking_code': b.booking_code,
            'name': b.passenger_name,
            'boarded_at': b.boarded_at.strftime('%H:%M'),
        })

    return jsonify({
        'status': 'ok',
        'boarded_at': now.strftime('%H:%M'),
    })
