import base64
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, render_template, request, jsonify, redirect,
                   url_for, flash, session, send_file, abort)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db, socketio, csrf
from app.models import Voyage, Booking, RouteStop, SeatLock, User, WINDOW_SEATS, SEAT_ADJACENCY
from app.customer.forms import CustomerLoginForm, CustomerRegisterForm, CustomerProfileForm
from app.logging import log_activity, notify_staff
from app.staff.ticket import generate_ticket, generate_group_ticket, generate_qr

customer_bp = Blueprint('customer', __name__, template_folder='../templates/customer')


def _get_cities():
    scheduled = Voyage.query.filter_by(status='scheduled')
    origins = sorted(set(
        r[0] for r in scheduled.with_entities(Voyage.origin).distinct().all()
    ))
    destinations = sorted(set(
        r[0] for r in scheduled.with_entities(Voyage.destination).distinct().all()
    ))
    return origins, destinations


def _get_or_create_sid():
    if 'cust_sid' not in session:
        session['cust_sid'] = secrets.token_hex(16)
    return session['cust_sid']


# ============================================================
# HOME
# ============================================================

@customer_bp.route('/')
def home():
    origins, destinations = _get_cities()
    popular_voyages = (Voyage.query
        .filter_by(status='scheduled')
        .filter(Voyage.departure_at > datetime.utcnow())
        .order_by(Voyage.departure_at)
        .limit(6).all())
    voyage_stops = {}
    for v in popular_voyages:
        srt = sorted(v.stops, key=lambda s: s.stop_order)
        voyage_stops[v.id] = {
            'boarding': [s for s in srt if s.stop_type == 'boarding'],
            'dropping': [s for s in srt if s.stop_type == 'dropping'],
        }
    return render_template('customer/home.html',
                           origins=origins,
                           destinations=destinations,
                           today=date.today().strftime('%Y-%m-%d'),
                           popular_voyages=popular_voyages,
                           voyage_stops=voyage_stops)


# ============================================================
# SEARCH
# ============================================================

@customer_bp.route('/search')
def search():
    from sqlalchemy import func
    origin = request.args.get('origin', '').strip()
    destination = request.args.get('destination', '').strip()
    travel_date_str = request.args.get('date', '').strip()
    sort_by = request.args.get('sort', 'time')

    voyages = []
    search_date = None

    if origin and destination and travel_date_str:
        try:
            search_date = datetime.strptime(travel_date_str, '%Y-%m-%d').date()
        except ValueError:
            search_date = date.today()

        voyages = (Voyage.query
                   .filter_by(status='scheduled')
                   .filter(Voyage.origin == origin)
                   .filter(Voyage.destination == destination)
                   .filter(func.date(Voyage.departure_at) == search_date)
                   .all())

        if sort_by == 'price':
            voyages.sort(key=lambda v: float(v.base_fare))
        elif sort_by == 'seats':
            voyages.sort(key=lambda v: v.bus.total_seats - v.seats_booked, reverse=True)
        else:
            voyages.sort(key=lambda v: v.departure_at)

    voyage_stops = {}
    for v in voyages:
        srt = sorted(v.stops, key=lambda s: s.stop_order)
        voyage_stops[v.id] = {
            'boarding': [s for s in srt if s.stop_type == 'boarding'],
            'dropping': [s for s in srt if s.stop_type == 'dropping'],
        }

    origins, destinations = _get_cities()

    return render_template(
        'customer/search_results.html',
        voyages=voyages,
        voyage_stops=voyage_stops,
        origin=origin,
        destination=destination,
        travel_date=travel_date_str,
        search_date=search_date,
        sort_by=sort_by,
        origins=origins,
        destinations=destinations,
        today_str=date.today().strftime('%Y-%m-%d'),
    )


# ============================================================
# STEP 3 — SEAT SELECTION / BOOKING PAGE
# ============================================================

