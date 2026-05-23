import re
from datetime import datetime, timedelta

from flask import request

from app.extensions import db


_BAD_UA_PATTERNS = ['python-requests', 'curl/', 'wget/', 'scrapy', 'bot', 'crawler', 'spider']


def get_client_ip():
    """Extract real client IP, accounting for Render's reverse proxy."""
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        ip = xff.split(',')[0].strip()
        if re.match(r'^(\d{1,3}\.){3}\d{1,3}$|^[0-9a-fA-F:]{3,39}$', ip):
            return ip
    return request.remote_addr or '0.0.0.0'


def is_ip_banned(ip):
    """Return (True, reason) if banned, (False, None) otherwise. Auto-removes expired bans."""
    from app.models import IpBan
    ban = IpBan.query.filter_by(ip_address=ip).first()
    if not ban:
        return False, None
    if ban.is_permanent:
        return True, ban.reason
    if ban.expires_at and datetime.utcnow() < ban.expires_at:
        return True, ban.reason
    # Expired — remove silently
    try:
        db.session.delete(ban)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return False, None


def auto_ban_ip(ip, hours=None, reason='Automated ban', permanent=False):
    """Create or extend an IP ban."""
    from app.models import IpBan
    ban = IpBan.query.filter_by(ip_address=ip).first()
    if ban:
        if permanent:
            ban.is_permanent = True
        if hours and not permanent:
            new_expiry = datetime.utcnow() + timedelta(hours=hours)
            if ban.expires_at is None or new_expiry > ban.expires_at:
                ban.expires_at = new_expiry
        ban.reason = reason
    else:
        ban = IpBan(
            ip_address=ip,
            reason=reason,
            is_permanent=permanent,
            expires_at=datetime.utcnow() + timedelta(hours=hours) if hours and not permanent else None,
        )
        db.session.add(ban)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def log_abuse_event(ip, event_type, user_id=None, details=None):
    """Log an abuse event and trigger auto-ban threshold checks."""
    from app.models import AbuseLog
    log = AbuseLog(ip_address=ip, user_id=user_id, event_type=event_type, details=details)
    db.session.add(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return
    _check_auto_ban_thresholds(ip)


def _check_auto_ban_thresholds(ip):
    from app.models import AbuseLog
    # Don't re-ban if already banned
    banned, _ = is_ip_banned(ip)
    if banned:
        return

    now = datetime.utcnow()
    events_1h = AbuseLog.query.filter(
        AbuseLog.ip_address == ip,
        AbuseLog.created_at >= now - timedelta(hours=1),
    ).count()
    events_24h = AbuseLog.query.filter(
        AbuseLog.ip_address == ip,
        AbuseLog.created_at >= now - timedelta(hours=24),
    ).count()
    total = AbuseLog.query.filter_by(ip_address=ip).count()

    if total >= 10:
        auto_ban_ip(ip, permanent=True, reason='10+ cumulative abuse events — permanent ban')
    elif events_24h >= 5:
        auto_ban_ip(ip, hours=24, reason='5+ abuse events in 24 hours')
    elif events_1h >= 3:
        auto_ban_ip(ip, hours=2, reason='3+ abuse events in 1 hour')


def check_booking_abuse(ip, user_id=None, phone=None, voyage_id=None):
    """
    Run all abuse detection rules.
    Returns (allowed: bool, reason: str, severity: str)
    severity values: 'ok', 'ban', 'block', 'rate_limit', 'captcha_required'
    """
    from app.models import AbuseLog, Booking

    now = datetime.utcnow()

    # Rule 1 — IP ban
    banned, ban_reason = is_ip_banned(ip)
    if banned:
        log_abuse_event(ip, 'banned_ip_attempt', user_id, details=ban_reason)
        return False, ban_reason or 'Access blocked.', 'ban'

    # Rule 7 — User agent
    ua = request.headers.get('User-Agent', '')
    if not ua:
        log_abuse_event(ip, 'suspicious_user_agent', user_id, 'Empty user agent')
        auto_ban_ip(ip, hours=24, reason='No user agent — likely automated')
        return False, 'Automated access is not allowed.', 'ban'
    ua_lower = ua.lower()
    for pattern in _BAD_UA_PATTERNS:
        if pattern in ua_lower:
            log_abuse_event(ip, 'suspicious_user_agent', user_id, f'UA: {ua[:100]}')
            auto_ban_ip(ip, hours=24, reason=f'Suspicious user agent: {ua[:80]}')
            return False, 'Automated access is not allowed.', 'ban'

    # Rule 2 — Rapid booking rate (5 min window)
    five_min_ago = now - timedelta(minutes=5)
    rapid_count = AbuseLog.query.filter(
        AbuseLog.ip_address == ip,
        AbuseLog.event_type == 'booking_created',
        AbuseLog.created_at >= five_min_ago,
    ).count()
    if rapid_count >= 5:
        log_abuse_event(ip, 'rapid_booking_attempt', user_id, f'{rapid_count} bookings in 5 min')
        auto_ban_ip(ip, hours=1, reason='Rapid booking: 5+ bookings in 5 minutes')
        return False, 'Too many booking attempts. Please try again later.', 'rate_limit'
    if rapid_count >= 3:
        log_abuse_event(ip, 'rapid_booking_attempt', user_id, f'{rapid_count} bookings in 5 min')
        return False, 'Please complete the security check to continue.', 'captcha_required'

    # Rule 3 — Daily IP limit
    day_ago = now - timedelta(hours=24)
    daily_count = AbuseLog.query.filter(
        AbuseLog.ip_address == ip,
        AbuseLog.event_type == 'booking_created',
        AbuseLog.created_at >= day_ago,
    ).count()
    if daily_count >= 15:
        log_abuse_event(ip, 'daily_limit_exceeded', user_id, f'{daily_count} bookings today')
        auto_ban_ip(ip, hours=24, reason='Daily booking limit: 15+ bookings in 24 hours')
        return False, 'Daily booking limit reached. Please try again tomorrow.', 'rate_limit'

    # Rule 4 — Phone number abuse
    if phone:
        phone_count = Booking.query.filter(
            Booking.passenger_phone == phone,
            Booking.status == 'confirmed',
            Booking.created_at >= day_ago,
        ).count()
        if phone_count >= 10:
            log_abuse_event(ip, 'phone_limit_exceeded', user_id,
                            f'Phone {phone[:6]}***: {phone_count} bookings in 24h')
            return False, 'This phone number has reached the daily booking limit.', 'block'

    # Rule 5 — Seat hoarding on same voyage
    if voyage_id:
        ip_voyage_count = AbuseLog.query.filter(
            AbuseLog.ip_address == ip,
            AbuseLog.event_type == 'booking_created',
            AbuseLog.details.contains(f'voyage:{voyage_id}'),
        ).count()
        phone_voyage_count = 0
        if phone:
            phone_voyage_count = Booking.query.filter(
                Booking.passenger_phone == phone,
                Booking.voyage_id == voyage_id,
                Booking.status == 'confirmed',
            ).count()
        if max(ip_voyage_count, phone_voyage_count) >= 6:
            log_abuse_event(ip, 'seat_hoarding_attempt', user_id,
                            f'voyage:{voyage_id} ip:{ip_voyage_count} phone:{phone_voyage_count}')
            return False, 'Maximum 6 seats per voyage. Use group booking for larger parties.', 'block'

    # Rule 6 — Cancel-rebook abuse
    two_hours_ago = now - timedelta(hours=2)
    cancel_count = AbuseLog.query.filter(
        AbuseLog.ip_address == ip,
        AbuseLog.event_type == 'booking_cancelled',
        AbuseLog.created_at >= two_hours_ago,
    ).count()
    if cancel_count >= 4:
        log_abuse_event(ip, 'cancel_rebook_abuse', user_id,
                        f'{cancel_count} cancellations in 2 hours')
        auto_ban_ip(ip, hours=6, reason='Cancel-rebook abuse: 4+ cancellations in 2 hours')
        return False, 'Your access has been temporarily restricted.', 'ban'

    # Rule 9 — Velocity check (set by route layer before calling this)
    # handled in route, not here, because session is request-scoped

    return True, '', 'ok'
