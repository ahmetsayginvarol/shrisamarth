from datetime import datetime
from flask import Blueprint, render_template, abort, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db, socketio
from app.models import Voyage, Booking, SEAT_ADJACENCY, WINDOW_SEATS
from app.staff.forms import BookingForm
from flask import send_file
from app.staff.ticket import generate_ticket, generate_group_ticket
import secrets
from app.staff.manifest import generate_manifest
from app.logging import log_activity

staff_bp = Blueprint('staff', __name__, template_folder='../templates/staff')


@staff_bp.before_request
@login_required
def restrict_to_staff():
    if not current_user.has_role('admin', 'reservation', 'driver'):
        abort(403)


# ============================================================
# DASHBOARD
# ============================================================
@staff_bp.route('/')
@staff_bp.route('/dashboard')
def dashboard():
    from datetime import datetime, date

    # Get date from query param, default to today
    date_str = request.args.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    # All scheduled voyages (for checking which dates have voyages)
    all_scheduled = (Voyage.query
                     .filter_by(status='scheduled')
                     .order_by(Voyage.departure_at.asc())
                     .all())

    # Filter voyages for the selected date
    day_voyages = [v for v in all_scheduled
                   if v.departure_at.date() == selected_date]

    # If no voyages on selected date, try to find the next date with voyages
    if not day_voyages and not date_str:
        for v in all_scheduled:
            if v.departure_at.date() >= date.today():
                selected_date = v.departure_at.date()
                day_voyages = [vv for vv in all_scheduled
                               if vv.departure_at.date() == selected_date]
                break

    # Which voyage is selected
    voyage_id = request.args.get('voyage_id', type=int)
    if voyage_id:
        voyage = Voyage.query.get_or_404(voyage_id)
    elif day_voyages:
        voyage = day_voyages[0]
    else:
        voyage = None

    # Driver restriction
    if current_user.role == 'driver' and voyage:
        if voyage.driver_id != current_user.id:
            voyage = next((v for v in day_voyages
                           if v.driver_id == current_user.id), None)

    bookings = []
    if voyage:
        bookings = Booking.query.filter_by(
            voyage_id=voyage.id, status='confirmed'
        ).all()

    seat_map = {b.seat_id: b for b in bookings}

    # Collect dates that have voyages (for highlighting in date picker)
    voyage_dates = list(set(
        v.departure_at.strftime('%Y-%m-%d') for v in all_scheduled
    ))

    return render_template(
        'staff/dashboard.html',
        voyage=voyage,
        day_voyages=day_voyages,
        scheduled=all_scheduled,
        seat_map=seat_map,
        window_seats=WINDOW_SEATS,
        role=current_user.role,
        selected_date=selected_date.strftime('%Y-%m-%d'),
        voyage_dates=voyage_dates,
    )


# ============================================================
# BOOKING JSON API (called by JS)
# ============================================================

@staff_bp.route('/api/seat/<int:voyage_id>/<seat_id>')
def seat_info(voyage_id, seat_id):
    """Return JSON for a clicked seat."""

    # Drivers get read-only — no booking form data
    if current_user.role == 'driver':
        booking = Booking.query.filter_by(
            voyage_id=voyage_id, seat_id=seat_id, status='confirmed'
        ).first()
        if booking:
            return jsonify({
                'status': 'booked',
                'seat_id': seat_id,
                'readonly': True,
                'booking': {
                    'id': booking.id,
                    'code': booking.booking_code,
                    'name': booking.passenger_name,
                    'phone': booking.passenger_phone,
                    'gender': booking.gender,
                    'boarding': booking.boarding_point,
                    'dropping': booking.dropping_point,
                    'fare': float(booking.fare),
                    'advance': float(booking.advance_paid or 0),
                    'balance': float(booking.balance_due or 0),
                }
            })
        else:
            return jsonify({'status': 'available', 'seat_id': seat_id, 'readonly': True})

    # Reservation / admin — full info
    booking = Booking.query.filter_by(
        voyage_id=voyage_id, seat_id=seat_id, status='confirmed'
    ).first()

    if booking:
        group_seats = []
        if booking.group_booking_code:
            siblings = Booking.query.filter_by(
                group_booking_code=booking.group_booking_code, status='confirmed'
            ).all()
            group_seats = [b.seat_id for b in siblings]

        return jsonify({
            'status': 'booked',
            'seat_id': seat_id,
            'readonly': False,
            'booking': {
                'id': booking.id,
                'code': booking.booking_code,
                'group_code': booking.group_booking_code,
                'group_seats': group_seats,
                'name': booking.passenger_name,
                'phone': booking.passenger_phone,
                'gender': booking.gender,
                'boarding': booking.boarding_point,
                'dropping': booking.dropping_point,
                'fare': float(booking.fare),
                'advance': float(booking.advance_paid or 0),
                'balance': float(booking.balance_due or 0),
            }
        })

    adjacent_seats = SEAT_ADJACENCY.get(seat_id, [])
    adjacent_genders = []
    for adj_id in adjacent_seats:
        adj_booking = Booking.query.filter_by(
            voyage_id=voyage_id, seat_id=adj_id, status='confirmed'
        ).first()
        if adj_booking:
            adjacent_genders.append({
                'seat': adj_id,
                'gender': adj_booking.gender,
                'name': adj_booking.passenger_name
            })

    return jsonify({
        'status': 'available',
        'seat_id': seat_id,
        'readonly': False,
        'is_window': seat_id in WINDOW_SEATS,
        'adjacent_genders': adjacent_genders,
    })

