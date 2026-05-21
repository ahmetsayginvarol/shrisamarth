import io
import qrcode
from flask import current_app
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Image as RLImage


# ===== Brand colors =====
INK       = colors.HexColor('#141b2d')
CREAM     = colors.HexColor('#faf6ef')
GOLD      = colors.HexColor('#d4a84c')
MUTED     = colors.HexColor('#6b6558')
LINE      = colors.HexColor('#d9d0bf')

# Custom ticket size: 105mm x 190mm (slightly taller than A6)
TICKET_W = 105 * mm
TICKET_H = 190 * mm
CONTENT_W = TICKET_W - 16 * mm  # margins on each side

# ===== Ticket label translations =====
_TICKET_LABELS = {
    'en': {
        'boarding_pass': 'BOARDING PASS',
        'group_boarding_pass': 'GROUP BOARDING PASS',
        'seat': 'SEAT',
        'gender': 'GENDER',
        'boarding': 'BOARDING',
        'dropping': 'DROPPING',
        'fare': 'FARE',
        'advance': 'ADVANCE',
        'balance': 'BALANCE',
        'booking_id': 'BOOKING ID',
        'group_booking_id': 'GROUP BOOKING ID',
        'passenger': 'PASSENGER',
        'contact': 'CONTACT',
        'bus': 'BUS',
        'show_qr': 'Show QR at boarding',
        'male': 'Male',
        'female': 'Female',
        'window': 'Window',
        'aisle': 'Aisle',
        'win_short': 'Win',
        'total': 'TOTAL',
        'type': 'TYPE',
        'seats': 'SEATS',
    },
    'hi': {
        'boarding_pass': 'बोर्डिंग पास',
        'group_boarding_pass': 'समूह बोर्डिंग पास',
        'seat': 'सीट',
        'gender': 'लिंग',
        'boarding': 'बोर्डिंग',
        'dropping': 'ड्रॉपिंग',
        'fare': 'किराया',
        'advance': 'अग्रिम',
        'balance': 'शेष',
        'booking_id': 'बुकिंग आईडी',
        'group_booking_id': 'समूह बुकिंग आईडी',
        'passenger': 'यात्री',
        'contact': 'संपर्क',
        'bus': 'बस',
        'show_qr': 'बोर्डिंग पर QR दिखाएं',
        'male': 'पुरुष',
        'female': 'महिला',
        'window': 'खिड़की',
        'aisle': 'गलियारा',
        'win_short': 'खि',
        'total': 'कुल',
        'type': 'प्रकार',
        'seats': 'सीटें',
    },
}

def _get_ticket_font(lang: str) -> str:
    """Return the appropriate font name for the given language."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os
    fonts_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
    if lang == 'hi':
        regular = os.path.join(fonts_dir, 'FreeSans.ttf')
        bold_path = os.path.join(fonts_dir, 'FreeSansBold.ttf')
        try:
            if 'FreeSans' not in pdfmetrics.getRegisteredFontNames():
                if os.path.exists(regular):
                    pdfmetrics.registerFont(TTFont('FreeSans', regular))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont('FreeSansBold', bold_path))
            return 'FreeSans'
        except Exception:
            pass
    return 'Helvetica'


def generate_qr(data: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                        box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#141b2d', back_color='#faf6ef')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def generate_ticket(booking, lang: str = 'en') -> io.BytesIO:
    buf = io.BytesIO()
    L = _TICKET_LABELS.get(lang, _TICKET_LABELS['en'])
    base_font = _get_ticket_font(lang)
    bold_font = base_font + '-Bold' if lang == 'en' else ('FreeSansBold' if lang == 'hi' else base_font)

    doc = SimpleDocTemplate(
        buf,
        pagesize=(TICKET_W, TICKET_H),
        leftMargin=8*mm, rightMargin=8*mm,
        topMargin=6*mm, bottomMargin=6*mm,
    )

    # ===== Styles =====
    s_brand = ParagraphStyle('brand', fontSize=14, textColor=CREAM,
        fontName=bold_font, alignment=TA_LEFT, leading=16)
    s_pass = ParagraphStyle('pass', fontSize=7, textColor=GOLD,
        fontName=bold_font, alignment=TA_RIGHT, leading=9,
        spaceAfter=0)
    s_route = ParagraphStyle('route', fontSize=14, textColor=INK,
        fontName=bold_font, alignment=TA_LEFT, leading=17)
    s_dep = ParagraphStyle('dep', fontSize=8, textColor=MUTED,
        fontName=base_font, alignment=TA_LEFT, leading=10)
    s_label = ParagraphStyle('label', fontSize=6, textColor=GOLD,
        fontName=bold_font, alignment=TA_LEFT, leading=8)
    s_val = ParagraphStyle('val', fontSize=9, textColor=INK,
        fontName=bold_font, alignment=TA_LEFT, leading=11)
    s_val_sm = ParagraphStyle('val_sm', fontSize=8, textColor=INK,
        fontName=base_font, alignment=TA_LEFT, leading=10)
    s_center = ParagraphStyle('center', fontSize=7, textColor=MUTED,
        fontName=base_font, alignment=TA_CENTER, leading=9)
    s_code = ParagraphStyle('code', fontSize=6, textColor=MUTED,
        fontName='Courier', alignment=TA_CENTER, leading=8)

    # ===== Helpers =====
    half = CONTENT_W / 2
    third = CONTENT_W / 3

    def field(label, value):
        return Table(
            [[Paragraph(label, s_label)], [Paragraph(str(value), s_val)]],
            colWidths=[CONTENT_W],
        )

    def field_sm(label, value):
        return Table(
            [[Paragraph(label, s_label)], [Paragraph(str(value), s_val_sm)]],
            colWidths=[CONTENT_W],
        )

    # ===== Header =====
    header = Table(
        [[Paragraph('SHRISAMARTH', s_brand),
          Paragraph(L['boarding_pass'], s_pass)]],
        colWidths=[half, half],
    )
    header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), INK),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (0,-1), 5),
        ('RIGHTPADDING', (-1,0), (-1,-1), 5),
    ]))

    # ===== Route =====
    route = f"{booking.voyage.origin}  —  {booking.voyage.destination}"
    dep = booking.voyage.departure_at.strftime('%d %B %Y · %H:%M')

    # ===== Details grid =====
    gender_label = L['male'] if booking.gender == 'M' else L['female']
    window_label = L['window'] if booking.is_window else L['aisle']

    row_seat_gender = Table([[
        Table([[Paragraph(L['seat'], s_label)], [Paragraph(f'{booking.seat_id}  ({window_label})', s_val)]],
              colWidths=[half]),
        Table([[Paragraph(L['gender'], s_label)], [Paragraph(gender_label, s_val)]],
              colWidths=[half]),
    ]], colWidths=[half, half])

    stop_times = {s.stop_name: s.stop_time for s in booking.voyage.stops}
    board_label = booking.boarding_point
    if stop_times.get(booking.boarding_point):
        board_label = f"{booking.boarding_point} ({stop_times[booking.boarding_point]})"
    row_board_drop = Table([[
        Table([[Paragraph(L['boarding'], s_label)], [Paragraph(board_label, s_val)]],
              colWidths=[half]),
        Table([[Paragraph(L['dropping'], s_label)], [Paragraph(booking.dropping_point, s_val)]],
              colWidths=[half]),
    ]], colWidths=[half, half])

    row_money = Table([[
        Table([[Paragraph(L['fare'], s_label)], [Paragraph(f'₹ {int(booking.fare)}', s_val_sm)]],
              colWidths=[third]),
        Table([[Paragraph(L['advance'], s_label)], [Paragraph(f'₹ {int(booking.advance_paid or 0)}', s_val_sm)]],
              colWidths=[third]),
        Table([[Paragraph(L['balance'], s_label)], [Paragraph(f'₹ {int(booking.balance_due or 0)}', s_val_sm)]],
              colWidths=[third]),
    ]], colWidths=[third, third, third])

    # ===== QR + footer =====
    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    verify_url = f"{domain}/verify/{booking.booking_code}"
    qr_buf = generate_qr(verify_url)
    qr_img = RLImage(qr_buf, width=20*mm, height=20*mm)

    footer = Table([[
        qr_img,
        Table([
            [Paragraph(L['booking_id'], s_label)],
            [Paragraph(booking.booking_code, s_code)],
            [Spacer(1, 2)],
            [Paragraph(L['show_qr'], s_center)],
        ], colWidths=[CONTENT_W - 24*mm]),
    ]], colWidths=[24*mm, CONTENT_W - 24*mm])

    footer.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    # ===== Assemble =====
    sp = Spacer(1, 2*mm)
    hr = HRFlowable(width='100%', thickness=0.4, color=LINE, spaceAfter=2*mm)
    hr_dash = HRFlowable(width='100%', thickness=0.4, color=LINE,
                         lineCap='round', spaceAfter=2*mm, dash=[2,3])

    story = [
        header,
        Spacer(1, 3*mm),
        Paragraph(route, s_route),
        Paragraph(dep, s_dep),
        sp,
        hr,
        field(L['passenger'], booking.passenger_name),
        sp,
        row_seat_gender,
        sp,
        row_board_drop,
        sp,
        row_money,
        sp,
        field_sm(L['bus'], booking.voyage.bus.registration),
        field_sm(L['contact'], booking.passenger_phone),
        Spacer(1, 3*mm),
        hr_dash,
        footer,
    ]

    doc.build(story)
    buf.seek(0)
    return buf


def generate_group_ticket(bookings, lang: str = 'en') -> io.BytesIO:
    """Generate a single e-ticket PDF for a multi-seat group booking."""
    if not bookings:
        raise ValueError("No bookings provided")
    L = _TICKET_LABELS.get(lang, _TICKET_LABELS['en'])
    base_font = _get_ticket_font(lang)
    bold_font = base_font + '-Bold' if lang == 'en' else ('FreeSansBold' if lang == 'hi' else base_font)

    first = bookings[0]
    voyage = first.voyage

    # Taller page for multiple seats
    per_seat_extra = max(0, len(bookings) - 1) * 10 * mm
    ticket_h = TICKET_H + per_seat_extra

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(TICKET_W, ticket_h),
        leftMargin=8*mm, rightMargin=8*mm,
        topMargin=6*mm, bottomMargin=6*mm,
    )

    s_brand = ParagraphStyle('brand2', fontSize=14, textColor=CREAM,
        fontName=bold_font, alignment=TA_LEFT, leading=16)
    s_pass = ParagraphStyle('pass2', fontSize=7, textColor=GOLD,
        fontName=bold_font, alignment=TA_RIGHT, leading=9)
    s_route = ParagraphStyle('route2', fontSize=14, textColor=INK,
        fontName=bold_font, alignment=TA_LEFT, leading=17)
    s_dep = ParagraphStyle('dep2', fontSize=8, textColor=MUTED,
        fontName=base_font, alignment=TA_LEFT, leading=10)
    s_label = ParagraphStyle('label2', fontSize=6, textColor=GOLD,
        fontName=bold_font, alignment=TA_LEFT, leading=8)
    s_val = ParagraphStyle('val2', fontSize=9, textColor=INK,
        fontName=bold_font, alignment=TA_LEFT, leading=11)
    s_val_sm = ParagraphStyle('val_sm2', fontSize=8, textColor=INK,
        fontName=base_font, alignment=TA_LEFT, leading=10)
    s_center = ParagraphStyle('center2', fontSize=7, textColor=MUTED,
        fontName=base_font, alignment=TA_CENTER, leading=9)
    s_code = ParagraphStyle('code2', fontSize=6, textColor=MUTED,
        fontName='Courier', alignment=TA_CENTER, leading=8)

    half = CONTENT_W / 2
    third = CONTENT_W / 3

    def field_sm(label, value):
        return Table(
            [[Paragraph(label, s_label)], [Paragraph(str(value), s_val_sm)]],
            colWidths=[CONTENT_W],
        )

    header = Table(
        [[Paragraph('SHRISAMARTH', s_brand),
          Paragraph(L['group_boarding_pass'], s_pass)]],
        colWidths=[half, half],
    )
    header.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), INK),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (0,-1), 5),
        ('RIGHTPADDING', (-1,0), (-1,-1), 5),
    ]))

    route = f"{voyage.origin}  —  {voyage.destination}"
    dep = voyage.departure_at.strftime('%d %B %Y · %H:%M')
    # Seats table — one row per seat, with per-passenger name
    seat_rows = [[
        Paragraph(L['seat'], s_label),
        Paragraph(L['passenger'], s_label),
        Paragraph(L['type'], s_label),
        Paragraph(L['fare'], s_label),
        Paragraph(L['advance'], s_label),
        Paragraph(L['balance'], s_label),
    ]]
    col_w = [CONTENT_W * f for f in (0.10, 0.30, 0.13, 0.16, 0.15, 0.16)]
    for b in bookings:
        window_label = L['win_short'] if b.is_window else L['aisle']
        seat_rows.append([
            Paragraph(b.seat_id, s_val),
            Paragraph(b.passenger_name, s_val_sm),
            Paragraph(window_label, s_val_sm),
            Paragraph(f'₹ {int(b.fare)}', s_val_sm),
            Paragraph(f'₹ {int(b.advance_paid or 0)}', s_val_sm),
            Paragraph(f'₹ {int(b.balance_due or 0)}', s_val_sm),
        ])

    seats_table = Table(seat_rows, colWidths=col_w)
    seats_table.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,0), 0.4, LINE),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]))

    total_fare = sum(int(b.fare) for b in bookings)
    total_advance = sum(int(b.advance_paid or 0) for b in bookings)
    total_balance = sum(int(b.balance_due or 0) for b in bookings)

    totals_row = Table([[
        Paragraph('', s_label),
        Paragraph(L['total'], s_label),
        Paragraph('', s_label),
        Paragraph(f'₹ {total_fare}', s_val_sm),
        Paragraph(f'₹ {total_advance}', s_val_sm),
        Paragraph(f'₹ {total_balance}', s_val_sm),
    ]], colWidths=col_w)
    totals_row.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 0.4, LINE),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
    ]))

    row_board_drop = Table([[
        Table([[Paragraph(L['boarding'], s_label)], [Paragraph(first.boarding_point, s_val)]],
              colWidths=[half]),
        Table([[Paragraph(L['dropping'], s_label)], [Paragraph(first.dropping_point, s_val)]],
              colWidths=[half]),
    ]], colWidths=[half, half])

    domain = current_app.config.get('APP_DOMAIN', 'https://shrisamarth.in')
    verify_url = f"{domain}/verify/{first.group_booking_code}"
    qr_buf = generate_qr(verify_url)
    qr_img = RLImage(qr_buf, width=20*mm, height=20*mm)

    footer = Table([[
        qr_img,
        Table([
            [Paragraph(L['group_booking_id'], s_label)],
            [Paragraph(first.group_booking_code, s_code)],
            [Spacer(1, 2)],
            [Paragraph(L['show_qr'], s_center)],
        ], colWidths=[CONTENT_W - 24*mm]),
    ]], colWidths=[24*mm, CONTENT_W - 24*mm])
    footer.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    sp = Spacer(1, 2*mm)
    hr = HRFlowable(width='100%', thickness=0.4, color=LINE, spaceAfter=2*mm)
    hr_dash = HRFlowable(width='100%', thickness=0.4, color=LINE,
                         lineCap='round', spaceAfter=2*mm, dash=[2,3])

    story = [
        header,
        Spacer(1, 3*mm),
        Paragraph(route, s_route),
        Paragraph(dep, s_dep),
        sp,
        hr,
        field_sm(L['contact'], first.passenger_phone),
        sp,
        hr,
        Table([[Paragraph(f'{L["seats"]} ({len(bookings)})', s_label)]], colWidths=[CONTENT_W]),
        Spacer(1, 1*mm),
        seats_table,
        totals_row,
        sp,
        row_board_drop,
        sp,
        field_sm(L['bus'], voyage.bus.registration),
        Spacer(1, 3*mm),
        hr_dash,
        footer,
    ]

    doc.build(story)
    buf.seek(0)
    return buf