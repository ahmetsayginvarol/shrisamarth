import io
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


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

# ===== Font registration =====
_FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'fonts')
_fonts_registered = False

def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    regular = os.path.join(_FONTS_DIR, 'FreeSans.ttf')
    bold    = os.path.join(_FONTS_DIR, 'FreeSansBold.ttf')
    if os.path.exists(regular):
        pdfmetrics.registerFont(TTFont('FreeSans', regular))
    if os.path.exists(bold):
        pdfmetrics.registerFont(TTFont('FreeSansBold', bold))
    _fonts_registered = True

# ===== Translations =====
_L = {
    'en': {
        'brand':       'SHRISAMARTH TRAVELS',
        'printed':     'Printed',
        'departure':   'departure',
        'bus':         'BUS',
        'driver':      'DRIVER',
        'total_seats': 'TOTAL SEATS',
        'booked':      'BOOKED',
        'col_seat':    '#',
        'col_passenger': 'PASSENGER',
        'col_contact': 'CONTACT',
        'col_boarding': 'BOARDING',
        'col_dropping': 'DROPPING',
        'col_fare':    'FARE',
        'col_balance': 'BALANCE',
        'col_remarks': 'REMARKS',
        'total_fare':  'TOTAL FARE',
        'collected':   'COLLECTED',
        'outstanding': 'OUTSTANDING',
        'driver_sig':  'Driver signature: ___________________',
        'supervisor':  'Supervisor: ___________________',
        'fuel':        'Fuel Usage:',
        'other_exp':   'Other Expenses:',
        'unassigned':  'Unassigned',
    },
    'hi': {
        'brand':       'श्री समर्थ ट्रैवल्स',
        'printed':     'मुद्रित',
        'departure':   'प्रस्थान',
        'bus':         'बस',
        'driver':      'चालक',
        'total_seats': 'कुल सीटें',
        'booked':      'बुक हुई',
        'col_seat':    '#',
        'col_passenger': 'यात्री',
        'col_contact': 'संपर्क',
        'col_boarding': 'बोर्डिंग',
        'col_dropping': 'ड्रॉपिंग',
        'col_fare':    'किराया',
        'col_balance': 'शेष',
        'col_remarks': 'टिप्पणी',
        'total_fare':  'कुल किराया',
        'collected':   'जमा',
        'outstanding': 'बकाया',
        'driver_sig':  'चालक के हस्ताक्षर: ___________________',
        'supervisor':  'पर्यवेक्षक: ___________________',
        'fuel':        'ईंधन उपयोग:',
        'other_exp':   'अन्य खर्च:',
        'unassigned':  'अनिर्धारित',
    },
}


