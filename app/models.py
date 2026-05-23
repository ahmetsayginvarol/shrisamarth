from datetime import datetime
from flask_login import UserMixin
from app.extensions import db, login_manager, bcrypt


# ============================================================
# USER & AUTH
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='reservation')
    # role values: 'admin', 'reservation', 'driver', 'customer'
    phone = db.Column(db.String(20), nullable=True)
    gender = db.Column(db.String(1), nullable=True)  # 'M' or 'F', optional
    credit_balance = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    is_active_account = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    email_verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============================================================
# FLEET
# ============================================================

class Bus(db.Model):
    __tablename__ = 'buses'

    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=True)  # e.g. "Pune Express 1"
    layout_name = db.Column(db.String(50), default='shrisamarth_49')
    total_seats = db.Column(db.Integer, default=49)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    voyages = db.relationship('Voyage', backref='bus', lazy=True)

    def __repr__(self):
        return f'<Bus {self.registration}>'

class Voyage(db.Model):
    __tablename__ = 'voyages'

    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    origin = db.Column(db.String(80), nullable=False)
    destination = db.Column(db.String(80), nullable=False)
    departure_at = db.Column(db.DateTime, nullable=False, index=True)
    arrival_at = db.Column(db.DateTime, nullable=True)
    base_fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='scheduled')
    # status values: scheduled, departed, completed, cancelled
    notes = db.Column(db.Text, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    recurrence_group = db.Column(db.String(30), nullable=True, index=True)

    driver = db.relationship('User', foreign_keys=[driver_id])
    cancelled_by = db.relationship('User', foreign_keys=[cancelled_by_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    bookings = db.relationship('Booking', backref='voyage', lazy=True,
                               cascade='all, delete-orphan')
    stops = db.relationship('RouteStop', backref='voyage', lazy=True,
                            cascade='all, delete-orphan')

    @property
    def seats_booked(self):
        return Booking.query.filter_by(
            voyage_id=self.id, status='confirmed'
        ).count()

    @property
    def is_cancellable(self):
        return self.status == 'scheduled'

    @property
    def occupancy_pct(self):
        if not self.bus or self.bus.total_seats == 0:
            return 0
        return round((self.seats_booked / self.bus.total_seats) * 100)

    def __repr__(self):
        return f'<Voyage {self.origin}→{self.destination} {self.departure_at}>'

# ============================================================
# ROUTE STOPS
# ============================================================

class RouteStop(db.Model):
    __tablename__ = 'route_stops'

    id = db.Column(db.Integer, primary_key=True)
    voyage_id = db.Column(db.Integer, db.ForeignKey('voyages.id'), nullable=False)
    stop_name = db.Column(db.String(80), nullable=False)
    stop_type = db.Column(db.String(10), nullable=False)  # 'boarding' or 'dropping'
    stop_time = db.Column(db.String(5), nullable=True)    # HH:MM format
    stop_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<RouteStop {self.stop_name} ({self.stop_type}) @{self.stop_time}>'


# ============================================================
# BOOKINGS
# ============================================================

class Booking(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    voyage_id = db.Column(db.Integer, db.ForeignKey('voyages.id'), nullable=False)
    seat_id = db.Column(db.String(8), nullable=False)  # '8', 'A', '37' — strings to handle letters

    passenger_name = db.Column(db.String(120), nullable=False)
    passenger_phone = db.Column(db.String(20), nullable=False)
    passenger_email = db.Column(db.String(120), nullable=True)
    gender = db.Column(db.String(1), nullable=True)  # 'M' or 'F'; None for gender-neutral group bookings

    boarding_point = db.Column(db.String(80))
    dropping_point = db.Column(db.String(80))

    fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    advance_paid = db.Column(db.Numeric(10, 2), default=0)
    balance_due = db.Column(db.Numeric(10, 2), default=0)

    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled
    booking_code = db.Column(db.String(30), unique=True, index=True)
    group_booking_code = db.Column(db.String(30), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    boarded_at = db.Column(db.DateTime, nullable=True)
    boarded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    boarded_by = db.relationship('User', foreign_keys=[boarded_by_id])

    created_by = db.relationship('User', foreign_keys=[created_by_id])

    __table_args__ = (
        # CRITICAL: prevents double-booking the same seat on the same voyage
        db.UniqueConstraint('voyage_id', 'seat_id', name='uq_voyage_seat'),
    )

    @property
    def is_window(self):
        from app.models import WINDOW_SEATS
        return self.seat_id in WINDOW_SEATS

    def __repr__(self):
        return f'<Booking {self.booking_code} seat {self.seat_id}>'
# ============================================================
# ACTIVITY LOG
# ============================================================

class ActivityLog(db.Model):
    __tablename__ = 'activity_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    # action values: booking_created, booking_cancelled, voyage_created,
    # voyage_edited, voyage_cancelled, bus_created, bus_edited,
    # user_created, user_edited, user_login, user_logout
    description = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(30), nullable=True)  # booking, voyage, bus, user
    target_id = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<Log {self.action} by user {self.user_id}>'


# ============================================================
# SEAT LOCK (temporary reservation during checkout)
# ============================================================

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(500), nullable=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    passenger_phone = db.Column(db.String(20), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])
    booking = db.relationship('Booking', foreign_keys=[booking_id])


class SeatLock(db.Model):
    __tablename__ = 'seat_locks'
    id = db.Column(db.Integer, primary_key=True)
    voyage_id = db.Column(db.Integer, db.ForeignKey('voyages.id'), nullable=False)
    seat_id = db.Column(db.String(8), nullable=False)
    session_id = db.Column(db.String(64), nullable=False)
    locked_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<SeatLock voyage={self.voyage_id} seat={self.seat_id}>'


# ============================================================
# EMAIL VERIFICATION TOKENS
# ============================================================

class EmailVerificationToken(db.Model):
    __tablename__ = 'email_verification_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f'<EmailVerificationToken user={self.user_id}>'


# ============================================================
# PASSWORD RESET TOKENS
# ============================================================

class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    @property
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f'<PasswordResetToken user={self.user_id}>'


# ============================================================
# CMS SITE CONTENT
# ============================================================

class SiteContent(db.Model):
    __tablename__ = 'site_content'

    id = db.Column(db.Integer, primary_key=True)
    section_key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    content_en = db.Column(db.Text, nullable=True)
    content_hi = db.Column(db.Text, nullable=True)
    content_type = db.Column(db.String(20), nullable=False, default='text')
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    updated_by = db.relationship('User', foreign_keys=[updated_by_id])

    def __repr__(self):
        return f'<SiteContent {self.section_key}>'


# ============================================================
# NEWSLETTER
# ============================================================

class Newsletter(db.Model):
    __tablename__ = 'newsletters'

    id = db.Column(db.Integer, primary_key=True)
    subject_en = db.Column(db.String(200), nullable=True)
    subject_hi = db.Column(db.String(200), nullable=True)
    content_en = db.Column(db.Text, nullable=True)
    content_hi = db.Column(db.Text, nullable=True)
    theme = db.Column(db.String(30), default='classic', nullable=False)
    status = db.Column(db.String(20), default='draft', nullable=False)
    recipient_count = db.Column(db.Integer, default=0)
    sent_at = db.Column(db.DateTime, nullable=True)
    sent_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sent_by = db.relationship('User', foreign_keys=[sent_by_id])

    def __repr__(self):
        return f'<Newsletter {self.id} status={self.status}>'


# ============================================================
# ABUSE DETECTION
# ============================================================

class AbuseLog(db.Model):
    __tablename__ = 'abuse_logs'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<AbuseLog {self.event_type} from {self.ip_address}>'


class IpBan(db.Model):
    __tablename__ = 'ip_bans'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False, index=True)
    reason = db.Column(db.String(200), nullable=True)
    banned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    banned_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_permanent = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    banned_by = db.relationship('User', foreign_keys=[banned_by_id])

    @property
    def is_active(self):
        if self.is_permanent:
            return True
        if self.expires_at and datetime.utcnow() < self.expires_at:
            return True
        return False

    def __repr__(self):
        return f'<IpBan {self.ip_address}>'


# ============================================================
    # SEAT LAYOUT HELPERS
    # ============================================================

SEAT_ADJACENCY = {
        'A': ['B'], 'B': ['A'], 'C': ['D'], 'D': ['C'],
        'E': ['F'], 'F': ['E'], 'G': ['H'], 'H': ['G'],
        '1': ['2'], '2': ['1'], '3': ['4'], '4': ['3'],
        '5': ['6'], '6': ['5'], '7': ['8'], '8': ['7'],
        '9': ['10'], '10': ['9'], '11': ['12'], '12': ['11'],
        '13': ['14'], '14': ['13'], '15': ['16'], '16': ['15'],
        '17': ['18'], '18': ['17'], '19': ['20'], '20': ['19'],
        '21': ['22'], '22': ['21'], '23': ['24'], '24': ['23'],
        '25': ['26'], '26': ['25'], '27': ['28'], '28': ['27'],
        '29': ['30'], '30': ['29'], '31': ['32'], '32': ['31'],
        '33': ['34'], '34': ['33'], '35': ['36'], '36': ['35'],
        '37': ['38'], '38': ['37', '39'], '39': ['38', '40'], '40': ['39', '41'], '41': ['40'],
    }

WINDOW_SEATS = {'A', 'D', 'E', 'H', '2', '4', '6', '8', '10', '12', '14', '16',
                    '18', '20', '22', '24', '26', '28', '30', '32', '34', '36', '37', '41'}