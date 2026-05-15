import io
import qrcode
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


def generate_ticket(booking) -> io.BytesIO:
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=(TICKET_W, TICKET_H),
        leftMargin=8*mm, rightMargin=8*mm,
        topMargin=6*mm, bottomMargin=6*mm,
    )

    # ===== Styles =====
    s_brand = ParagraphStyle('brand', fontSize=14, textColor=CREAM,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=16)

    s_pass = ParagraphStyle('pass', fontSize=7, textColor=GOLD,
        fontName='Helvetica-Bold', alignment=TA_RIGHT, leading=9,
        spaceAfter=0)

    s_route = ParagraphStyle('route', fontSize=14, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=17)

    s_dep = ParagraphStyle('dep', fontSize=8, textColor=MUTED,
        fontName='Helvetica', alignment=TA_LEFT, leading=10)

    s_label = ParagraphStyle('label', fontSize=6, textColor=GOLD,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=8)

    s_val = ParagraphStyle('val', fontSize=9, textColor=INK,
        fontName='Helvetica-Bold', alignment=TA_LEFT, leading=11)

    s_val_sm = ParagraphStyle('val_sm', fontSize=8, textColor=INK,
        fontName='Helvetica', alignment=TA_LEFT, leading=10)

    s_center = ParagraphStyle('center', fontSize=7, textColor=MUTED,
        fontName='Helvetica', alignment=TA_CENTER, leading=9)

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
          Paragraph('BOARDING PASS', s_pass)]],
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
    gender_label = 'Male' if booking.gender == 'M' else 'Female'
    window_label = 'Window' if booking.is_window else 'Aisle'

    row_seat_gender = Table([[
        Table([[Paragraph('SEAT', s_label)], [Paragraph(f'{booking.seat_id}  ({window_label})', s_val)]],
              colWidths=[half]),
        Table([[Paragraph('GENDER', s_label)], [Paragraph(gender_label, s_val)]],
              colWidths=[half]),
    ]], colWidths=[half, half])

    row_board_drop = Table([[
        Table([[Paragraph('BOARDING', s_label)], [Paragraph(booking.boarding_point, s_val)]],
              colWidths=[half]),
        Table([[Paragraph('DROPPING', s_label)], [Paragraph(booking.dropping_point, s_val)]],
              colWidths=[half]),
    ]], colWidths=[half, half])

    row_money = Table([[
        Table([[Paragraph('FARE', s_label)], [Paragraph(f'₹ {int(booking.fare)}', s_val_sm)]],
              colWidths=[third]),
        Table([[Paragraph('ADVANCE', s_label)], [Paragraph(f'₹ {int(booking.advance_paid or 0)}', s_val_sm)]],
              colWidths=[third]),
        Table([[Paragraph('BALANCE', s_label)], [Paragraph(f'₹ {int(booking.balance_due or 0)}', s_val_sm)]],
              colWidths=[third]),
    ]], colWidths=[third, third, third])

    # ===== QR + footer =====
    verify_url = f"https://shrisamarth.onrender.com/verify/{booking.booking_code}"
    qr_buf = generate_qr(verify_url)
    qr_img = RLImage(qr_buf, width=20*mm, height=20*mm)

    footer = Table([[
        qr_img,
        Table([
            [Paragraph('BOOKING ID', s_label)],
            [Paragraph(booking.booking_code, s_code)],
            [Spacer(1, 2)],
            [Paragraph('Show QR at boarding', s_center)],
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
        field('PASSENGER', booking.passenger_name),
        sp,
        row_seat_gender,
        sp,
        row_board_drop,
        sp,
        row_money,
        sp,
        field_sm('BUS', booking.voyage.bus.registration),
        field_sm('CONTACT', booking.passenger_phone),
        Spacer(1, 3*mm),
        hr_dash,
        footer,
    ]

    doc.build(story)
    buf.seek(0)
    return buf