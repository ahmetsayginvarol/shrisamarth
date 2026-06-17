import base64
import json
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, render_template, request, jsonify, redirect,
                   url_for, flash, session, send_file, abort, current_app)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db, socketio, csrf, limiter
from app.abuse import get_client_ip, is_ip_banned, check_booking_abuse, log_abuse_event, auto_ban_ip
from app.captcha import generate_captcha, verify_captcha
from app.models import Voyage, Booking, RouteStop, SeatLock, User, WINDOW_SEATS, SEAT_ADJACENCY, SiteContent, PasswordResetToken, EmailVerificationToken
from app.customer.forms import CustomerLoginForm, CustomerRegisterForm, CustomerProfileForm, ForgotPasswordForm, ResetPasswordForm
from app.logging import log_activity, notify_staff
from app.user_activity import log_user_activity
from app.staff.ticket import generate_ticket, generate_group_ticket, generate_qr

customer_bp = Blueprint('customer', __name__, template_folder='../templates/customer')


def _get_cms() -> dict:
    """Return all site_content rows keyed by section_key."""
    try:
        rows = SiteContent.query.all()
        return {r.section_key: r for r in rows}
    except Exception:
        return {}


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


_DEFAULT_FAQ_EN = [
    {"q": "How do I book a bus ticket on SHRISAMARTH?", "a": "Select your origin, destination and date on the homepage. Choose your preferred bus, pick your seat on the visual seat map, fill in your details and confirm. You'll receive an e-ticket instantly."},
    {"q": "Can I cancel my booking?", "a": "Yes. Go to My Bookings, find your booking and click Cancel. Cancellations are subject to the operator's refund policy."},
    {"q": "How do I receive my ticket?", "a": "Your e-ticket is available to download immediately after booking. You can also share it via WhatsApp directly from the booking confirmation page."},
    {"q": "Do I need to create an account to book?", "a": "No. You can book as a guest. Creating an account lets you view your booking history and manage your tickets easily."},
    {"q": "What should I carry at boarding?", "a": "Show your e-ticket QR code to the driver — either on your phone screen or as a printed copy."},
    {"q": "How are seats allocated?", "a": "You choose your own seat from the live seat map. What you select is what you get."},
]
_DEFAULT_FAQ_HI = [
    {"q": "SHRISAMARTH पर बस टिकट कैसे बुक करें?", "a": "होमपेज पर अपना मूल स्थान, गंतव्य और तारीख चुनें। अपनी पसंदीदा बस चुनें, विजुअल सीट मैप से सीट चुनें, अपनी जानकारी भरें और पुष्टि करें। आपको तुरंत ई-टिकट मिलेगा।"},
    {"q": "क्या मैं अपनी बुकिंग रद्द कर सकता/सकती हूँ?", "a": "हाँ। मेरी बुकिंग पर जाएं, अपनी बुकिंग खोजें और रद्द करें पर क्लिक करें। रद्दीकरण ऑपरेटर की धनवापसी नीति के अधीन है।"},
    {"q": "मुझे मेरा टिकट कैसे मिलेगा?", "a": "बुकिंग के तुरंत बाद आपका ई-टिकट डाउनलोड के लिए उपलब्ध है। आप बुकिंग पुष्टि पृष्ठ से सीधे WhatsApp पर भी शेयर कर सकते हैं।"},
    {"q": "क्या बुकिंग के लिए खाता बनाना जरूरी है?", "a": "नहीं। आप बिना खाते के भी बुकिंग कर सकते हैं। खाता बनाने से आप अपनी बुकिंग इतिहास देख सकते हैं और टिकट आसानी से प्रबंधित कर सकते हैं।"},
    {"q": "बोर्डिंग पर क्या लाना है?", "a": "ड्राइवर को अपना ई-टिकट QR कोड दिखाएं — फोन स्क्रीन पर या प्रिंट कॉपी के रूप में।"},
    {"q": "सीटें कैसे आवंटित होती हैं?", "a": "आप लाइव सीट मैप से अपनी सीट स्वयं चुनते हैं। जो आप चुनते हैं, वही आपको मिलती है।"},
]


def _get_faq_items():
    """Return list of {q_en, a_en, q_hi, a_hi} for the FAQ accordion."""
    try:
        row = SiteContent.query.filter_by(section_key='faq_items').first()
        if row:
            en_list = json.loads(row.content_en or '[]')
            hi_list = json.loads(row.content_hi or '[]')
            if en_list:
                return [
                    {
                        'q_en': e.get('q', ''),
                        'a_en': e.get('a', ''),
                        'q_hi': (hi_list[i].get('q', '') if i < len(hi_list) else ''),
                        'a_hi': (hi_list[i].get('a', '') if i < len(hi_list) else ''),
                    }
                    for i, e in enumerate(en_list)
                ]
    except Exception:
        pass
    return [
        {'q_en': e['q'], 'a_en': e['a'], 'q_hi': h['q'], 'a_hi': h['a']}
        for e, h in zip(_DEFAULT_FAQ_EN, _DEFAULT_FAQ_HI)
    ]


