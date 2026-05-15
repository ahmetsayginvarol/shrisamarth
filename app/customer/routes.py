from datetime import date, datetime
from flask import Blueprint, render_template, request
from sqlalchemy import func

from app.models import Voyage

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


@customer_bp.route('/')
def home():
    origins, destinations = _get_cities()
    return render_template('customer/home.html',
                           origins=origins,
                           destinations=destinations,
                           today=date.today().strftime('%Y-%m-%d'))


@customer_bp.route('/search')
def search():
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


@customer_bp.route('/book/<int:voyage_id>')
def book(voyage_id):
    # Step 3 — seat selection (coming soon)
    from flask import abort
    abort(404)