def generate_manifest(voyage, bookings, lang='en') -> io.BytesIO:
    """
    Generate a printable A4 manifest for a voyage.
    voyage:   Voyage model instance with bus and driver loaded.
    bookings: list of confirmed Booking instances.
    lang:     'en' or 'hi'
    """
    _register_fonts()

    lx = _L.get(lang, _L['en'])
    is_hi = (lang == 'hi')

    # Choose font family based on language
    f_regular = 'FreeSans'    if is_hi else 'Helvetica'
    f_bold    = 'FreeSansBold' if is_hi else 'Helvetica-Bold'

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )

    content_w = A4[0] - 30*mm

    # ===== Styles =====
    def sty(name, size, color=INK, font=None, align=TA_LEFT, leading=None, **kw):
        if font is None:
            font = f_regular
        return ParagraphStyle(name, fontSize=size, textColor=color,
            fontName=font, alignment=align,
            leading=leading or size * 1.25, **kw)

    s_brand        = sty('brand',      16, INK,  f_bold,    TA_LEFT,  20)
    s_subtitle     = sty('subtitle',    8, MUTED, f_regular, TA_LEFT,  10)
    s_route        = sty('route',      20, INK,  f_bold,    TA_LEFT,  24)
    s_meta_label   = sty('meta_label',  6, GOLD,  f_bold,    TA_LEFT,   8)
    s_meta_val     = sty('meta_val',    9, INK,  f_bold,    TA_LEFT,  11)
    s_th           = sty('th',          7, MUTED, f_bold,    TA_LEFT,   9)
    s_td           = sty('td',          8, INK,  f_regular, TA_LEFT,  10)
    s_td_bold      = sty('td_bold',     8, INK,  f_bold,    TA_LEFT,  10)
    s_td_right     = sty('td_right',    8, INK,  f_regular, TA_RIGHT, 10)
    s_td_right_bold = sty('td_rb',      8, INK,  f_bold,    TA_RIGHT, 10)
    s_sum_label    = sty('sum_label',   9, MUTED, f_regular, TA_LEFT,  12)
    s_sum_val      = sty('sum_val',    11, INK,  f_bold,    TA_RIGHT, 14)
    s_footer       = sty('footer',      7, MUTED, f_regular, TA_CENTER, 9)
    s_expense_label= sty('exp_label',   8, MUTED, f_bold,    TA_LEFT,  10)

    # ===== Header =====
    header = Table([[
        Paragraph(lx['brand'], s_brand),
        Paragraph(f"{lx['printed']} {datetime.now().strftime('%d %b %Y · %H:%M')}", s_subtitle),
    ]], colWidths=[content_w * 0.65, content_w * 0.35])
    header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('ALIGN',  (1,0), (1,0),   'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    # ===== Route & meta =====
    route = f"{voyage.origin}  —  {voyage.destination}"
    dep   = voyage.departure_at.strftime(f'%d %B %Y · %H:%M {lx["departure"]}')

    driver_name = voyage.driver.full_name if voyage.driver else lx['unassigned']
    quarter = content_w / 4

    meta = Table([[
        Table([[Paragraph(lx['bus'],         s_meta_label)],
               [Paragraph(voyage.bus.registration, s_meta_val)]], colWidths=[quarter]),
        Table([[Paragraph(lx['driver'],      s_meta_label)],
               [Paragraph(driver_name,       s_meta_val)]], colWidths=[quarter]),
        Table([[Paragraph(lx['total_seats'], s_meta_label)],
               [Paragraph(str(voyage.bus.total_seats), s_meta_val)]], colWidths=[quarter]),
        Table([[Paragraph(lx['booked'],      s_meta_label)],
               [Paragraph(f'{len(bookings)} ({round(len(bookings)/voyage.bus.total_seats*100) if voyage.bus.total_seats else 0}%)', s_meta_val)]], colWidths=[quarter]),
    ]], colWidths=[quarter]*4)

    # ===== Passenger table =====
    boarding_order = {s.stop_name: s.stop_order
                      for s in voyage.stops if s.stop_type == 'boarding'}

    def manifest_sort(b):
        stop_pos = boarding_order.get(b.boarding_point, 999)
        seat = b.seat_id
        seat_key = (1, int(seat)) if seat.isdigit() else (0, seat)
        return (stop_pos,) + seat_key

    sorted_bookings = sorted(bookings, key=manifest_sort)

    # Columns: #, Passenger, Contact, Boarding, Dropping, Fare, Balance, Remarks
    col_widths = [11*mm, 40*mm, 28*mm, 22*mm, 22*mm, 18*mm, 20*mm, 26*mm]

    table_data = [[
        Paragraph(lx['col_seat'],      s_th),
        Paragraph(lx['col_passenger'], s_th),
        Paragraph(lx['col_contact'],   s_th),
        Paragraph(lx['col_boarding'],  s_th),
        Paragraph(lx['col_dropping'],  s_th),
        Paragraph(lx['col_fare'],      s_th),
        Paragraph(lx['col_balance'],   s_th),
        Paragraph(lx['col_remarks'],   s_th),
    ]]

    total_fare = total_advance = total_balance = 0

    for b in sorted_bookings:
        fare    = int(b.fare or 0)
        advance = int(b.advance_paid or 0)
        balance = int(b.balance_due or 0)
        total_fare    += fare
        total_advance += advance
        total_balance += balance

        bal_style = ParagraphStyle('bal_due',  parent=s_td_right, textColor=RUBY) \
                    if balance > 0 else \
                    ParagraphStyle('bal_paid', parent=s_td_right, textColor=SAGE)

        gender_marker = '♂' if b.gender == 'M' else '♀'

        table_data.append([
            Paragraph(f'{b.seat_id}', s_td_bold),
            Paragraph(f'{gender_marker} {b.passenger_name}', s_td),
            Paragraph(b.passenger_phone or '', s_td),
            Paragraph(b.boarding_point or '', s_td),
            Paragraph(b.dropping_point or '', s_td),
            Paragraph(f'₹{fare}', s_td_right),
            Paragraph(f'₹{balance}' if balance > 0 else '✓', bal_style),
            Paragraph('', s_td),  # blank Remarks cell
        ])

    passenger_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_style = [
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 3),
        ('RIGHTPADDING',  (0,0), (-1,-1), 3),
        ('LINEBELOW',     (0,0), (-1,0),  0.5, LINE),
        ('LINEBELOW',     (0,-1),(-1,-1), 0.5, LINE),
        # Box the Remarks column so there's a visible write-in area
        ('BOX',           (7,1), (7,-1),  0.4, LINE),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            table_style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor('#f3ecdf')))

    passenger_table.setStyle(TableStyle(table_style))

    # ===== Summary row =====
    third = content_w / 3
    summary = Table([[
        Table([[Paragraph(lx['total_fare'],  s_meta_label)],
               [Paragraph(f'₹ {total_fare}', s_sum_val)]], colWidths=[third]),
        Table([[Paragraph(lx['collected'],   s_meta_label)],
               [Paragraph(f'₹ {total_advance}', s_sum_val)]], colWidths=[third]),
        Table([[Paragraph(lx['outstanding'], s_meta_label)],
               [Paragraph(f'₹ {total_balance}', s_sum_val)]], colWidths=[third]),
    ]], colWidths=[third]*3)
    summary.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#f3ecdf')),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))

    # ===== Expense fields (write-in boxes) =====
    box_w = content_w / 2 - 4*mm
    def write_box(label):
        return Table([[
            Paragraph(label, s_expense_label),
            Paragraph('₹ _____________', s_footer),
        ]], colWidths=[box_w * 0.5, box_w * 0.5])

    expenses = Table([[
        write_box(lx['fuel']),
        write_box(lx['other_exp']),
    ]], colWidths=[content_w/2, content_w/2])
    expenses.setStyle(TableStyle([
        ('BOX',           (0,0), (0,0), 0.5, LINE),
        ('BOX',           (1,0), (1,0), 0.5, LINE),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ('RIGHTPADDING',  (0,0), (-1,-1), 6),
    ]))

    # ===== Signature line =====
    sig = Table([[
        Paragraph(lx['driver_sig'],  s_footer),
        Paragraph(lx['supervisor'],  s_footer),
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
        Spacer(1, 5*mm),
        expenses,
        Spacer(1, 6*mm),
        sig,
    ]

    doc.build(story)
    buf.seek(0)
    return buf
