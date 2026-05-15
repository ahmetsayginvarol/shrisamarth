# SHRISAMARTH Bus Reservation System

## Tech Stack
- Flask + SQLAlchemy + Flask-SocketIO + Flask-Login
- SQLite (dev) / PostgreSQL (prod on Render)
- ReportLab for PDFs, qrcode for QR codes
- Jinja2 templates + vanilla JS

## What's Built (Phase 1 - Complete)
- Auth with roles: admin, reservation, driver
- Interactive 49-seat grid with realtime WebSocket sync
- Booking creation/cancellation with gender-conflict warnings
- Date picker + voyage filter on dashboard
- Admin panel: buses, voyages, users, revenue dashboard, activity log
- Driver view: read-only manifest
- E-ticket PDF with QR code
- Printable manifest PDF
- WhatsApp ticket delivery
- Hindi/English toggle
- Deployed on Render (free tier)

## To-Do
1. Multi-seat selection (group/family bookings) — ONE name for all seats
2. Mobile responsive — driver view first
3. Route stops model — dynamic boarding/dropping per voyage
4. Phase 2: Customer-facing site (redBus-style)

## Project Structure
- app/__init__.py — app factory
- app/models.py — User, Bus, Voyage, Booking, ActivityLog
- app/extensions.py — db, socketio, login_manager, csrf, etc.
- app/auth/routes.py — login, logout
- app/staff/routes.py — dashboard, seat API, booking CRUD, ticket/manifest PDF
- app/admin/routes.py — buses, voyages, users, logs, revenue dashboard
- app/logging.py — activity log helper
- app/staff/ticket.py — e-ticket PDF generator
- app/staff/manifest.py — manifest PDF generator
- app/static/js/dashboard.js — seat grid interactivity + realtime sync
- app/static/css/style.css — all styling

## Credentials (dev only)
- admin / admin123
- reservation / res123
- driver / drv123