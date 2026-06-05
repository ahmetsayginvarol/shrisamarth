from datetime import datetime
import io
import calendar as cal_module
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, jsonify, send_file
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (Bus, Voyage, Booking, User, ActivityLog, RouteStop, SiteContent,
                        PasswordResetToken, AbuseLog, IpBan, Newsletter,
                        FinancialEntry, EXPENSE_CATEGORIES, INCOME_CATEGORIES)
from datetime import datetime, timedelta, date as date_type
from sqlalchemy import func, and_
from app.admin.forms import BusForm, VoyageForm, UserForm, UserEditForm
from app.logging import log_activity

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')


def _save_stops(voyage_id):
    """Parse stop arrays from POST data and save RouteStop rows."""
    names = request.form.getlist('stop_name[]')
    types = request.form.getlist('stop_type[]')
    times = request.form.getlist('stop_time[]')
    fares = request.form.getlist('stop_fare_override[]')
    for i, name in enumerate(names):
        name = name.strip()
        if not name:
            continue
        stop_type = types[i] if i < len(types) else 'boarding'
        stop_time = times[i].strip() if i < len(times) else ''
        raw_fare = fares[i].strip() if i < len(fares) else ''
        fare_override = None
        if stop_type == 'boarding' and raw_fare:
            try:
                fare_override = float(raw_fare)
            except ValueError:
                fare_override = None
        db.session.add(RouteStop(
            voyage_id=voyage_id,
            stop_name=name,
            stop_type=stop_type,
            stop_time=stop_time or None,
            stop_order=i,
            fare_override=fare_override,
        ))


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
        v_boarded = sum(1 for b in v_bookings if b.boarded_at)
        voyage_stats.append({
            'voyage': v,
            'bookings': len(v_bookings),
            'boarded': v_boarded,
            'fare': v_fare,
            'collected': v_collected,
            'outstanding': v_outstanding,
        })

    # Net profit for dashboard card (this month ticket revenue minus logged expenses)
    month_start = today.replace(day=1)
    month_ticket_rev = float(db.session.query(
        func.coalesce(func.sum(Booking.advance_paid), 0)
    ).filter(
        Booking.status == 'confirmed',
        func.date(Booking.created_at) >= month_start,
    ).scalar() or 0)
    month_expenses = float(db.session.query(
        func.coalesce(func.sum(FinancialEntry.amount), 0)
    ).filter(
        FinancialEntry.entry_type == 'expense',
        FinancialEntry.entry_date >= month_start,
    ).scalar() or 0)
    month_net_profit = month_ticket_rev - month_expenses

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
        month_ticket_rev=month_ticket_rev,
        month_expenses=month_expenses,
        month_net_profit=month_net_profit,
    )

# ============================================================
# ACTIVITY LOG
# ============================================================

@admin_bp.route('/logs/clear', methods=['POST'])
def logs_clear():
    data = request.get_json() or {}
    password = data.get('password', '')
    verify_only = data.get('verify_only', False)
    if not current_user.check_password(password):
        return jsonify({'status': 'error', 'message': 'Incorrect password.'}), 403
    if verify_only:
        return jsonify({'status': 'ok'})
    count = ActivityLog.query.count()
    ActivityLog.query.delete()
    db.session.commit()
    log_activity('log_cleared', f'Activity log cleared — {count} records permanently deleted')
    return jsonify({'status': 'success', 'count': count})