@customer_bp.route('/book/<int:voyage_id>')
def book(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)

    # Confirmed bookings
    bookings = Booking.query.filter_by(voyage_id=voyage.id, status='confirmed').all()
    seat_map = {b.seat_id: b for b in bookings}

    # Route stops
    sorted_stops = sorted(voyage.stops, key=lambda s: s.stop_order)
    boarding_stops = [s for s in sorted_stops if s.stop_type == 'boarding']
    dropping_stops = [s for s in sorted_stops if s.stop_type == 'dropping']

    # Seat locks — cleanup expired first
    SeatLock.query.filter(SeatLock.expires_at < datetime.utcnow()).delete()
    db.session.commit()

    cust_sid = _get_or_create_sid()

    active_locks = SeatLock.query.filter_by(voyage_id=voyage.id)\
        .filter(SeatLock.expires_at > datetime.utcnow()).all()

    locked_mine = [l.seat_id for l in active_locks if l.session_id == cust_sid]
    locked_other = [l.seat_id for l in active_locks if l.session_id != cust_sid]

    prefill = {}
    if current_user.is_authenticated and current_user.role == 'customer':
        prefill = {
            'name': current_user.full_name,
            'phone': current_user.phone or '',
            'email': current_user.email or '',
            'gender': current_user.gender or '',
        }

    return render_template(
        'customer/book.html',
        voyage=voyage,
        seat_map=seat_map,
        window_seats=WINDOW_SEATS,
        boarding_stops=boarding_stops,
        dropping_stops=dropping_stops,
        locked_other=locked_other,
        locked_mine=locked_mine,
        prefill=prefill,
    )


# ============================================================
# STEP 3 — CUSTOMER BOOKING API
# ============================================================

