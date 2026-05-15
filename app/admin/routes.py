from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Bus, Voyage, Booking, User, ActivityLog
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from app.admin.forms import BusForm, VoyageForm, UserForm, UserEditForm
from app.logging import log_activity

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


@admin_bp.before_request
@login_required
def restrict_to_admin():
    if not current_user.has_role('admin'):
        abort(403)

# ============================================================
# DASHBOARD / REPORTS
# ============================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
def dashboard():
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)

    # All confirmed bookings
    all_bookings = Booking.query.filter_by(status='confirmed').all()

    # Today's voyages
    today_voyages = Voyage.query.filter(
        func.date(Voyage.departure_at) == today
    ).all()
    today_voyage_ids = [v.id for v in today_voyages]

    # Today's bookings
    today_bookings = [b for b in all_bookings if b.voyage_id in today_voyage_ids]

    # This week's voyages
    week_voyages = Voyage.query.filter(
        func.date(Voyage.departure_at) >= week_ago,
        func.date(Voyage.departure_at) <= today
    ).all()

    # Stats
    total_revenue = sum(float(b.fare or 0) for b in all_bookings)
    total_collected = sum(float(b.advance_paid or 0) for b in all_bookings)
    total_outstanding = sum(float(b.balance_due or 0) for b in all_bookings)

    today_revenue = sum(float(b.fare or 0) for b in today_bookings)
    today_collected = sum(float(b.advance_paid or 0) for b in today_bookings)

    # Upcoming voyages with occupancy
    upcoming = (Voyage.query
                .filter_by(status='scheduled')
                .order_by(Voyage.departure_at.asc())
                .limit(10)
                .all())

    # Recent bookings
    recent = (Booking.query
              .filter_by(status='confirmed')
              .order_by(Booking.created_at.desc())
              .limit(20)
              .all())

    # Per-voyage revenue breakdown
    voyage_stats = []
    for v in upcoming:
        v_bookings = [b for b in all_bookings if b.voyage_id == v.id]
        v_fare = sum(float(b.fare or 0) for b in v_bookings)
        v_collected = sum(float(b.advance_paid or 0) for b in v_bookings)
        v_outstanding = sum(float(b.balance_due or 0) for b in v_bookings)
        voyage_stats.append({
            'voyage': v,
            'bookings': len(v_bookings),
            'fare': v_fare,
            'collected': v_collected,
            'outstanding': v_outstanding,
        })

    return render_template('admin/dashboard.html',
        total_revenue=total_revenue,
        total_collected=total_collected,
        total_outstanding=total_outstanding,
        today_revenue=today_revenue,
        today_collected=today_collected,
        today_bookings=len(today_bookings),
        total_bookings=len(all_bookings),
        upcoming=upcoming,
        voyage_stats=voyage_stats,
        recent=recent,
    )

# ============================================================
# ACTIVITY LOG
# ============================================================

@admin_bp.route('/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', 'all')
    user_filter = request.args.get('user', 0, type=int)

    query = ActivityLog.query.order_by(ActivityLog.created_at.desc())

    if action_filter != 'all':
        query = query.filter_by(action=action_filter)
    if user_filter:
        query = query.filter_by(user_id=user_filter)

    logs = query.paginate(page=page, per_page=50, error_out=False)

    # Get unique actions and users for filter dropdowns
    all_actions = db.session.query(ActivityLog.action).distinct().all()
    all_actions = sorted([a[0] for a in all_actions])
    all_users = User.query.order_by(User.full_name).all()

    return render_template('admin/logs.html',
        logs=logs,
        action_filter=action_filter,
        user_filter=user_filter,
        all_actions=all_actions,
        all_users=all_users,
    )
# ============================================================
# BUSES
# ============================================================

@admin_bp.route('/buses')
def buses():
    all_buses = Bus.query.order_by(Bus.created_at.desc()).all()
    return render_template('admin/buses.html', buses=all_buses)


