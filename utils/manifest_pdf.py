"""
Connecticut Marijuana Transportation Manifest PDF generation.

Renders one manifest per trip stop (TripOrder), matching the layout BioTrack prints.
Data sources:
  - origin licensee block  -> GlobalPreference (entered on /config)
  - transporters / vehicle -> Driver, Vehicle (synced from BioTrack)
  - destination block      -> Vendor (BioTrack licensed premises) + Customer phone
  - departure/arrival/route-> Trip.route_data segment for this stop
  - item rows              -> TripOrderItem (sublot UID captured at execution)
"""

import json
import logging
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.graphics.barcode import code128
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

from models import db, TripOrder, TripOrderItem, Driver, Vehicle, GlobalPreference

logger = logging.getLogger('utils.manifest_pdf')

# Blank item rows are printed so a driver can hand-write additions, matching the
# BioTrack form. The table is padded out to fill page one, never beyond it - how many
# rows that is depends on how long the travel route text runs.
MAX_ITEM_ROWS = 15

GRID = colors.HexColor('#000000')
SHADE = colors.HexColor('#D9D9D9')

# Every table is laid out against a 7.5in x 10in content area. SimpleDocTemplate's frame
# adds 6pt of padding on each side, so the page margin is set 6pt short of half an inch
# to make the usable area exactly that - otherwise the fitting maths below is wrong by
# 12pt in each direction and the item table silently spills onto a second page.
FRAME_PADDING = 6
PAGE_MARGIN = 0.5 * inch - FRAME_PADDING
CONTENT_WIDTH = 7.5 * inch
CONTENT_HEIGHT = 10 * inch

_LABEL = ParagraphStyle('label', fontName='Helvetica-Bold', fontSize=8, leading=9.5)
_HEAD = ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=8, leading=9.5, alignment=TA_CENTER)
_VALUE = ParagraphStyle('value', fontName='Helvetica', fontSize=8, leading=9.5, alignment=TA_CENTER)
_TITLE = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=11, leading=13, alignment=TA_CENTER)
_SMALL = ParagraphStyle('small', fontName='Helvetica', fontSize=7.5, leading=9, alignment=TA_CENTER)
_ROUTE = ParagraphStyle('route', fontName='Helvetica', fontSize=7.5, leading=9.5, alignment=TA_CENTER)


def _text(value):
    """Prepare arbitrary stored text for a Paragraph.

    Paragraph parses its input as markup, so '&' in a product name would break the
    render, and newlines from the config textarea would collapse onto one line.
    """
    return escape(str(value) if value is not None else '').replace('\n', '<br/>')


def _flowing_text(value):
    """Escape text and collapse its line breaks so it wraps as a paragraph.

    Google Maps returns one route step per line. Honouring those breaks makes the
    route block as tall as the route has steps, which pushes the item table down and
    can spill onto a second page for no reason. Wrapping matches the printed form,
    where the route runs as continuous prose.
    """
    return ' '.join(escape(str(value) if value is not None else '').split())


def _pref(key):
    """Read a GlobalPreference value, escaped for the PDF. Empty string when unset."""
    row = db.session.query(GlobalPreference).filter_by(preference_key=key).first()
    return _text(row.preference_value) if row else ''


def _fmt_ts(timestamp):
    """Unix timestamp -> 'MM-DD-YYYY HH:MM:SS' in Eastern, as printed on the manifest."""
    if not timestamp:
        return ''
    from utils.timezone import convert_utc_to_est
    return convert_utc_to_est(datetime.utcfromtimestamp(int(timestamp))).strftime('%m-%d-%Y %H:%M:%S')


def _route_segment(trip, trip_order):
    """The Google Maps segment for this stop, keyed by sequence."""
    if not trip.route_data:
        return None
    try:
        segments = json.loads(trip.route_data)
    except json.JSONDecodeError:
        logger.warning(f"Trip {trip.id} has unparseable route_data")
        return None
    index = trip_order.sequence_order - 1
    return segments[index] if 0 <= index < len(segments) else None


def _vehicle_description(vehicle):
    """'2021 White Dodge Ram Promaster BL73032' from the synced vehicle record."""
    parts = [vehicle.year, vehicle.color, vehicle.make, vehicle.model, vehicle.plate]
    return _text(' '.join(p for p in parts if p))


def _numbered(first, second):
    """Two transporter values stacked as '#1: x' / '#2: y'."""
    return f"#1: {_text(first)}<br/>#2: {_text(second)}"


def _checkbox():
    """An empty box for the 'Received' column, drawn rather than a glyph so it
    renders with the core PDF fonts."""
    box = Table([['']], colWidths=[7], rowHeights=[7])
    box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, GRID)]))
    return box


