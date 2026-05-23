# SHRISAMARTH — Project Notes

## Rules
- Push to **main** only. No feature branches. No pull requests.

## Production
- Hosted on **Render.com**
- Domain: **https://shrisamarth.in**
- Database: PostgreSQL (managed by Render)

## Environment Variables (Render Dashboard → Environment)

| Variable | Value | Notes |
|---|---|---|
| `SECRET_KEY` | (random secret) | Required |
| `DATABASE_URL` | (Render PostgreSQL URL) | Set automatically by Render |
| `APP_DOMAIN` | `https://shrisamarth.in` | Used in QR codes and share links |

**Important:** Set `APP_DOMAIN=https://shrisamarth.in` in the Render dashboard under
Environment Variables. Without it, QR codes on PDF tickets will fall back to
`https://shrisamarth.in` (the default), but setting it explicitly is best practice.

## Local Development

Copy `.env.example` to `.env` and fill in values, or ensure `.env` contains:

```
APP_DOMAIN=https://shrisamarth.in
```

Run locally:
```
python run.py
```

## Security System

The app includes a built-in anti-abuse system (`app/abuse.py`, `app/captcha.py`):

- **IP banning**: automatic and manual, temporary or permanent
- **Detection rules**: rapid booking rate, daily IP limit, phone abuse, seat hoarding,
  cancel-rebook pattern, bad user agents, honeypot field, velocity fingerprinting
- **Math CAPTCHA**: no external service, served inline when suspicious activity detected
- **Rate limiting**: Flask-Limiter on auth, booking, and registration endpoints
- **Admin panel**: `/admin/security` — live ban management, abuse log with CSV export

Admin env var needed on Render: none (security system works out of the box).

## Database

The app auto-creates all tables on startup via `db.create_all()` — no manual migration
needed for fresh deployments. For schema changes, use Flask-Migrate:

```
flask db migrate -m "description"
flask db upgrade
```

## Newsletter System

Admin-only email broadcast tool at `/admin/newsletter`:

- **4 themes**: Classic (cream/navy), Dark (midnight), Festival (marigold/warm), Minimal (white)
- **Bilingual**: English-only, Hindi-only, or both (auto-detected based on filled fields)
- **Live preview**: right-side iframe, debounced 500ms as you type
- **Mobile preview toggle**: simulates 375px width
- **Draft save/edit/duplicate/delete**: full lifecycle before sending
- **Unsubscribe**: every email includes a unique unsubscribe link (`/unsubscribe/<token>`)
  - Token auto-generated per user on first send
  - `newsletter_unsubscribed` flag excludes users from future sends
- **Recipient filter**: verified + active customers who haven't unsubscribed
- **Batch sending**: 50 emails/batch, 0.5s delay between batches
- **Resend warning**: shown in UI when recipient count > 80

Env var needed on Render: `RESEND_API_KEY` (same one used for auth emails).