@customer_bp.route('/api/customer/book', methods=['POST'])
def customer_book():
    # --- Parse request ---
    if request.is_json:
        data = request.get_json()
        voyage_id = data.get('voyage_id')
        passengers = data.get('passengers', [])  # [{seat_id, name, phone, gender}, ...]
        boarding_point = (data.get('boarding_point') or '').strip()
        dropping_point = (data.get('dropping_point') or '').strip()
        passenger_email = (data.get('email') or '').strip() or None
        seat_ids = [str(p['seat_id']).strip() for p in passengers]
    else:
        voyage_id = request.form.get('voyage_id', type=int)
        seat_ids_raw = request.form.getlist('seat_ids[]')
        seat_ids = [s.strip() for s in seat_ids_raw if s.strip()]
        passenger_name = (request.form.get('passenger_name') or '').strip()
        passenger_phone = (request.form.get('passenger_phone') or '').strip()
        passenger_email = (request.form.get('passenger_email') or '').strip() or None
        gender = request.form.get('gender', '')
        boarding_point = request.form.get('boarding_point', '')
        dropping_point = request.form.get('dropping_point', '')
        passengers = [{'seat_id': s, 'name': passenger_name, 'phone': passenger_phone, 'gender': gender} for s in seat_ids]

    # --- Validate ---
    if not voyage_id or not passengers:
        return jsonify({'status': 'error', 'message': 'Missing required fields.'}), 400

    is_group = len(seat_ids) > 1
    for p in passengers:
        if not p.get('name') or not p.get('phone'):
            return jsonify({'status': 'error', 'message': f'Missing details for seat {p.get("seat_id", "?")}'}), 400
        if not is_group and p.get('gender') not in ('M', 'F'):
            return jsonify({'status': 'error', 'message': 'Gender is required'}), 400

    voyage = Voyage.query.get_or_404(voyage_id)
    fare = float(voyage.base_fare)
    dep_date = voyage.departure_at.strftime('%Y%m%d')

    # Adjacent gender check only for single-seat bookings with gender
    if not is_group:
        seat_ids_set = set(seat_ids)
        for p in passengers:
            sid = str(p['seat_id']).strip()
            pg = p.get('gender')
            for adj_id in SEAT_ADJACENCY.get(sid, []):
                if adj_id in seat_ids_set:
                    continue
                adj = Booking.query.filter_by(voyage_id=voyage.id, seat_id=adj_id, status='confirmed').first()
                if adj and adj.gender and adj.gender != pg:
                    return jsonify({
                        'status': 'error',
                        'message': f'Seat {sid} is adjacent to seat {adj_id}, which is reserved by a passenger of the opposite gender. Please choose a different seat.'
                    }), 200

    group_code = f"GRP-{dep_date}-{secrets.token_hex(4).upper()}" if is_group else None

    bookings_created = []
    try:
        for p in passengers:
            sid = str(p['seat_id']).strip()
            code = f"SHRI-{dep_date}-{sid}-{secrets.token_hex(3).upper()}"
            b = Booking(
                voyage_id=voyage.id,
                seat_id=sid,
                passenger_name=p['name'].strip(),
                passenger_phone=p['phone'].strip(),
                passenger_email=passenger_email,
                gender=p['gender'],
                boarding_point=boarding_point,
                dropping_point=dropping_point,
                fare=fare,
                advance_paid=0,
                balance_due=fare,
                booking_code=code,
                group_booking_code=group_code,
                created_by_id=current_user.id if current_user.is_authenticated else None,
                status='confirmed',
            )
            db.session.add(b)
            bookings_created.append(b)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'One or more seats were just booked.'}), 409

    cust_sid = session.get('cust_sid')
    for b in bookings_created:
        if cust_sid:
            SeatLock.query.filter_by(voyage_id=voyage.id, seat_id=b.seat_id, session_id=cust_sid).delete()
        socketio.emit('seat_booked', {
            'voyage_id': voyage.id,
            'seat_id': b.seat_id,
            'gender': b.gender,
            'name': b.passenger_name,
        })
        if not is_group:
            log_activity('booking_created',
                         f'Customer booking {b.booking_code}: seat {b.seat_id} for {b.passenger_name} on {voyage.origin}→{voyage.destination}',
                         'booking', b.id)
    if is_group and bookings_created:
        seat_detail = ' | '.join(f"{b.seat_id}: {b.passenger_name}" for b in bookings_created)
        log_activity(
            'group_booking_created',
            f'Customer group booking {group_code}: {len(bookings_created)} seats · {voyage.origin}→{voyage.destination} | {seat_detail}',
            'booking', bookings_created[0].id,
        )
    db.session.commit()

    primary = bookings_created[0]
    notify_staff(
        title='New Customer Booking',
        message=f"{primary.passenger_name}{'+ others' if is_group else ''} — {len(seat_ids)} seat{'s' if is_group else ''} ({', '.join(seat_ids)}) — {voyage.origin}→{voyage.destination} {voyage.departure_at.strftime('%d %b %Y')}",
        link=url_for('staff.dashboard', voyage_id=voyage.id, date=voyage.departure_at.strftime('%Y-%m-%d')),
        booking_id=primary.id,
        passenger_phone=primary.passenger_phone,
    )

    return jsonify({'status': 'success', 'code': group_code if is_group else bookings_created[0].booking_code, 'is_group': is_group})


# ============================================================
# STEP 4 — CONFIRMATION PAGE
# ============================================================

@customer_bp.route('/booking/confirmation/<code>')
def confirmation(code):
    # Try booking_code first, then group_booking_code
    booking = Booking.query.filter_by(booking_code=code, status='confirmed').first()
    is_group = False

    if booking:
        bookings = [booking]
    else:
        bookings = Booking.query.filter_by(
            group_booking_code=code, status='confirmed'
        ).order_by(Booking.seat_id).all()
        if bookings:
            is_group = True
            booking = bookings[0]
        else:
            abort(404)

    # Generate QR
    qr_buf = generate_qr(f"https://shrisamarth.onrender.com/verify/{code}")
    qr_b64 = base64.b64encode(qr_buf.read()).decode()

    return render_template(
        'customer/confirmation.html',
        bookings=bookings,
        booking=booking,
        is_group=is_group,
        code=code,
        qr_b64=qr_b64,
    )


