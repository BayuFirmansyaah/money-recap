"""
Ekstraksi rekening koran Mandiri dari PDF ConsolidatedStatement.
Pipeline: pikepdf (unlock) → pdfplumber (table extract) → normalize.
"""

import io
import re


# ─────────────────────────────────────────────────────────
#  UNLOCK
# ─────────────────────────────────────────────────────────

def unlock_pdf(pdf_bytes, password):
    """Buka PDF berpassword, return bytes yang sudah di-unlock."""
    import pikepdf
    try:
        pdf = pikepdf.open(io.BytesIO(pdf_bytes), password=str(password))
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
    except pikepdf.PasswordError:
        raise ValueError("Password PDF salah. Periksa MANDIRI_PDF_PASSWORD di file .env.")
    except Exception as e:
        raise ValueError(f"Gagal membuka PDF: {e}")


# ─────────────────────────────────────────────────────────
#  AMOUNT PARSER
# ─────────────────────────────────────────────────────────

def _parse_amount(s):
    """
    '300,000.00 D' → (300000.0, 'debit')
    '9,157,156.00'  → (9157156.0, 'kredit')
    Returns (float|None, 'debit'|'kredit'|None)
    """
    if not s:
        return None, None
    s = str(s).strip()
    is_debit = s.upper().endswith('D')
    clean = re.sub(r'[,\s]', '', s.rstrip('DdKk').strip())
    try:
        return float(clean), 'debit' if is_debit else 'kredit'
    except Exception:
        return None, None


def _parse_saldo(s):
    if not s:
        return None
    clean = re.sub(r'[,\s]', '', str(s).strip())
    try:
        return float(clean)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
#  DATE PARSER
# ─────────────────────────────────────────────────────────

def _parse_date(d, year_hint):
    """'01/05' + year 2026 → '2026-05-01'"""
    if not d:
        return None
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', str(d).strip())
    if m:
        day, month = m.groups()
        return f"{year_hint}-{month.zfill(2)}-{day.zfill(2)}"
    return None


# ─────────────────────────────────────────────────────────
#  HEADER / SUMMARY PARSERS
# ─────────────────────────────────────────────────────────

def _extract_header(text):
    """Ekstrak info akun dari teks halaman 1."""
    result = {}

    # No. Rekening: pola XXX-XX-XXXXXXX-X
    m = re.search(r'(\d{3}-\d{2}-\d{7}-\d)', text)
    if m:
        result['no_rekening'] = m.group(1)

    # Nama Produk
    m = re.search(r'(MANDIRI\s+TAB\s+\S+)', text, re.IGNORECASE)
    if m:
        result['nama_produk'] = m.group(1).strip()

    # Cabang
    m = re.search(r'(\d{5}\s*-\s*[A-Z][^\n]+)', text)
    if m:
        result['cabang'] = m.group(1).strip()

    # Periode: "1/05/26 s/d 31/05/26" atau "01/05/2026 s/d 31/05/2026"
    m = re.search(r'(\d{1,2}/\d{2}/(\d{2,4}))\s+s/d\s+(\d{1,2}/\d{2}/\d{2,4})', text)
    if m:
        start_raw, yr_raw, end_raw = m.group(1), m.group(2), m.group(3)
        year = int(yr_raw) + (2000 if len(yr_raw) == 2 else 0)
        result['year_hint'] = year

        def fmt(raw, y):
            parts = raw.split('/')
            if len(parts) == 3:
                d, mo, y2 = parts
                y2 = int(y2) + (2000 if len(y2) == 2 else 0)
                return f"{y2}-{mo.zfill(2)}-{d.zfill(2)}"
            if len(parts) == 2:
                d, mo = parts
                return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
            return None

        result['periode_mulai'] = fmt(start_raw, year)
        result['periode_akhir'] = fmt(end_raw, year)

    return result


