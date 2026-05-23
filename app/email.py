import logging
from flask import current_app

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
