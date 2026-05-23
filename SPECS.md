# SHRISAMARTH Travels — Application Specifications

**Full-stack web application for bus seat booking, fleet management, and passenger operations.**
Live at [shrisamarth.in](https://shrisamarth.in) · Built with Python / Flask · Hosted on Render

---

## Table of Contents

1. [Overview](#1-overview)
2. [User Roles](#2-user-roles)
3. [Customer Booking Flow](#3-customer-booking-flow)
4. [Real-Time Seat Map](#4-real-time-seat-map)
5. [Fleet & Voyage Management](#5-fleet--voyage-management)
6. [Staff Operations Dashboard](#6-staff-operations-dashboard)
7. [Admin Panel](#7-admin-panel)
8. [Email System](#8-email-system)
9. [Security & Anti-Abuse](#9-security--anti-abuse)
10. [Newsletter System](#10-newsletter-system)
11. [Content Management](#11-content-management)
12. [Reporting & Analytics](#12-reporting--analytics)
13. [Internationalization](#13-internationalization)
14. [Database Schema](#14-database-schema)
15. [Tech Stack](#15-tech-stack)
16. [Configuration](#16-configuration)

---

## 1. Overview

SHRISAMARTH is a **multi-role bus booking platform** built for a regional transport operator in Maharashtra, India. It handles the complete lifecycle of a journey — from customer seat selection to driver check-in — with real-time updates, bilingual support (English / Hindi), automated emails, and a full admin back-office.

**Key capabilities at a glance:**

- Online seat booking with real-time locking (prevents double-booking)
- Gender-pair seating enforcement on adjacent seats
- Staff dashboard for counter sales, group bookings, and passenger check-in
- Admin panel: fleet, voyages, users, reports, security, newsletter, CMS
- Automated e-ticket emails on booking confirmation
- Built-in anti-abuse system: IP banning, honeypot, math CAPTCHA, rate limiting
- Bilingual newsletter broadcast (EN / HI) with unsubscribe management
- PDF generation: e-tickets, passenger manifests, daily reports
- QR code on every ticket, scannable at boarding

---

## 2. User Roles

Four roles, each with scoped access:

| Role | Description | Access Level |
|------|-------------|--------------|
| **Admin** | System owner | Full access to all features |
| **Reservation** | Counter/office staff | Booking creation, check-in, manifests |
| **Driver** | Bus driver | View-only for assigned voyages |
| **Customer** | Passenger | Self-serve booking portal |

**Account features (all roles):**
- Email + password authentication with bcrypt hashing
- Email verification required for new customer accounts (24-hour token)
- Password reset via email (1-hour token)
- Persistent 8-hour sessions
- Account deactivation (soft disable without data deletion)

---

## 3. Customer Booking Flow

### Step 1 — Search

Route: `GET /search`

Customers search by **origin**, **destination**, and **date**. Results show all scheduled voyages with:
- Departure time and estimated arrival
- Available seats remaining
- Fare per seat
- Boarding and dropping stop options

Results can be sorted by **time**, **price**, or **seat availability**.

### Step 2 — Seat Selection

Route: `GET /book/<voyage_id>`

A visual seat map renders the bus layout (default: 49 seats). Seats are colour-coded:

| Colour | Meaning |
|--------|---------|
| Available (light) | Free to select |
| Selected (gold) | Chosen by this customer |
| Booked — Male | Confirmed male passenger |
| Booked — Female | Confirmed female passenger |
| Locked (grey) | Another customer is checking out (5-min hold) |
| Window highlight | Preferred window seat |

Seat locks are held for **5 minutes** via WebSocket. If a customer abandons checkout, the lock expires automatically and the seat becomes available again.

**Gender-pair seating:** Adjacent seat pairs enforce gender compatibility. Booking a seat adjacent to an opposite-gender confirmed passenger is blocked with a clear error message. Reservation/admin staff can override this constraint.

### Step 3 — Passenger Details

Customers enter:
- Passenger name, phone number, email address
- Gender (required for individual bookings; optional for group bookings)
- Boarding point and dropping point (from the voyage's defined stops)

**Group bookings:** Multiple seats can be selected in one transaction. Each seat gets its own booking code; all are linked by a shared group code.

### Step 4 — Confirmation

Route: `GET /booking/confirmation/<code>`

After booking:
- A unique booking code is issued: `SHRI-YYYYMMDD-SEAT-HEX`
- Group bookings share a code: `GRP-YYYYMMDD-HEX`
- A **QR code** is generated and displayed
- **E-ticket PDF** download link appears
- **WhatsApp share** link with booking details
- A confirmation email with the e-ticket is sent automatically if an email was provided

### My Bookings

Route: `GET /my-bookings`

Logged-in customers see all their bookings with:
- Upcoming vs. completed trips
- Total amount spent and outstanding balance
- Individual ticket download per booking

---

## 4. Real-Time Seat Map

Built on **Flask-SocketIO** (WebSockets). All connected clients on the same voyage receive live events:

| Event | Trigger | Effect |
|-------|---------|--------|
| `seat_locked` | Customer starts checkout | Seat greys out for others |
| `seat_unlocked` | Checkout abandoned / timeout | Seat becomes available |
| `seat_booked` | Booking confirmed | Seat shows passenger name and gender |
| `seat_freed` | Booking cancelled | Seat returns to available |
| `passenger_checkin` | Driver/staff checks passenger in | Dashboard updates |
| `passenger_uncheckin` | Check-in undone | Dashboard updates |

**Seat Lock API:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/seat-status/<voyage_id>` | GET | Returns booked + locked seats |
| `/api/lock-seat` | POST | Holds a seat for 5 minutes |
| `/api/unlock-seat` | POST | Releases a held seat |

---

## 5. Fleet & Voyage Management

### Buses

Each bus record holds:
- **Registration plate** (unique identifier)
- **Name** (e.g. "Pune Express 1")
- **Seat layout** (default: `shrisamarth_49` — 49-seat configuration)
- **Total seats**, active/inactive flag, notes

### Voyages

A voyage is one departure of one bus on one route:

| Field | Detail |
|-------|--------|
| Origin / Destination | Free-text city names |
| Departure / Arrival | Date + time |
| Bus | Linked bus record |
| Driver | Assigned driver user |
| Base fare | Per-seat price (₹) |
| Status | `scheduled` · `departed` · `completed` · `cancelled` |
| Route stops | Ordered boarding and dropping points with times |

### Recurring Schedules

When creating a voyage, admin can define a **recurrence pattern**:

- **Frequency:** daily, every 2/3 days, weekly, specific weekdays
- **End date:** up to 90 days ahead
- Up to 90 voyages created in a single action
- Conflict detection skips dates where the same bus is already scheduled
- All voyages in a group can be **bulk-edited** (update time, fare, driver for all future occurrences)
- Future occurrences can be **cancelled in bulk** without affecting past ones

---

## 6. Staff Operations Dashboard

Route: `GET /staff/dashboard`

### Layout

- **Date picker** (left) highlights dates that have scheduled voyages
- **Voyage selector** (top) filters by selected date
- **Seat map** (main area) shows all 49 seats in real time

Drivers see only their assigned voyages. Reservation staff and admins see all.

### Booking Operations

**Single booking** (`/staff/booking/create`):
- Manual passenger entry for counter/phone sales
- Fare, advance payment, and balance due recorded
- Gender conflict warning with staff override option

**Group booking** (`/staff/booking/create-group`):
- Multiple passengers in one operation
- Per-seat fare, advance, and balance
- Per-passenger boarding/dropping points
- Linked by a shared group code

**Cancel** (`/staff/booking/<id>/cancel`):
- Immediately frees the seat
- Logged in the activity trail

**Check-in** (`/staff/booking/<id>/checkin`):
- Records boarding time and which staff member checked the passenger in
- Prevents duplicate check-ins
- **5-minute undo window** for reservation/admin staff

### Downloads

| Document | Format | Contents |
|----------|--------|---------|
| Individual e-ticket | PDF | Booking code, route, seat, passenger, fare |
| Group ticket | PDF | All passengers in the group on one document |
| Passenger manifest | PDF (EN or HI) | Full passenger list with payment status, check-in status |

---

## 7. Admin Panel

### Dashboard

Route: `/admin/dashboard`

**KPI cards:**
- Total revenue (all time)
- Total collected vs. outstanding balance
- Today's revenue and bookings

**Upcoming voyages table** (next 10): bookings count, boarded count, revenue, occupancy %.

**Recent bookings** (last 20 confirmed).

### Buses

Full CRUD for the bus fleet. Each bus shows linked voyage history.

### Voyages

Full CRUD with recurrence scheduling. Cancellation cascades to notify all affected passengers (via activity log; notification hooks in place for future SMS/push).

### Users (Staff)

- Create, edit, and deactivate staff accounts (admin, reservation, driver roles)
- Send a password reset email directly from the user record

### Passengers (Customers)

- Directory of all customer accounts with aggregated stats: trips, total spent, balance due
- Per-customer detail page: full booking history, account toggle, manual credit addition

### Activity Log

- All system events: bookings, logins, edits, cancellations, newsletter sends, security actions
- Filters: action type, user, date range
- Pagination (50 entries/page)
- Print-friendly view
- Clear history option (requires admin password confirmation)

### Day Report (PDF)

Route: `/admin/reports/day?date=YYYY-MM-DD`

A printable daily operations report:
- Summary: voyages, passengers, total revenue, collected, outstanding
- Per-voyage summary table with occupancy %
- Full passenger manifest per voyage (seat, name, gender, boarding/dropping, fare breakdown, check-in status)

---

## 8. Email System

**Provider:** [Resend](https://resend.com) — transactional email API.
**Fallback:** If `RESEND_API_KEY` is not set, emails are printed to the server console (useful for local development).
**From address:** `SHRISAMARTH <no-reply@shrisamarth.in>`

### Transactional Emails

| Trigger | Template | Contents |
|---------|----------|---------|
| Customer registers | `verify_email.html` | Verification link (expires 24h) |
| Forgot password | `reset_password.html` | Reset link (expires 1h) |
| Booking confirmed | `eticket.html` | Full e-ticket with booking details |

### E-Ticket Email

Sent automatically after every confirmed booking where an email address was provided. Contains:
- Booking reference (prominent, gold monospace display)
- Route, date, departure time
- Seat number
- Passenger name and phone
- Boarding and dropping point
- Total fare and balance due (or "Paid ✓" if fully paid)
- Group booking code (if part of a group)
- Boarding reminder (15 minutes before departure)

Email sending is **fire-and-forget** — it never delays or blocks the booking response.

### Newsletter Emails

Four visual themes available (see [Newsletter System](#10-newsletter-system)).

---

## 9. Security & Anti-Abuse

### Automatic Detection Rules

| Rule | Threshold | Action |
|------|-----------|--------|
| Active IP ban | Any | Block booking, log attempt |
| Empty / bot user-agent | `curl`, `wget`, `scrapy`, `requests` | 24-hour auto-ban |
| Rapid booking (severe) | 5+ bookings in 5 minutes | 1-hour auto-ban |
| Rapid booking (mild) | 3+ bookings in 5 minutes | Require CAPTCHA |
| Daily IP limit | 15+ bookings in 24 hours | 24-hour auto-ban |
| Phone abuse | 10+ bookings per phone in 24 hours | Block (manual review) |
| Seat hoarding | 6+ seats on same voyage from one IP | Block |
| Cancel-rebook pattern | 4+ cancellations in 2 hours | 6-hour auto-ban |
| Honeypot triggered | Hidden form field filled in | 7-day auto-ban |
| Velocity check | Form submitted in under 3 seconds | Require CAPTCHA |

Auto-ban thresholds escalate: 3 events/hour → 2h ban; 5 events/24h → 24h ban; 10 total events → permanent ban.

### Math CAPTCHA

A simple arithmetic challenge (addition, subtraction, or multiplication) is shown when suspicious behaviour is detected. No external service required — tokens are stored server-side with a 10-minute expiry. Each token is single-use.

### IP Ban Management

Route: `/admin/security`

- View all active bans (IP, reason, expiry, type)
- Manual ban: enter any IP, set reason and duration (hours or permanent)
- Unban individually or in bulk
- Promote a temporary ban to permanent
- Temporary bans auto-expire and are cleaned up on the next check

### Rate Limiting

Applied via Flask-Limiter on sensitive endpoints:

| Endpoint | Limit |
|----------|-------|
| Customer login | 5 per hour |
| Customer register | 3 per hour |
| Resend verification | 3 per hour |
| Email verification | 10 per hour |
| Booking creation | 10 per minute / 100 per hour |

### Abuse Log

All abuse events are logged to the `abuse_logs` table: IP address, event type, details, timestamp, and linked user (if authenticated). The `/admin/security` page displays the log with filtering and CSV export (up to 5,000 recent entries).

---

## 10. Newsletter System

Route: `/admin/newsletter`

Admin-only email broadcast tool.

### Composing

- **Subject line:** separate fields for English and Hindi
- **Body content:** separate textareas for English and Hindi (max 500 characters each)
- Language behaviour: if both are filled, both are sent in one email; if only one is filled, that language is sent
- Character counter with warning at 450+

### Themes

| Theme | Visual Style |
|-------|-------------|
| Classic | Cream background, dark navy header, gold accent |
| Dark | Midnight background, black header, gold border |
| Festival | Marigold header, warm cream background |
| Minimal | White background, thin border, clean layout |

### Live Preview

A live preview iframe on the right side of the compose form renders the email as you type (debounced 500 ms). A mobile toggle simulates a 375 px viewport.

### Sending

Emails are sent in **batches of 50** with a 0.5-second delay between batches to respect rate limits.

**Recipient filter:** Only users who are:
- Role: customer
- Email verified
- Account active
- Not unsubscribed

A warning is shown in the UI when the recipient count exceeds 80.

### Unsubscribe System

Every outgoing newsletter includes a unique unsubscribe link (`/unsubscribe/<token>`). Clicking it:
1. Sets `newsletter_unsubscribed = true` on the user record
2. Shows a confirmation page
3. Excludes the user from all future sends

Users can re-subscribe from their account profile.

### Draft Management

Newsletters can be saved as drafts, edited, duplicated, or deleted before sending. Sent newsletters are read-only (can be duplicated as a new draft).

---

## 11. Content Management

Route: `/admin/cms`

Admins can edit homepage content without touching code.

### Managed Sections

**Announcement banner:**
- Toggle on/off with a checkbox
- Banner text (shown site-wide at the top of every customer page)

**FAQ:**
- Bilingual question-answer pairs (English + Hindi)
- Accordion display on the homepage
- JSON-based storage; default pairs are shown if DB is empty

---

## 12. Reporting & Analytics

### Admin Dashboard KPIs

| Metric | Scope |
|--------|-------|
| Total revenue | All confirmed bookings |
| Total collected | Sum of `advance_paid` |
| Total outstanding | Sum of `balance_due` |
| Today's revenue | Bookings created today |
| Today's bookings | Count created today |

### Day Report PDF

A professional branded PDF for a selected date, used for end-of-day reconciliation and operations review. Includes:
- Overall summary (voyages, passengers, revenue, collected, outstanding)
- Per-voyage summary with occupancy percentage
- Full passenger list per voyage with check-in status and payment breakdown

### Activity Log

A complete audit trail of all system activity. Every booking, login, edit, cancellation, and admin action is logged with:
- Action type
- Human-readable description
- Target record (booking ID, voyage ID, etc.)
- IP address
- Timestamp

Filterable by action, actor, and date range. Exportable as a print-friendly page.

### Calendar API

`GET /admin/api/calendar?year=YYYY&month=MM`

Returns JSON with per-day stats for the month: voyage count, passenger count, revenue, and occupancy — used to power the admin calendar view.

---

## 13. Internationalization

Supported languages: **English** and **Hindi (हिंदी)**.

- Language toggle (EN / हिं) in the admin topbar
- UI labels use `data-i18n` attributes; a `TRANSLATIONS` object drives client-side switching
- CMS content (FAQ, announcements) stored as separate EN/HI fields
- Newsletter subjects and body content stored separately per language
- Passenger manifest PDF available in both languages
- Email templates support bilingual content blocks

---

## 14. Database Schema

14 tables in PostgreSQL (SQLite for local development):

| Table | Purpose |
|-------|---------|
| `users` | All accounts (admin, staff, customer) |
| `buses` | Bus fleet records |
| `voyages` | Individual departures |
| `route_stops` | Boarding/dropping stops per voyage |
| `bookings` | Seat reservations |
| `seat_locks` | Temporary 5-minute seat holds |
| `activity_log` | Full audit trail |
| `notifications` | In-app staff notifications |
| `email_verification_tokens` | 24-hour email verification tokens |
| `password_reset_tokens` | 1-hour password reset tokens |
| `site_content` | CMS content (FAQ, banners) |
| `newsletters` | Newsletter drafts and sent records |
| `abuse_logs` | Abuse detection event log |
| `ip_bans` | Active and expired IP bans |

Schema migrations run automatically on startup (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — no manual migration commands needed for column additions on existing tables.

---

## 15. Tech Stack

### Backend

| Component | Technology |
|-----------|-----------|
| Framework | Flask 3.1 |
| ORM | SQLAlchemy 2.0 + Flask-SQLAlchemy |
| Authentication | Flask-Login + Flask-Bcrypt |
| Forms & CSRF | Flask-WTF |
| WebSockets | Flask-SocketIO 5.6 |
| Rate limiting | Flask-Limiter |
| Translations | Flask-Babel |
| Email | Resend API |
| PDF generation | ReportLab 4.5 |
| QR codes | qrcode + Pillow |
| Database | PostgreSQL (production) · SQLite (development) |
| Server | Gunicorn 26 |

### Frontend

| Component | Technology |
|-----------|-----------|
| Styling | Custom CSS (design system with CSS variables) |
| Real-time client | Socket.IO 4.7 (CDN) |
| Seat map | Vanilla JS (`book.js`, `dashboard.js`) |
| Fonts | Georgia (serif body) · Instrument Serif (headings) |
| PDF fonts | FreeSans / FreeSansBold (bundled TTF) |

### Infrastructure

| Component | Detail |
|-----------|--------|
| Hosting | [Render.com](https://render.com) |
| Database | Render managed PostgreSQL |
| Domain | [shrisamarth.in](https://shrisamarth.in) |
| Email | [Resend](https://resend.com) · `no-reply@shrisamarth.in` |
| Repository | GitHub (`ahmetsayginvarol/shrisamarth`) |

---

## 16. Configuration

All configuration is handled through environment variables:

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | Yes | Flask session signing key |
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string (auto-set by Render) |
| `APP_DOMAIN` | Yes | Canonical URL for QR codes and links — `https://shrisamarth.in` |
| `RESEND_API_KEY` | Yes (prod) | Resend email API key |

**Session lifetime:** 8 hours (permanent sessions).

**Database fallback:** If `DATABASE_URL` is not set, the app uses a local SQLite file at `instance/shrisamarth.db`. All features work identically on SQLite for local development.

---

*SHRISAMARTH Travels · Maharashtra, India · shrisamarth.in*