def _extract_summary(text):
    """Ekstrak Saldo Awal, Mutasi Kredit/Debit, Saldo Akhir dari seluruh teks."""
    result = {}
    patterns = {
        'saldo_awal':    r'Saldo\s+Awal[^:]*:\s*([\d,]+\.?\d*)',
        'mutasi_kredit': r'Mutasi\s+Kredit[^:]*:\s*([\d,]+\.?\d*)',
        'mutasi_debit':  r'Mutasi\s+Debit[^:]*:\s*([\d,]+\.?\d*)',
        'saldo_akhir':   r'Saldo\s+Akhir[^:]*:\s*([\d,]+\.?\d*)',
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result[key] = float(m.group(1).replace(',', ''))
            except Exception:
                pass
    return result


# ─────────────────────────────────────────────────────────
#  TABLE ROW PARSER
# ─────────────────────────────────────────────────────────

_HEADER_PATTERN = re.compile(
    r'Tanggal|Transaction\s*Date|Debit|Credit|Saldo|Balance|Rincian',
    re.IGNORECASE
)
_SUMMARY_PATTERN = re.compile(
    r'Saldo\s*(Awal|Akhir)|Mutasi\s*(Kredit|Debit)|Previous\s*Balance|Current\s*Balance',
    re.IGNORECASE
)


def _parse_rows(rows, year_hint):
    """
    Konversi baris tabel pdfplumber → list transaksi dict.
    Tiap baris: [tgl, tgl_valuta, rincian, debit_kredit, saldo]
    Baris lanjutan: tgl kosong, rincian diisi (ref/lokasi)
    """
    transactions = []
    current = None

    for row in rows:
        if not row:
            continue
        # Normalise ke 5 kolom
        row = [str(c).strip() if c else '' for c in row]
        while len(row) < 5:
            row.append('')

        tgl, tgl_val, rincian, dk, saldo_str = row[0], row[1], row[2], row[3], row[4]

        # Skip baris header tabel
        if _HEADER_PATTERN.search(tgl) or _HEADER_PATTERN.search(rincian):
            continue
        # Skip baris summary
        if _SUMMARY_PATTERN.search(rincian) or _SUMMARY_PATTERN.search(tgl):
            continue
        # Skip baris "Saldo Awal" di dalam tabel
        if re.match(r'Saldo\s+Awal', rincian, re.IGNORECASE):
            continue

        parsed_date = _parse_date(tgl, year_hint)
        jumlah, tipe = _parse_amount(dk)

        if parsed_date and jumlah is not None:
            # Simpan transaksi sebelumnya
            if current:
                transactions.append(current)

            # Pisah rincian dari pdfplumber yang kadang multi-line (\n)
            lines = [l.strip() for l in rincian.replace('\n', '\n').split('\n') if l.strip()]
            main_desc = lines[0] if lines else rincian
            ref = '\n'.join(lines[1:]) if len(lines) > 1 else ''

            current = {
                'tanggal':        parsed_date,
                'tanggal_valuta': _parse_date(tgl_val, year_hint) or parsed_date,
                'rincian':        main_desc,
                'no_referensi':   ref,
                'tipe':           tipe,
                'jumlah':         jumlah,
                'saldo':          _parse_saldo(saldo_str),
            }
        elif rincian and current:
            # Baris lanjutan — tambah ke referensi
            if current['no_referensi']:
                current['no_referensi'] += '\n' + rincian
            else:
                current['no_referensi'] = rincian

    if current:
        transactions.append(current)

    return transactions


# ─────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────

def ekstrak_rk(pdf_bytes, password, filename=''):
    """
    Ekstrak rekening koran dari PDF bytes Mandiri ConsolidatedStatement.

    Args:
        pdf_bytes: raw bytes PDF
        password:  string password (dari MANDIRI_PDF_PASSWORD)
        filename:  nama file untuk referensi (opsional)

    Returns:
        {
          'statement': { no_rekening, periode_mulai, periode_akhir,
                         saldo_awal, mutasi_kredit, mutasi_debit, saldo_akhir, ... },
          'transaksi': [ { tanggal, rincian, tipe, jumlah, saldo, ... }, ... ]
        }
    """
    import pdfplumber

    # 1. Unlock
    unlocked = unlock_pdf(pdf_bytes, password)

    # 2. Extract text + tables
    all_rows = []
    text_page1 = ''
    text_all = ''

    with pdfplumber.open(io.BytesIO(unlocked)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            if i == 0:
                text_page1 = text
            text_all += text + '\n'

            # extract_tables() returns list of tables; each table is list of rows
            for table in (page.extract_tables() or []):
                all_rows.extend(table)

    # 3. Parse header & summary
    header  = _extract_header(text_page1 or text_all)
    summary = _extract_summary(text_all)
    year_hint = header.get('year_hint', 2026)

    # 4. Parse transaksi
    transaksi = _parse_rows(all_rows, year_hint)

    # 5. Fallback year from filename: ConsolidatedStatement_May_2026.pdf
    if not header.get('year_hint') and filename:
        m = re.search(r'(\d{4})', filename)
        if m:
            year_hint = int(m.group(1))
            # Re-parse with correct year
            transaksi = _parse_rows(all_rows, year_hint)

    statement = {
        'filename':       filename,
        'no_rekening':    header.get('no_rekening', ''),
        'nama_produk':    header.get('nama_produk', ''),
        'cabang':         header.get('cabang', ''),
        'periode_mulai':  header.get('periode_mulai', ''),
        'periode_akhir':  header.get('periode_akhir', ''),
        'valuta':         'IDR',
        'saldo_awal':     summary.get('saldo_awal', 0),
        'mutasi_kredit':  summary.get('mutasi_kredit', 0),
        'mutasi_debit':   summary.get('mutasi_debit', 0),
        'saldo_akhir':    summary.get('saldo_akhir', 0),
    }

    return {'statement': statement, 'transaksi': transaksi}