@admin_bp.route('/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', 'all')
    user_filter = request.args.get('user', '')   # '' | 'customers' | '<int id>'
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    is_print = request.args.get('format') == 'print'

    query = ActivityLog.query.order_by(ActivityLog.created_at.desc())

    if action_filter != 'all':
        query = query.filter_by(action=action_filter)
    if user_filter == 'customers':
        customer_ids = db.session.query(User.id).filter_by(role='customer').subquery()
        query = query.filter(ActivityLog.user_id.in_(customer_ids))
    elif user_filter and user_filter.isdigit():
        query = query.filter_by(user_id=int(user_filter))
    if date_from:
        try:
            query = query.filter(ActivityLog.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(ActivityLog.created_at < dt_to)
        except ValueError:
            pass

    all_actions = db.session.query(ActivityLog.action).distinct().all()
    all_actions = sorted([a[0] for a in all_actions])
    staff_users = User.query.filter(User.role != 'customer').order_by(User.full_name).all()

    if is_print:
        all_logs = query.all()
        return render_template('admin/logs_print.html',
            all_logs=all_logs,
            action_filter=action_filter,
            user_filter=user_filter,
            date_from=date_from,
            date_to=date_to,
            staff_users=staff_users,
            now=datetime.utcnow(),
        )

    logs = query.paginate(page=page, per_page=50, error_out=False)

    return render_template('admin/logs.html',
        logs=logs,
        action_filter=action_filter,
        user_filter=user_filter,
        date_from=date_from,
        date_to=date_to,
        all_actions=all_actions,
        staff_users=staff_users,
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to save bus. Please try again.', 'error')
            return render_template('admin/bus_form.html', form=form, title='Add Bus')
        log_activity('bus_created', f'Added bus {bus.registration}', 'bus', bus.id)
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to save bus. Please try again.', 'error')
            return render_template('admin/bus_form.html', form=form, title='Edit Bus', bus=bus)
        log_activity('bus_edited', f'Edited bus {bus.registration}', 'bus', bus.id)
        flash(f'Bus {bus.registration} updated.', 'success')
        return redirect(url_for('admin.buses'))
    return render_template('admin/bus_form.html', form=form, title='Edit Bus', bus=bus)


# ============================================================
# VOYAGES
# ============================================================

@admin_bp.route('/api/voyage/<int:voyage_id>/stop-fare')
def voyage_stop_fare(voyage_id):
    voyage = Voyage.query.get_or_404(voyage_id)
    stop_name = request.args.get('stop', '').strip()
    base = float(voyage.base_fare)
    if stop_name:
        stop = RouteStop.query.filter_by(
            voyage_id=voyage_id,
            stop_name=stop_name,
            stop_type='boarding',
        ).first()
        if stop and stop.fare_override is not None:
            return jsonify({'fare': float(stop.fare_override), 'is_override': True, 'base_fare': base})
    return jsonify({'fare': base, 'is_override': False, 'base_fare': base})


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
        db.session.flush()
        _save_stops(voyage.id)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to create voyage. Please try again.', 'error')
            return redirect(url_for('admin.voyage_new'))

        # Handle recurrence
        recurrence = request.form.get('recurrence', 'none')
        repeat_until_str = request.form.get('repeat_until', '')
        custom_days_raw = request.form.getlist('custom_days')
        rec_group = None

        if recurrence != 'none':
            import secrets as _secrets
            rec_group = 'REC-' + _secrets.token_hex(5).upper()
            voyage.recurrence_group = rec_group

            try:
                repeat_until = datetime.strptime(repeat_until_str, '%Y-%m-%d')
            except Exception:
                repeat_until = voyage.departure_at + timedelta(days=30)

            max_date = voyage.departure_at + timedelta(days=90)
            repeat_until = min(repeat_until, max_date)

            step_map = {'daily': 1, 'every2': 2, 'every3': 3, 'weekly': 7}
            step = step_map.get(recurrence, 1)
            custom_days = [int(x) for x in custom_days_raw if x.isdigit()]

            if recurrence == 'custom':
                current_dt = voyage.departure_at + timedelta(days=1)
            else:
                current_dt = voyage.departure_at + timedelta(days=step)

            created = 1  # count base voyage
            skipped = 0

            while current_dt.date() <= repeat_until.date() and created < 91:
                if recurrence == 'custom':
                    wd = current_dt.weekday()
                    if wd not in custom_days:
                        current_dt += timedelta(days=1)
                        continue

                conflict = Voyage.query.filter_by(
                    bus_id=voyage.bus_id,
                    status='scheduled',
                ).filter(
                    func.date(Voyage.departure_at) == current_dt.date()
                ).first()

                if conflict:
                    skipped += 1
                else:
                    arr = None
                    if voyage.arrival_at:
                        arr = voyage.arrival_at + (current_dt - voyage.departure_at)
                    v = Voyage(
                        bus_id=voyage.bus_id,
                        origin=voyage.origin,
                        destination=voyage.destination,
                        departure_at=current_dt,
                        arrival_at=arr,
                        base_fare=voyage.base_fare,
                        driver_id=voyage.driver_id,
                        status='scheduled',
                        notes=voyage.notes,
                        recurrence_group=rec_group,
                        created_by_id=current_user.id,
                    )
                    db.session.add(v)
                    db.session.flush()
                    for s in voyage.stops:
                        db.session.add(RouteStop(
                            voyage_id=v.id,
                            stop_name=s.stop_name,
                            stop_type=s.stop_type,
                            stop_time=s.stop_time,
                            stop_order=s.stop_order,
                        ))
                    created += 1

                if recurrence == 'custom':
                    current_dt += timedelta(days=1)
                else:
                    current_dt += timedelta(days=step)

            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash('Failed to create recurring voyages. Please try again.', 'error')
                return redirect(url_for('admin.voyages'))

        # Handle return voyage
        create_return = request.form.get('create_return') == 'on'
        return_dep_str = request.form.get('return_departure_at', '').strip()
        return_voyage = None
        return_created = 0

        if create_return and return_dep_str:
            try:
                return_dep_at = datetime.strptime(return_dep_str, '%Y-%m-%dT%H:%M')
            except Exception:
                return_dep_at = None

            if return_dep_at:
                outbound_stops = sorted(voyage.stops, key=lambda s: s.stop_order)
                reversed_stops = list(reversed(outbound_stops))

                # Flip stop_type: boarding ↔ dropping
                def _flip(t):
                    return 'dropping' if t == 'boarding' else 'boarding'

                ret_rec_group = (rec_group + '-RETURN') if rec_group else None

                return_voyage = Voyage(
                    origin=voyage.destination,
                    destination=voyage.origin,
                    departure_at=return_dep_at,
                    bus_id=voyage.bus_id,
                    driver_id=voyage.driver_id,
                    base_fare=voyage.base_fare,
                    notes=voyage.notes,
                    recurrence_group=ret_rec_group,
                    created_by_id=current_user.id,
                    status='scheduled',
                )
                db.session.add(return_voyage)
                db.session.flush()
                for i, s in enumerate(reversed_stops):
                    db.session.add(RouteStop(
                        voyage_id=return_voyage.id,
                        stop_name=s.stop_name,
                        stop_type=_flip(s.stop_type),
                        stop_time=s.stop_time,
                        stop_order=i,
                    ))
                return_created = 1

                # Create return recurrences for each outbound recurring voyage
                if rec_group:
                    recurring_out = Voyage.query.filter(
                        Voyage.recurrence_group == rec_group,
                        Voyage.id != voyage.id,
                    ).order_by(Voyage.departure_at).all()

                    for v_out in recurring_out:
                        r_dt = v_out.departure_at.replace(
                            hour=return_dep_at.hour,
                            minute=return_dep_at.minute,
                            second=0, microsecond=0,
                        )
                        r_v = Voyage(
                            origin=voyage.destination,
                            destination=voyage.origin,
                            departure_at=r_dt,
                            bus_id=voyage.bus_id,
                            driver_id=voyage.driver_id,
                            base_fare=voyage.base_fare,
                            notes=voyage.notes,
                            recurrence_group=ret_rec_group,
                            created_by_id=current_user.id,
                            status='scheduled',
                        )
                        db.session.add(r_v)
                        db.session.flush()
                        for i, s in enumerate(reversed_stops):
                            db.session.add(RouteStop(
                                voyage_id=r_v.id,
                                stop_name=s.stop_name,
                                stop_type=_flip(s.stop_type),
                                stop_time=s.stop_time,
                                stop_order=i,
                            ))
                        return_created += 1

                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    flash('Voyage created but failed to create return voyage.', 'error')
                    return redirect(url_for('admin.voyages'))

        # Flash and log
        if recurrence != 'none':
            skip_msg = f" ({skipped} date{'s' if skipped != 1 else ''} skipped — bus conflict)" if skipped else ""
            if return_voyage:
                flash(
                    f"Created {created} recurring voyage{'s' if created != 1 else ''}{skip_msg}. "
                    f"Return voyage {voyage.destination} → {voyage.origin} also created ({return_created} voyage{'s' if return_created != 1 else ''}).",
                    'success'
                )
            else:
                flash(f"Created {created} recurring voyage{'s' if created != 1 else ''}{skip_msg}.", 'success')
            if return_voyage:
                log_activity('voyage_created',
                             f"Created recurring voyage {voyage.origin}→{voyage.destination} ({created} voyages) with return voyage {voyage.destination}→{voyage.origin} ({return_created} voyages)",
                             'voyage', voyage.id)
            else:
                log_activity('voyage_created',
                             f"Created recurring voyage {voyage.origin}→{voyage.destination} ({created} voyages, {recurrence}, {voyage.departure_at.strftime('%d %b')} - {repeat_until.strftime('%d %b %Y')})",
                             'voyage', voyage.id)
        else:
            if return_voyage:
                flash(
                    f'Voyage created. Return voyage {voyage.destination} → {voyage.origin} also created.',
                    'success'
                )
                log_activity('voyage_created',
                             f'Created voyage {voyage.origin}→{voyage.destination} with return voyage {voyage.destination}→{voyage.origin}',
                             'voyage', voyage.id)
            else:
                flash(f'Voyage {voyage.origin} → {voyage.destination} created.', 'success')
                log_activity('voyage_created',
                             f'Created voyage {voyage.origin}→{voyage.destination} on {voyage.departure_at.strftime("%d %b %Y")}',
                             'voyage', voyage.id)

        return redirect(url_for('admin.voyages'))

    return render_template('admin/voyage_form.html', form=form, title='New Voyage',
                           stops_json='[]')


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
        apply_scope = request.form.get('apply_scope', 'this')

        # Fields to update on every affected voyage
        new_origin      = form.origin.data.strip()
        new_destination = form.destination.data.strip()
        new_departure   = form.departure_at.data
        new_arrival     = form.arrival_at.data
        new_bus_id      = form.bus_id.data
        new_driver_id   = form.driver_id.data if form.driver_id.data != 0 else None
        new_base_fare   = form.base_fare.data
        new_notes       = form.notes.data

        # Collect stops from POST (used for all affected voyages)
        stop_names  = [n.strip() for n in request.form.getlist('stop_name[]')]
        stop_types  = request.form.getlist('stop_type[]')
        stop_times  = request.form.getlist('stop_time[]')
        new_stops   = [
            {'name': stop_names[i], 'type': stop_types[i] if i < len(stop_types) else 'boarding',
             'time': stop_times[i].strip() if i < len(stop_times) else ''}
            for i, n in enumerate(stop_names) if stop_names[i]
        ]

        def apply_to_voyage(v, new_dep, new_arr):
            v.origin       = new_origin
            v.destination  = new_destination
            v.departure_at = new_dep
            v.arrival_at   = new_arr
            v.bus_id       = new_bus_id
            v.driver_id    = new_driver_id
            v.base_fare    = new_base_fare
            v.notes        = new_notes
            RouteStop.query.filter_by(voyage_id=v.id).delete()
            for i, s in enumerate(new_stops):
                db.session.add(RouteStop(
                    voyage_id=v.id, stop_name=s['name'], stop_type=s['type'],
                    stop_time=s['time'] or None, stop_order=i,
                ))

        # Always update this voyage
        apply_to_voyage(voyage, new_departure, new_arrival)

        affected = 1
        if apply_scope == 'following' and voyage.recurrence_group:
            # Time offsets from the edited voyage's new departure
            dep_time = (new_departure.hour, new_departure.minute)
            arr_time = (new_arrival.hour, new_arrival.minute) if new_arrival else None

            siblings = Voyage.query.filter(
                Voyage.recurrence_group == voyage.recurrence_group,
                Voyage.id != voyage.id,
                Voyage.departure_at >= voyage.departure_at,
                Voyage.status == 'scheduled',
            ).all()

            for sib in siblings:
                sib_dep = sib.departure_at.replace(hour=dep_time[0], minute=dep_time[1], second=0, microsecond=0)
                sib_arr = None
                if arr_time and sib.arrival_at:
                    sib_arr = sib.arrival_at.replace(hour=arr_time[0], minute=arr_time[1], second=0, microsecond=0)
                apply_to_voyage(sib, sib_dep, sib_arr)
                affected += 1

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to save voyage. Please try again.', 'error')
            return redirect(url_for('admin.voyage_edit', voyage_id=voyage.id))
        suffix = f' (and {affected - 1} following)' if affected > 1 else ''
        log_activity('voyage_edited',
                     f'Edited voyage {new_origin}→{new_destination}{suffix}',
                     'voyage', voyage.id)
        flash(f'Voyage updated{suffix}.', 'success')
        return redirect(url_for('admin.voyages'))

    import json
    existing = [
        {'name': s.stop_name, 'type': s.stop_type,
         'time': s.stop_time or '', 'order': s.stop_order,
         'fare_override': float(s.fare_override) if s.fare_override is not None else None}
        for s in sorted(voyage.stops, key=lambda s: s.stop_order)
    ]
    has_future_siblings = False
    if voyage.recurrence_group:
        has_future_siblings = Voyage.query.filter(
            Voyage.recurrence_group == voyage.recurrence_group,
            Voyage.id != voyage.id,
            Voyage.departure_at >= voyage.departure_at,
            Voyage.status == 'scheduled',
        ).count() > 0

    return render_template('admin/voyage_form.html', form=form,
                           title='Edit Voyage', voyage=voyage,
                           stops_json=json.dumps(existing),
                           has_future_siblings=has_future_siblings)


@admin_bp.route('/voyages/cancel-recurrence/<group>', methods=['POST'])
def cancel_recurrence(group):
    future = Voyage.query.filter_by(recurrence_group=group, status='scheduled')\
        .filter(Voyage.departure_at > datetime.utcnow()).all()
    count = 0
    for v in future:
        v.status = 'cancelled'
        v.cancelled_at = datetime.utcnow()
        v.cancelled_by_id = current_user.id
        count += 1
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Failed to cancel recurring voyages. Please try again.', 'error')
        return redirect(url_for('admin.voyages'))
    log_activity('voyage_cancelled', f'Cancelled {count} future recurring voyages in group {group}', 'voyage', None)
    flash(f"Cancelled {count} future recurring voyages.", 'success')
    return redirect(url_for('admin.voyages'))


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
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Failed to cancel voyage. Please try again.', 'error')
        return redirect(url_for('admin.voyages'))
    log_activity('voyage_cancelled',
                 f'Cancelled voyage {voyage.origin}→{voyage.destination} ({len(confirmed_bookings)} bookings cancelled)',
                 'voyage', voyage.id)
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to create user. Please try again.', 'error')
            return render_template('admin/user_form.html', form=form, title='Add User')
        log_activity('user_created', f'Created user {user.username} ({user.role})', 'user', user.id)
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

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Failed to save user. Please try again.', 'error')
            return render_template('admin/user_form.html', form=form, title='Edit User', user=user)
        log_activity('user_edited', f'Edited user {user.username} ({user.role})', 'user', user.id)
        flash(f'User {user.username} updated.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/user_form.html', form=form,
                           title='Edit User', user=user)


@admin_bp.route('/users/<int:user_id>/send-reset', methods=['POST'])
@login_required
def user_send_reset(user_id):
    user = User.query.get_or_404(user_id)
    if not user.email:
        return jsonify({'status': 'error', 'message': 'User has no email address.'}), 400

    from app.email import send_email
    from flask import current_app, render_template as _rt
    import secrets as _sec

    # Expire old unused tokens for this user
    PasswordResetToken.query.filter_by(user_id=user.id, used=False).delete()
    db.session.flush()

    token_str = _sec.token_urlsafe(48)
    token = PasswordResetToken(
        user_id=user.id,
        token=token_str,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db.session.add(token)
    db.session.commit()

    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    reset_url = f"{domain}/reset-password/{token_str}"
    html = _rt('email/reset_password.html', user=user, reset_url=reset_url, domain=domain)

    ok = send_email(user.email, 'Reset your SHRISAMARTH password', html)
    if ok:
        log_activity('password_reset_sent',
                     f'Password reset email sent to {user.email} (user {user.username})',
                     'user', user.id)
        return jsonify({'status': 'ok', 'email': user.email})
    return jsonify({'status': 'error', 'message': 'Failed to send email.'}), 500

# ============================================================
# REGISTERED PASSENGERS
# ============================================================

@admin_bp.route('/passengers')
@login_required
def passengers():
    customers = (User.query
                 .filter_by(role='customer')
                 .order_by(User.created_at.desc())
                 .all())

    # Annotate each customer with booking stats
    stats = {}
    for c in customers:
        bookings = Booking.query.filter_by(created_by_id=c.id).all()
        confirmed = [b for b in bookings if b.status == 'confirmed']
        stats[c.id] = {
            'total':    len(confirmed),
            'upcoming': sum(1 for b in confirmed if b.voyage.departure_at > datetime.utcnow()),
            'fare':     sum(float(b.fare) for b in confirmed),
            'balance':  sum(float(b.balance_due or 0) for b in confirmed),
        }

    return render_template('admin/passengers.html', customers=customers, stats=stats)


@admin_bp.route('/passengers/<int:customer_id>')
@login_required
def passenger_detail(customer_id):
    customer = User.query.filter_by(id=customer_id, role='customer').first_or_404()

    bookings = (Booking.query
                .filter_by(created_by_id=customer_id)
                .order_by(Booking.created_at.desc())
                .all())

    confirmed = [b for b in bookings if b.status == 'confirmed']
    stats = {
        'total':    len(confirmed),
        'upcoming': sum(1 for b in confirmed if b.voyage.departure_at > datetime.utcnow()),
        'fare':     sum(float(b.fare) for b in confirmed),
        'balance':  sum(float(b.balance_due or 0) for b in confirmed),
    }

    return render_template('admin/passenger_detail.html',
                           customer=customer, bookings=bookings, stats=stats)


@admin_bp.route('/passengers/<int:customer_id>/add-credit', methods=['POST'])
@login_required
def passenger_add_credit(customer_id):
    customer = User.query.filter_by(id=customer_id, role='customer').first_or_404()

    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'error')
        return redirect(url_for('admin.passenger_detail', customer_id=customer_id))

    if amount <= 0:
        flash('Amount must be positive.', 'error')
        return redirect(url_for('admin.passenger_detail', customer_id=customer_id))

    note = request.form.get('note', '').strip() or 'Manual credit by admin'
    customer.credit_balance = float(customer.credit_balance or 0) + amount
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Failed to add credit. Please try again.', 'error')
        return redirect(url_for('admin.passenger_detail', customer_id=customer_id))

    log_activity('user_edited',
                 f'Added ₹{amount:.0f} credit to {customer.full_name} ({customer.email}) — {note}',
                 'user', customer.id)
    flash(f'₹{amount:.0f} added to {customer.full_name}\'s account.', 'success')
    return redirect(url_for('admin.passenger_detail', customer_id=customer_id))


@admin_bp.route('/passengers/<int:customer_id>/toggle-active', methods=['POST'])
@login_required
def passenger_toggle_active(customer_id):
    customer = User.query.filter_by(id=customer_id, role='customer').first_or_404()
    customer.is_active_account = not customer.is_active_account
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Failed to update account status. Please try again.', 'error')
        return redirect(url_for('admin.passenger_detail', customer_id=customer_id))
    state = 'activated' if customer.is_active_account else 'deactivated'
    log_activity('user_edited', f'Customer account {state}: {customer.email}', 'user', customer.id)
    flash(f'Account {state}.', 'success')
    return redirect(url_for('admin.passenger_detail', customer_id=customer_id))


# ============================================================
# CALENDAR API
# ============================================================

@admin_bp.route('/api/calendar')
def calendar_data():
    year = request.args.get('year', datetime.utcnow().year, type=int)
    month = request.args.get('month', datetime.utcnow().month, type=int)

    # Get start/end of month
    first_day = date_type(year, month, 1)
    last_day_num = cal_module.monthrange(year, month)[1]
    last_day = date_type(year, month, last_day_num)

    # Query all voyages departing in this month
    voyages = Voyage.query.filter(
        func.date(Voyage.departure_at) >= first_day,
        func.date(Voyage.departure_at) <= last_day,
    ).all()

    if not voyages:
        return jsonify({})

    voyage_ids = [v.id for v in voyages]

    # Query confirmed bookings for those voyages
    bookings = Booking.query.filter(
        Booking.voyage_id.in_(voyage_ids),
        Booking.status == 'confirmed',
    ).all()

    # Group bookings by voyage_id
    bookings_by_voyage = {}
    for b in bookings:
        bookings_by_voyage.setdefault(b.voyage_id, []).append(b)

    # Group voyages by date
    result = {}
    voyages_by_date = {}
    for v in voyages:
        d = v.departure_at.date().isoformat()
        voyages_by_date.setdefault(d, []).append(v)

    for date_str, day_voyages in voyages_by_date.items():
        total_seats = sum(v.bus.total_seats for v in day_voyages)
        day_bookings = []
        for v in day_voyages:
            day_bookings.extend(bookings_by_voyage.get(v.id, []))

        confirmed = len(day_bookings)
        boarded = sum(1 for b in day_bookings if b.boarded_at)
        expected_revenue = sum(float(b.fare or 0) for b in day_bookings)
        collected = sum(float(b.advance_paid or 0) for b in day_bookings)
        outstanding = sum(float(b.balance_due or 0) for b in day_bookings)
        occupancy_pct = int(confirmed / total_seats * 100) if total_seats > 0 else 0

        voyage_list = []
        for v in day_voyages:
            v_bkgs = bookings_by_voyage.get(v.id, [])
            v_confirmed = len(v_bkgs)
            v_boarded = sum(1 for b in v_bkgs if b.boarded_at)
            v_revenue = sum(float(b.fare or 0) for b in v_bkgs)
            v_collected = sum(float(b.advance_paid or 0) for b in v_bkgs)
            v_outstanding = sum(float(b.balance_due or 0) for b in v_bkgs)
            v_seats = v.bus.total_seats
            voyage_list.append({
                'id': v.id,
                'origin': v.origin,
                'destination': v.destination,
                'departure': v.departure_at.strftime('%H:%M'),
                'confirmed': v_confirmed,
                'boarded': v_boarded,
                'total_seats': v_seats,
                'revenue': round(v_revenue, 2),
                'collected': round(v_collected, 2),
                'outstanding': round(v_outstanding, 2),
                'occupancy_pct': int(v_confirmed / v_seats * 100) if v_seats > 0 else 0,
                'bus': v.bus.registration,
                'driver': v.driver.full_name if v.driver_id else None,
                'passengers': [
                    {
                        'name': b.passenger_name,
                        'seat': b.seat_id,
                        'boarding': b.boarding_point or '',
                        'dropping': b.dropping_point or '',
                        'gender': b.gender or 'M',
                        'checked_in': bool(b.boarded_at),
                    }
                    for b in sorted(v_bkgs, key=lambda x: (x.boarding_point or '', x.seat_id or ''))
                ],
            })

        result[date_str] = {
            'voyage_count': len(day_voyages),
            'total_seats': total_seats,
            'confirmed_bookings': confirmed,
            'boarded': boarded,
            'expected_revenue': round(expected_revenue, 2),
            'collected': round(collected, 2),
            'outstanding': round(outstanding, 2),
            'occupancy_pct': occupancy_pct,
            'voyages': voyage_list,
        }

    return jsonify(result)


# ============================================================
# DAY REPORT PDF
# ============================================================

@admin_bp.route('/reports/day')
def day_report():
    date_str = request.args.get('date', '')
    try:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        abort(400)

    voyages = Voyage.query.filter(
        func.date(Voyage.departure_at) == report_date
    ).all()

    voyage_ids = [v.id for v in voyages]
    bookings_all = Booking.query.filter(
        Booking.voyage_id.in_(voyage_ids),
        Booking.status == 'confirmed',
    ).all() if voyage_ids else []

    bookings_by_voyage = {}
    for b in bookings_all:
        bookings_by_voyage.setdefault(b.voyage_id, []).append(b)

    pdf_buf = _generate_day_report_pdf(report_date, voyages, bookings_by_voyage)
    filename = f"day-report-{date_str}.pdf"
    return send_file(pdf_buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


def _generate_day_report_pdf(report_date, voyages, bookings_by_voyage):
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    INK    = rl_colors.HexColor('#141b2d')
    CREAM  = rl_colors.HexColor('#faf6ef')
    CREAM2 = rl_colors.HexColor('#f3ecdf')
    GOLD   = rl_colors.HexColor('#d4a84c')
    MUTED  = rl_colors.HexColor('#6b6558')
    LINE   = rl_colors.HexColor('#d9d0bf')
    SAGE   = rl_colors.HexColor('#7a9a5a')
    RUBY   = rl_colors.HexColor('#a83232')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm)
    content_w = A4[0] - 30*mm

    s_brand   = ParagraphStyle('brand', fontSize=16, textColor=INK, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=20)
    s_sub     = ParagraphStyle('sub', fontSize=8, textColor=MUTED, fontName='Helvetica', alignment=TA_LEFT, leading=10)
    s_title   = ParagraphStyle('title', fontSize=22, textColor=INK, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=26)
    s_th      = ParagraphStyle('th', fontSize=7, textColor=MUTED, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=9)
    s_td      = ParagraphStyle('td', fontSize=8, textColor=INK, fontName='Helvetica', alignment=TA_LEFT, leading=10)
    s_td_bold = ParagraphStyle('td_bold', fontSize=8, textColor=INK, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=10)
    s_td_r    = ParagraphStyle('td_r', fontSize=8, textColor=INK, fontName='Helvetica', alignment=TA_RIGHT, leading=10)
    s_meta_l  = ParagraphStyle('meta_l', fontSize=6, textColor=GOLD, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=8)
    s_meta_v  = ParagraphStyle('meta_v', fontSize=10, textColor=INK, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=12)
    s_h2      = ParagraphStyle('h2', fontSize=13, textColor=INK, fontName='Helvetica-Bold', alignment=TA_LEFT, leading=16)
    s_footer  = ParagraphStyle('footer', fontSize=7, textColor=MUTED, fontName='Helvetica', alignment=TA_CENTER, leading=9)

    hr = HRFlowable(width='100%', thickness=0.4, color=LINE, spaceAfter=3*mm)
    sp = Spacer(1, 3*mm)

    all_bookings = [b for blist in bookings_by_voyage.values() for b in blist]
    total_fare = sum(float(b.fare or 0) for b in all_bookings)
    total_collected = sum(float(b.advance_paid or 0) for b in all_bookings)
    total_outstanding = sum(float(b.balance_due or 0) for b in all_bookings)
    total_passengers = len(all_bookings)
    total_boarded = sum(1 for b in all_bookings if b.boarded_at)
    total_seats = sum(v.bus.total_seats for v in voyages)

    # Header
    header_tbl = Table([[
        Paragraph('SHRISAMARTH TRAVELS', s_brand),
        Paragraph(f'Printed {datetime.now().strftime("%d %b %Y · %H:%M")}', s_sub),
    ]], colWidths=[content_w * 0.65, content_w * 0.35])
    header_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    date_label = report_date.strftime('%d %B %Y')

    # Summary totals
    quarter = content_w / 4
    totals_tbl = Table([[
        Table([[Paragraph('VOYAGES', s_meta_l)], [Paragraph(str(len(voyages)), s_meta_v)]], colWidths=[quarter]),
        Table([[Paragraph('PASSENGERS', s_meta_l)], [Paragraph(f'{total_passengers} / {total_seats}', s_meta_v)]], colWidths=[quarter]),
        Table([[Paragraph('TOTAL REVENUE', s_meta_l)], [Paragraph(f'₹ {int(total_fare):,}', s_meta_v)]], colWidths=[quarter]),
        Table([[Paragraph('COLLECTED', s_meta_l)], [Paragraph(f'₹ {int(total_collected):,}', s_meta_v)]], colWidths=[quarter]),
    ]], colWidths=[quarter]*4)

    # Per-voyage summary table
    v_summary_data = [[
        Paragraph('ROUTE', s_th),
        Paragraph('DEP', s_th),
        Paragraph('BUS', s_th),
        Paragraph('PAX / SEATS', s_th),
        Paragraph('OCC%', s_th),
        Paragraph('REVENUE', s_th),
        Paragraph('COLLECTED', s_th),
        Paragraph('OUTSTANDING', s_th),
    ]]
    col_w_sum = [content_w*0.18, content_w*0.08, content_w*0.14, content_w*0.11, content_w*0.07,
                 content_w*0.16, content_w*0.13, content_w*0.13]
    for v in voyages:
        v_bkgs = bookings_by_voyage.get(v.id, [])
        v_pax = len(v_bkgs)
        v_seats = v.bus.total_seats
        v_occ = int(v_pax / v_seats * 100) if v_seats else 0
        v_fare = sum(float(b.fare or 0) for b in v_bkgs)
        v_coll = sum(float(b.advance_paid or 0) for b in v_bkgs)
        v_out  = sum(float(b.balance_due or 0) for b in v_bkgs)
        v_summary_data.append([
            Paragraph(f'{v.origin} → {v.destination}', s_td_bold),
            Paragraph(v.departure_at.strftime('%H:%M'), s_td),
            Paragraph(v.bus.registration, s_td),
            Paragraph(f'{v_pax} / {v_seats}', s_td),
            Paragraph(f'{v_occ}%', s_td),
            Paragraph(f'₹ {int(v_fare):,}', s_td_r),
            Paragraph(f'₹ {int(v_coll):,}', s_td_r),
            Paragraph(f'₹ {int(v_out):,}', s_td_r),
        ])
    v_summary_tbl = Table(v_summary_data, colWidths=col_w_sum, repeatRows=1)
    v_summary_tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, LINE),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, LINE),
        *[('BACKGROUND', (0,i), (-1,i), CREAM2) for i in range(2, len(v_summary_data), 2)],
    ]))

    story = [
        header_tbl, sp,
        Paragraph(f'Day Report — {date_label}', s_title), sp, hr,
        totals_tbl, sp, hr,
        Paragraph('Voyage Summary', s_h2), Spacer(1, 2*mm),
        v_summary_tbl,
    ]

    # Per-voyage passenger pages
    pax_col_widths = [12*mm, 42*mm, 10*mm, 26*mm, 26*mm, 18*mm, 18*mm, 18*mm, 16*mm]
    for v in voyages:
        v_bkgs = bookings_by_voyage.get(v.id, [])
        sorted_bkgs = sorted(v_bkgs, key=lambda b: (b.boarding_point or '', b.seat_id or ''))
        v_fare  = sum(float(b.fare or 0) for b in v_bkgs)
        v_coll  = sum(float(b.advance_paid or 0) for b in v_bkgs)
        v_out   = sum(float(b.balance_due or 0) for b in v_bkgs)
        driver_name = v.driver.full_name if v.driver_id else 'Unassigned'

        story.append(PageBreak())
        story.append(Paragraph(f'{v.origin} → {v.destination}', s_title))
        story.append(Paragraph(f'{v.departure_at.strftime("%d %B %Y · %H:%M")} · {v.bus.registration} · {driver_name}', s_sub))
        story.append(sp)

        pax_data = [[
            Paragraph('SEAT', s_th),
            Paragraph('PASSENGER', s_th),
            Paragraph('G', s_th),
            Paragraph('BOARDING', s_th),
            Paragraph('DROPPING', s_th),
            Paragraph('FARE', s_th),
            Paragraph('PAID', s_th),
            Paragraph('BALANCE', s_th),
            Paragraph('CHK', s_th),
        ]]
        for b in sorted_bkgs:
            fare = int(b.fare or 0)
            paid = int(b.advance_paid or 0)
            bal  = int(b.balance_due or 0)
            bal_p = ParagraphStyle('bal', parent=s_td_r, textColor=(RUBY if bal > 0 else SAGE))
            pax_data.append([
                Paragraph(str(b.seat_id), s_td_bold),
                Paragraph(b.passenger_name or '', s_td),
                Paragraph('♂' if (b.gender or 'M') == 'M' else '♀', s_td),
                Paragraph(b.boarding_point or '', s_td),
                Paragraph(b.dropping_point or '', s_td),
                Paragraph(f'₹{fare}', s_td_r),
                Paragraph(f'₹{paid}', s_td_r),
                Paragraph(f'₹{bal}' if bal > 0 else '✓', bal_p),
                Paragraph('✓' if b.boarded_at else '', s_td),
            ])

        pax_tbl = Table(pax_data, colWidths=pax_col_widths, repeatRows=1)
        pax_style = [
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('LINEBELOW', (0,0), (-1,0), 0.5, LINE),
            ('LINEBELOW', (0,-1), (-1,-1), 0.5, LINE),
        ]
        for i in range(1, len(pax_data)):
            if i % 2 == 0:
                pax_style.append(('BACKGROUND', (0,i), (-1,i), CREAM2))
        pax_tbl.setStyle(TableStyle(pax_style))

        story.append(pax_tbl)
        story.append(sp)

        # Summary row
        sum_tbl = Table([[
            Table([[Paragraph('TOTAL FARE', s_meta_l)], [Paragraph(f'₹ {int(v_fare):,}', s_meta_v)]], colWidths=[content_w/3]),
            Table([[Paragraph('COLLECTED', s_meta_l)], [Paragraph(f'₹ {int(v_coll):,}', s_meta_v)]], colWidths=[content_w/3]),
            Table([[Paragraph('OUTSTANDING', s_meta_l)], [Paragraph(f'₹ {int(v_out):,}', s_meta_v)]], colWidths=[content_w/3]),
        ]], colWidths=[content_w/3]*3)
        sum_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), CREAM2),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(sum_tbl)

    doc.build(story)
    buf.seek(0)
    return buf


