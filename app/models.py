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
    is_active_account = db.Column(db.Boolean, default=True)
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
    registration = db.Column(db.String(20), unique=True, nullable=False)  # MH-12-DK-4721
    layout_name = db.Column(db.String(50), default='shrisamarth_49')      # which seat layout to use
    total_seats = db.Column(db.Integer, default=49)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)

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
    base_fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, departed, completed, cancelled

    driver = db.relationship('User', foreign_keys=[driver_id])
    bookings = db.relationship('Booking', backref='voyage', lazy=True, cascade='all, delete-orphan')

    @property
    def seats_booked(self):
        return Booking.query.filter_by(voyage_id=self.id, status='confirmed').count()

    def __repr__(self):
        return f'<Voyage {self.origin}→{self.destination} {self.departure_at}>'


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
    gender = db.Column(db.String(1), nullable=False)  # 'M' or 'F'

    boarding_point = db.Column(db.String(80))
    dropping_point = db.Column(db.String(80))

    fare = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    advance_paid = db.Column(db.Numeric(10, 2), default=0)
    balance_due = db.Column(db.Numeric(10, 2), default=0)

    status = db.Column(db.String(20), default='confirmed')  # confirmed, cancelled
    booking_code = db.Column(db.String(30), unique=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship('User', foreign_keys=[created_by_id])

    __table_args__ = (
        # CRITICAL: prevents double-booking the same seat on the same voyage
        db.UniqueConstraint('voyage_id', 'seat_id', name='uq_voyage_seat'),
    )

    def __repr__(self):
        return f'<Booking {self.booking_code} seat {self.seat_id}>'