# ============================================================
# TICKET DOWNLOADS (customer-facing)
# ============================================================

@customer_bp.route('/booking/<int:booking_id>/ticket')
def download_ticket(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    _ = booking.voyage.bus
    pdf = generate_ticket(booking)
    filename = f"ticket-{booking.booking_code}.pdf"
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=filename)


@customer_bp.route('/booking/group/<group_code>/ticket')
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


# ============================================================
# STEP 5 — CUSTOMER AUTH
# ============================================================

@customer_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'customer':
            return redirect(url_for('customer.my_bookings'))
        return redirect(url_for('staff.dashboard'))

    form = CustomerLoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip(), role='customer').first()
        if user and user.check_password(form.password.data):
            login_user(user)
            log_activity('user_login', f'Customer login: {user.email}', 'user', user.id)
            return redirect(request.args.get('next') or url_for('customer.my_bookings'))
        flash('Invalid email or password.', 'error')

    return render_template('customer/login.html', form=form)


@customer_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated and current_user.role == 'customer':
        return redirect(url_for('customer.my_bookings'))

    form = CustomerRegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'error')
            return render_template('customer/register.html', form=form)

        user = User(
            username=email,
            email=email,
            full_name=form.full_name.data.strip(),
            phone=form.phone.data.strip(),
            gender=form.gender.data or None,
            role='customer',
            is_active_account=True,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        log_activity('user_created', f'New customer account: {email}', 'user', user.id)
        login_user(user)
        flash('Welcome to SHRISAMARTH! Your account has been created.', 'success')
        return redirect(url_for('customer.my_bookings'))

    return render_template('customer/register.html', form=form)


@customer_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('customer.home'))


@customer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if current_user.role != 'customer':
        return redirect(url_for('staff.dashboard'))

    form = CustomerProfileForm(obj=current_user)

    if form.validate_on_submit():
        if form.new_password.data:
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return render_template('customer/profile.html', form=form)
            current_user.set_password(form.new_password.data)

        current_user.full_name = form.full_name.data.strip()
        current_user.email = form.email.data.lower().strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('customer.profile'))

    from collections import Counter
    bookings = Booking.query.filter_by(created_by_id=current_user.id, status='confirmed').all()
    total_trips = len(bookings)
    routes = Counter(f"{b.voyage.origin}→{b.voyage.destination}" for b in bookings)
    fav_route = routes.most_common(1)[0][0] if routes else '—'

    return render_template('customer/profile.html', form=form, stats={
        'total_trips': total_trips,
        'fav_route': fav_route,
        'member_since': current_user.created_at.strftime('%B %Y') if current_user.created_at else '—',
    })


@customer_bp.route('/profile/delete', methods=['POST'])
@login_required
def delete_account():
    if current_user.role != 'customer':
        abort(403)
    current_user.is_active_account = False
    db.session.commit()
    logout_user()
    flash('Your account has been deactivated.', 'info')
    return redirect(url_for('customer.home'))


@customer_bp.route('/my-bookings')
@login_required
def my_bookings():
    if current_user.role != 'customer':
        return redirect(url_for('staff.dashboard'))

    bookings = Booking.query.filter_by(
        created_by_id=current_user.id
    ).order_by(Booking.created_at.desc()).all()

    # Stats
    confirmed = [b for b in bookings if b.status == 'confirmed']
    upcoming = [b for b in confirmed if b.voyage.departure_at > datetime.utcnow()]
    total_spent = sum(float(b.fare) for b in confirmed)
    balance_due = sum(float(b.balance_due) for b in confirmed)
    soon = [b for b in upcoming if b.voyage.departure_at <= datetime.utcnow() + timedelta(hours=24)]

    # Group by group_booking_code
    seen_groups = set()
    grouped = []
    for b in bookings:
        if b.group_booking_code:
            if b.group_booking_code not in seen_groups:
                seen_groups.add(b.group_booking_code)
                group_bookings = [x for x in bookings if x.group_booking_code == b.group_booking_code]
                grouped.append({'type': 'group', 'code': b.group_booking_code, 'bookings': group_bookings})
        else:
            grouped.append({'type': 'single', 'code': b.booking_code, 'bookings': [b]})

    return render_template('customer/my_bookings.html',
        grouped=grouped,
        stats={'total': len(confirmed), 'upcoming': len(upcoming), 'spent': total_spent, 'balance': balance_due},
        soon_bookings=soon,
    )


