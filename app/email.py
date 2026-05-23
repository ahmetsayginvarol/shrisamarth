import logging
from flask import current_app, render_template

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Falls back to console log if API key is missing."""
    api_key = current_app.config.get('RESEND_API_KEY')
    if not api_key:
        logger.warning('[EMAIL - no RESEND_API_KEY] To: %s | Subject: %s', to, subject)
        print(f'\n--- EMAIL (console fallback) ---\nTo: {to}\nSubject: {subject}\n{html}\n---\n')
        return True

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            'from': 'SHRISAMARTH <no-reply@shrisamarth.in>',
            'to': [to],
            'subject': subject,
            'html': html,
        })
        return True
    except Exception as exc:
        logger.error('Failed to send email to %s: %s', to, exc)
        return False


def send_eticket(booking, voyage) -> bool:
    """Render and send an e-ticket email for a confirmed booking.

    Returns True if sent (or queued), False if no email address or send failed.
    Never raises — safe to call fire-and-forget.
    """
    to = booking.passenger_email
    if not to:
        return False
    try:
        domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
        fare = f"{float(booking.fare):,.0f}" if booking.fare else '0'
        balance = f"{float(booking.balance_due):,.0f}" if booking.balance_due else '0'
        html = render_template(
            'email/eticket.html',
            passenger_name=booking.passenger_name,
            booking_code=booking.booking_code,
            origin=voyage.origin,
            destination=voyage.destination,
            departure_date=voyage.departure_at.strftime('%A, %d %B %Y'),
            departure_time=voyage.departure_at.strftime('%I:%M %p'),
            seat_id=booking.seat_id,
            phone=booking.passenger_phone,
            boarding_point=booking.boarding_point or '',
            dropping_point=booking.dropping_point or '',
            fare=fare,
            balance_due=balance,
            is_group=bool(booking.group_booking_code),
            group_booking_code=booking.group_booking_code,
            domain=domain,
        )
        subject = (
            f"Your ticket — {voyage.origin} → {voyage.destination} "
            f"on {voyage.departure_at.strftime('%d %b %Y')} | {booking.booking_code}"
        )
        return send_email(to, subject, html)
    except Exception as exc:
        logger.error('send_eticket failed for booking %s: %s', booking.booking_code, exc)
        return False

