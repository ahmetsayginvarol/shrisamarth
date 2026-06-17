# SHRISAMARTH

Bus booking and fleet management system for Shrisamarth Travels. Handles customer seat reservations, driver operations, cash accountability, and financial reporting.

**Live:** [shrisamarth.in](https://shrisamarth.in)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3 · Flask 3 · SQLAlchemy 2 · Flask-SocketIO |
| Auth | Flask-Login · Flask-Bcrypt · Flask-WTF (CSRF) |
| Database | PostgreSQL (production) · SQLite (local dev) |
| PDF / QR | ReportLab · qrcode · Pillow |
| Email | Resend API |
| Hosting | Render.com |

---

## Quick Start

```bash
git clone https://github.com/ahmetsayginvarol/shrisamarth.git
cd shrisamarth
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
python run.py
```

The app auto-creates all tables on first startup — no manual migration needed.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session secret |
| `DATABASE_URL` | Yes | PostgreSQL URL (set automatically on Render) |
| `APP_DOMAIN` | Yes | `https://shrisamarth.in` — used in QR codes and ticket links |
| `RESEND_API_KEY` | Yes | For email verification, password reset, and newsletters |

---

## Project Structure

```
app/
├── admin/          # Admin blueprint (/admin) — voyages, bookings, finances, users
├── auth/           # Auth blueprint (/auth) — login, register, password reset
├── customer/       # Customer blueprint (/) — search, booking, profile
├── staff/          # Staff blueprint (/staff) — driver + reservation dashboard
├── verify/         # Email verification flow
├── models.py       # All SQLAlchemy models
├── templates/      # Jinja2 templates (admin/, staff/, customer/, errors/)
├── static/         # CSS, JS, icons
├── abuse.py        # IP ban + abuse detection
├── captcha.py      # Inline math CAPTCHA (no external service)
├── email.py        # Resend email helpers
└── logging.py      # Activity log helpers
```

---

## User Roles

| Role | Access |
|---|---|
| `super_admin` | Full system access |
| `admin` | Admin panel, driver cash, finances, trip reports |
| `reservation` | Staff dashboard (booking + manifest, no admin panel) |
| `driver` | Driver-only dashboard — seat map, manifest, cash collection, check-in |
| `customer` | Online booking and profile |

---

## Key Features

### Customer Booking
- Seat map with real-time availability via WebSocket
- Session-based seat locking (prevents double-booking)
- Dynamic fare pricing per boarding stop
- Online payments + advance payment tracking
- PDF ticket with QR code for check-in
- Bilingual interface (English / Hindi)

### Staff & Driver Dashboard
- Live seat map for the day's voyage
- Manifest with boarding/dropping stop filters
- Per-passenger check-in button
- Walk-in booking with seat assignment and gender conflict detection
- Cash collection per passenger (POC — Payment on Boarding support)
- Country code dropdown for phone entry

### Admin Panel
- Voyage management with route stops and fare overrides
- Clone voyage for repeat routes
- Trip report review (approve / flag)
- Driver Cash Accountability Tracker — live view of cash each driver holds, submit/receive/verify flow with discrepancy resolution
- Financial ledger with CSV export
- Newsletter editor (4 themes, EN/HI, live preview, unsubscribe links)
- Passenger management with activity timeline
- Security panel — IP bans, abuse log, rate limiting
- Danger Zone — site suspension, DB reset, data backup

### Driver Cash Workflow
1. Driver collects cash during voyage (recorded as `CashCollection`)
2. Driver presses **Submit Cash** → selects admin, submits all or partial amount
3. Admin sees "In Transit" entry in Driver Cash panel
4. Admin clicks **Mark Received**, enters counted amount
5. System auto-reconciles: `verified` if amounts match, `discrepancy` if not
6. Discrepancies resolved as: pay later / write off / adjust
7. Verified receipts auto-create `FinancialEntry(Ticket Sales — Cash)`

---

## Schema Migrations

Schema changes are applied automatically on startup via `_run_schema_migrations()` in `app/__init__.py` using `IF NOT EXISTS` (PostgreSQL) or `try/except` (SQLite). No manual migration step needed for existing deployments.

For structural changes that require Flask-Migrate:

```bash
flask db migrate -m "description"
flask db upgrade
```

---

## Deployment (Render)

1. Connect the GitHub repo to a new Render Web Service
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn -w 4 -b 0.0.0.0:$PORT "app:create_app()"` (or see `Procfile`)
4. Add a Render PostgreSQL database — `DATABASE_URL` is injected automatically
5. Set `SECRET_KEY`, `APP_DOMAIN`, and `RESEND_API_KEY` in the Render Environment tab