@customer_bp.before_request
def check_site_suspension():
    """Block customer pages when site is suspended; let staff/admin through."""
    # Skip suspension check for auth routes (so admin can still log in)
    if request.path.startswith('/auth') or request.path.startswith('/admin') or request.path.startswith('/staff'):
        return
    try:
        row = SiteContent.query.filter_by(section_key='site_suspended').first()
        if row and row.content_en == '1':
            # Staff and admin bypass suspension
            if current_user.is_authenticated and current_user.has_role('admin'):
                return
            if current_user.is_authenticated and current_user.has_role('reservation'):
                return
            msg_row = SiteContent.query.filter_by(section_key='suspension_message').first()
            message = msg_row.content_en if msg_row else None
            return render_template('errors/suspended.html', message=message), 503
    except Exception:
        pass


@customer_bp.context_processor
def inject_cms():
    """Make CMS content and announcement banner available in all customer templates."""
    cms = _get_cms()
    banner_active = cms.get('announcement_banner_active')
    show_banner = banner_active and banner_active.content_en == '1'
    return dict(
        cms=cms,
        show_banner=show_banner,
    )


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
                           voyage_stops=voyage_stops,
                           faq_items=_get_faq_items())


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

    import time as _time
    session['booking_page_loaded'] = _time.time()

    # Build stop-fare map for JS: {stop_name: fare}
    stop_fares = {
        s.stop_name: float(s.fare_override) if s.fare_override is not None else float(voyage.base_fare)
        for s in boarding_stops
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
        stop_fares=stop_fares,
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

    # --- IP ban check ---
    _ip = get_client_ip()
    _banned, _ban_reason = is_ip_banned(_ip)
    if _banned:
        log_abuse_event(_ip, 'banned_ip_booking_attempt',
                        user_id=current_user.id if current_user.is_authenticated else None)
        return jsonify({'status': 'error', 'message': 'Access temporarily restricted.'}), 403

    # --- Honeypot ---
    if request.form.get('website', '').strip():
        log_abuse_event(_ip, 'honeypot_triggered',
                        user_id=current_user.id if current_user.is_authenticated else None)
        auto_ban_ip(_ip, hours=168, reason='Honeypot triggered — automated submission')
        return jsonify({'status': 'error', 'message': 'Access blocked.'}), 403

    # --- Velocity check ---
    import time as _time
    _page_load = session.get('booking_page_loaded')
    if _page_load and _time.time() - _page_load < 3:
        log_abuse_event(_ip, 'velocity_too_fast',
                        user_id=current_user.id if current_user.is_authenticated else None)
        session['require_captcha'] = True

    # --- Captcha verification (if required) ---
    if session.get('require_captcha'):
        _cap_token = request.form.get('captcha_token', '')
        _cap_answer = request.form.get('captcha_answer', '')
        if _cap_token and _cap_answer:
            if verify_captcha(_cap_token, _cap_answer):
                session.pop('require_captcha', None)
                session['captcha_passed_for_ip'] = _ip
            else:
                _tok, _q = generate_captcha()
                return jsonify({'status': 'captcha_required', 'token': _tok,
                                'question': _q, 'error': 'Incorrect answer. Try again.'}), 200
        elif session.get('captcha_passed_for_ip') != _ip:
            _tok, _q = generate_captcha()
            return jsonify({'status': 'captcha_required', 'token': _tok, 'question': _q}), 200

    # --- Abuse checks ---
    _phone_for_abuse = passengers[0].get('phone', '') if passengers else ''
    _allowed, _abuse_reason, _severity = check_booking_abuse(
        ip=_ip,
        user_id=current_user.id if current_user.is_authenticated else None,
        phone=_phone_for_abuse,
        voyage_id=voyage_id,
    )
    if not _allowed:
        if _severity == 'captcha_required' and session.get('captcha_passed_for_ip') != _ip:
            session['require_captcha'] = True
            _tok, _q = generate_captcha()
            return jsonify({'status': 'captcha_required', 'token': _tok, 'question': _q}), 200
        return jsonify({'status': 'error', 'message': _abuse_reason}), 403

    # --- Email verification gate ---
    if current_user.is_authenticated and current_user.role == 'customer' and not current_user.email_verified:
        return jsonify({
            'status': 'error',
            'message': 'Please verify your email before booking. Check your inbox or resend the verification email.',
            'verify_required': True,
        }), 403

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
    # Server-side fare lookup — never trust client-submitted fare
    fare = _get_stop_fare(voyage, boarding_point)
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
                booking_type='customer',
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

    # Log to user activity timeline (only for registered customers)
    if current_user.is_authenticated and current_user.role == 'customer':
        _primary = bookings_created[0] if bookings_created else None
        if _primary:
            _desc = (f"Booked {len(bookings_created)} seat{'s' if is_group else ''} on "
                     f"{voyage.origin}→{voyage.destination} "
                     f"({voyage.departure_at.strftime('%d %b %Y')})")
            log_user_activity(current_user.id, 'booking_created', _desc,
                              metadata={'voyage_id': voyage.id, 'seats': seat_ids})

    # Log booking to abuse tracker
    log_abuse_event(_ip, 'booking_created',
                    user_id=current_user.id if current_user.is_authenticated else None,
                    details=f'voyage:{voyage_id} seats:{",".join(b.seat_id for b in bookings_created)}')

    # Send e-ticket emails (fire-and-forget, never blocks response)
    if passenger_email:
        from app.email import send_eticket
        for b in bookings_created:
            send_eticket(b, voyage)

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
    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    qr_buf = generate_qr(f"{domain}/verify/{code}")
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
    if current_user.is_authenticated and current_user.role == 'customer':
        if booking.created_by_id != current_user.id:
            abort(403)
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
    if current_user.is_authenticated and current_user.role == 'customer':
        if bookings[0].created_by_id != current_user.id:
            abort(403)
    _ = bookings[0].voyage.bus
    pdf = generate_group_ticket(bookings)
    filename = f"ticket-{group_code}.pdf"
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=filename)


