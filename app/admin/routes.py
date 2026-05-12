from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Bus, Voyage, Booking, User
from app.admin.forms import BusForm, VoyageForm

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


@admin_bp.before_request
@login_required
def restrict_to_admin():
    if not current_user.has_role('admin'):
        abort(403)


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

    flash(f'Voyage cancelled. {len(confirmed_bookings)} booking(s) also cancelled.', 'success')
    return redirect(url_for('admin.voyages'))


# ============================================================
# USERS (stub for now)
# ============================================================

@admin_bp.route('/users')
def users():
    all_users = User.query.order_by(User.role, User.full_name).all()
    return render_template('admin/users.html', users=all_users)