# ============================================================
# CMS — HOMEPAGE CONTENT EDITOR
# ============================================================

@admin_bp.route('/cms')
def cms():
    import json as _json
    rows = SiteContent.query.all()
    content = {r.section_key: r for r in rows}
    faq_en, faq_hi = [], []
    faq_row = content.get('faq_items')
    if faq_row:
        try: faq_en = _json.loads(faq_row.content_en or '[]')
        except Exception: pass
        try: faq_hi = _json.loads(faq_row.content_hi or '[]')
        except Exception: pass
    return render_template('admin/cms.html', content=content, faq_en=faq_en, faq_hi=faq_hi)


@admin_bp.route('/cms/save', methods=['POST'])
def cms_save():
    data = request.get_json() or {}
    section_key = data.get('section_key', '').strip()
    content_en  = data.get('content_en', '')
    content_hi  = data.get('content_hi', '')

    if not section_key:
        return jsonify({'status': 'error', 'message': 'Missing section_key'}), 400

    row = SiteContent.query.filter_by(section_key=section_key).first()
    if row:
        row.content_en     = content_en
        row.content_hi     = content_hi
        row.updated_at     = datetime.utcnow()
        row.updated_by_id  = current_user.id
    else:
        row = SiteContent(
            section_key=section_key,
            content_en=content_en,
            content_hi=content_hi,
            updated_at=datetime.utcnow(),
            updated_by_id=current_user.id,
        )
        db.session.add(row)

    try:
        db.session.commit()
        log_activity('cms_edit', f'Updated homepage section: {section_key}',
                     target_type='site_content')
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ============================================================
# SECURITY & IP BAN MANAGEMENT
# ============================================================