@admin_bp.route('/buses/new', methods=['GET', 'POST'])
def bus_new():
    form = BusForm()
    if form.validate_on_submit():
        bus = Bus(
            registration=form.registration.data.strip().upper(),
            name=form.name.data.strip() if form.name.data else None,
            total_seats=form.total_seats.data,
            notes=form.notes.data,
            is_active=form.is_active.data,
        )
        db.session.add(bus)
        db.session.commit()
        log_activity('bus_created', f'Added bus {bus.registration}', 'bus', bus.id)
        flash(f'Bus {bus.registration} added.', 'success')
        flash(f'Bus {bus.registration} added.', 'success')
        return redirect(url_for('admin.buses'))
    return render_template('admin/bus_form.html', form=form, title='Add Bus')


@admin_bp.route('/buses/<int:bus_id>/edit', methods=['GET', 'POST'])
def bus_edit(bus_id):
    bus = Bus.query.get_or_404(bus_id)
    form = BusForm(obj=bus)
    if form.validate_on_submit():
        bus.registration = form.registration.data.strip().upper()
        bus.name = form.name.data.strip() if form.name.data else None
        bus.total_seats = form.total_seats.data
        bus.notes = form.notes.data
        bus.is_active = form.is_active.data
        db.session.commit()
        log_activity('bus_edited', f'Edited bus {bus.registration}', 'bus', bus.id)
        flash(f'Bus {bus.registration} updated.', 'success')
        flash(f'Bus {bus.registration} updated.', 'success')
        return redirect(url_for('admin.buses'))
    return render_template('admin/bus_form.html', form=form, title='Edit Bus', bus=bus)


# ============================================================
# VOYAGES
# ============================================================

@admin_bp.route('/voyages')
def voyages():
    status_filter = request.args.get('status', 'scheduled')
    query = Voyage.query.order_by(Voyage.departure_at.asc())
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    all_voyages = query.all()
    return render_template('admin/voyages.html',
                           voyages=all_voyages,
                           status_filter=status_filter)


@admin_bp.route('/voyages/new', methods=['GET', 'POST'])
def voyage_new():
    form = VoyageForm()
    form.bus_id.choices = [
        (b.id, f'{b.registration}{" — " + b.name if b.name else ""}')
        for b in Bus.query.filter_by(is_active=True).all()
    ]
    drivers = User.query.filter_by(role='driver', is_active_account=True).all()
    form.driver_id.choices = [(0, '— Unassigned —')] + [
        (d.id, d.full_name) for d in drivers
    ]

    if form.validate_on_submit():
        voyage = Voyage(
            origin=form.origin.data.strip(),
            destination=form.destination.data.strip(),
            departure_at=form.departure_at.data,
            arrival_at=form.arrival_at.data,
            bus_id=form.bus_id.data,
            driver_id=form.driver_id.data if form.driver_id.data != 0 else None,
            base_fare=form.base_fare.data,
            notes=form.notes.data,
            created_by_id=current_user.id,
        )
        db.session.add(voyage)
        db.session.commit()
        log_activity('voyage_created',
                     f'Created voyage {voyage.origin}→{voyage.destination} on {voyage.departure_at.strftime("%d %b %Y")}',
                     'voyage', voyage.id)
        flash(f'Voyage {voyage.origin} → {voyage.destination} created.', 'success')
        flash(f'Voyage {voyage.origin} → {voyage.destination} created.', 'success')
        return redirect(url_for('admin.voyages'))

    return render_template('admin/voyage_form.html', form=form, title='New Voyage')