# ============================================================
# STEP 5 — CUSTOMER AUTH
# ============================================================

@customer_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per hour", methods=["POST"])
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
            log_user_activity(user.id, 'login', 'Logged in', performed_by_id=user.id)
            return redirect(request.args.get('next') or url_for('customer.my_bookings'))
        flash('Invalid email or password.', 'error')

    return render_template('customer/login.html', form=form)


@customer_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per hour", methods=["POST"])
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
            email_verified=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
            return render_template('customer/register.html', form=form)

        log_activity('user_created', f'New customer account: {email}', 'user', user.id)
        log_user_activity(user.id, 'register', 'Created account', performed_by_id=user.id)
        _send_verification_email(user)
        login_user(user)
        return redirect(url_for('customer.verify_pending'))

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
        password_changed = bool(form.new_password.data)
        if password_changed:
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'error')
                return render_template('customer/profile.html', form=form)
            current_user.set_password(form.new_password.data)

        current_user.full_name = form.full_name.data.strip()
        current_user.email = form.email.data.lower().strip()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Update failed. Please try again.', 'error')
            return render_template('customer/profile.html', form=form)
        if password_changed:
            log_user_activity(current_user.id, 'password_changed', 'Changed password')
        else:
            log_user_activity(current_user.id, 'profile_updated', 'Updated profile')
        flash('Profile updated.', 'success')
        return redirect(url_for('customer.profile'))

    from collections import Counter
    from app.models import UserActivityLog
    from app.user_activity import EVENT_ICONS
    bookings = Booking.query.filter_by(created_by_id=current_user.id, status='confirmed').all()
    total_trips = len(bookings)
    routes = Counter(f"{b.voyage.origin}→{b.voyage.destination}" for b in bookings)
    fav_route = routes.most_common(1)[0][0] if routes else '—'

    activity_log = (UserActivityLog.query
                    .filter_by(user_id=current_user.id)
                    .order_by(UserActivityLog.created_at.desc())
                    .limit(21).all())
    has_more = len(activity_log) > 20
    activity_log = activity_log[:20]

    return render_template('customer/profile.html', form=form, stats={
        'total_trips': total_trips,
        'fav_route': fav_route,
        'member_since': current_user.created_at.strftime('%B %Y') if current_user.created_at else '—',
    }, activity_log=activity_log, has_more=has_more, event_icons=EVENT_ICONS,
       credit_balance=current_user.credit_balance)


@customer_bp.route('/profile/qr.png')
@login_required
def profile_qr():
    if current_user.role != 'customer':
        abort(403)
    if not current_user.profile_qr_token:
        current_user.profile_qr_token = secrets.token_hex(16)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            abort(500)
    domain = current_app.config.get('APP_DOMAIN', '')
    buf = generate_qr(f"{domain}/staff/walkin-profile/{current_user.profile_qr_token}")
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@customer_bp.route('/profile/delete', methods=['POST'])
@login_required
def delete_account():
    if current_user.role != 'customer':
        abort(403)
    current_user.is_active_account = False
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Could not delete account. Please try again.', 'error')
        return redirect(url_for('customer.profile'))
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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'db_error'}), 500

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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        socketio.emit('seat_unlocked', {'voyage_id': voyage_id, 'seat_id': seat_id})

    return jsonify({'status': 'unlocked'})