@admin_bp.route('/security')
@login_required
def security():
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    active_bans = IpBan.query.filter(
        (IpBan.is_permanent == True) |
        (IpBan.expires_at > now)
    ).order_by(IpBan.banned_at.desc()).all()

    abuse_24h = AbuseLog.query.filter(AbuseLog.created_at >= day_ago).count()
    blocked_today = AbuseLog.query.filter(
        AbuseLog.created_at >= day_ago,
        AbuseLog.event_type.in_([
            'banned_ip_attempt', 'banned_ip_booking_attempt', 'honeypot_triggered',
            'rapid_booking_attempt', 'daily_limit_exceeded', 'phone_limit_exceeded',
            'seat_hoarding_attempt', 'cancel_rebook_abuse', 'suspicious_user_agent', 'velocity_too_fast',
        ]),
    ).count()

    banned_ips = [b.ip_address for b in active_bans]
    suspicious_q = (
        db.session.query(AbuseLog.ip_address, func.count(AbuseLog.id).label('cnt'))
        .filter(AbuseLog.ip_address.notin_(banned_ips) if banned_ips else db.text('1=1'))
        .group_by(AbuseLog.ip_address)
        .having(func.count(AbuseLog.id) >= 2)
        .order_by(func.count(AbuseLog.id).desc())
        .limit(10)
        .all()
    )
    suspicious_ips = []
    for row in suspicious_q:
        last_log = AbuseLog.query.filter_by(ip_address=row.ip_address).order_by(AbuseLog.created_at.desc()).first()
        types = list(set(
            r.event_type for r in AbuseLog.query.filter_by(ip_address=row.ip_address).limit(20).all()
        ))
        suspicious_ips.append({'ip': row.ip_address, 'count': row.cnt,
                                'last_seen': last_log.created_at if last_log else None,
                                'types': types})

    page = request.args.get('page', 1, type=int)
    event_filter = request.args.get('event', 'all')
    period_filter = request.args.get('period', '24h')
    period_map = {'24h': day_ago, '7d': now - timedelta(days=7), '30d': now - timedelta(days=30)}
    since = period_map.get(period_filter, day_ago)

    log_q = AbuseLog.query.filter(AbuseLog.created_at >= since)
    if event_filter != 'all':
        log_q = log_q.filter(AbuseLog.event_type == event_filter)
    abuse_logs = log_q.order_by(AbuseLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    all_event_types = [r[0] for r in db.session.query(AbuseLog.event_type).distinct().all()]

    return render_template('admin/security.html',
        active_bans=active_bans, abuse_24h=abuse_24h, blocked_today=blocked_today,
        suspicious_ips=suspicious_ips, abuse_logs=abuse_logs,
        all_event_types=all_event_types, event_filter=event_filter,
        period_filter=period_filter, now=now,
    )


@admin_bp.route('/security/ban', methods=['POST'])
@login_required
def security_ban_ip():
    ip = request.form.get('ip', '').strip()
    reason = request.form.get('reason', '').strip()
    duration = request.form.get('duration', '24')
    if not ip:
        flash('IP address is required.', 'error')
        return redirect(url_for('admin.security'))

    from app.abuse import auto_ban_ip
    if duration == 'permanent':
        auto_ban_ip(ip, permanent=True, reason=reason or 'Manually banned by admin')
    else:
        auto_ban_ip(ip, hours=int(duration), reason=reason or f'Manually banned by admin')

    ban = IpBan.query.filter_by(ip_address=ip).first()
    if ban:
        ban.banned_by_id = current_user.id
        db.session.commit()

    log_activity('ip_banned', f'Admin banned IP {ip}: {reason}', target_type='ip_ban')
    flash(f'IP {ip} has been banned.', 'success')
    return redirect(url_for('admin.security'))


@admin_bp.route('/security/unban/<int:ban_id>', methods=['POST'])
@login_required
def security_unban(ban_id):
    ban = IpBan.query.get_or_404(ban_id)
    ip = ban.ip_address
    db.session.delete(ban)
    db.session.commit()
    log_activity('ip_unbanned', f'Admin unbanned IP {ip}', target_type='ip_ban')
    flash(f'IP {ip} has been unbanned.', 'success')
    return redirect(url_for('admin.security'))


@admin_bp.route('/security/make-permanent/<int:ban_id>', methods=['POST'])
@login_required
def security_make_permanent(ban_id):
    ban = IpBan.query.get_or_404(ban_id)
    ban.is_permanent = True
    ban.expires_at = None
    db.session.commit()
    log_activity('ip_ban_made_permanent', f'Admin made IP {ban.ip_address} permanently banned')
    flash(f'IP {ban.ip_address} is now permanently banned.', 'success')
    return redirect(url_for('admin.security'))


@admin_bp.route('/security/bulk-unban', methods=['POST'])
@login_required
def security_bulk_unban():
    ban_ids = request.form.getlist('ban_ids[]')
    count = 0
    for bid in ban_ids:
        ban = IpBan.query.get(int(bid))
        if ban:
            db.session.delete(ban)
            count += 1
    db.session.commit()
    log_activity('ip_bulk_unbanned', f'Admin bulk unbanned {count} IP(s)')
    flash(f'Unbanned {count} IP(s).', 'success')
    return redirect(url_for('admin.security'))


@admin_bp.route('/security/abuse-log/csv')
@login_required
def security_abuse_log_csv():
    import csv
    import io as _io
    from flask import Response
    logs = AbuseLog.query.order_by(AbuseLog.created_at.desc()).limit(5000).all()
    output = _io.StringIO()
    w = csv.writer(output)
    w.writerow(['id', 'ip_address', 'event_type', 'user_id', 'details', 'created_at'])
    for entry in logs:
        w.writerow([entry.id, entry.ip_address, entry.event_type,
                    entry.user_id, entry.details, entry.created_at])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=abuse_log.csv'})


# ============================================================
# NEWSLETTER
# ============================================================

def _newsletter_recipients():
    """Return list of eligible newsletter recipients."""
    return User.query.filter(
        User.role == 'customer',
        User.email_verified == True,
        User.is_active_account == True,
        User.newsletter_unsubscribed == False,
        User.email != None,
    ).all()


def _ensure_unsubscribe_token(user):
    """Generate an unsubscribe token for a user if they don't have one."""
    import secrets as _sec
    if not user.unsubscribe_token:
        user.unsubscribe_token = _sec.token_urlsafe(32)


@admin_bp.route('/newsletter')
@login_required
def newsletter():
    recipients = _newsletter_recipients()
    history = Newsletter.query.order_by(Newsletter.created_at.desc()).all()
    draft = request.args.get('draft', type=int)
    edit_nl = Newsletter.query.get(draft) if draft else None
    return render_template('admin/newsletter.html',
                           recipient_count=len(recipients),
                           history=history,
                           edit_nl=edit_nl)


@admin_bp.route('/newsletter/preview-email', methods=['POST'])
@login_required
def newsletter_preview():
    data = request.get_json() or {}
    theme = data.get('theme', 'classic')
    content_en = data.get('content_en', '')
    content_hi = data.get('content_hi', '')
    lang = data.get('lang', 'en')
    from flask import current_app
    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    html = render_template(
        f'email/newsletter_{theme}.html',
        content_en=content_en,
        content_hi=content_hi,
        lang=lang,
        user_name='Preview User',
        unsubscribe_url='#',
        domain=domain,
    )
    return jsonify({'html': html})


@admin_bp.route('/newsletter/save-draft', methods=['POST'])
@login_required
def newsletter_save_draft():
    nl_id = request.form.get('newsletter_id', type=int)
    nl = Newsletter.query.get(nl_id) if nl_id else Newsletter()
    nl.subject_en = request.form.get('subject_en', '').strip() or None
    nl.subject_hi = request.form.get('subject_hi', '').strip() or None
    nl.content_en = request.form.get('content_en', '').strip() or None
    nl.content_hi = request.form.get('content_hi', '').strip() or None
    nl.theme = request.form.get('theme', 'classic')
    nl.status = 'draft'
    if not nl_id:
        db.session.add(nl)
    db.session.commit()
    flash('Draft saved.', 'success')
    return redirect(url_for('admin.newsletter', draft=nl.id))


@admin_bp.route('/newsletter/send', methods=['POST'])
@login_required
def newsletter_send():
    import time as _time
    from flask import current_app
    from app.email import send_email

    nl_id = request.form.get('newsletter_id', type=int)
    nl = Newsletter.query.get(nl_id) if nl_id else Newsletter()
    nl.subject_en = request.form.get('subject_en', '').strip() or None
    nl.subject_hi = request.form.get('subject_hi', '').strip() or None
    nl.content_en = request.form.get('content_en', '').strip() or None
    nl.content_hi = request.form.get('content_hi', '').strip() or None
    nl.theme = request.form.get('theme', 'classic')

    # Validate: need at least one language pair
    has_en = bool(nl.subject_en and nl.content_en)
    has_hi = bool(nl.subject_hi and nl.content_hi)
    if not has_en and not has_hi:
        flash('Please fill in at least one language (subject + content).', 'error')
        return redirect(url_for('admin.newsletter'))

    if not nl_id:
        db.session.add(nl)
        db.session.flush()

    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    recipients = _newsletter_recipients()

    # Ensure all recipients have unsubscribe tokens
    for user in recipients:
        _ensure_unsubscribe_token(user)
    db.session.commit()

    # Determine subject
    if has_en and has_hi:
        subject = f"{nl.subject_en} / {nl.subject_hi}"
        lang = 'both'
    elif has_en:
        subject = nl.subject_en
        lang = 'en'
    else:
        subject = nl.subject_hi
        lang = 'hi'

    sent_count = 0
    batch_size = 50
    for i, user in enumerate(recipients):
        unsubscribe_url = f"{domain}/unsubscribe/{user.unsubscribe_token}"
        try:
            html = render_template(
                f'email/newsletter_{nl.theme}.html',
                content_en=nl.content_en or '',
                content_hi=nl.content_hi or '',
                lang=lang,
                user_name=user.full_name,
                unsubscribe_url=unsubscribe_url,
                domain=domain,
            )
            ok = send_email(user.email, subject, html)
            if ok:
                sent_count += 1
        except Exception:
            pass
        # Small delay between batches
        if (i + 1) % batch_size == 0:
            _time.sleep(0.5)

    nl.status = 'sent'
    nl.sent_at = datetime.utcnow()
    nl.sent_by_id = current_user.id
    nl.recipient_count = sent_count
    db.session.commit()

    log_activity('newsletter_sent',
                 f'Newsletter "{subject[:80]}" sent to {sent_count} customers',
                 'newsletter', nl.id)
    flash(f'Newsletter sent to {sent_count} customers ✓', 'success')
    return redirect(url_for('admin.newsletter'))


@admin_bp.route('/newsletter/<int:nl_id>/delete', methods=['POST'])
@login_required
def newsletter_delete(nl_id):
    nl = Newsletter.query.get_or_404(nl_id)
    if nl.status == 'sent':
        flash('Cannot delete a sent newsletter.', 'error')
        return redirect(url_for('admin.newsletter'))
    db.session.delete(nl)
    db.session.commit()
    flash('Draft deleted.', 'success')
    return redirect(url_for('admin.newsletter'))


@admin_bp.route('/newsletter/<int:nl_id>/duplicate', methods=['POST'])
@login_required
def newsletter_duplicate(nl_id):
    src = Newsletter.query.get_or_404(nl_id)
    copy = Newsletter(
        subject_en=src.subject_en,
        subject_hi=src.subject_hi,
        content_en=src.content_en,
        content_hi=src.content_hi,
        theme=src.theme,
        status='draft',
    )
    db.session.add(copy)
    db.session.commit()
    flash('Duplicated as new draft.', 'success')
    return redirect(url_for('admin.newsletter', draft=copy.id))


# ============================================================
# FINANCIAL TRACKER
# ============================================================

import csv
import io as _io
from datetime import date as _date
from calendar import month_abbr

_ALL_CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES


def _date_range(period, custom_start=None, custom_end=None):
    today = _date.today()
    if period == 'today':
        return today, today
    if period == 'week':
        return today - timedelta(days=today.weekday()), today
    if period == 'year':
        return today.replace(month=1, day=1), today
    if period == 'custom' and custom_start and custom_end:
        return custom_start, custom_end
    # default: this month
    return today.replace(day=1), today


def _ticket_sales_by_date(date_start, date_end, type_filter, category_filter, search):
    """Synthetic read-only ticket-sales rows derived from bookings."""
    if type_filter == 'expense':
        return []
    if category_filter and category_filter != 'Ticket Sales':
        return []
    q = (db.session.query(
            func.date(Booking.created_at).label('entry_date'),
            func.sum(Booking.advance_paid).label('total'),
            func.count(Booking.id).label('cnt'),
         )
         .filter(Booking.status == 'confirmed', Booking.advance_paid > 0)
         .filter(func.date(Booking.created_at) >= date_start)
         .filter(func.date(Booking.created_at) <= date_end)
         .group_by(func.date(Booking.created_at))
         .all())
    entries = []
    for r in q:
        if float(r.total or 0) <= 0:
            continue
        desc = f'{r.cnt} booking(s)'
        if search and search.lower() not in desc.lower() and 'ticket' not in search.lower():
            continue
        entries.append({
            'id': None, 'entry_type': 'income', 'category': 'Ticket Sales',
            'amount': float(r.total), 'description': desc,
            'entry_date': r.entry_date, 'created_by': None, 'is_auto': True,
        })
    return entries


def _this_month_summary():
    today = _date.today()
    ms = today.replace(day=1)
    # last month
    if ms.month == 1:
        lms = ms.replace(year=ms.year - 1, month=12)
    else:
        lms = ms.replace(month=ms.month - 1)
    lme = ms - timedelta(days=1)

    def _month_income(start, end):
        return float(db.session.query(func.coalesce(func.sum(FinancialEntry.amount), 0))
                     .filter(FinancialEntry.entry_type == 'income',
                             FinancialEntry.entry_date >= start,
                             FinancialEntry.entry_date <= end).scalar() or 0)

    def _month_expense(start, end):
        return float(db.session.query(func.coalesce(func.sum(FinancialEntry.amount), 0))
                     .filter(FinancialEntry.entry_type == 'expense',
                             FinancialEntry.entry_date >= start,
                             FinancialEntry.entry_date <= end).scalar() or 0)

    def _month_tickets(start, end):
        r = (db.session.query(
                func.coalesce(func.sum(Booking.advance_paid), 0).label('total'),
                func.count(Booking.id).label('cnt'))
             .filter(Booking.status == 'confirmed', Booking.advance_paid > 0,
                     func.date(Booking.created_at) >= start,
                     func.date(Booking.created_at) <= end)
             .first())
        return float(r.total or 0), int(r.cnt or 0)

    cur_income = _month_income(ms, today)
    cur_expense = _month_expense(ms, today)
    cur_tickets, cur_ticket_count = _month_tickets(ms, today)
    last_income = _month_income(lms, lme)
    last_expense = _month_expense(lms, lme)
    last_tickets, _ = _month_tickets(lms, lme)

    def _pct_change(cur, prev):
        if prev == 0:
            return None
        return round((cur - prev) / prev * 100)

    return {
        'income': cur_income,
        'expense': cur_expense,
        'tickets': cur_tickets,
        'ticket_count': cur_ticket_count,
        'balance': cur_income + cur_tickets - cur_expense,
        'income_pct': _pct_change(cur_income, last_income),
        'expense_pct': _pct_change(cur_expense, last_expense),
        'tickets_pct': _pct_change(cur_tickets, last_tickets),
    }


def _monthly_breakdown(n_months=6):
    today = _date.today()
    rows = []
    for i in range(n_months):
        if today.month - i < 1:
            yr = today.year - 1
            mo = 12 + (today.month - i)
        else:
            yr = today.year
            mo = today.month - i
        ms = _date(yr, mo, 1)
        import calendar
        last_day = calendar.monthrange(yr, mo)[1]
        me = _date(yr, mo, last_day)

        # Manual income by category
        inc_cats = (db.session.query(FinancialEntry.category,
                                     func.sum(FinancialEntry.amount).label('total'))
                    .filter(FinancialEntry.entry_type == 'income',
                            FinancialEntry.entry_date >= ms,
                            FinancialEntry.entry_date <= me)
                    .group_by(FinancialEntry.category).all())
        # Ticket sales
        ts = float(db.session.query(func.coalesce(func.sum(Booking.advance_paid), 0))
                   .filter(Booking.status == 'confirmed', Booking.advance_paid > 0,
                           func.date(Booking.created_at) >= ms,
                           func.date(Booking.created_at) <= me).scalar() or 0)

        # Expense by category
        exp_cats = (db.session.query(FinancialEntry.category,
                                     func.sum(FinancialEntry.amount).label('total'))
                    .filter(FinancialEntry.entry_type == 'expense',
                            FinancialEntry.entry_date >= ms,
                            FinancialEntry.entry_date <= me)
                    .group_by(FinancialEntry.category).all())

        inc_total = sum(float(c.total) for c in inc_cats) + ts
        exp_total = sum(float(c.total) for c in exp_cats)

        income_breakdown = [{'category': 'Ticket Sales', 'amount': ts, 'is_auto': True}] if ts > 0 else []
        income_breakdown += [{'category': c.category, 'amount': float(c.total), 'is_auto': False}
                              for c in inc_cats]
        expense_breakdown = [{'category': c.category, 'amount': float(c.total)}
                              for c in sorted(exp_cats, key=lambda x: -float(x.total))]

        rows.append({
            'label': f'{ms.strftime("%B")} {yr}',
            'month_key': f'{yr}-{mo:02d}',
            'income': inc_total,
            'expense': exp_total,
            'net': inc_total - exp_total,
            'income_breakdown': income_breakdown,
            'expense_breakdown': expense_breakdown,
            'exp_max': max((float(c.total) for c in exp_cats), default=1),
        })
    return rows


@admin_bp.route('/finances', methods=['GET', 'POST'])
def finances():
    today = _date.today()

    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            entry_type = request.form.get('entry_type', 'expense')
            category = request.form.get('category', '').strip()
            try:
                amount = float(request.form.get('amount', 0))
            except ValueError:
                flash('Invalid amount.', 'error')
                return redirect(url_for('admin.finances'))
            if amount <= 0:
                flash('Amount must be positive.', 'error')
                return redirect(url_for('admin.finances'))
            description = request.form.get('description', '').strip() or None
            try:
                entry_date = _date.fromisoformat(request.form.get('entry_date', str(today)))
            except ValueError:
                entry_date = today
            entry = FinancialEntry(
                entry_type=entry_type,
                category=category,
                amount=amount,
                description=description,
                entry_date=entry_date,
                created_by_id=current_user.id,
            )
            db.session.add(entry)
            db.session.commit()
            log_activity('finance_add', f'Added {entry_type} entry: {category} ₹{amount:.0f}')
            flash('Entry added.', 'success')
        return redirect(url_for('admin.finances',
                                period=request.args.get('period', 'month'),
                                category=request.args.get('category', ''),
                                type=request.args.get('type', ''),
                                q=request.args.get('q', '')))

    period = request.args.get('period', 'month')
    category_filter = request.args.get('category', '')
    type_filter = request.args.get('type', '')
    search = request.args.get('q', '').strip()
    custom_start_raw = request.args.get('date_start', '')
    custom_end_raw = request.args.get('date_end', '')
    custom_start = _date.fromisoformat(custom_start_raw) if custom_start_raw else None
    custom_end = _date.fromisoformat(custom_end_raw) if custom_end_raw else None
    page = max(1, int(request.args.get('page', 1)))
    per_page = 25

    date_start, date_end = _date_range(period, custom_start, custom_end)

    # Manual entries
    q = FinancialEntry.query.filter(
        FinancialEntry.entry_date >= date_start,
        FinancialEntry.entry_date <= date_end,
    )
    if category_filter and category_filter != 'Ticket Sales':
        q = q.filter(FinancialEntry.category == category_filter)
    if type_filter:
        q = q.filter(FinancialEntry.entry_type == type_filter)
    if search:
        q = q.filter(FinancialEntry.description.ilike(f'%{search}%'))
    manual = q.order_by(FinancialEntry.entry_date.desc(), FinancialEntry.created_at.desc()).all()

    manual_dicts = [{
        'id': e.id, 'entry_type': e.entry_type, 'category': e.category,
        'amount': float(e.amount), 'description': e.description,
        'entry_date': e.entry_date,
        'created_by': e.created_by.full_name if e.created_by else '—',
        'is_auto': False,
    } for e in manual]

    # Synthetic ticket sales (if not filtering to exclude income/other category)
    auto = _ticket_sales_by_date(date_start, date_end, type_filter, category_filter, search)

    # Merge and sort
    all_entries = sorted(manual_dicts + auto, key=lambda e: e['entry_date'], reverse=True)

    total_pages = max(1, (len(all_entries) + per_page - 1) // per_page)
    page = min(page, total_pages)
    paginated = all_entries[(page - 1) * per_page: page * per_page]

    summary = _this_month_summary()
    monthly = _monthly_breakdown(6)

    all_category_options = ['Ticket Sales'] + INCOME_CATEGORIES + EXPENSE_CATEGORIES

    return render_template('admin/finances.html',
        entries=paginated,
        page=page,
        total_pages=total_pages,
        total_entries=len(all_entries),
        summary=summary,
        monthly=monthly,
        period=period,
        category_filter=category_filter,
        type_filter=type_filter,
        search=search,
        custom_start=custom_start_raw,
        custom_end=custom_end_raw,
        date_start=date_start,
        date_end=date_end,
        today=today,
        expense_categories=EXPENSE_CATEGORIES,
        income_categories=INCOME_CATEGORIES,
        all_category_options=all_category_options,
    )


@admin_bp.route('/finances/<int:entry_id>/edit', methods=['POST'])
def finances_edit(entry_id):
    entry = FinancialEntry.query.get_or_404(entry_id)
    data = request.get_json() or {}
    try:
        amount = float(data.get('amount', entry.amount))
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid amount'}), 400
    if amount <= 0:
        return jsonify({'status': 'error', 'message': 'Amount must be positive'}), 400
    entry.amount = amount
    entry.category = data.get('category', entry.category)
    entry.description = data.get('description', entry.description) or None
    raw_date = data.get('entry_date', '')
    if raw_date:
        try:
            entry.entry_date = _date.fromisoformat(raw_date)
        except ValueError:
            pass
    db.session.commit()
    log_activity('finance_edit', f'Edited entry #{entry_id}: {entry.category} ₹{float(entry.amount):.0f}')
    return jsonify({'status': 'ok', 'amount': float(entry.amount),
                    'category': entry.category, 'description': entry.description or ''})


@admin_bp.route('/finances/<int:entry_id>/delete', methods=['POST'])
def finances_delete(entry_id):
    entry = FinancialEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    log_activity('finance_delete', f'Deleted entry #{entry_id}: {entry.category} ₹{float(entry.amount):.0f}')
    return jsonify({'status': 'ok'})


@admin_bp.route('/finances/export')
def finances_export():
    period = request.args.get('period', 'month')
    category_filter = request.args.get('category', '')
    type_filter = request.args.get('type', '')
    search = request.args.get('q', '').strip()
    custom_start_raw = request.args.get('date_start', '')
    custom_end_raw = request.args.get('date_end', '')
    custom_start = _date.fromisoformat(custom_start_raw) if custom_start_raw else None
    custom_end = _date.fromisoformat(custom_end_raw) if custom_end_raw else None

    date_start, date_end = _date_range(period, custom_start, custom_end)

    q = FinancialEntry.query.filter(
        FinancialEntry.entry_date >= date_start,
        FinancialEntry.entry_date <= date_end,
    )
    if category_filter and category_filter != 'Ticket Sales':
        q = q.filter(FinancialEntry.category == category_filter)
    if type_filter:
        q = q.filter(FinancialEntry.entry_type == type_filter)
    if search:
        q = q.filter(FinancialEntry.description.ilike(f'%{search}%'))
    manual = q.order_by(FinancialEntry.entry_date.desc()).all()

    manual_dicts = [{
        'entry_date': e.entry_date, 'entry_type': e.entry_type, 'category': e.category,
        'description': e.description or '', 'amount': float(e.amount), 'is_auto': False,
    } for e in manual]
    auto = _ticket_sales_by_date(date_start, date_end, type_filter, category_filter, search)
    all_rows = sorted(manual_dicts + auto, key=lambda e: e['entry_date'], reverse=True)

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Type', 'Category', 'Description', 'Amount'])
    for r in all_rows:
        writer.writerow([
            r['entry_date'].strftime('%Y-%m-%d') if hasattr(r['entry_date'], 'strftime') else str(r['entry_date']),
            r['entry_type'].capitalize(),
            r['category'],
            r['description'],
            f"{r['amount']:.2f}",
        ])

    filename = f"shrisamarth_finances_{date_start.strftime('%b%Y').lower()}.csv"
    return send_file(
        _io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )
