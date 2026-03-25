"""One-time seed script. Run with: python seed.py"""
from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.models import User, Bus, Voyage, Booking

app = create_app()

with app.app_context():
    # Wipe existing (dev only!)
    db.drop_all()
    db.create_all()

    # Users — one of each role
    admin = User(username='admin', full_name='Ahmet Saygin Varol', role='admin', email='admin@shrisamarth.com')
    admin.set_password('admin123')

    res = User(username='reservation', full_name='Priya Reservation', role='reservation')
    res.set_password('res123')

    drv = User(username='driver', full_name='R. Deshmukh', role='driver')
    drv.set_password('drv123')

    db.session.add_all([admin, res, drv])
    db.session.commit()

    # Bus
    bus = Bus(registration='MH-12-DK-4721', layout_name='shrisamarth_49', total_seats=49)
    db.session.add(bus)
    db.session.commit()

    # Voyage tomorrow at 21:30
    tomorrow = (datetime.utcnow() + timedelta(days=1)).replace(hour=21, minute=30, second=0, microsecond=0)
    voyage = Voyage(bus_id=bus.id, origin='Mumbai', destination='Pune',
                    departure_at=tomorrow, base_fare=800, driver_id=drv.id)
    db.session.add(voyage)
    db.session.commit()

    # A few bookings
    sample = [
        ('8',  'Anjali Joshi',    '+91 93720 88910', 'F', 'Dadar',    'Shivajinagar', 400, 400),
        ('A',  'Rajesh Sharma',   '+91 98200 11234', 'M', 'Andheri',  'Swargate',     400, 400),
        ('1',  'Amit Kumar',      '+91 97600 22345', 'M', 'Thane',    'Katraj',       400, 400),
        ('2',  'Neha Kumar',      '+91 97600 22345', 'F', 'Thane',    'Katraj',       400, 400),
        ('17', 'Meena Bhosale',   '+91 98888 65432', 'F', 'Dadar',    'Shivajinagar', 800, 0),
    ]
    for seat, name, phone, gender, board, drop, adv, bal in sample:
        b = Booking(voyage_id=voyage.id, seat_id=seat, passenger_name=name,
                    passenger_phone=phone, gender=gender, boarding_point=board,
                    dropping_point=drop, fare=800, advance_paid=adv, balance_due=bal,
                    booking_code=f'SHRI-{tomorrow.strftime("%Y%m%d")}-{seat}',
                    created_by_id=res.id)
        db.session.add(b)
    db.session.commit()

    print("✓ Seeded successfully.")
    print("  admin / admin123")
    print("  reservation / res123")
    print("  driver / drv123")