# ============================================================
# EMAIL VERIFICATION
# ============================================================

def _send_verification_email(user):
    """Generate a fresh token and email it to the user. Expires old tokens first."""
    EmailVerificationToken.query.filter_by(user_id=user.id).update({'used_at': datetime.utcnow()})
    db.session.flush()

    token_str = secrets.token_urlsafe(32)
    token = EmailVerificationToken(
        user_id=user.id,
        token=token_str,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(token)
    db.session.commit()

    from app.email import send_email
    from flask import render_template as _rt
    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    verify_url = f"{domain}/verify-email/{token_str}"
    html = _rt('email/verify_email.html', user=user, verify_url=verify_url, domain=domain)
    send_email(user.email, 'Verify your email — SHRISAMARTH Travels', html)


@customer_bp.route('/verify-pending')
@login_required
def verify_pending():
    if current_user.role != 'customer':
        return redirect(url_for('staff.dashboard'))
    if current_user.email_verified:
        return redirect(url_for('customer.my_bookings'))
    return render_template('customer/verify_pending.html')


@customer_bp.route('/verify-email/<token>')
@limiter.limit("10 per hour")
def verify_email(token):
    record = EmailVerificationToken.query.filter_by(token=token).first()

    if not record:
        return render_template('customer/verify_email_result.html',
                               state='invalid')

    if record.used_at is not None:
        return render_template('customer/verify_email_result.html',
                               state='used')

    if datetime.utcnow() >= record.expires_at:
        return render_template('customer/verify_email_result.html',
                               state='expired', user=record.user)

    record.user.email_verified = True
    record.user.email_verified_at = datetime.utcnow()
    record.used_at = datetime.utcnow()
    db.session.commit()
    log_activity('email_verified',
                 f'Customer {record.user.email} verified their email address',
                 'user', record.user.id)
    login_user(record.user)
    flash('Email verified! Welcome to SHRISAMARTH.', 'success')
    return redirect(url_for('customer.my_bookings'))


@customer_bp.route('/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    if current_user.role != 'customer':
        abort(403)
    if current_user.email_verified:
        return jsonify({'status': 'ok', 'message': 'Already verified.'})

    # Rate limit: max 3 tokens in the last hour
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent = EmailVerificationToken.query.filter(
        EmailVerificationToken.user_id == current_user.id,
        EmailVerificationToken.created_at >= one_hour_ago,
    ).count()
    if recent >= 3:
        return jsonify({'status': 'error',
                        'message': 'Too many requests. Please wait before trying again.'}), 429

    _send_verification_email(current_user)
    return jsonify({'status': 'ok'})


# ============================================================
# PASSWORD RESET
# ============================================================

@customer_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('customer.dashboard'))

    form = ForgotPasswordForm()
    sent = False

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email, role='customer').first()
        if user:
            # Expire old unused tokens
            PasswordResetToken.query.filter_by(user_id=user.id, used=False).delete()
            db.session.flush()

            token_str = secrets.token_urlsafe(48)
            token = PasswordResetToken(
                user_id=user.id,
                token=token_str,
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.session.add(token)
            db.session.commit()

            domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
            reset_url = f"{domain}/reset-password/{token_str}"

            from app.email import send_email
            from flask import render_template as _rt
            html = _rt('email/reset_password.html',
                       user=user, reset_url=reset_url, domain=domain)
            send_email(user.email, 'Reset your SHRISAMARTH password', html)

        # Always show sent message to prevent email enumeration
        sent = True

    return render_template('customer/forgot_password.html', form=form, sent=sent)


@customer_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('customer.dashboard'))

    record = PasswordResetToken.query.filter_by(token=token).first()
    if not record or not record.is_valid:
        return render_template('customer/reset_password.html',
                               form=None, invalid=True)

    form = ResetPasswordForm()
    done = False

    if form.validate_on_submit():
        record.user.set_password(form.password.data)
        record.used = True
        db.session.commit()
        log_activity('password_reset', f'Password reset via email for {record.user.email}',
                     'user', record.user.id)
        done = True

    return render_template('customer/reset_password.html',
                           form=form, invalid=False, done=done)


@customer_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    user = User.query.filter_by(unsubscribe_token=token).first()
    if not user:
        return render_template('customer/unsubscribe.html', found=False)
    if not user.newsletter_unsubscribed:
        user.newsletter_unsubscribed = True
        db.session.commit()
        log_activity('newsletter_unsubscribe',
                     f'Customer {user.email} unsubscribed from newsletters',
                     'user', user.id)
    return render_template('customer/unsubscribe.html', found=True, user=user)
