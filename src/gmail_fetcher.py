"""
Gmail fetcher — mendukung banyak bank sekaligus.
OAuth credentials dimuat dari database (fallback ke file).
"""

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.banks import BankConfig

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

BASE_DIR = Path(__file__).parent.parent

# Mandiri-specific senders (tetap untuk backward compat payroll & rekening koran)
PAYROLL_SENDER = 'mcm@bankmandiri.co.id'
RK_SENDER      = 'consolidatedstatement@bankmandiri.co.id'


# ── Authentication ────────────────────────────────────────────────────────────

def get_gmail_service():
    """
    Autentikasi ke Gmail dan return service object.
    Credentials dimuat dari DB (fallback ke file untuk backward compat).
    """
    from src.config import (
        get_google_client_config, get_google_token,
        save_google_token, dict_to_creds,
    )

    creds = None

    token_data = get_google_token()
    if token_data:
        creds = dict_to_creds(token_data)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_google_token(creds)
        else:
            client_config = get_google_client_config()
            if not client_config:
                raise FileNotFoundError(
                    "Google credentials tidak ditemukan.\n"
                    "Upload credentials.json melalui halaman Settings di dashboard."
                )
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            save_google_token(creds)

    return build('gmail', 'v1', credentials=creds)


# ── Generic Bank Email Fetcher ────────────────────────────────────────────────

def fetch_bank_emails(
    service,
    bank: BankConfig,
    max_results: int = 99999,
    extra_query: str = '',
) -> List[dict]:
    """
    Ambil email notifikasi untuk satu bank.
    Gunakan bank.gmail_query jika diset, fallback ke sender-based query.
    Returns list of dict: id, subject, date_str, timestamp, body
    """
    if bank.gmail_query:
        query = bank.gmail_query
    else:
        parts = ' OR '.join(f'from:{s}' for s in bank.senders)
        query = f'({parts})'

    if extra_query:
        query += f' {extra_query}'

    print(f"  [{bank.name}] Query: {query[:80]}...")

    all_ids: List[dict] = []
    page_token: Optional[str] = None

    while True:
        kwargs: dict = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token

        result = service.users().messages().list(**kwargs).execute()
        messages = result.get('messages', [])
        if not messages:
            break

        all_ids.extend(messages)
        page_token = result.get('nextPageToken')
        if not page_token or len(all_ids) >= max_results:
            break

    total = len(all_ids)
    if total == 0:
        print(f"  [{bank.name}] Tidak ada email ditemukan.")
        return []

    print(f"  [{bank.name}] {total} email ditemukan, mengambil detail...")

    emails: List[dict] = []
    for i, msg in enumerate(all_ids, 1):
        print(f"  [{bank.name}] [{i:>5}/{total}] Mengambil...", end='\r')
        email_data = get_email_detail(service, msg['id'])
        if email_data:
            emails.append(email_data)

    print(f"  [{bank.name}] [{total}/{total}] Selesai.                              ")

    emails.sort(key=lambda x: x['timestamp'])
    print(f"  [{bank.name}] ✓ {len(emails)} email siap diparse.")
    return emails


def fetch_all_banks_emails(
    service,
    bank_ids: List[str],
    extra_query: str = '',
) -> List[dict]:
    """
    Fetch email dari semua bank dalam bank_ids.
    Returns list of dict dengan tambahan field 'bank_id'.
    """
    from src.banks import get_bank

    all_emails: List[dict] = []
    for bank_id in bank_ids:
        bank = get_bank(bank_id)
        if not bank:
            print(f"  ⚠️  Bank '{bank_id}' tidak dikenal, dilewati.")
            continue
        emails = fetch_bank_emails(service, bank, extra_query=extra_query)
        for e in emails:
            e['bank_id'] = bank_id
        all_emails.extend(emails)

    # Urutkan global berdasarkan timestamp
    all_emails.sort(key=lambda x: x['timestamp'])
    return all_emails


# ── Mandiri-specific Fetchers (tetap untuk payroll & rekening koran) ──────────

def fetch_livin_emails(service, max_results=99999, extra_query=''):
    """
    Ambil email Livin by Mandiri.
    Wrapper untuk backward compat — gunakan fetch_bank_emails() untuk kode baru.
    """
    from src.banks import get_bank
    bank = get_bank('mandiri')
    emails = fetch_bank_emails(service, bank, max_results=max_results, extra_query=extra_query)
    for e in emails:
        e['bank_id'] = 'mandiri'
    return emails


def fetch_payroll_emails(service, max_results=99999, extra_query=''):
    """Ambil email payroll Mandiri Cash Management."""
    query = f'from:{PAYROLL_SENDER} subject:"Priority Payroll"'
    if extra_query:
        query += f' {extra_query}'

    all_ids, page_token = [], None
    while True:
        kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token
        result = service.users().messages().list(**kwargs).execute()
        messages = result.get('messages', [])
        if not messages:
            break
        all_ids.extend(messages)
        page_token = result.get('nextPageToken')
        if not page_token or len(all_ids) >= max_results:
            break

    total = len(all_ids)
    if total == 0:
        print("  Tidak ada email payroll ditemukan.")
        return []

    print(f"  {total} email payroll ditemukan. Mengambil detail...")
    emails = []
    for i, msg in enumerate(all_ids, 1):
        print(f"  [{i:>4}/{total}] Mengambil payroll...", end='\r')
        email_data = get_email_detail(service, msg['id'])
        if email_data:
            emails.append(email_data)

    print(f"  [{total}/{total}] Selesai.                     ")
    emails.sort(key=lambda x: x['timestamp'])
    print(f"  {len(emails)} email payroll siap diproses.")
    return emails


