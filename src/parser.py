"""
Parser untuk email notifikasi Livin by Mandiri.
Mendukung: QRIS/Pembayaran, Transfer, Top-up
"""

import re
from datetime import datetime
from enum import Enum


class TipeTransaksi(Enum):
    QRIS = "QRIS"
    TRANSFER_KELUAR = "Transfer Keluar"
    TOP_UP = "Top-up"
    TIDAK_DIKENAL = "Tidak Dikenal"


# Kategori otomatis berdasarkan merchant/penerima
KATEGORI_RULES = {
    'makanan & minuman': [
        'roti o', 'kfc', 'mcd', 'mcdonalds', 'burger', 'pizza', 'bakso',
        'warung', 'makan', 'resto', 'restaurant', 'cafe', 'coffee', 'kopi',
        'milk', 'boba', 'sushi', 'ayam', 'geprek', 'nasi', 'mie', 'bakmi',
        'indomaret', 'alfamart', 'lawson', 'minimarket', 'mart', 'food',
        'padang', 'seafood', 'soto', 'gado', 'ketoprak', 'martabak',
        'teh', 'juice', 'es ', 'minuman', 'snack', 'jajan',
    ],
    'transportasi': [
        'grab', 'gojek', 'ojek', 'taxi', 'taksi', 'parkir', 'park',
        'tol', 'bensin', 'bbm', 'pertamina', 'shell', 'spbu',
        'kereta', 'bus', 'angkot', 'transjakarta', 'kai',
    ],
    'belanja online': [
        'shopee', 'tokopedia', 'lazada', 'bukalapak', 'blibli',
        'jd.id', 'zalora', 'tiktok shop', 'shopee pay', 'shopeepay',
    ],
    'kesehatan': [
        'apotek', 'apotik', 'farmasi', 'klinik', 'rs ', 'rumah sakit',
        'dokter', 'puskesmas', 'laboratorium', 'dental', 'optik',
        'kimia farma', 'guardian', 'watson',
    ],
    'pendidikan': [
        'sekolah', 'kampus', 'universitas', 'univ', 'spp', 'bimbel',
        'kursus', 'les ', 'ruangguru', 'zenius', 'udemy',
    ],
    'hiburan': [
        'netflix', 'spotify', 'youtube', 'disney', 'prime video',
        'bioskop', 'cinema', 'cgv', 'xxi', 'game', 'steam',
        'tiktok', 'karaoke',
    ],
    'tagihan & utilitas': [
        'pln', 'listrik', 'pdam', 'air ', 'telkom', 'indihome',
        'internet', 'wifi', 'pascabayar', 'tagihan', 'token', 'pulsa',
        'xl', 'telkomsel', 'im3', 'indosat', 'by.u', 'smartfren',
    ],
    'transfer': [
        # Ini akan otomatis diassign untuk tipe transfer
    ],
    'top-up': [
        # Ini akan otomatis diassign untuk tipe top-up
    ],
}


def parse_nominal(text):
    """Konversi 'Rp 24.000,00' → 24000.0"""
    match = re.search(r'Rp\s*([\d.,]+)', text)
    if not match:
        return 0.0
    nominal_str = match.group(1)
    # Hapus titik sebagai pemisah ribuan, ganti koma desimal dengan titik
    nominal_str = nominal_str.replace('.', '').replace(',', '.')
    try:
        return float(nominal_str)
    except ValueError:
        return 0.0


def parse_tanggal(text):
    """
    Parse tanggal dari berbagai format:
    - '21 Mar 2026' → datetime
    - '15 Jun 2026' → datetime
    """
    bulan_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'mei': 5, 'jun': 6, 'jul': 7,
        'aug': 8, 'agt': 8, 'sep': 9, 'oct': 10,
        'okt': 10, 'nov': 11, 'dec': 12, 'des': 12,
    }

    # Format: DD Mon YYYY
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        year = int(match.group(3))
        month = bulan_map.get(month_str, 1)
        return datetime(year, month, day)

    return None


def parse_jam(text):
    """Ekstrak jam dari format '10:36:26 WIB'"""
    match = re.search(r'(\d{2}:\d{2}:\d{2})\s*WIB', text)
    if match:
        return match.group(1)
    match = re.search(r'(\d{2}:\d{2}:\d{2})', text)
    if match:
        return match.group(1)
    return '00:00:00'


def tentukan_kategori(tipe, merchant_atau_penerima):
    """Tentukan kategori otomatis berdasarkan tipe dan nama merchant/penerima."""
    if tipe == TipeTransaksi.TRANSFER_KELUAR:
        return 'Transfer'
    if tipe == TipeTransaksi.TOP_UP:
        return 'Top-up'

    if not merchant_atau_penerima:
        return 'Lainnya'

    nama_lower = merchant_atau_penerima.lower()
    for kategori, keywords in KATEGORI_RULES.items():
        for kw in keywords:
            if kw in nama_lower:
                return kategori.title()

    return 'Lainnya'