# ============================================================
# CREATE BOOKING
# =================================# CANCEL BOOKING
# ============================================================
@staff_bp.route('/booking/create', methods=['POST'])
def create_booking():
    if not current_user.has_role('admin', 'reservation'):
        abort(403)

    form = BookingForm()
    if not form.validate_on_submit():
        return jsonify({'status': 'error', 'errors': form.errors}), 400

    voyage = Voyage.query.get_or_404(int(form.voyage_id.data))
    seat_id = form.seat_id.data.strip()

    # Server-side gender conflict check
    adjacent = SEAT_ADJACENCY.get(seat_id, [])
    conflicts = []
    for adj_id in adjacent:
        adj = Booking.query.filter_by(
            voyage_id=voyage.id, seat_id=adj_id, status='confirmed'
        ).first()
        if adj and adj.gender != form.gender.data:
            conflicts.append(adj.seat_id)

    if conflicts and form.confirm_gender_conflict.data != 'yes':
        return jsonify({
            'status': 'gender_conflict',
            'conflict_seats': conflicts,
            'message': f'Adjacent seat(s) {", ".join(conflicts)} booked by opposite gender.'
        }), 200

    fare = form.fare.data
    advance = form.advance_paid.data or 0
    balance = fare - advance
    code = f"SHRI-{voyage.departure_at.strftime('%Y%m%d')}-{seat_id}-{secrets.token_hex(3).upper()}"
    booking = Booking(
        voyage_id=voyage.id,
        seat_id=seat_id,
        passenger_name=form.passenger_name.data.strip(),
        passenger_phone=form.passenger_phone.data.strip(),
        gender=form.gender.data,
        boarding_point=form.boarding_point.data,
        dropping_point=form.dropping_point.data,
        fare=fare,
        advance_paid=advance,
        balance_due=balance,
        booking_code=code,
        created_by_id=current_user.id,
        status='confirmed',
    )

    try:
        db.session.add(booking)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': 'This seat was just booked by someone else. Please refresh and try again.'
        }), 409

    log_activity('booking_created',
                 f'Booked seat {booking.seat_id} for {booking.passenger_name} on {voyage.origin}→{voyage.destination}',
                 'booking', booking.id)
    socketio.emit('seat_booked', {
        'voyage_id': voyage.id,
        'seat_id': booking.seat_id,
        'gender': booking.gender,
        'name': booking.passenger_name,
    })

    return jsonify({
        'status': 'success',
        'booking': {
            'id': booking.id,
            'code': booking.booking_code,
            'seat_id': booking.seat_id,
            'name': booking.passenger_name,
            'gender': booking.gender,
        }
    })