def get_pdf_attachment(service, msg_id):
    """Ambil attachment PDF dari satu email."""
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload']['headers']}

        def find_pdf(payload):
            mime = (payload.get('mimeType') or '').lower()
            is_pdf = 'pdf' in mime or (
                'octet-stream' in mime and (payload.get('filename') or '').lower().endswith('.pdf')
            )
            if is_pdf:
                body = payload.get('body', {})
                fname = payload.get('filename') or 'statement.pdf'
                if body.get('attachmentId'):
                    att = service.users().messages().attachments().get(
                        userId='me', messageId=msg_id, id=body['attachmentId']
                    ).execute()
                    return base64.urlsafe_b64decode(att['data'] + '=='), fname
                if body.get('data'):
                    return base64.urlsafe_b64decode(body['data'] + '=='), fname
            for part in payload.get('parts', []):
                result = find_pdf(part)
                if result[0] is not None:
                    return result
            return None, None

        pdf_bytes, filename = find_pdf(msg['payload'])
        if not pdf_bytes:
            return None

        return {
            'id':        msg_id,
            'subject':   headers.get('Subject', ''),
            'date_str':  headers.get('Date', ''),
            'timestamp': int(msg.get('internalDate', 0)),
            'filename':  filename,
            'pdf_bytes': pdf_bytes,
        }
    except Exception as e:
        print(f"  ⚠️  Gagal ambil PDF {msg_id}: {e}")
        return None


def fetch_rk_emails(service, max_results=99999, extra_query=''):
    """Ambil email rekening koran Mandiri (ConsolidatedStatement)."""
    query = f'from:{RK_SENDER} has:attachment'
    if extra_query:
        query += f' {extra_query}'

    all_ids, page_token = [], None
    while True:
        kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token
        result = service.users().messages().list(**kwargs).execute()
        messages = result.get('messages', [])
        if not messages:
            break
        all_ids.extend(messages)
        page_token = result.get('nextPageToken')
        if not page_token or len(all_ids) >= max_results:
            break

    total = len(all_ids)
    if total == 0:
        print("  Tidak ada email rekening koran ditemukan.")
        return []

    print(f"  {total} email rekening koran ditemukan. Mengambil attachment PDF...")
    emails = []
    for i, msg in enumerate(all_ids, 1):
        print(f"  [{i:>3}/{total}] Mengambil PDF...", end='\r')
        email_data = get_pdf_attachment(service, msg['id'])
        if email_data:
            emails.append(email_data)

    print(f"  [{total}/{total}] Selesai.               ")
    emails.sort(key=lambda x: x['timestamp'])
    print(f"  {len(emails)} email rekening koran siap diproses.")
    return emails


# ── Email Parsing Utilities ───────────────────────────────────────────────────

def get_email_detail(service, msg_id):
    """Ambil detail satu email: subject, tanggal, body teks."""
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        return {
            'id':        msg_id,
            'subject':   headers.get('Subject', ''),
            'date_str':  headers.get('Date', ''),
            'timestamp': int(msg.get('internalDate', 0)),
            'body':      extract_body(msg['payload']),
        }
    except Exception as e:
        print(f"  ⚠️  Gagal ambil email {msg_id}: {e}")
        return None


def html_to_text(html):
    """Konversi HTML email ke teks terstruktur."""
    import re as _re
    html = _re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
    html = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL | _re.IGNORECASE)
    html = _re.sub(r'</p>|</h[1-6]>|</td>|</th>|</tr>|</div>|<br\s*/?>', '\n', html, flags=_re.IGNORECASE)
    html = _re.sub(r'<[^>]+>', '', html)
    html = (html
            .replace('&nbsp;', ' ').replace('&amp;', '&')
            .replace('&lt;', '<').replace('&gt;', '>')
            .replace('&#39;', "'").replace('&quot;', '"'))
    lines = [line.strip() for line in html.splitlines()]
    return '\n'.join(l for l in lines if l)


def _get_part_text(payload, mime_type):
    if payload.get('mimeType') == mime_type:
        data = payload.get('body', {}).get('data', '')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    for part in payload.get('parts', []):
        result = _get_part_text(part, mime_type)
        if result:
            return result
    return ''


def extract_body(payload):
    """Ekstrak teks dari payload email. Prioritas: text/plain → text/html → body langsung."""
    body = _get_part_text(payload, 'text/plain')
    if body:
        return body
    html = _get_part_text(payload, 'text/html')
    if html:
        return html_to_text(html)
    data = payload.get('body', {}).get('data', '')
    if data:
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return ''