@admin_bp.route('/voyages/<int:voyage_id>/edit', methods=['GET', 'POST'])
def voyage_edit(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)
    if voyage.status == 'cancelled':
        flash('Cancelled voyages cannot be edited.', 'error')
        return redirect(url_for('admin.voyages'))

    form = VoyageForm(obj=voyage)
    form.bus_id.choices = [
        (b.id, f'{b.registration}{" — " + b.name if b.name else ""}')
        for b in Bus.query.filter_by(is_active=True).all()
    ]
    drivers = User.query.filter_by(role='driver', is_active_account=True).all()
    form.driver_id.choices = [(0, '— Unassigned —')] + [
        (d.id, d.full_name) for d in drivers
    ]

    if form.validate_on_submit():
        voyage.origin = form.origin.data.strip()
        voyage.destination = form.destination.data.strip()
        voyage.departure_at = form.departure_at.data
        voyage.arrival_at = form.arrival_at.data
        voyage.bus_id = form.bus_id.data
        voyage.driver_id = form.driver_id.data if form.driver_id.data != 0 else None
        voyage.base_fare = form.base_fare.data
        voyage.notes = form.notes.data
        db.session.commit()
        log_activity('voyage_edited',
                     f'Edited voyage {voyage.origin}→{voyage.destination}',
                     'voyage', voyage.id)
        flash('Voyage updated.', 'success')
        flash('Voyage updated.', 'success')
        return redirect(url_for('admin.voyages'))

    return render_template('admin/voyage_form.html', form=form,
                           title='Edit Voyage', voyage=voyage)


@admin_bp.route('/voyages/<int:voyage_id>/cancel', methods=['POST'])
def voyage_cancel(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)
    if not voyage.is_cancellable:
        flash('This voyage cannot be cancelled.', 'error')
        return redirect(url_for('admin.voyages'))

    confirmed_bookings = Booking.query.filter_by(
        voyage_id=voyage.id, status='confirmed'
    ).all()

    for booking in confirmed_bookings:
        booking.status = 'cancelled'

    voyage.status = 'cancelled'
    voyage.cancelled_at = datetime.utcnow()
    voyage.cancelled_by_id = current_user.id
    db.session.commit()
    log_activity('voyage_cancelled',
                 f'Cancelled voyage {voyage.origin}→{voyage.destination} ({len(confirmed_bookings)} bookings cancelled)',
                 'voyage', voyage.id)
    flash(f'Voyage cancelled. {len(confirmed_bookings)} booking(s) also cancelled.', 'success')
    flash(f'Voyage cancelled. {len(confirmed_bookings)} booking(s) also cancelled.', 'success')
    return redirect(url_for('admin.voyages'))


# ============================================================
# USERS
# ============================================================

@admin_bp.route('/users')
def users():
    all_users = User.query.order_by(User.role, User.full_name).all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    form = UserForm()
    if form.validate_on_submit():
        # Check if username already exists
        existing = User.query.filter_by(username=form.username.data.strip()).first()
        if existing:
            flash('Username already taken.', 'error')
            return render_template('admin/user_form.html', form=form, title='Add User')

        user = User(
            username=form.username.data.strip().lower(),
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip() if form.email.data else None,
            role=form.role.data,
            is_active_account=form.is_active_account.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        log_activity('user_created', f'Created user {user.username} ({user.role})', 'user', user.id)
        flash(f'User {user.username} created.', 'success')
        flash(f'User {user.username} created.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form, title='Add User')


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)

    if form.validate_on_submit():
        # Check username uniqueness (excluding current user)
        existing = User.query.filter(
            User.username == form.username.data.strip(),
            User.id != user.id
        ).first()
        if existing:
            flash('Username already taken.', 'error')
            return render_template('admin/user_form.html', form=form,
                                   title='Edit User', user=user)

        user.username = form.username.data.strip().lower()
        user.full_name = form.full_name.data.strip()
        user.email = form.email.data.strip() if form.email.data else None
        user.role = form.role.data
        user.is_active_account = form.is_active_account.data

        # Only update password if provided
        if form.new_password.data:
            user.set_password(form.new_password.data)

        db.session.commit()
        log_activity('user_edited', f'Edited user {user.username} ({user.role})', 'user', user.id)
        flash(f'User {user.username} updated.', 'success')
        flash(f'User {user.username} updated.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form,
                           title='Edit User', user=user)