def _header_table(trip_order, trip, driver1, driver2, vehicle):
    """Origin licensee, vehicle, transporters, and the manifest barcode."""
    manifest_id = trip_order.manifest_id or ''

    barcode_cell = ''
    if manifest_id:
        barcode = code128.Code128(manifest_id, barHeight=0.42 * inch, barWidth=0.011 * inch, humanReadable=False)
        barcode_cell = [barcode, Spacer(1, 2), Paragraph(manifest_id, _SMALL)]

    origin_address = _pref('manifest_origin_address')
    delivery_date = trip.delivery_date.strftime('%b %d, %Y') if trip.delivery_date else ''

    rows = [
        [Paragraph('Date:', _LABEL), Paragraph(delivery_date, _VALUE),
         Paragraph("Licensee's License #:", _LABEL), Paragraph(_pref('manifest_origin_license'), _VALUE),
         Paragraph('Barcode', _TITLE)],

        [Paragraph("Licensee's<br/>Name:", _LABEL), Paragraph(_pref('manifest_origin_name'), _VALUE),
         Paragraph('Vehicle ID #:', _LABEL), Paragraph(_text(vehicle.vin), _VALUE),
         barcode_cell],

        [Paragraph("Licensee's<br/>Address:", _LABEL), Paragraph(origin_address, _VALUE),
         Paragraph('Vehicle Color /<br/>Make /<br/>Model / License<br/>Plate:', _LABEL),
         Paragraph(_vehicle_description(vehicle), _VALUE), ''],

        ['', '', Paragraph("Transporter's<br/>Name:", _LABEL),
         Paragraph(_numbered(driver1.name, driver2.name), _VALUE), ''],

        [Paragraph("Licensee's Phone:", _LABEL), Paragraph(_pref('manifest_origin_phone'), _VALUE),
         Paragraph("Transporter's Date<br/>of Birth:", _LABEL),
         Paragraph(_numbered(driver1.dob, driver2.dob), _VALUE), ''],

        [Paragraph('Transporter<br/>ID:', _LABEL),
         Paragraph(_numbered(driver1.biotrack_id, driver2.biotrack_id), _VALUE),
         Paragraph("Transporter's<br/>Signature:", _LABEL), '', ''],

        ['', '', Paragraph("Transporter's<br/>Signature:", _LABEL), '', ''],
    ]

    table = Table(rows, colWidths=[1.0 * inch, 1.55 * inch, 1.25 * inch, 1.75 * inch, 1.95 * inch])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, GRID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (4, 1), (4, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (4, 1), (4, 6)),   # barcode occupies the full right column
        ('SPAN', (0, 2), (0, 3)),   # Licensee's Address label
        ('SPAN', (1, 2), (1, 3)),   # Licensee's Address value
    ]))
    return table


