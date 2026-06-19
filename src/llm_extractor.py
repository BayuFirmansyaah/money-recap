"""
Ekstraksi data transaksi dari email bank menggunakan LLM (OpenAI).
Mendukung multi-bank dengan prompt yang disesuaikan per bank.
"""

import json
from typing import Optional

# ── System Prompts ────────────────────────────────────────────────────────────

_BASE_TRANSACTION_PROMPT = """Kamu adalah parser email notifikasi transaksi bank Indonesia.
Ekstrak data transaksi dari email dan kembalikan dalam format JSON.

Field yang harus diisi:
- tipe: jenis transaksi (contoh: "QRIS", "Transfer Keluar", "Top-up", "Debit", "Kredit", "Pembayaran", dll.)
  Gunakan istilah yang paling sesuai dengan isi email. Kembalikan null jika bukan notifikasi transaksi.
- merchant_penerima: nama merchant (QRIS/pembayaran), nama penerima (transfer), atau penyedia jasa (top-up)
- nominal: jumlah nominal transaksi (angka float, tanpa format rupiah)
- biaya: biaya/fee transaksi (angka float, 0 jika tidak ada)
- total: total yang dibayarkan (angka float, biasanya nominal + biaya)
- tanggal: tanggal transaksi format YYYY-MM-DD (bulan numerik 01-12, BUKAN singkatan Jan/Dec)
- jam: jam transaksi format HH:MM:SS
- no_referensi: nomor referensi transaksi (string kosong jika tidak ada)
- keterangan: keterangan atau berita transfer (string kosong jika tidak ada)
- kategori: pilih salah satu berdasarkan merchant/tujuan:
  "Makanan & Minuman", "Transportasi", "Belanja Online", "Kesehatan",
  "Pendidikan", "Hiburan", "Tagihan & Utilitas", "Transfer", "Top-Up", "Lainnya"

Aturan kategori:
- Tipe transfer (keluar/masuk antar rekening) → "Transfer"
- Tipe top-up/isi saldo → "Top-Up"
- QRIS/pembayaran: tentukan dari nama merchant

Jika email bukan notifikasi transaksi bank, kembalikan: {"tipe": null}
Semua nilai nominal/biaya/total harus berupa angka (float), bukan string."""

MANDIRI_PROMPT = f"""Konteks: Email notifikasi transaksi Livin by Mandiri.
Tipe transaksi umum: QRIS, Transfer Keluar, Top-up.

{_BASE_TRANSACTION_PROMPT}"""

GENERIC_BANK_PROMPT = _BASE_TRANSACTION_PROMPT

PAYROLL_PROMPT = """Kamu adalah parser email notifikasi payroll dari Mandiri Cash Management (mcm@bankmandiri.co.id).
Email berisi notifikasi transfer gaji masuk (Priority Payroll).

Ekstrak data dan kembalikan dalam format JSON:
- tanggal: format YYYY-MM-DD dengan bulan numerik 01-12 (contoh: 2024-12-30, BUKAN 2024-Dec-30)
- jam: format HH:MM:SS (sudah GMT+7, tidak perlu konversi)
- pengirim: nama perusahaan pengirim (Sender Name / Nama Pengirim)
- bank_penerima: nama bank penerima (Beneficiary Bank Name)
- no_rekening: nomor rekening saja tanpa nama (digits only, dari "NO_REK - IDR - NAMA")
- nama_penerima: nama penerima saja (dari format "NO_REK - IDR - NAMA PENERIMA")
- jumlah: jumlah transfer sebagai float IDR tanpa pemisah ribuan (contoh: "IDR 8,206,506.00" → 8206506.0)
- berita: Payment Detail / Berita (string kosong jika "-")
- berita_tambahan: Extended Payment Detail / Berita Tambahan (string kosong jika "-")

Jika bukan email payroll Mandiri, kembalikan: {"valid": false}
Jika berhasil, tambahkan "valid": true."""


# ── Client Factory ────────────────────────────────────────────────────────────

def get_openai_client(api_key: Optional[str] = None):
    """
    Buat OpenAI client.
    Priority: parameter api_key → DB config → environment variable.
    """
    import os
    from openai import OpenAI

    if not api_key:
        from src.config import get_ai_config
        ai_cfg = get_ai_config()
        api_key = ai_cfg.get('api_key') or os.environ.get('OPENAI_API_KEY', '')

    if not api_key:
        raise ValueError(
            "API key AI tidak ditemukan.\n"
            "Atur melalui halaman Settings di dashboard, atau set OPENAI_API_KEY di .env"
        )
    return OpenAI(api_key=api_key)


def _get_model() -> str:
    """Ambil model yang dikonfigurasi dari DB, default gpt-4o-mini."""
    try:
        from src.config import get_ai_config
        return get_ai_config().get('model', 'gpt-4o-mini') or 'gpt-4o-mini'
    except Exception:
        return 'gpt-4o-mini'


# ── Extraction Functions ──────────────────────────────────────────────────────

def ekstrak_transaksi(email_data: dict, client=None, bank_id: str = 'mandiri') -> Optional[dict]:
    """
    Ekstrak data transaksi dari email menggunakan LLM.
    bank_id digunakan untuk memilih prompt yang sesuai dan dilampirkan ke hasil.
    Returns dict transaksi atau None jika gagal/bukan transaksi.
    """
    if client is None:
        client = get_openai_client()

    body = email_data.get('body', '')
    if not body:
        return None

    subject = email_data.get('subject', '')
    system_prompt = MANDIRI_PROMPT if bank_id == 'mandiri' else GENERIC_BANK_PROMPT

    # Tambahkan bank hint jika bukan Mandiri
    if bank_id != 'mandiri':
        from src.banks import get_bank
        bank = get_bank(bank_id)
        if bank and bank.prompt_hint:
            system_prompt = f"Konteks: {bank.prompt_hint}\n\n{_BASE_TRANSACTION_PROMPT}"

    user_content = f"Subject: {subject}\n\nBody:\n{body[:4000]}"

    try:
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        result = json.loads(response.choices[0].message.content)

        if not result.get('tipe'):
            return None

        result['gmail_id']        = email_data['id']
        result['email_timestamp'] = email_data.get('timestamp', 0)
        result['bank']            = bank_id
        return result

    except Exception as e:
        print(f"  ⚠️  LLM error [{email_data.get('id', '?')}]: {e}")
        return None


def ekstrak_payroll(email_data: dict, client=None) -> Optional[dict]:
    """
    Ekstrak data payroll dari email Mandiri Cash Management.
    Returns dict payroll atau None jika gagal/bukan payroll.
    """
    if client is None:
        client = get_openai_client()

    body = email_data.get('body', '')
    if not body:
        return None

    user_content = f"Subject: {email_data.get('subject', '')}\n\nBody:\n{body[:4000]}"

    try:
        response = client.chat.completions.create(
            model=_get_model(),
            messages=[
                {"role": "system", "content": PAYROLL_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        result = json.loads(response.choices[0].message.content)

        if not result.get('valid') or not result.get('jumlah'):
            return None

        result.pop('valid', None)
        result['gmail_id']        = email_data['id']
        result['email_timestamp'] = email_data.get('timestamp', 0)
        return result

    except Exception as e:
        print(f"  ⚠️  LLM payroll error [{email_data.get('id', '?')}]: {e}")
        return None
