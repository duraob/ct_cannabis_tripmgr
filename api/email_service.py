"""
Manifest email delivery via Microsoft Graph.

Credentials are entered on the config page and read from GlobalPreference; the client
secret is stored encrypted (see utils/crypto.py). Messages are sent as HTML so the
template can carry formatting and links.
"""

import base64
import logging

import msal
import requests

from models import db, GlobalPreference, EmailContact, TripOrder

logger = logging.getLogger('api.email_service')

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
GRAPH_USER_URL = "https://graph.microsoft.com/v1.0/users/{sender}"
REQUEST_TIMEOUT = 30


def _preference(key):
    row = db.session.query(GlobalPreference).filter_by(preference_key=key).first()
    return row.preference_value if row else ''


def _credentials():
    """Azure app credentials from config. Raises when the app has not been set up."""
    from utils.crypto import decrypt

    tenant_id = _preference('azure_tenant_id')
    client_id = _preference('azure_client_id')
    sender = _preference('azure_sender_email')
    secret = _preference('azure_client_secret')

    missing = [name for name, value in [
        ('tenant ID', tenant_id), ('client ID', client_id),
        ('sender email', sender), ('client secret', secret),
    ] if not value]
    if missing:
        raise Exception(f"Email is not configured - missing {', '.join(missing)} on the config page")

    return tenant_id, client_id, sender, decrypt(secret)


def get_access_token():
    """Acquire an application token for Microsoft Graph."""
    tenant_id, client_id, _, secret = _credentials()

    client = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=secret,
    )
    result = client.acquire_token_for_client(scopes=GRAPH_SCOPE)

    if "access_token" not in result:
        raise Exception(
            f"Azure token request failed: {result.get('error_description', result.get('error', 'unknown error'))}"
        )
    return result["access_token"]


def test_connection():
    """Check the Azure setup without sending anything.

    The three ways this breaks fail at different points and look nothing alike, so
    each is checked separately: a bad secret fails at login, a missing Mail.Send
    grant only shows up as a 403 at send time, and an unreachable sender mailbox
    fails even when both of those are correct.
    """
    import base64 as _b64
    import json as _json

    checks = []

    tenant_id, client_id, sender, secret = _credentials()
    checks.append({'name': 'Credentials present', 'ok': True,
                   'detail': f"tenant {tenant_id[:8]}..., client {client_id[:8]}..., sender {sender}"})

    # 1. Does the secret authenticate?
    client = msal.ConfidentialClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=secret,
    )
    result = client.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        detail = str(result.get('error_description') or result.get('error') or 'unknown error').split('\r')[0]
        if 'AADSTS7000215' in detail:
            detail = ("Invalid client secret. Azure truncates the Value column on screen - use the "
                      "copy button when creating the secret, and check it is 40 characters. "
                      "Do not use the Secret ID.")
        elif 'AADSTS700016' in detail:
            detail = "Application not found in this tenant - check the Client ID and Tenant ID match the same app."
        checks.append({'name': 'Azure sign-in', 'ok': False, 'detail': detail})
        return {'success': False, 'checks': checks}

    token = result['access_token']

    # 2. Was Mail.Send actually granted? Read it off the token's roles claim.
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    claims = _json.loads(_b64.urlsafe_b64decode(payload))
    roles = claims.get('roles', [])
    app_name = claims.get('app_displayname', client_id)
    checks.append({'name': 'Azure sign-in', 'ok': True, 'detail': f"authenticated as app '{app_name}'"})

    has_mail_send = 'Mail.Send' in roles
    checks.append({
        'name': 'Mail.Send permission',
        'ok': has_mail_send,
        'detail': (f"granted (roles: {', '.join(roles)})" if has_mail_send else
                   "NOT granted. Add Microsoft Graph > Application permissions > Mail.Send to this app "
                   "and click 'Grant admin consent'. "
                   + (f"Current roles: {', '.join(roles)}" if roles else "This app has no application permissions.")),
    })

    # 3. Can Graph actually see the sender mailbox?
    response = requests.get(
        GRAPH_USER_URL.format(sender=sender),
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT,
    )
    # Reading a user requires User.Read.All, which sending does not. An app with only
    # Mail.Send gets a 403 here and still sends perfectly well, so that case is reported
    # as unverified rather than failed - calling a working setup broken sends people
    # chasing a permission they do not need.
    check = {'name': 'Sender mailbox'}
    if response.status_code == 200:
        check.update(ok=True, detail=f"{response.json().get('displayName', sender)} <{sender}>")
    elif response.status_code == 403:
        check.update(ok=False, warn=True,
                     detail=(f"Could not verify '{sender}' - this app cannot read the directory "
                             "(needs User.Read.All). Sending is unaffected; Mail.Send is what matters."))
    elif response.status_code == 404:
        check.update(ok=False, detail=f"No mailbox found for '{sender}' in this tenant - check the sender address.")
    else:
        check.update(ok=False, detail=f"Graph returned {response.status_code}: {response.text[:150]}")
    checks.append(check)

    # A warning is not a failure - only hard failures block sending.
    return {'success': all(c['ok'] or c.get('warn') for c in checks), 'checks': checks}