def _stop_table(trip_order, vendor, phone, segment, item_count, stop_total):
    """Destination licensee block plus approximate departure/arrival."""
    bar = Table([[Paragraph(f'Stop {trip_order.sequence_order} of {stop_total} ({item_count} Items)', _LABEL)]],
                colWidths=[7.5 * inch])
    bar.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, GRID),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    address_parts = [vendor.address1, vendor.address2]
    city_line = ', '.join(p for p in [vendor.city, vendor.state] if p)
    if vendor.zip:
        city_line = f"{city_line} {vendor.zip}".strip()
    full_address = '<br/>'.join(_text(p) for p in address_parts + [city_line] if p)

    rows = [
        [Paragraph('Destination Licensee<br/>Name:', _LABEL), Paragraph(_text(vendor.name), _VALUE),
         Paragraph('Approx. Departure<br/>Date/Time:', _LABEL),
         Paragraph(_fmt_ts(segment.get('departure_time')) if segment else '', _VALUE)],

        [Paragraph('Destination License #:', _LABEL), Paragraph(_text(vendor.biotrack_vendor_id), _VALUE),
         Paragraph('Approx. Arrival<br/>Date/Time:', _LABEL),
         Paragraph(_fmt_ts(segment.get('arrival_time')) if segment else '', _VALUE)],

        [Paragraph('Destination Licensee<br/>Address:', _LABEL), Paragraph(full_address, _VALUE), '', ''],

        [Paragraph('Destination Licensee<br/>Phone:', _LABEL), Paragraph(_text(phone), _VALUE), '', ''],
    ]

    table = Table(rows, colWidths=[1.6 * inch, 2.15 * inch, 1.75 * inch, 2.0 * inch])
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (1, -1), 0.75, GRID),
        ('GRID', (2, 0), (3, 1), 0.75, GRID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return bar, table


def _items_table(items, min_rows):
    """The batch/lot table, padded with blank rows like the printed form.

    min_rows only ever adds blank rows; every item is always rendered.
    """
    header = [
        Paragraph('#', _LABEL), Paragraph('Batch / Lot ID', _HEAD),
        Paragraph('Item Description', _HEAD), Paragraph('Shipped', _HEAD),
        Paragraph('Received', _HEAD),
    ]
    rows = [header]

    for index, item in enumerate(items, start=1):
        rows.append([
            Paragraph(str(index), _VALUE),
            Paragraph(_text(item.sublot_barcode_id), _VALUE),
            Paragraph(_text(item.product_name), _VALUE),
            Paragraph(_text(item.quantity) if item.quantity is not None else '', _VALUE),
            _checkbox(),
        ])

    for index in range(len(items) + 1, min_rows + 1):
        rows.append([Paragraph(str(index), _VALUE), '', '', '', ''])

    table = Table(rows, colWidths=[0.4 * inch, 1.9 * inch, 3.2 * inch, 0.9 * inch, 1.1 * inch],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, GRID),
        ('BACKGROUND', (0, 0), (-1, 0), SHADE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return table


def _banner(text, style=_LABEL, shaded=False):
    """Full-width bordered row used for the section headings."""
    table = Table([[Paragraph(text, style)]], colWidths=[7.5 * inch])
    commands = [
        ('GRID', (0, 0), (-1, -1), 0.75, GRID),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if shaded:
        commands.append(('BACKGROUND', (0, 0), (-1, -1), SHADE))
    table.setStyle(TableStyle(commands))
    return table


def build_manifest_pdf(trip_order_id):
    """Render the manifest for one stop and return the PDF bytes.

    Raises if the stop has not been manifested or if required trip data is missing -
    a partially filled regulatory document is worse than no document.
    """
    trip_order = db.session.get(TripOrder, trip_order_id)
    if not trip_order:
        raise Exception(f"Trip order {trip_order_id} not found")
    if not trip_order.manifest_id:
        raise Exception(f"Trip order {trip_order_id} has no manifest ID - execute the trip first")

    trip = trip_order.trip
    driver1 = db.session.get(Driver, trip.driver1_id)
    driver2 = db.session.get(Driver, trip.driver2_id)
    vehicle = db.session.get(Vehicle, trip.vehicle_id)
    if not driver1 or not driver2 or not vehicle:
        raise Exception(f"Trip {trip.id} is missing driver or vehicle records")

    vendor = trip_order.vendor
    if not vendor:
        raise Exception(f"Trip order {trip_order_id} has no destination vendor")

    mapping = trip_order.location_mapping
    phone = mapping.customer.phone if mapping and mapping.customer else ''

    items = db.session.query(TripOrderItem).filter_by(trip_order_id=trip_order.id).order_by(TripOrderItem.id).all()
    stop_total = db.session.query(TripOrder).filter_by(trip_id=trip.id).count()
    segment = _route_segment(trip, trip_order)

    disclaimer = ('* These directions are for planning purposes only. You may find that the suggested route '
                  'takes you outside the State of Connecticut; you must plan your route so that you remain '
                  'within the State of Connecticut at all times.')
    instructions = ('Instructions: If the quantity received is less than the quantity shipped, check the box in '
                    'the appropriate field below and indicate the actual quantity received.')

    def story_for(total_pages):
        """Flowables are consumed by build(), so the story is rebuilt for each pass."""
        title = Table(
            [[Paragraph(f'Connecticut Marijuana Transportation Manifest (Regular) ID<br/>'
                        f'{trip_order.manifest_id}', _TITLE),
              Paragraph(f'Page 1 of {total_pages}', _LABEL)]],
            colWidths=[6.3 * inch, 1.2 * inch],
        )
        title.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.75, GRID),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))

        stop_bar, stop_table = _stop_table(trip_order, vendor, phone, segment, len(items), stop_total)

        footer = Table(
            [[Paragraph(f'Stop , Items 1-{len(items)} of {len(items)}', _LABEL),
              Paragraph(f'Manifest ID {trip_order.manifest_id}', _LABEL)]],
            colWidths=[3.75 * inch, 3.75 * inch],
        )
        footer.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.75, GRID),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

        head = [
            title,
            _header_table(trip_order, trip, driver1, driver2, vehicle),
            Spacer(1, 6),
            stop_bar,
            stop_table,
            _banner(disclaimer, _SMALL),
            _banner('Travel Route:', _TITLE),
            _banner(_flowing_text(segment.get('route', '')) if segment else '', _ROUTE),
            _banner(instructions),
            footer,
        ]

        # Pad the item table out to fill the remaining space on page one. A long travel
        # route leaves room for fewer blank rows, so the count is measured, not assumed.
        remaining = CONTENT_HEIGHT - sum(
            flowable.wrap(CONTENT_WIDTH, CONTENT_HEIGHT)[1] for flowable in head
        )

        min_rows = len(items)
        for candidate in range(MAX_ITEM_ROWS, len(items), -1):
            if _items_table(items, candidate).wrap(CONTENT_WIDTH, remaining)[1] <= remaining:
                min_rows = candidate
                break

        return head + [_items_table(items, min_rows)]

    def render(total_pages):
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
            topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN,
            title=f"Manifest {trip_order.manifest_id}",
        )
        doc.build(story_for(total_pages))
        return buffer.getvalue(), doc.page

    # First pass discovers the real page count so the "Page 1 of N" label is accurate;
    # a long enough item list legitimately runs onto a second sheet.
    _, page_count = render(1)
    pdf, _ = render(page_count)

    logger.info(f"Generated manifest PDF for trip order {trip_order_id} "
                f"({len(items)} items, {page_count} page(s))")
    return pdf
