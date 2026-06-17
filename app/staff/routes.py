from datetime import datetime
from flask import Blueprint, render_template, abort, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db, socketio, limiter
from app.models import Voyage, Booking, RouteStop, SEAT_ADJACENCY, WINDOW_SEATS, CashCollection, TripReport, DriverCashSubmission, User
from app.staff.forms import BookingForm
from flask import send_file
from app.staff.ticket import generate_ticket, generate_group_ticket
import secrets
from app.staff.manifest import generate_manifest
from app.logging import log_activity, notify_staff
from app.models import Notification

staff_bp = Blueprint('staff', __name__, template_folder='../templates/staff')


def _get_stop_fare(voyage, boarding_point: str) -> float:
    """Return the correct fare for a boarding stop, falling back to base fare."""
    if boarding_point:
        stop = RouteStop.query.filter_by(
            voyage_id=voyage.id,
            stop_name=boarding_point,
            stop_type='boarding',
        ).first()
        if stop and stop.fare_override is not None:
            return float(stop.fare_override)
    return float(voyage.base_fare)


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

    is_driver = current_user.role == 'driver'

    if is_driver:
        # Drivers always see today only, filtered to their own voyages
        selected_date = date.today()
        date_str = None
        all_scheduled = (Voyage.query
                         .filter_by(status='scheduled', driver_id=current_user.id)
                         .order_by(Voyage.departure_at.asc())
                         .all())
    else:
        date_str = request.args.get('date')
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                selected_date = date.today()
        else:
            selected_date = date.today()

        all_scheduled = (Voyage.query
                         .filter_by(status='scheduled')
                         .order_by(Voyage.departure_at.asc())
                         .all())

    # Filter voyages for the selected date
    day_voyages = [v for v in all_scheduled
                   if v.departure_at.date() == selected_date]

    # Non-drivers: if no voyages today, jump to next available date
    if not is_driver and not day_voyages and not date_str:
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
        # Drivers can only see their own voyages
        if is_driver and voyage.driver_id != current_user.id:
            voyage = day_voyages[0] if day_voyages else None
    elif day_voyages:
        voyage = day_voyages[0]
    else:
        voyage = None

    from app.models import SeatLock

    bookings = []
    if voyage:
        bookings = Booking.query.filter_by(
            voyage_id=voyage.id, status='confirmed'
        ).all()

    seat_map = {b.seat_id: b for b in bookings}

    # Cleanup expired seat locks and get active ones for display
    SeatLock.query.filter(SeatLock.expires_at < datetime.utcnow()).delete()
    db.session.commit()
    locked_seats = []
    if voyage:
        locked_seats = [l.seat_id for l in
                        SeatLock.query.filter_by(voyage_id=voyage.id)
                        .filter(SeatLock.expires_at > datetime.utcnow()).all()]

    # Collect dates that have voyages (for highlighting in date picker)
    voyage_dates = list(set(
        v.departure_at.strftime('%Y-%m-%d') for v in all_scheduled
    ))

    boarding_stops = []
    dropping_stops = []
    stop_fares = {}
    if voyage:
        sorted_stops = sorted(voyage.stops, key=lambda s: s.stop_order)
        boarding_stops = [s for s in sorted_stops if s.stop_type == 'boarding']
        dropping_stops = [s for s in sorted_stops if s.stop_type == 'dropping']
        for s in boarding_stops:
            if s.fare_override is not None:
                stop_fares[s.stop_name] = float(s.fare_override)

    # POC summary for driver manifest
    poc_count = 0
    poc_total = 0
    for b in bookings:
        if b.payment_on_checkin:
            poc_count += 1
            poc_total += float(b.payment_on_checkin_amount or b.fare)

    # Driver outstanding cash balance = cash collected that is still physically
    # in the driver's hands = total collected - cash that has left their hands.
    # Cash leaves their hands once a submission reaches submitted/verified/
    # discrepancy/resolved. We key off expected_amount (what the driver claimed
    # to hand over) rather than submitted_amount, because the admin overwrites
    # submitted_amount with their own (possibly lower) count on a discrepancy —
    # and that dispute must NOT make the cash look like it's back in the driver's
    # pocket. A counted shortage is tracked separately as a discrepancy.
    driver_outstanding = 0
    if current_user.role == 'driver':
        all_driver_collections = CashCollection.query.filter_by(driver_id=current_user.id).all()
        total_driver_collected = sum(float(c.amount) for c in all_driver_collections)
        total_driver_handed_over = sum(
            float(s.expected_amount or 0)
            for s in DriverCashSubmission.query.filter(
                DriverCashSubmission.driver_id == current_user.id,
                DriverCashSubmission.submission_status.in_(
                    ['submitted', 'verified', 'discrepancy', 'resolved'])
            ).all()
        )
        driver_outstanding = max(0.0, total_driver_collected - total_driver_handed_over)

    admin_users = (
        User.query.filter(User.role.in_(['admin', 'super_admin']),
                          User.is_active_account == True)
        .order_by(User.full_name).all()
        if is_driver else []
    )

    return render_template(
        'staff/dashboard.html',
        voyage=voyage,
        day_voyages=day_voyages,
        scheduled=all_scheduled,
        seat_map=seat_map,
        window_seats=WINDOW_SEATS,
        locked_seats=locked_seats,
        role=current_user.role,
        selected_date=selected_date.strftime('%Y-%m-%d'),
        today_display=selected_date.strftime('%d %b %Y'),
        voyage_dates=voyage_dates,
        boarding_stops=boarding_stops,
        dropping_stops=dropping_stops,
        stop_fares=stop_fares,
        poc_count=poc_count,
        poc_total=int(poc_total),
        driver_outstanding=driver_outstanding,
        admin_users=admin_users,
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
            voyage = booking.voyage
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
                    'departure_date': voyage.departure_at.strftime('%d %b %Y'),
                    'departure_time': voyage.departure_at.strftime('%H:%M'),
                    'boarded_at': booking.boarded_at.strftime('%H:%M') if booking.boarded_at else None,
                    'boarded_by': booking.boarded_by.full_name if booking.boarded_by else None,
                    'payment_on_checkin': bool(booking.payment_on_checkin),
                    'poc_amount': float(booking.payment_on_checkin_amount) if booking.payment_on_checkin_amount else float(booking.fare),
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

        voyage = booking.voyage
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
                'departure_date': voyage.departure_at.strftime('%d %b %Y'),
                'departure_time': voyage.departure_at.strftime('%H:%M'),
                'boarded_at': booking.boarded_at.strftime('%H:%M') if booking.boarded_at else None,
                'boarded_by': booking.boarded_by.full_name if booking.boarded_by else None,
                'payment_on_checkin': bool(booking.payment_on_checkin),
                'poc_amount': float(booking.payment_on_checkin_amount) if booking.payment_on_checkin_amount else float(booking.fare),
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
@limiter.limit("10 per minute;100 per hour")
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

    # Server-side fare: ignore form value, look up correct stop fare
    fare = _get_stop_fare(voyage, form.boarding_point.data)
    advance = float(form.advance_paid.data or 0)
    # Payment on Check-in
    payment_on_checkin = request.form.get('payment_on_checkin') == '1'
    poc_amount_raw = request.form.get('payment_on_checkin_amount')
    payment_on_checkin_amount = float(poc_amount_raw) if poc_amount_raw else None
    if payment_on_checkin:
        advance = 0
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
        payment_on_checkin=payment_on_checkin,
        payment_on_checkin_amount=payment_on_checkin_amount,
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

    if booking.passenger_email:
        from app.email import send_eticket
        send_eticket(booking, voyage)

    socketio.emit('seat_booked', {
        'voyage_id': voyage.id,
        'seat_id': booking.seat_id,
        'gender': booking.gender,
        'name': booking.passenger_name,
    })
    notify_staff(
        title='New Booking',
        message=f"{booking.passenger_name} — Seat {booking.seat_id} — {voyage.origin}→{voyage.destination} {voyage.departure_at.strftime('%d %b %Y')}",
        link=url_for('staff.dashboard', voyage_id=voyage.id, date=voyage.departure_at.strftime('%Y-%m-%d')),
        booking_id=booking.id,
        passenger_phone=booking.passenger_phone,
    )

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
@limiter.limit("10 per minute;100 per hour")
def create_group_booking():
    if not current_user.has_role('admin', 'reservation'):
        abort(403)

    # New JSON format: per-seat individual passengers
    if request.is_json:
        data = request.get_json()
        voyage_id = data.get('voyage_id')
        passengers = data.get('passengers', [])  # [{seat_id, name, phone, gender}, ...]
        boarding_point = (data.get('boarding_point') or '').strip()
        dropping_point = (data.get('dropping_point') or '').strip()
        fare_per_seat = float(data.get('fare_per_seat', 0))
        advance_paid = float(data.get('advance_paid', 0))
        seat_ids = [str(p.get('seat_id', '')).strip() for p in passengers]
    else:
        # Legacy form-encoded format (backward compat)
        voyage_id = request.form.get('voyage_id', type=int)
        seat_ids_raw = request.form.getlist('seat_ids[]')
        passenger_name = (request.form.get('passenger_name') or '').strip()
        passenger_phone = (request.form.get('passenger_phone') or '').strip()
        gender = request.form.get('gender', '')
        boarding_point = (request.form.get('boarding_point') or '').strip()
        dropping_point = (request.form.get('dropping_point') or '').strip()
        fare_per_seat = request.form.get('fare', type=float, default=0)
        advance_paid = request.form.get('advance_paid', type=float, default=0)
        seat_ids = [s.strip() for s in seat_ids_raw if s.strip()]
        passengers = [{'seat_id': sid, 'name': passenger_name, 'phone': passenger_phone, 'gender': gender} for sid in seat_ids]

    if not voyage_id or not passengers:
        return jsonify({'status': 'error', 'message': 'Missing required fields.'}), 400

    # Validate each passenger record (gender optional for groups)
    is_group = len(seat_ids) > 1
    for p in passengers:
        if not p.get('name') or not p.get('phone') or not str(p.get('seat_id', '')).strip():
            return jsonify({'status': 'error', 'message': f'Missing details for seat {p.get("seat_id", "?")}'}), 400
        if not is_group and p.get('gender') not in ('M', 'F'):
            return jsonify({'status': 'error', 'message': f'Gender required for seat {p.get("seat_id", "?")}'}), 400

    voyage = Voyage.query.get_or_404(voyage_id)

    # Verify all seats still available
    for sid in seat_ids:
        existing = Booking.query.filter_by(voyage_id=voyage.id, seat_id=sid, status='confirmed').first()
        if existing:
            return jsonify({'status': 'error', 'message': f'Seat {sid} was just booked. Please refresh.'}), 409

    # Adjacent gender conflict check only applies to single-seat bookings with gender
    if not is_group:
        confirm_conflict = (
            data.get('confirm_gender_conflict') == 'yes' if request.is_json
            else request.form.get('confirm_gender_conflict') == 'yes'
        )
        if not confirm_conflict:
            seat_ids_set = set(seat_ids)
            conflict_msgs = []
            for p in passengers:
                sid = str(p['seat_id']).strip()
                pg = p.get('gender')
                for adj_id in SEAT_ADJACENCY.get(sid, []):
                    if adj_id in seat_ids_set:
                        continue
                    adj = Booking.query.filter_by(voyage_id=voyage.id, seat_id=adj_id, status='confirmed').first()
                    if adj and adj.gender and adj.gender != pg:
                        conflict_msgs.append(f"Seat {sid} ({p.get('name','')}) next to seat {adj_id} ({adj.passenger_name})")
            if conflict_msgs:
                return jsonify({
                    'status': 'gender_conflict',
                    'message': 'Adjacent seats have passengers of the opposite gender:\n' + '\n'.join(conflict_msgs),
                }), 200

    group_code = f"GRP-{voyage.departure_at.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}" if is_group else None

    bookings_created = []
    try:
        for p in passengers:
            sid = str(p['seat_id']).strip()
            # Server-side fare lookup per passenger boarding point
            p_boarding = (p.get('boarding_point') or boarding_point or '').strip()
            p_fare = _get_stop_fare(voyage, p_boarding)
            per_seat_advance = round(advance_paid / len(passengers), 2)
            per_seat_balance = p_fare - per_seat_advance
            code = f"SHRI-{voyage.departure_at.strftime('%Y%m%d')}-{sid}-{secrets.token_hex(3).upper()}"
            b = Booking(
                voyage_id=voyage.id,
                seat_id=sid,
                passenger_name=p['name'].strip(),
                passenger_phone=p['phone'].strip(),
                gender=p['gender'],
                boarding_point=p_boarding,
                dropping_point=(p.get('dropping_point') or dropping_point or '').strip(),
                fare=p_fare,
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

    if is_group and bookings_created:
        seat_detail = ' | '.join(f"{b.seat_id}: {b.passenger_name}" for b in bookings_created)
        log_activity(
            'group_booking_created',
            f'Group booking {group_code}: {len(bookings_created)} seats · {voyage.origin}→{voyage.destination} | {seat_detail}',
            'booking', bookings_created[0].id,
        )
    elif bookings_created:
        b = bookings_created[0]
        log_activity('booking_created',
                     f'Booking {b.booking_code}: seat {b.seat_id} for {b.passenger_name} on {voyage.origin}→{voyage.destination}',
                     'booking', b.id)

    # Send e-tickets for any booking that has an email (fire-and-forget)
    _has_email = any(b.passenger_email for b in bookings_created)
    if _has_email:
        from app.email import send_eticket
        for b in bookings_created:
            send_eticket(b, voyage)

    for b in bookings_created:
        socketio.emit('seat_booked', {
            'voyage_id': voyage.id,
            'seat_id': b.seat_id,
            'gender': b.gender,
            'name': b.passenger_name,
            'group_code': group_code,
        })

    first_name = bookings_created[0].passenger_name if bookings_created else ''
    if is_group:
        notify_staff(
            title='New Group Booking',
            message=f"{first_name} +{len(seat_ids)-1} — {len(seat_ids)} seats ({', '.join(seat_ids)}) — {voyage.origin}→{voyage.destination} {voyage.departure_at.strftime('%d %b %Y')}",
            link=url_for('staff.dashboard', voyage_id=voyage.id, date=voyage.departure_at.strftime('%Y-%m-%d')),
            booking_id=bookings_created[0].id if bookings_created else None,
            passenger_phone=bookings_created[0].passenger_phone if bookings_created else '',
        )
    else:
        b = bookings_created[0]
        notify_staff(
            title='New Booking',
            message=f"{b.passenger_name} — Seat {b.seat_id} — {voyage.origin}→{voyage.destination} {voyage.departure_at.strftime('%d %b %Y')}",
            link=url_for('staff.dashboard', voyage_id=voyage.id, date=voyage.departure_at.strftime('%Y-%m-%d')),
            booking_id=b.id,
            passenger_phone=b.passenger_phone,
        )

    return jsonify({
        'status': 'success',
        'group_code': group_code,
        'seat_ids': seat_ids,
        'bookings': [{'id': b.id, 'seat_id': b.seat_id, 'code': b.booking_code, 'name': b.passenger_name, 'gender': b.gender} for b in bookings_created],
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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Database error. Please try again.'}), 500

    log_activity('booking_cancelled',
                 f'Cancelled seat {booking.seat_id} ({booking.passenger_name}) on voyage {booking.voyage_id}',
                 'booking', booking_id)
    try:
        from app.abuse import get_client_ip, log_abuse_event
        log_abuse_event(get_client_ip(), 'booking_cancelled',
                        user_id=current_user.id,
                        details=f'booking:{booking.booking_code}')
    except Exception:
        pass
    socketio.emit('seat_freed', {
        'voyage_id': booking.voyage_id,
        'seat_id': booking.seat_id,
    })
    notify_staff(
        title='Booking Cancelled',
        message=f"{booking.passenger_name} — Seat {booking.seat_id} — {booking.voyage.origin}→{booking.voyage.destination}",
        booking_id=booking.id,
        passenger_phone=booking.passenger_phone,
    )

    return jsonify({'status': 'success', 'seat_id': booking.seat_id})


@staff_bp.route('/booking/<int:booking_id>/checkin', methods=['POST'])
@login_required
def checkin_booking(booking_id):
    if not current_user.has_role('admin', 'reservation', 'driver'):
        abort(403)
    booking = Booking.query.get_or_404(booking_id)
    if booking.boarded_at:
        return jsonify({
            'status': 'already_checked_in',
            'boarded_at': booking.boarded_at.strftime('%H:%M'),
            'boarded_by': booking.boarded_by.full_name if booking.boarded_by else None,
        })
    booking.boarded_at = datetime.utcnow()
    booking.boarded_by_id = current_user.id
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Database error. Please try again.'}), 500
    voyage = booking.voyage
    log_activity('passenger_checkin',
                 f'{current_user.full_name} checked in {booking.passenger_name} seat {booking.seat_id} on {voyage.origin}→{voyage.destination}',
                 'booking', booking.id)
    socketio.emit('passenger_checkin', {
        'voyage_id': voyage.id,
        'seat_id': booking.seat_id,
        'booking_id': booking.id,
        'passenger_name': booking.passenger_name,
        'boarded_at': booking.boarded_at.strftime('%H:%M'),
        'gender': booking.gender,
    })
    return jsonify({
        'status': 'ok',
        'boarded_at': booking.boarded_at.strftime('%H:%M'),
        'boarded_by': current_user.full_name,
    })


@staff_bp.route('/booking/<int:booking_id>/uncheckin', methods=['POST'])
@login_required
def uncheckin_booking(booking_id):
    if not current_user.has_role('admin', 'reservation', 'driver'):
        abort(403)
    booking = Booking.query.get_or_404(booking_id)
    if not booking.boarded_at:
        return jsonify({'status': 'not_checked_in'})
    # Allow undo within 5 minutes, or if admin/reservation
    from datetime import datetime, timedelta
    elapsed = datetime.utcnow() - booking.boarded_at
    if elapsed > timedelta(minutes=5) and not current_user.has_role('admin', 'reservation'):
        return jsonify({'status': 'error', 'message': 'Undo window expired (5 minutes)'}), 403
    voyage = booking.voyage
    booking.boarded_at = None
    booking.boarded_by_id = None
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Database error. Please try again.'}), 500
    log_activity('passenger_uncheckin',
                 f'{current_user.full_name} undid check-in for {booking.passenger_name} seat {booking.seat_id} on {voyage.origin}→{voyage.destination}',
                 'booking', booking.id)
    socketio.emit('passenger_uncheckin', {
        'voyage_id': voyage.id,
        'seat_id': booking.seat_id,
        'booking_id': booking.id,
        'gender': booking.gender,
    })
    return jsonify({'status': 'ok'})


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
@staff_bp.route('/api/notifications')
def get_notifications():
    if not current_user.has_role('admin', 'reservation'):
        return jsonify({'error': 'forbidden'}), 403

    notes = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).limit(20).all()

    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

    def time_ago(dt):
        diff = datetime.utcnow() - dt
        if diff.seconds < 60: return 'just now'
        if diff.seconds < 3600: return f"{diff.seconds//60}m ago"
        if diff.days == 0: return f"{diff.seconds//3600}h ago"
        return f"{diff.days}d ago"

    return jsonify({
        'unread': unread,
        'notifications': [{
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'booking_id': n.booking_id,
            'passenger_phone': n.passenger_phone,
            'is_read': n.is_read,
            'time_ago': time_ago(n.created_at),
        } for n in notes]
    })


@staff_bp.route('/api/notifications/read/<int:nid>', methods=['POST'])
def mark_notification_read(nid):
    n = Notification.query.filter_by(id=nid, user_id=current_user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({'ok': True})


@staff_bp.route('/api/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})


@staff_bp.route('/manifest/<int:voyage_id>/pdf')
def download_manifest(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)

    _ = voyage.bus
    _ = voyage.driver

    bookings = Booking.query.filter_by(
        voyage_id=voyage.id, status='confirmed'
    ).all()

    lang = request.args.get('lang', 'en')
    if lang not in ('en', 'hi'):
        lang = 'en'

    pdf = generate_manifest(voyage, bookings, lang=lang)

    filename = f"manifest-{voyage.origin}-{voyage.destination}-{voyage.departure_at.strftime('%Y%m%d')}.pdf"
    return send_file(
        pdf,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )


# ============================================================
# CASH COLLECTION API (driver)
# ============================================================

@staff_bp.route('/cash/collect', methods=['POST'])
@login_required
def cash_collect():
    """Driver records cash collected for an existing booking's balance."""
    if not current_user.has_role('driver', 'admin', 'reservation'):
        abort(403)

    data = request.get_json() or {}
    booking_id = data.get('booking_id')
    if not booking_id:
        return jsonify({'status': 'error', 'message': 'booking_id required'}), 400

    booking = Booking.query.get_or_404(booking_id)

    # Check if already collected
    existing = CashCollection.query.filter_by(booking_id=booking_id).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Cash already recorded for this booking.'}), 409

    amount = float(data.get('amount', float(booking.balance_due or 0)))
    if amount <= 0:
        return jsonify({'status': 'error', 'message': 'Amount must be positive.'}), 400

    cc = CashCollection(
        voyage_id=booking.voyage_id,
        booking_id=booking.id,
        driver_id=current_user.id,
        passenger_name=booking.passenger_name,
        passenger_phone=booking.passenger_phone,
        seat_id=booking.seat_id,
        boarding_point=booking.boarding_point,
        dropping_point=booking.dropping_point,
        amount=amount,
        is_walkin=False,
        notes=data.get('notes', '').strip() or None,
    )
    db.session.add(cc)
    # Clear payment_on_checkin flag once cash is collected
    if booking.payment_on_checkin:
        booking.payment_on_checkin = False
    db.session.commit()

    log_activity('cash_collected',
                 f'{current_user.full_name} collected ₹{int(amount)} from {booking.passenger_name} (seat {booking.seat_id})',
                 'booking', booking.id)

    socketio.emit('cash_collected', {
        'driver_id': current_user.id,
        'voyage_id': booking.voyage_id,
        'amount': amount,
    })

    return jsonify({'status': 'ok', 'collection_id': cc.id, 'amount': amount})


@staff_bp.route('/cash/walkin', methods=['POST'])
@login_required
def cash_walkin():
    """Driver adds a walk-in passenger not pre-booked online."""
    if not current_user.has_role('driver', 'admin', 'reservation'):
        abort(403)

    data = request.get_json() or {}
    voyage_id = data.get('voyage_id')
    if not voyage_id:
        return jsonify({'status': 'error', 'message': 'voyage_id required'}), 400

    voyage = Voyage.query.get_or_404(int(voyage_id))

    if current_user.role == 'driver' and voyage.driver_id != current_user.id:
        abort(403)

    seat_id = str(data.get('seat_id', '')).strip()
    if not seat_id:
        return jsonify({'status': 'error', 'message': 'Seat ID required'}), 400

    existing = Booking.query.filter_by(voyage_id=voyage.id, seat_id=seat_id, status='confirmed').first()
    if existing:
        return jsonify({'status': 'error', 'message': f'Seat {seat_id} is already booked.'}), 409

    name = data.get('passenger_name', '').strip()
    phone = data.get('passenger_phone', '').strip()
    gender = data.get('gender', '') or None
    boarding = data.get('boarding_point', '').strip()
    dropping = data.get('dropping_point', '').strip()
    amount = float(data.get('amount', 0))

    if not name or not phone:
        return jsonify({'status': 'error', 'message': 'Name and phone are required.'}), 400

    code = f"WALK-{voyage.departure_at.strftime('%Y%m%d')}-{seat_id}-{secrets.token_hex(3).upper()}"
    booking = Booking(
        voyage_id=voyage.id,
        seat_id=seat_id,
        passenger_name=name,
        passenger_phone=phone,
        gender=gender,
        boarding_point=boarding,
        dropping_point=dropping,
        fare=amount,
        advance_paid=amount,
        balance_due=0,
        booking_code=code,
        booking_type='walkin',
        created_by_id=current_user.id,
        status='confirmed',
    )

    cc = CashCollection(
        voyage_id=voyage.id,
        driver_id=current_user.id,
        passenger_name=name,
        passenger_phone=phone,
        seat_id=seat_id,
        boarding_point=boarding,
        dropping_point=dropping,
        amount=amount,
        is_walkin=True,
    )

    try:
        db.session.add(booking)
        db.session.flush()
        cc.booking_id = booking.id
        db.session.add(cc)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Seat {seat_id} was just taken. Please refresh.'}), 409

    log_activity('booking_created',
                 f'Walk-in booking {code}: seat {seat_id} for {name} on {voyage.origin}→{voyage.destination}',
                 'booking', booking.id)

    socketio.emit('seat_booked', {
        'voyage_id': voyage.id,
        'seat_id': seat_id,
        'gender': gender or 'g',
        'name': name,
    })

    socketio.emit('cash_collected', {
        'driver_id': current_user.id,
        'voyage_id': voyage.id,
        'amount': amount,
    })

    return jsonify({
        'status': 'ok',
        'booking_code': code,
        'seat_id': seat_id,
        'booking_id': booking.id,
    })


@staff_bp.route('/cash/voyage/<int:voyage_id>/collections')
@login_required
def voyage_collections(voyage_id):
    """Get all cash collections for a voyage."""
    voyage = Voyage.query.get_or_404(voyage_id)

    if current_user.role == 'driver' and voyage.driver_id != current_user.id:
        abort(403)

    driver_id = current_user.id if current_user.role == 'driver' else None
    q = CashCollection.query.filter_by(voyage_id=voyage_id)
    if driver_id:
        q = q.filter_by(driver_id=driver_id)
    collections = q.order_by(CashCollection.collected_at).all()

    total = sum(float(c.amount) for c in collections)

    existing_report = TripReport.query.filter_by(voyage_id=voyage_id, driver_id=current_user.id).first()

    # Latest pending/submitted record (driver view — disable Submit Cash if awaiting verification)
    sub = None
    verified_amount = 0.0
    in_transit_amount = 0.0
    handed_over_amount = 0.0
    if driver_id:
        sub = DriverCashSubmission.query.filter(
            DriverCashSubmission.driver_id == driver_id,
            DriverCashSubmission.voyage_id == voyage_id,
            DriverCashSubmission.submission_status.in_(['pending', 'submitted'])
        ).order_by(DriverCashSubmission.created_at.desc()).first()

        # All submissions for this voyage, bucketed by state
        voyage_subs = DriverCashSubmission.query.filter(
            DriverCashSubmission.driver_id == driver_id,
            DriverCashSubmission.voyage_id == voyage_id,
        ).all()
        for s in voyage_subs:
            if s.submission_status in ('verified', 'resolved'):
                verified_amount += float(s.submitted_amount or 0)
            elif s.submission_status == 'submitted':
                in_transit_amount += float(s.submitted_amount or 0)
            # Cash that has physically left the driver's hands (incl. discrepancy).
            # Keyed off expected_amount (the claimed hand-over) so an admin's
            # later short count does not make the cash reappear as outstanding.
            if s.submission_status in ('submitted', 'verified', 'discrepancy', 'resolved'):
                handed_over_amount += float(s.expected_amount or 0)

    # What the driver still physically holds for this voyage
    unsubmitted_amount = max(0.0, total - handed_over_amount)

    # Global outstanding across ALL voyages (for the persistent reminder banner,
    # which is not voyage-specific). Same rule: collected minus everything that
    # has left the driver's hands (keyed off expected_amount / the claim).
    driver_total_outstanding = 0.0
    if driver_id:
        all_driver_collected = sum(
            float(c.amount)
            for c in CashCollection.query.filter_by(driver_id=driver_id).all()
        )
        all_driver_handed_over = sum(
            float(s.expected_amount or 0)
            for s in DriverCashSubmission.query.filter(
                DriverCashSubmission.driver_id == driver_id,
                DriverCashSubmission.submission_status.in_(
                    ['submitted', 'verified', 'discrepancy', 'resolved'])
            ).all()
        )
        driver_total_outstanding = max(0.0, all_driver_collected - all_driver_handed_over)

    return jsonify({
        'collections': [{
            'id': c.id,
            'passenger_name': c.passenger_name,
            'seat_id': c.seat_id,
            'amount': float(c.amount),
            'is_walkin': c.is_walkin,
            'collected_at': c.collected_at.strftime('%H:%M'),
            'booking_id': c.booking_id,
        } for c in collections],
        'total': total,
        'count': len(collections),
        'report_submitted': existing_report is not None,
        'report_status': existing_report.status if existing_report else None,
        'submission_status': sub.submission_status if sub else None,
        'submitted_to': sub.submitted_to_admin.full_name if sub and sub.submitted_to_admin else None,
        'submitted_at': sub.submitted_at.strftime('%d %b · %H:%M') if sub and sub.submitted_at else None,
        'verified_amount': verified_amount,
        'in_transit_amount': in_transit_amount,
        'unsubmitted_amount': unsubmitted_amount,
        'driver_total_outstanding': driver_total_outstanding,
    })


@staff_bp.route('/trip-report/submit', methods=['POST'])
@login_required
def submit_trip_report():
    """Driver submits trip report at end of voyage."""
    if not current_user.has_role('driver', 'admin', 'reservation'):
        abort(403)

    data = request.get_json() or {}
    voyage_id = data.get('voyage_id')
    if not voyage_id:
        return jsonify({'status': 'error', 'message': 'voyage_id required'}), 400

    voyage = Voyage.query.get_or_404(int(voyage_id))

    if current_user.role == 'driver' and voyage.driver_id != current_user.id:
        abort(403)

    existing = TripReport.query.filter_by(voyage_id=voyage_id, driver_id=current_user.id).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Trip report already submitted.'}), 400

    collections = CashCollection.query.filter_by(
        voyage_id=voyage_id, driver_id=current_user.id
    ).all()
    total_collected = sum(float(c.amount) for c in collections)
    walkin_count = sum(1 for c in collections if c.is_walkin)

    report = TripReport(
        voyage_id=voyage_id,
        driver_id=current_user.id,
        status='pending',
        total_collected=total_collected,
        walkin_count=walkin_count,
        notes=data.get('notes', '').strip() or None,
    )
    db.session.add(report)
    db.session.commit()

    notify_staff(
        title='Trip Report Submitted',
        message=(f"{current_user.full_name} — {voyage.origin}→{voyage.destination} "
                 f"{voyage.departure_at.strftime('%d %b %Y')} — "
                 f"₹{int(total_collected)} collected ({len(collections)} entries)"),
        link=url_for('admin.trip_reports'),
    )
    log_activity('trip_report_submitted',
                 f'Driver {current_user.full_name} submitted trip report for voyage {voyage_id}',
                 'voyage', voyage_id)

    return jsonify({'status': 'ok', 'report_id': report.id, 'total_collected': total_collected})


@staff_bp.route('/cash/poc-clear/<int:booking_id>', methods=['POST'])
@login_required
def poc_clear(booking_id):
    """Clear payment_on_checkin flag after driver collects cash."""
    if not current_user.has_role('driver', 'admin', 'reservation'):
        abort(403)
    booking = Booking.query.get_or_404(booking_id)
    booking.payment_on_checkin = False
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'Database error.'}), 500
    return jsonify({'status': 'ok'})


# ============================================================
# DRIVER → ADMIN CASH HANDOVER
# ============================================================

@staff_bp.route('/cash/submit', methods=['POST'])
@login_required
def submit_cash_to_admin():
    """Driver physically hands cash to an admin — creates DriverCashSubmission records."""
    if current_user.role != 'driver':
        abort(403)

    data = request.get_json() or {}
    admin_id = int(data.get('admin_id') or 0)
    mode = data.get('mode', 'all')       # 'all' | 'custom'
    custom_amount = float(data.get('amount') or 0)
    notes = (data.get('notes') or '').strip()

    admin = User.query.get(admin_id)
    if not admin or admin.role not in ('admin', 'super_admin'):
        return jsonify({'error': 'Invalid admin selected'}), 400

    from collections import defaultdict

    # Amount per voyage that has already physically left the driver's hands.
    # Covers verified/resolved (confirmed by admin), submitted (in transit,
    # awaiting count) and discrepancy (handed over but disputed). The driver
    # cannot re-submit any of this — only cash still in hand is submittable.
    # Keyed off expected_amount (the claimed hand-over) so a disputed short
    # count by the admin doesn't re-open the cash for submission.
    handed_over_per_voyage = defaultdict(float)
    for s in DriverCashSubmission.query.filter(
        DriverCashSubmission.driver_id == current_user.id,
        DriverCashSubmission.submission_status.in_(
            ['verified', 'resolved', 'submitted', 'discrepancy'])
    ).all():
        handed_over_per_voyage[s.voyage_id] += float(s.expected_amount or 0)

    # Only pending records can be upserted — submitted records are already in admin's hands
    existing_subs = {}
    for s in DriverCashSubmission.query.filter(
        DriverCashSubmission.driver_id == current_user.id,
        DriverCashSubmission.submission_status == 'pending'
    ).all():
        existing_subs[s.voyage_id] = s

    all_collections = CashCollection.query.filter_by(driver_id=current_user.id).all()
    by_voyage = defaultdict(list)
    for c in all_collections:
        if c.voyage_id:
            by_voyage[c.voyage_id].append(c)

    # Only voyages with cash still physically in the driver's hands
    outstanding_voyages = {}
    total_outstanding = 0.0
    for voyage_id, cols in by_voyage.items():
        voyage_total = sum(float(c.amount) for c in cols)
        already_handed_over = handed_over_per_voyage.get(voyage_id, 0.0)
        outstanding = voyage_total - already_handed_over
        if outstanding > 0.01:
            outstanding_voyages[voyage_id] = {
                'collections': cols,
                'expected': outstanding,
                'existing_sub': existing_subs.get(voyage_id),
            }
            total_outstanding += outstanding

    if not outstanding_voyages:
        return jsonify({'error': 'No outstanding cash to submit'}), 400

    if mode == 'all':
        submit_total = total_outstanding
    else:
        # Custom amount: must be positive and cannot exceed cash in hand
        if custom_amount <= 0:
            return jsonify({'error': 'Enter a valid amount to submit'}), 400
        if custom_amount > total_outstanding + 0.01:
            return jsonify({
                'error': f'You can submit at most ₹{total_outstanding:.0f} '
                         f'(cash currently in hand).'
            }), 400
        submit_total = custom_amount
    now = datetime.utcnow()
    created = 0

    # Allocate the submitted total across voyages proportionally. Track the
    # running remainder so the final voyage absorbs any rounding drift and the
    # per-voyage amounts always sum exactly to submit_total.
    voyage_items = list(outstanding_voyages.items())
    allocated = 0.0
    for idx, (voyage_id, info) in enumerate(voyage_items):
        voyage_expected = info['expected']
        if mode == 'all':
            voyage_submitted = voyage_expected
        elif idx == len(voyage_items) - 1:
            voyage_submitted = round(submit_total - allocated, 2)
        else:
            voyage_submitted = round(voyage_expected / total_outstanding * submit_total, 2) if total_outstanding else 0
        allocated += voyage_submitted

        # expected_amount = the driver's claim for THIS hand-over (what they say
        # they're submitting now). The admin later overwrites submitted_amount
        # with the actual counted cash and flags a discrepancy only if their
        # count differs from this claim. For a partial submission the remaining
        # cash stays in hand (tracked via collections) for a later hand-over —
        # it must NOT be treated as a shortage here.
        if voyage_submitted <= 0.005:
            continue
        if info['existing_sub']:
            sub = info['existing_sub']
            sub.expected_amount = voyage_submitted
            sub.submitted_amount = voyage_submitted
            sub.submission_status = 'submitted'
            sub.submitted_to_admin_id = admin_id
            sub.submitted_at = now
            sub.driver_notes = notes or sub.driver_notes
        else:
            sub = DriverCashSubmission(
                driver_id=current_user.id,
                voyage_id=voyage_id,
                expected_amount=voyage_submitted,
                submitted_amount=voyage_submitted,
                submission_status='submitted',
                submitted_to_admin_id=admin_id,
                submitted_at=now,
                driver_notes=notes or None,
            )
            db.session.add(sub)
        created += 1

    db.session.commit()

    log_activity(
        'driver_cash_submitted',
        f'Driver {current_user.full_name} submitted ₹{submit_total:.0f} to Admin {admin.full_name} '
        f'({created} voyage(s))',
        'user', current_user.id,
    )

    notify_staff(
        title='Cash Submitted — Action Required',
        message=(f'{current_user.full_name} handed ₹{submit_total:.0f} to {admin.full_name} '
                 f'— {created} voyage(s) awaiting your verification.'),
        link=url_for('admin.driver_cash'),
    )

    socketio.emit('driver_cash_submitted', {
        'driver_id': current_user.id,
        'driver_name': current_user.full_name,
        'amount': submit_total,
        'voyages': created,
    })

    return jsonify({'status': 'ok', 'total': submit_total, 'voyages': created})