def get_recipients(trip_order):
    """(to, cc) addresses for a stop.

    'to' comes from the contacts on that dispensary's location mapping; 'cc' is the
    internal staff list, which applies to every send.
    """
    to_addresses = []
    if trip_order.location_mapping_id:
        contacts = db.session.query(EmailContact).filter_by(
            location_mapping_id=trip_order.location_mapping_id, is_active=True
        ).all()
        to_addresses = [c.email for c in contacts]

    internal = db.session.query(EmailContact).filter_by(
        location_mapping_id=None, is_active=True
    ).all()

    return to_addresses, [c.email for c in internal]


def render_template_text(text, trip_order):
    """Substitute the placeholders the config page documents."""
    trip = trip_order.trip
    vendor = trip_order.vendor

    values = {
        'order_id': trip_order.order_id or '',
        'manifest_id': trip_order.manifest_id or '',
        'customer_name': vendor.name if vendor else '',
        'stop_number': str(trip_order.sequence_order or ''),
        'delivery_date': trip.delivery_date.strftime('%b %d, %Y') if trip and trip.delivery_date else '',
    }

    for placeholder, value in values.items():
        text = text.replace('{' + placeholder + '}', value)
    return text


def send_manifest_email(trip_order_id, subject, body_html, to_addresses, cc_addresses):
    """Send the manifest PDF for one stop. Returns the recipient counts."""
    from utils.manifest_pdf import build_manifest_pdf

    trip_order = db.session.get(TripOrder, trip_order_id)
    if not trip_order:
        raise Exception(f"Trip order {trip_order_id} not found")
    if not to_addresses:
        raise Exception("No recipients - add contacts for this dispensary on the mapping page")

    token = get_access_token()
    _, _, sender, _ = _credentials()

    pdf = build_manifest_pdf(trip_order_id)
    filename = f"manifest_{trip_order.manifest_id}.pdf"

    message = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to_addresses],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in cc_addresses],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(pdf).decode(),
            }],
        },
        "saveToSentItems": True,
    }

    response = requests.post(
        GRAPH_SEND_URL.format(sender=sender),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=message,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 202:
        logger.error(f"Graph sendMail failed ({response.status_code}): {response.text}")
        raise Exception(f"Microsoft Graph rejected the message ({response.status_code}): {response.text}")

    logger.info(
        f"Manifest email sent for trip order {trip_order_id}",
        extra={'extra_fields': {
            'trip_order_id': trip_order_id,
            'manifest_id': trip_order.manifest_id,
            'to_count': len(to_addresses),
            'cc_count': len(cc_addresses),
        }}
    )
    return {'to_count': len(to_addresses), 'cc_count': len(cc_addresses)}