# ============================================================
# STEP 6 — SEAT LOCK API
# ============================================================

@customer_bp.route('/api/seat-status/<int:voyage_id>')
def seat_status(voyage_id):
    # Cleanup expired locks
    SeatLock.query.filter(SeatLock.expires_at < datetime.utcnow()).delete()
    db.session.commit()

    cust_sid = _get_or_create_sid()

    booked = {}
    bookings = Booking.query.filter_by(voyage_id=voyage_id, status='confirmed').all()
    for b in bookings:
        booked[b.seat_id] = b.gender

    active_locks = SeatLock.query.filter_by(voyage_id=voyage_id)\
        .filter(SeatLock.expires_at > datetime.utcnow()).all()

    locked_mine = [l.seat_id for l in active_locks if l.session_id == cust_sid]
    locked_other = [l.seat_id for l in active_locks if l.session_id != cust_sid]

    return jsonify({'booked': booked, 'locked_mine': locked_mine, 'locked_other': locked_other})


@csrf.exempt
@customer_bp.route('/api/lock-seat', methods=['POST'])
def lock_seat():
    data = request.get_json(force=True) or {}
    voyage_id = data.get('voyage_id')
    seat_id = data.get('seat_id')

    if not voyage_id or not seat_id:
        return jsonify({'error': 'missing_fields'}), 400

    cust_sid = _get_or_create_sid()

    # Cleanup expired
    SeatLock.query.filter(SeatLock.expires_at < datetime.utcnow()).delete()
    db.session.commit()

    # Check already booked
    existing_booking = Booking.query.filter_by(
        voyage_id=voyage_id, seat_id=seat_id, status='confirmed'
    ).first()
    if existing_booking:
        return jsonify({'error': 'already_booked'}), 409

    # Check locked by other session
    other_lock = SeatLock.query.filter_by(voyage_id=voyage_id, seat_id=seat_id)\
        .filter(SeatLock.session_id != cust_sid)\
        .filter(SeatLock.expires_at > datetime.utcnow()).first()
    if other_lock:
        return jsonify({'error': 'locked_by_other'}), 409

    # Upsert: delete existing lock for this session+seat, create new
    SeatLock.query.filter_by(voyage_id=voyage_id, seat_id=seat_id, session_id=cust_sid).delete()

    expires = datetime.utcnow() + timedelta(minutes=5)
    lock = SeatLock(
        voyage_id=voyage_id,
        seat_id=seat_id,
        session_id=cust_sid,
        expires_at=expires,
    )
    db.session.add(lock)
    db.session.commit()

    socketio.emit('seat_locked', {
        'voyage_id': voyage_id,
        'seat_id': seat_id,
        'session_id': cust_sid,
    })

    return jsonify({'status': 'locked', 'expires_at': expires.isoformat()})


@csrf.exempt
@customer_bp.route('/api/unlock-seat', methods=['POST'])
def unlock_seat():
    data = request.get_json(force=True) or {}
    voyage_id = data.get('voyage_id')
    seat_id = data.get('seat_id')

    cust_sid = session.get('cust_sid')
    if cust_sid and voyage_id and seat_id:
        SeatLock.query.filter_by(
            voyage_id=voyage_id, seat_id=seat_id, session_id=cust_sid
        ).delete()
        db.session.commit()
        socketio.emit('seat_unlocked', {'voyage_id': voyage_id, 'seat_id': seat_id})

    return jsonify({'status': 'unlocked'})
