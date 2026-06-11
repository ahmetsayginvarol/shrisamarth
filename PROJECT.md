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

## Financial Tracker

Admin-only ledger at `/admin/finances`:

- **Manual entries**: income and expense entries with category, amount, description, date
- **Auto ticket sales**: advance_paid from bookings grouped by date — read-only 🎫 rows, no entry needed
- **Categories** — Expense: Fuel, Driver Salary, Bus Maintenance, Toll & Permits, Office Rent, Staff Salary, Insurance, Cleaning, Food & Refreshments, Marketing, Other Expense
  Income: Charter Booking, Parcel/Cargo, Advance Payment, Other Income
- **Summary cards**: This Month Income / Expenses / Ticket Sales / Net Balance with % vs last month
- **Filters**: Today / This Week / This Month / This Year / Custom date range; category, type, search
- **Pagination**: 25 entries per page
- **Monthly breakdown**: last 6 months, collapsible, category bar charts for income + expenses
- **CSV export**: `/admin/finances/export` — filters respected, UTF-8 BOM for Excel compatibility
- **Dashboard net profit card**: ticket revenue minus logged expenses, with link to finances

Model: `FinancialEntry` — `entry_type` (income/expense), `category`, `amount`, `entry_date`, `description`, `created_by_id`

Schema: `CREATE TABLE IF NOT EXISTS financial_entries` — auto-created via `_run_schema_migrations` on startup (PostgreSQL), or `db.create_all()` (SQLite).

## Gender Silhouette Icons on Seat Map

Booked seats display a small white silhouette icon (18×18 px) inside the coloured seat cell:
- Blue seats (male booking): male silhouette (broad shoulders, rectangular torso, two legs)
- Pink seats (female booking): female silhouette (narrow torso, triangular skirt, two legs)
- Gender-neutral / unknown: no icon (seat number only, same as before)
- Checked-in seats: same icon + CSS `::after` ✓ overlay still applied

**Generated icons**: `app/static/icons/male.png` and `female.png` (64×64, RGBA, white fill on transparent background). Regenerate with `python3 scripts/generate_icons.py` (requires Pillow).

**Legend**: Both staff `dashboard.html` and customer `book.html` legends use the actual icons inside coloured swatches instead of plain text M/F labels.

**CSS**: `.seat.booked-m`, `.seat.booked-f`, `.seat.checked-in-m`, `.seat.checked-in-f` switch from `grid` to `flex column` layout so icon and seat-number stack vertically. `.seat-gender-icon` (18×18) and `.seat-num` (8 px font) added. `.legend-swatch-icon` added for legend use.

### Finance edit and delete buttons

The ✏️ edit button uses `data-*` attributes (auto HTML-escaped by Jinja2) instead of inline `onclick` string parameters — avoids JS parse errors when descriptions contain `"` or `'`.

`base_admin.html` already declares `const CSRF_TOKEN` at global scope. `finances.html` must NOT redeclare it — multiple `<script>` tags share the browser's global scope, and a second `const CSRF_TOKEN` throws `Identifier 'CSRF_TOKEN' has already been declared`, silently killing the entire finances script block (all functions undefined). The fix is to remove the duplicate declaration from `finances.html` and rely on the one already set by `{{ super() }}`.

## Danger Zone

Admin-only destructive operations at `/admin/danger-zone`. All actions require admin password confirmation.

### Features

| Action | Description |
|---|---|
| **Site Suspension** | Toggle a maintenance mode for all customer pages. Visitors see a customisable "We'll be right back" page (503). Staff and admins bypass it. |
| **Purge Seat Locks** | Release all temporary session seat locks. Use when seats are stuck "locked" with no active booking. |
| **Clear Activity Log** | Permanently delete all `ActivityLog` entries. |
| **Export Data Backup** | Download a full CSV of all bookings, voyages, and financial entries before any destructive action. |
| **Reset Database Content** | Delete ALL bookings, voyages, buses, financial entries, logs, newsletters, abuse logs, and customer accounts. Admin/staff accounts are preserved. Requires typing `RESET EVERYTHING` + password. |

### Implementation

- **Suspension**: Stored in `SiteContent` with `section_key='site_suspended'` (`content_en='1'`/`'0'`) and `section_key='suspension_message'`. `customer_bp.before_request` checks this on every customer-facing route.
- **Suspension page**: `app/templates/errors/suspended.html` — extends `base_customer.html`, served with HTTP 503.
- **Routes**: `admin.danger_zone` (GET), `admin.danger_suspend`, `admin.danger_unsuspend`, `admin.danger_purge_locks`, `admin.danger_clear_logs`, `admin.danger_reset_db` (POST, JSON body with `password`), `admin.danger_backup` (GET).
- **Password helper**: `_dz_check_password(data)` calls `current_user.check_password(password)` → 403 on failure.
- **Sidebar**: "Danger Zone" link at the bottom in red, below Security.
- **Reset-DB deletion order**: Notifications → SeatLocks → Bookings → RouteStops → Voyages → Buses → FinancialEntries → ActivityLogs → AbuseLogs → IpBans → Newsletters → Customer users.
