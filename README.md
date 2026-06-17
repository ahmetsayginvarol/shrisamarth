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
├── verify/         # QR boarding verification (/verify/<code>)
├── models.py       # All SQLAlchemy models
├── templates/      # Jinja2 templates (admin/, staff/, customer/, errors/)
├── static/         # CSS, JS, icons
├── abuse.py        # IP ban + abuse detection
├── captcha.py      # Inline math CAPTCHA (no external service)
├── email.py        # Resend email helpers
└── logging.py      # Activity log + notification helpers
```

---

## User Roles

| Role | Access |
|---|---|
| `super_admin` | Full system access |
| `admin` | Admin panel, driver cash, finances, trip reports |
| `reservation` | Staff dashboard (booking + manifest, no admin panel) |
| `driver` | Driver-only dashboard — seat map, manifest, cash collection, QR scanner |
| `customer` | Online booking and profile |

---

## Key Features

### Customer Booking
- Seat map with real-time availability via WebSocket
- Group/family bookings (multi-seat, one name)
- Session-based seat locking (prevents double-booking)
- Dynamic fare pricing per boarding stop
- Online payments + advance payment tracking
- PDF ticket with QR code for boarding
- Bilingual interface (English / Hindi)

### Staff & Driver Dashboard
- Live seat map with real-time SocketIO sync across all connected sessions
- Manifest with boarding/dropping stop filters
- Per-passenger check-in (seat tap or manifest row)
- Payment on Boarding (POC) — flag bookings for cash collection at the bus door
- Walk-in booking with seat assignment and gender conflict detection
- **Continuous QR Scanner** — camera stays open throughout boarding:
  - Boards the passenger automatically on scan (no manual "Mark as Boarded" tap)
  - Inline flash card overlays the camera for 3 seconds: name, seat, balance status
  - Audio beep feedback (Web Audio API — ascending for boarded, warning for already-boarded, low for invalid)
  - Manual code entry also triggers the same instant-board flow

### Driver Cash Workflow
1. Driver collects cash per passenger (recorded as `CashCollection`)
2. Driver taps **Submit Cash** — selects admin, submits all or a partial amount
3. Multiple partial submissions are supported before full settlement
4. Admin sees the in-transit entry and clicks **Mark Received**, enters counted amount
5. System reconciles: `verified` if amounts match → auto-creates income ledger entry; `discrepancy` if short
6. Discrepancies resolved as: pay later / write off / adjust
7. All steps emit SocketIO events — both panels update in real time without refresh

### Admin Panel
- Voyage management with route stops, fare overrides, and clone-voyage
- Trip report review (approve / flag) with auto-created financial entries on approval
- **Driver Cash Accountability** — live view of cash each driver holds, in transit, and any discrepancies
- Financial ledger with income/expense categories, monthly breakdown, CSV export
- Newsletter editor (4 themes, EN/HI, live preview, unsubscribe links)
- Passenger management with activity timeline
- Security panel — IP bans, abuse log, rate limiting
- Danger Zone — site suspension, DB reset, full data backup
- Real-time notification bell and sidebar badge updates via SocketIO

---

## Driver Cash Accounting Model

Cash in hand = `total_collected − sum(expected_amount for submissions in [submitted, verified, discrepancy, resolved])`

`expected_amount` is the driver's claimed hand-over amount and never changes after submission. The admin's counted amount (`submitted_amount`) may differ — the gap is tracked as a discrepancy, not re-added to the driver's outstanding balance. This prevents cash from "reappearing" after an admin records a shortage.

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

