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
from app.logging import log_activity, notify_staff
from app.models import Notification

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
    if voyage:
        sorted_stops = sorted(voyage.stops, key=lambda s: s.stop_order)
        boarding_stops = [s for s in sorted_stops if s.stop_type == 'boarding']
        dropping_stops = [s for s in sorted_stops if s.stop_type == 'dropping']

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

    # Validate each passenger record
    for p in passengers:
        if not p.get('name') or not p.get('phone') or p.get('gender') not in ('M', 'F') or not str(p.get('seat_id', '')).strip():
            return jsonify({'status': 'error', 'message': f'Missing details for seat {p.get("seat_id", "?")}'}), 400

    voyage = Voyage.query.get_or_404(voyage_id)

    # Verify all seats still available
    for sid in seat_ids:
        existing = Booking.query.filter_by(voyage_id=voyage.id, seat_id=sid, status='confirmed').first()
        if existing:
            return jsonify({'status': 'error', 'message': f'Seat {sid} was just booked. Please refresh.'}), 409

    # Adjacent gender conflict check (staff: warn, not hard block)
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
                    continue  # adjacent group members — no conflict
                adj = Booking.query.filter_by(voyage_id=voyage.id, seat_id=adj_id, status='confirmed').first()
                if adj and adj.gender != pg:
                    conflict_msgs.append(f"Seat {sid} ({p.get('name','')}) next to seat {adj_id} ({adj.passenger_name})")
        if conflict_msgs:
            return jsonify({
                'status': 'gender_conflict',
                'message': 'Adjacent seats have passengers of the opposite gender:\n' + '\n'.join(conflict_msgs),
            }), 200

    is_group = len(seat_ids) > 1
    group_code = f"GRP-{voyage.departure_at.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}" if is_group else None

    bookings_created = []
    try:
        for p in passengers:
            sid = str(p['seat_id']).strip()
            per_seat_advance = round(advance_paid / len(passengers), 2)
            per_seat_balance = fare_per_seat - per_seat_advance
            code = f"SHRI-{voyage.departure_at.strftime('%Y%m%d')}-{sid}-{secrets.token_hex(3).upper()}"
            b = Booking(
                voyage_id=voyage.id,
                seat_id=sid,
                passenger_name=p['name'].strip(),
                passenger_phone=p['phone'].strip(),
                gender=p['gender'],
                boarding_point=(p.get('boarding_point') or boarding_point or '').strip(),
                dropping_point=(p.get('dropping_point') or dropping_point or '').strip(),
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
    db.session.commit()

    log_activity('booking_cancelled',
                 f'Cancelled seat {booking.seat_id} ({booking.passenger_name}) on voyage {booking.voyage_id}',
                 'booking', booking_id)
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
    db.session.commit()
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
    db.session.commit()
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