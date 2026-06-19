"""
Konfigurasi bank yang didukung.
Tambahkan BankConfig baru di sini untuk menambah dukungan bank.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BankConfig:
    id: str
    name: str
    senders: List[str]         # Email sender addresses
    gmail_query: str           # Full Gmail query (jika diset, override sender-based query)
    subject_keywords: str      # Kata kunci tambahan untuk subject (opsional)
    prompt_hint: str           # Context hint untuk LLM parser
    tipe_transaksi: List[str]  # Contoh tipe transaksi dari bank ini


# ─── Registry Bank ────────────────────────────────────────────────────────────

BANKS: dict = {
    'mandiri': BankConfig(
        id='mandiri',
        name='Bank Mandiri (Livin)',
        senders=['noreply.livin@bankmandiri.co.id'],
        gmail_query='',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi Livin by Mandiri. Tipe umum: QRIS, Transfer Keluar, Top-up.',
        tipe_transaksi=['QRIS', 'Transfer Keluar', 'Top-up'],
    ),
    'bca': BankConfig(
        id='bca',
        name='Bank BCA (myBCA / KlikBCA)',
        senders=['e-statement@bca.co.id', 'bcaid@bca.co.id', 'halobca@bca.co.id'],
        gmail_query='(from:bca.co.id) (subject:"Notifikasi Transaksi" OR subject:"e-Statement" OR subject:"transaksi")',
        subject_keywords='Notifikasi Transaksi',
        prompt_hint='Notifikasi transaksi BCA dari myBCA atau KlikBCA.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS', 'Pembayaran'],
    ),
    'bri': BankConfig(
        id='bri',
        name='Bank BRI (BRImo)',
        senders=['bri_care@bri.co.id', 'noreply@bri.co.id', 'estatement@bri.co.id'],
        gmail_query='(from:bri.co.id) subject:"Notifikasi Transaksi"',
        subject_keywords='Notifikasi Transaksi',
        prompt_hint='Notifikasi transaksi BRI melalui BRImo.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
    'bni': BankConfig(
        id='bni',
        name='Bank BNI',
        senders=['bnicall@bni.co.id', 'no-reply@bni.co.id', 'e-statement@bni.co.id'],
        gmail_query='(from:bni.co.id)',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi BNI via mobile banking atau internet banking.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
    'bsi': BankConfig(
        id='bsi',
        name='Bank Syariah Indonesia (BSI)',
        senders=['no-reply@bankbsi.co.id', 'contact@bankbsi.co.id'],
        gmail_query='(from:bankbsi.co.id)',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi BSI Mobile (Bank Syariah Indonesia).',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
    'jago': BankConfig(
        id='jago',
        name='Bank Jago',
        senders=['tanya@jago.com', 'noreply@jago.com'],
        gmail_query='(from:jago.com) (subject:"Kantong" OR subject:"Uang Masuk" OR subject:"Uang Keluar" OR subject:"Transfer")',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi Bank Jago. Fitur utama: Kantong, Uang Masuk, Uang Keluar.',
        tipe_transaksi=['Uang Keluar', 'Uang Masuk', 'Transfer', 'QRIS'],
    ),
    'blu': BankConfig(
        id='blu',
        name='Blu by BCA Digital',
        senders=['haloblu@blubybca.id'],
        gmail_query='(from:blubybca.id)',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi Blu by BCA Digital.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
    'seabank': BankConfig(
        id='seabank',
        name='SeaBank',
        senders=['cs@seabank.co.id'],
        gmail_query='(from:seabank.co.id)',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi SeaBank.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
    'allo': BankConfig(
        id='allo',
        name='Allo Bank',
        senders=['hi@allobank.com'],
        gmail_query='(from:allobank.com)',
        subject_keywords='',
        prompt_hint='Notifikasi transaksi Allo Bank.',
        tipe_transaksi=['Debit', 'Kredit', 'Transfer', 'QRIS'],
    ),
}


def get_bank(bank_id: str) -> Optional[BankConfig]:
    return BANKS.get(bank_id)


def get_all_banks() -> List[BankConfig]:
    return list(BANKS.values())
