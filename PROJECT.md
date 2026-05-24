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

## Stop-Based Dynamic Fare Pricing

Boarding stops can have individual fare overrides instead of the voyage base fare.

**Model**: `RouteStop.fare_override` (NUMERIC 10,2, nullable). NULL means use voyage base_fare.

**Admin voyage form**: Each boarding stop row has an optional "Override fare (₹)" input.
Dropping stops always use base fare. A fare summary table below the stops list previews
the range in real time.

**Server enforcement**: Fare is never taken from client. `_get_stop_fare(voyage, boarding_point)`
helper in both `customer/routes.py` and `staff/routes.py` computes the correct fare:
- Looks up the `RouteStop` for the selected boarding stop
- Returns `fare_override` if set, otherwise `voyage.base_fare`

**Search results display**: Shows "From ₹X per seat" when any boarding stop is cheaper than
base fare. Each boarding stop shows its fare next to the stop name in the expanded card.

**Customer booking page**: When a boarding stop is selected, the fare updates live.
Below the boarding stop selector: "Fare for your journey: ₹X (₹Y off base fare)" in green
when discounted.

**Staff dashboard**: Single-seat booking fare field updates when boarding stop is changed.
Group booking fare-per-seat field also updates on boarding stop change.

**Voyage list/display**: `Voyage.min_fare` property returns cheapest fare; `Voyage.fare_display`
returns "₹X – ₹Y" range or single "₹X". Used in admin voyage list and search results.

**Schema migration**: `_run_schema_migrations()` in `app/__init__.py` adds
`route_stops.fare_override` column to existing databases automatically on startup.