@staff_bp.route('/booking/create-group', methods=['POST'])
def create_group_booking():
    if not current_user.has_role('admin', 'reservation'):
        abort(403)

    voyage_id = request.form.get('voyage_id', type=int)
    seat_ids_raw = request.form.getlist('seat_ids[]')
    passenger_name = (request.form.get('passenger_name') or '').strip()
    passenger_phone = (request.form.get('passenger_phone') or '').strip()
    gender = request.form.get('gender', '')
    boarding_point = request.form.get('boarding_point', '')
    dropping_point = request.form.get('dropping_point', '')
    fare_per_seat = request.form.get('fare', type=float, default=0)
    advance_paid = request.form.get('advance_paid', type=float, default=0)

    seat_ids = [s.strip() for s in seat_ids_raw if s.strip()]

    if not voyage_id or not seat_ids or not passenger_name or not passenger_phone or gender not in ('M', 'F'):
        return jsonify({'status': 'error', 'message': 'Missing required fields.'}), 400

    voyage = Voyage.query.get_or_404(voyage_id)

    # Verify all seats are still available
    for sid in seat_ids:
        existing = Booking.query.filter_by(voyage_id=voyage.id, seat_id=sid, status='confirmed').first()
        if existing:
            return jsonify({'status': 'error', 'message': f'Seat {sid} was just booked. Please refresh.'}), 409

    total_fare = fare_per_seat * len(seat_ids)
    balance = total_fare - advance_paid

    group_code = f"GRP-{voyage.departure_at.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"

    bookings_created = []
    try:
        for sid in seat_ids:
            per_seat_advance = round(advance_paid / len(seat_ids), 2)
            per_seat_balance = fare_per_seat - per_seat_advance
            code = f"SHRI-{voyage.departure_at.strftime('%Y%m%d')}-{sid}-{secrets.token_hex(3).upper()}"
            b = Booking(
                voyage_id=voyage.id,
                seat_id=sid,
                passenger_name=passenger_name,
                passenger_phone=passenger_phone,
                gender=gender,
                boarding_point=boarding_point,
                dropping_point=dropping_point,
                fare=fare_per_seat,
                advance_paid=per_seat_advance,
                balance_due=per_seat_balance,
                booking_code=code,
                group_booking_code=group_code,
                created_by_id=current_user.id,
                status='confirmed',
            )
            db.session.add(b)
            bookings_created.append(b)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'One or more seats were just booked. Please refresh.'}), 409

    for b in bookings_created:
        log_activity('booking_created',
                     f'Group booking {group_code}: seat {b.seat_id} for {b.passenger_name} on {voyage.origin}→{voyage.destination}',
                     'booking', b.id)
        socketio.emit('seat_booked', {
            'voyage_id': voyage.id,
            'seat_id': b.seat_id,
            'gender': b.gender,
            'name': b.passenger_name,
        })

    return jsonify({
        'status': 'success',
        'group_code': group_code,
        'seat_ids': seat_ids,
        'bookings': [{'id': b.id, 'seat_id': b.seat_id, 'code': b.booking_code} for b in bookings_created],
        'name': passenger_name,
        'gender': gender,
    })


@staff_bp.route('/booking/group/<group_code>/ticket')
def download_group_ticket(group_code):
    bookings = Booking.query.filter_by(
        group_booking_code=group_code, status='confirmed'
    ).order_by(Booking.seat_id).all()
    if not bookings:
        abort(404)
    _ = bookings[0].voyage.bus
    pdf = generate_group_ticket(bookings)
    filename = f"ticket-{group_code}.pdf"
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=filename)


@staff_bp.route('/booking/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    if not current_user.has_role('admin', 'reservation'):
        abort(403)

    booking = Booking.query.get_or_404(booking_id)
    booking.status = 'cancelled'
    db.session.commit()

    log_activity('booking_cancelled',
                 f'Cancelled seat {booking.seat_id} ({booking.passenger_name}) on voyage {booking.voyage_id}',
                 'booking', booking_id)
    socketio.emit('seat_freed', {
        'voyage_id': booking.voyage_id,
        'seat_id': booking.seat_id,
    })

    return jsonify({'status': 'success', 'seat_id': booking.seat_id})

@staff_bp.route('/booking/<int:booking_id>/ticket')
def download_ticket(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # Load relationships explicitly
    _ = booking.voyage.bus

    pdf = generate_ticket(booking)

    filename = f"ticket-{booking.booking_code}.pdf"
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )
@staff_bp.route('/manifest/<int:voyage_id>/pdf')
def download_manifest(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)

    # Load relationships
    _ = voyage.bus
    _ = voyage.driver

    bookings = Booking.query.filter_by(
        voyage_id=voyage.id, status='confirmed'
    ).all()

    pdf = generate_manifest(voyage, bookings)

    filename = f"manifest-{voyage.origin}-{voyage.destination}-{voyage.departure_at.strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )