import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ===== Colors =====
INK    = colors.HexColor('#141b2d')
CREAM  = colors.HexColor('#faf6ef')
GOLD   = colors.HexColor('#d4a84c')
MUTED  = colors.HexColor('#6b6558')
LINE   = colors.HexColor('#d9d0bf')
MALE   = colors.HexColor('#3f6da8')
FEMALE = colors.HexColor('#b85685')
SAGE   = colors.HexColor('#7a9a5a')
RUBY   = colors.HexColor('#a83232')


def generate_manifest(voyage, bookings) -> io.BytesIO:
    """
    Generate a printable A4 manifest for a voyage.
    voyage: Voyage model instance with bus and driver loaded.
    bookings: list of confirmed Booking instances.
    """
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )

    content_w = A4[0] - 30*mm

    # ===== Styles =====
    s_brand = ParagraphStyle('brand', fontSize=16, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=20)

    s_subtitle = ParagraphStyle('subtitle', fontSize=8, textColor=MUTED,
        fontName='Helvetica', alignment=TA_LEFT, leading=10)

    s_route = ParagraphStyle('route', fontSize=20, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=24)

    s_meta_label = ParagraphStyle('meta_label', fontSize=6, textColor=GOLD,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=8)

    s_meta_val = ParagraphStyle('meta_val', fontSize=9, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=11)

    s_th = ParagraphStyle('th', fontSize=7, textColor=MUTED,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=9)

    s_td = ParagraphStyle('td', fontSize=8, textColor=INK,
        fontName='Helvetica', alignment=TA_LEFT, leading=10)

    s_td_bold = ParagraphStyle('td_bold', fontSize=8, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=10)

    s_td_right = ParagraphStyle('td_right', fontSize=8, textColor=INK,
        fontName='Helvetica', alignment=TA_RIGHT, leading=10)

    s_td_right_bold = ParagraphStyle('td_right_bold', fontSize=8, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_RIGHT, leading=10)

    s_summary_label = ParagraphStyle('sum_label', fontSize=9, textColor=MUTED,
        fontName='Helvetica', alignment=TA_LEFT, leading=12)

    s_summary_val = ParagraphStyle('sum_val', fontSize=11, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_RIGHT, leading=14)

    s_footer = ParagraphStyle('footer', fontSize=7, textColor=MUTED,
        fontName='Helvetica', alignment=TA_CENTER, leading=9)

    # ===== Header =====
    header = Table([[
        Paragraph('SHRISAMARTH TRAVELS', s_brand),
        Paragraph(f'Printed {datetime.now().strftime("%d %b %Y · %H:%M")}', s_subtitle),
    ]], colWidths=[content_w * 0.65, content_w * 0.35])
    header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    # ===== Route =====
    route = f"{voyage.origin}  —  {voyage.destination}"
    dep = voyage.departure_at.strftime('%d %B %Y · %H:%M departure')

    # ===== Meta info row =====
    driver_name = voyage.driver.full_name if voyage.driver else 'Unassigned'
    quarter = content_w / 4

    meta = Table([[
        Table([[Paragraph('BUS', s_meta_label)],
               [Paragraph(voyage.bus.registration, s_meta_val)]],
              colWidths=[quarter]),
        Table([[Paragraph('DRIVER', s_meta_label)],
               [Paragraph(driver_name, s_meta_val)]],
              colWidths=[quarter]),
        Table([[Paragraph('TOTAL SEATS', s_meta_label)],
               [Paragraph(str(voyage.bus.total_seats), s_meta_val)]],
              colWidths=[quarter]),
        Table([[Paragraph('BOOKED', s_meta_label)],
               [Paragraph(f'{len(bookings)} ({round(len(bookings)/voyage.bus.total_seats*100) if voyage.bus.total_seats else 0}%)', s_meta_val)]],
              colWidths=[quarter]),
    ]], colWidths=[quarter]*4)

    # ===== Passenger table =====
    # Sort by boarding stop_order, then seat as tiebreaker
    boarding_order = {s.stop_name: s.stop_order
                      for s in voyage.stops if s.stop_type == 'boarding'}

    def manifest_sort(b):
        stop_pos = boarding_order.get(b.boarding_point, 999)
        seat = b.seat_id
        seat_key = (1, int(seat)) if seat.isdigit() else (0, seat)
        return (stop_pos,) + seat_key

    sorted_bookings = sorted(bookings, key=manifest_sort)

    # Table header
    col_widths = [12*mm, 45*mm, 30*mm, 25*mm, 25*mm, 20*mm, 23*mm]

    table_data = [[
        Paragraph('#', s_th),
        Paragraph('PASSENGER', s_th),
        Paragraph('CONTACT', s_th),
        Paragraph('BOARDING', s_th),
        Paragraph('DROPPING', s_th),
        Paragraph('FARE', s_th),
        Paragraph('BALANCE', s_th),
    ]]

    total_fare = 0
    total_advance = 0
    total_balance = 0

    for b in sorted_bookings:
        fare = int(b.fare or 0)
        advance = int(b.advance_paid or 0)
        balance = int(b.balance_due or 0)
        total_fare += fare
        total_advance += advance
        total_balance += balance

        # Color-code balance
        bal_style = s_td_right
        if balance > 0:
            bal_style = ParagraphStyle('bal_due', parent=s_td_right,
                textColor=RUBY)
        else:
            bal_style = ParagraphStyle('bal_paid', parent=s_td_right,
                textColor=SAGE)

        gender_marker = '♂' if b.gender == 'M' else '♀'

        table_data.append([
            Paragraph(f'{b.seat_id}', s_td_bold),
            Paragraph(f'{gender_marker} {b.passenger_name}', s_td),
            Paragraph(b.passenger_phone or '', s_td),
            Paragraph(b.boarding_point or '', s_td),
            Paragraph(b.dropping_point or '', s_td),
            Paragraph(f'₹{fare}', s_td_right),
            Paragraph(f'₹{balance}' if balance > 0 else '✓ Paid', bal_style),
        ])

    passenger_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Alternate row shading
    table_style = [
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, LINE),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, LINE),
    ]

    for i in range(1, len(table_data)):
        if i % 2 == 0:
            table_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor('#f3ecdf')))

    passenger_table.setStyle(TableStyle(table_style))

    # ===== Summary row =====
    summary = Table([[
        Table([[Paragraph('TOTAL FARE', s_meta_label)],
               [Paragraph(f'₹ {total_fare}', s_summary_val)]],
              colWidths=[content_w/3]),
        Table([[Paragraph('COLLECTED', s_meta_label)],
               [Paragraph(f'₹ {total_advance}', s_summary_val)]],
              colWidths=[content_w/3]),
        Table([[Paragraph('OUTSTANDING', s_meta_label)],
               [Paragraph(f'₹ {total_balance}', s_summary_val)]],
              colWidths=[content_w/3]),
    ]], colWidths=[content_w/3]*3)

    summary.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f3ecdf')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))

    # ===== Signature line =====
    sig = Table([[
        Paragraph('Driver signature: ___________________', s_footer),
        Paragraph('Supervisor: ___________________', s_footer),
    ]], colWidths=[content_w/2, content_w/2])

    # ===== Build =====
    hr = HRFlowable(width='100%', thickness=0.4, color=LINE, spaceAfter=3*mm)
    sp = Spacer(1, 3*mm)

    story = [
        header,
        Spacer(1, 2*mm),
        Paragraph(route, s_route),
        Paragraph(dep, s_subtitle),
        sp,
        hr,
        meta,
        sp,
        hr,
        passenger_table,
        sp,
        summary,
        Spacer(1, 8*mm),
        sig,
    ]

    doc.build(story)
    buf.seek(0)
    return buf