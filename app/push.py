"""Web Push notification helpers using VAPID + pywebpush."""
import json
import base64
import threading

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def _generate_vapid_keys():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).rstrip(b'=').decode()
    return private_pem, public_b64


def get_vapid_keys():
    """Return (private_pem, public_b64), generating and persisting on first call."""
    from app.models import AppSetting
    from app.extensions import db

    priv_row = AppSetting.query.get('vapid_private_key')
    pub_row = AppSetting.query.get('vapid_public_key')

    if priv_row and pub_row:
        return priv_row.value, pub_row.value

    private_pem, public_b64 = _generate_vapid_keys()

    if not priv_row:
        db.session.add(AppSetting(key='vapid_private_key', value=private_pem))
    else:
        priv_row.value = private_pem
    if not pub_row:
        db.session.add(AppSetting(key='vapid_public_key', value=public_b64))
    else:
        pub_row.value = public_b64
    db.session.commit()

    return private_pem, public_b64


def _do_send(app, title, body, url, user_ids):
    try:
        from pywebpush import webpush, WebPushException
        from app.models import PushSubscription
        from app.extensions import db

        with app.app_context():
            private_pem, _ = get_vapid_keys()
            domain = app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
            subject = 'mailto:admin@' + domain.replace('https://', '').replace('http://', '')
            payload = json.dumps({'title': title, 'body': body, 'url': url or '/admin'})

            q = PushSubscription.query
            if user_ids is not None:
                q = q.filter(PushSubscription.user_id.in_(user_ids))
            subs = q.all()

            expired = []
            for sub in subs:
                try:
                    webpush(
                        subscription_info={
                            'endpoint': sub.endpoint,
                            'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                        },
                        data=payload,
                        vapid_private_key=private_pem,
                        vapid_claims={'sub': subject},
                    )
                except WebPushException as e:
                    if e.response and e.response.status_code in (404, 410):
                        expired.append(sub)
                except Exception:
                    pass

            for sub in expired:
                db.session.delete(sub)
            if expired:
                db.session.commit()
    except Exception:
        pass  # Never let push failures affect the main request


def send_push_to_admins(app, title, body, url=None, user_ids=None):
    """Fire-and-forget: send urgent web push on a background thread.

    user_ids: list of user IDs to target. None = all subscribed admins.
    """
    t = threading.Thread(target=_do_send, args=(app, title, body, url, user_ids), daemon=True)
    t.start()
