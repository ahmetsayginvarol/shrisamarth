# SHRISAMARTH — Current State

## Status: Live in Production
- URL: **https://shrisamarth.in**
- Hosting: Render.com (web service + managed PostgreSQL)
- Stack: Flask 3 · SQLAlchemy 2 · Flask-SocketIO · Jinja2 · Vanilla JS

---

## Roles

| Role | Access |
|---|---|
| `super_admin` | Full system access |
| `admin` | Admin panel, finances, driver cash, trip reports |
| `reservation` | Staff dashboard — booking + manifest |
| `driver` | Driver dashboard — seat map, manifest, cash, QR scanner |
| `customer` | Online booking and profile |

---

## What's Built

### Customer Side
- Seat map with real-time availability (WebSocket)
- Session seat locking to prevent double-booking
- Group/family bookings (multi-seat, one name)
- Dynamic fare pricing per boarding stop
- Online payments + advance payment tracking
- PDF e-ticket with QR code
- Email verification, password reset (Resend API)
- WhatsApp ticket delivery
- Bilingual interface (English / Hindi)
- Math CAPTCHA + IP ban system

### Staff / Driver Dashboard
- Live seat map with real-time SocketIO sync
- Date picker + voyage switcher
- Manifest with boarding/dropping stop filters
- Per-passenger check-in (seat tap or manifest row)
- Payment on Boarding (POC) — flag + collect at boarding point
- Walk-in booking with seat assignment + gender conflict detection
- **QR Scanner** — continuous boarding mode:
  - Camera stays open; never closes between scans
  - Auto-boards immediately on QR detection (no manual tap)
  - Inline flash card over camera viewport (3 s) — name, seat, balance status
  - Web Audio beep: ascending tone (boarded), mid tone (already boarded), low tone (invalid)
  - Same-code cooldown prevents double-fire
  - Manual code entry also triggers auto-board flow

### Cash Accountability Workflow
1. Driver collects cash per passenger (CashCollection record)
2. **Submit Cash** modal — select admin, submit all OR a partial custom amount
   - Multiple partial submissions supported before full settlement
   - `expected_amount` = driver's claimed hand-over (never shrinks on discrepancy)
   - Proportional allocation across voyages; rounding absorbed by last voyage
3. Admin sees "In Transit" badge and "Awaiting Verification" panel
4. Admin clicks **Mark Received**, enters actual counted amount
5. `verified` if amounts match → auto-creates FinancialEntry (Ticket Sales — Cash)
6. `discrepancy` if short → resolve as: pay later / write off / adjust
7. Real-time SocketIO events: `cash_collected`, `driver_cash_submitted`, `driver_cash_verified`

**Calculation model:** cash in hand = `total_collected − sum(expected_amount for status in [submitted, verified, discrepancy, resolved])`. Keyed off `expected_amount` (the driver's claim) so an admin's lower count doesn't make cash reappear as outstanding.

### Admin Panel
- Voyage management — route stops, fare overrides, clone voyage
- Trip report review — approve / flag
- Driver Cash Accountability — live per-driver holding, in-transit, discrepancy cards
- Financial ledger — manual entries, auto ticket sales, CSV export
- Passenger management with activity timeline
- Newsletter editor — 4 themes, EN/HI, live preview, unsubscribe
- Security panel — IP bans, abuse log
- Danger Zone — site suspension, DB reset, data backup
- Real-time notification bell (SocketIO `new_notification`)
- Sidebar cash badge updates live via SocketIO

---

## Key Models

| Model | Purpose |
|---|---|
| `User` | All roles |
| `Bus` | Fleet |
| `Voyage` | A scheduled trip |
| `RouteStop` | Boarding/dropping stop with optional fare override |
| `Booking` | Seat reservation (`staff` / `customer` / `walkin`) |
| `CashCollection` | Cash collected by driver per passenger |
| `DriverCashSubmission` | Driver→admin hand-over record (`pending→submitted→verified/discrepancy→resolved`) |
| `TripReport` | End-of-trip driver report (`pending→approved/flagged`) |
| `FinancialEntry` | Income/expense ledger |
| `Notification` | In-app alerts for staff |
| `SiteContent` | CMS — homepage, suspension message |
| `Newsletter` | Draft + sent broadcast emails |
| `UserActivityLog` | Customer event timeline |
| `IpBan` / `AbuseLog` | Anti-abuse system |

---

## SocketIO Events

| Event | Emitted by | Consumed by |
|---|---|---|
| `seat_booked` | booking create | seat map (all sessions) |
| `seat_unlocked` | seat lock release | seat map |
| `passenger_boarded` | QR scan / check-in | manifest, boarding counter |
| `passenger_uncheckin` | undo check-in | manifest |
| `cash_collected` | cash collect / walk-in | driver cash section |
| `driver_cash_submitted` | Submit Cash | admin Driver Cash page, sidebar badge |
| `driver_cash_verified` | Mark Received | driver dashboard, admin Driver Cash page |
| `new_notification` | any notify_staff() call | notification bell badge |

---

## Schema Migrations
Auto-applied on startup via `_run_schema_migrations()` in `app/__init__.py` — `IF NOT EXISTS` for PostgreSQL, `try/except` for SQLite. No manual step needed for existing deployments.

---

## Local Dev

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Dev credentials: `admin / admin123` · `reservation / res123` · `driver / drv123`