def parse_qris(body):
    """Parse email QRIS/Pembayaran."""
    # Ambil nama merchant (baris setelah 'Penerima')
    merchant = ''
    penerima_match = re.search(r'Penerima\s*\n(.+)', body)
    if penerima_match:
        merchant = penerima_match.group(1).strip()

    # Ambil nominal
    nominal_match = re.search(r'Nominal Transaksi\s*(Rp[\s\d.,]+)', body)
    nominal = parse_nominal(nominal_match.group(1)) if nominal_match else 0.0

    # Ambil tanggal & jam
    tanggal_match = re.search(r'Tanggal\s*([\d\w\s]+)', body)
    tanggal = parse_tanggal(tanggal_match.group(1)) if tanggal_match else None

    jam_match = re.search(r'Jam\s*([\d:]+\s*WIB)', body)
    jam = parse_jam(jam_match.group(1)) if jam_match else '00:00:00'

    # No. Referensi
    ref_match = re.search(r'No\. Referensi\s*(\w+)', body)
    no_ref = ref_match.group(1) if ref_match else ''

    return {
        'tipe': TipeTransaksi.QRIS.value,
        'merchant_penerima': merchant,
        'nominal': nominal,
        'biaya': 0.0,
        'total': nominal,
        'tanggal': tanggal,
        'jam': jam,
        'no_referensi': no_ref,
        'keterangan': '',
        'kategori': tentukan_kategori(TipeTransaksi.QRIS, merchant),
    }


def parse_transfer(body):
    """Parse email Transfer."""
    # Nama penerima
    penerima = ''
    penerima_match = re.search(r'Penerima\s*\n(.+)', body)
    if penerima_match:
        penerima = penerima_match.group(1).strip()

    # Nominal
    nominal_match = re.search(r'Nominal\s*(Rp[\s\d.,]+)', body)
    nominal = parse_nominal(nominal_match.group(1)) if nominal_match else 0.0

    # Tanggal & jam
    tanggal_match = re.search(r'Tanggal\s*([\d\w\s]+)', body)
    tanggal = parse_tanggal(tanggal_match.group(1)) if tanggal_match else None

    jam_match = re.search(r'Jam\s*([\d:]+\s*WIB)', body)
    jam = parse_jam(jam_match.group(1)) if jam_match else '00:00:00'

    # No. referensi & keterangan
    ref_match = re.search(r'No\. Referensi\s*(\w+)', body)
    no_ref = ref_match.group(1) if ref_match else ''

    ket_match = re.search(r'Keterangan\s*(.+)', body)
    keterangan = ket_match.group(1).strip() if ket_match else ''
    if keterangan == '-':
        keterangan = ''

    return {
        'tipe': TipeTransaksi.TRANSFER_KELUAR.value,
        'merchant_penerima': penerima,
        'nominal': nominal,
        'biaya': 0.0,
        'total': nominal,
        'tanggal': tanggal,
        'jam': jam,
        'no_referensi': no_ref,
        'keterangan': keterangan,
        'kategori': tentukan_kategori(TipeTransaksi.TRANSFER_KELUAR, penerima),
    }


def parse_topup(body):
    """Parse email Top-up."""
    # Penyedia jasa
    penyedia = ''
    penyedia_match = re.search(r'Penyedia Jasa\s*\n(.+)', body)
    if penyedia_match:
        penyedia = penyedia_match.group(1).strip()

    # Nominal & biaya
    nominal_match = re.search(r'Nominal Top-up\s*(Rp[\s\d.,]+)', body)
    nominal = parse_nominal(nominal_match.group(1)) if nominal_match else 0.0

    biaya_match = re.search(r'Biaya Transaksi\s*(Rp[\s\d.,]+)', body)
    biaya = parse_nominal(biaya_match.group(1)) if biaya_match else 0.0

    total_match = re.search(r'Total Transaksi\s*(Rp[\s\d.,]+)', body)
    total = parse_nominal(total_match.group(1)) if total_match else (nominal + biaya)

    # Tanggal & jam
    tanggal_match = re.search(r'Tanggal\s*([\d\w\s]+)', body)
    tanggal = parse_tanggal(tanggal_match.group(1)) if tanggal_match else None

    jam_match = re.search(r'Jam\s*([\d:]+\s*WIB)', body)
    jam = parse_jam(jam_match.group(1)) if jam_match else '00:00:00'

    ref_match = re.search(r'No\. Referensi\s*(\w+)', body)
    no_ref = ref_match.group(1) if ref_match else ''

    return {
        'tipe': TipeTransaksi.TOP_UP.value,
        'merchant_penerima': penyedia,
        'nominal': nominal,
        'biaya': biaya,
        'total': total,
        'tanggal': tanggal,
        'jam': jam,
        'no_referensi': no_ref,
        'keterangan': '',
        'kategori': tentukan_kategori(TipeTransaksi.TOP_UP, penyedia),
    }


def parse_email(email_data):
    """
    Entry point: tentukan tipe email dan parse.
    Returns dict transaksi atau None jika tidak bisa diparse.
    """
    subject = email_data.get('subject', '').lower()
    body = email_data.get('body', '')

    if not body:
        return None

    # Deteksi tipe dari subject
    if 'pembayaran berhasil' in subject or 'qris' in subject.lower():
        result = parse_qris(body)
    elif 'transfer berhasil' in subject:
        result = parse_transfer(body)
    elif 'top-up berhasil' in subject or 'top up berhasil' in subject:
        result = parse_topup(body)
    # Fallback: cek isi body
    elif 'Pembayaran Berhasil' in body:
        result = parse_qris(body)
    elif 'Transfer Berhasil' in body:
        result = parse_transfer(body)
    elif 'Top-up Berhasil' in body or 'Top Up Berhasil' in body:
        result = parse_topup(body)
    else:
        return None  # Email tidak dikenal, skip

    if result and result['nominal'] > 0:
        result['gmail_id'] = email_data['id']
        result['email_timestamp'] = email_data['timestamp']
        return result

    return None
