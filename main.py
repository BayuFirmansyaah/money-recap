"""
Livin Tracker - Main Script

Penggunaan:
  python main.py sync      → ambil email dari semua bank yang aktif
  python main.py dashboard → buka dashboard web (localhost:5050)
  python main.py laporan   → tampilkan statistik pengeluaran
  python main.py list      → tampilkan semua transaksi
  python main.py kategori <id> <kategori>  → koreksi kategori manual
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def format_rupiah(angka):
    if angka is None:
        return 'Rp 0'
    return f"Rp {angka:,.0f}".replace(',', '.')


def save_to_logs(transaksi_list, total_emails, gagal):
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)

    now = datetime.now()
    filename = logs_dir / f"sync_{now.strftime('%Y%m%d_%H%M%S')}.json"

    data = []
    for t in transaksi_list:
        row = dict(t)
        if hasattr(row.get('tanggal'), 'strftime'):
            row['tanggal'] = row['tanggal'].strftime('%Y-%m-%d')
        data.append(row)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'sync_at':        now.isoformat(),
            'total_email':    total_emails,
            'berhasil_parse': len(transaksi_list),
            'gagal_parse':    gagal,
            'transaksi':      data,
        }, f, ensure_ascii=False, indent=2)

    return filename


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_sync():
    """Ambil email dari semua bank aktif dan simpan ke database via LLM."""
    print("=" * 60)
    print("  LIVIN TRACKER — SYNC EMAIL MULTI-BANK")
    print("=" * 60)

    _load_env()

    from src.database import (
        init_db, simpan_transaksi, catat_sync, gmail_id_exists,
        gmail_id_payroll_exists, simpan_payroll,
    )
    from src.gmail_fetcher import (
        get_gmail_service, fetch_all_banks_emails, fetch_payroll_emails,
    )
    from src.llm_extractor import ekstrak_transaksi, ekstrak_payroll, get_openai_client
    from src.config import get_enabled_banks
    from src.banks import get_bank

    init_db()

    print("\n📧 Menghubungkan ke Gmail...")
    service = get_gmail_service()

    enabled_banks = get_enabled_banks()
    bank_names = [get_bank(b).name if get_bank(b) else b for b in enabled_banks]
    print(f"\n🏦 Bank aktif ({len(enabled_banks)}): {', '.join(bank_names)}")

    try:
        client = get_openai_client()
    except ValueError as e:
        print(f"\n❌ {e}")
        return

    # ── FASE 1: Transaksi dari semua bank ──────────────────────────────────
    print(f"\n🔍 Mengambil email dari semua bank...")
    emails = fetch_all_banks_emails(service, enabled_banks)

    if not emails:
        print("Tidak ada email ditemukan dari bank yang aktif.")
    else:
        total = len(emails)
        print(f"\n⚙️  Memproses {total} email dengan LLM...")
        print(f"  {'#':>6}  {'Status':<10}  {'Bank':<10}  {'Tipe':<16}  {'Nominal':>13}  {'Merchant/Penerima':<20}  Tanggal")
        print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*16}  {'-'*13}  {'-'*20}  {'-'*10}")

        baru = skip_db = skip_llm = 0
        transaksi_list = []

        for i, email in enumerate(emails, 1):
            bank_id = email.get('bank_id', 'mandiri')

            if gmail_id_exists(email['id']):
                print(f"  [{i:>5}/{total}]  ⏭️  DB skip   [{bank_id:<8}] (sudah tersimpan)")
                skip_db += 1
                continue

            result = ekstrak_transaksi(email, client, bank_id=bank_id)
            if result:
                tipe     = (result.get('tipe') or '')[:16]
                nominal  = format_rupiah(result.get('total') or 0)
                merchant = (result.get('merchant_penerima') or 'N/A')[:20]
                tanggal  = (result.get('tanggal') or '-')
                print(f"  [{i:>5}/{total}]  ✅ OK        [{bank_id:<8}]  {tipe:<16}  {nominal:>13}  {merchant:<20}  {tanggal}")

                if simpan_transaksi(result) == 'baru':
                    baru += 1
                    transaksi_list.append(result)
            else:
                subject = (email.get('subject', '') or '')[:40]
                print(f"  [{i:>5}/{total}]  ⚠️  LLM skip  [{bank_id:<8}] {subject}")
                skip_llm += 1

        print(f"\n  Tersimpan baru : {baru}")
        print(f"  Skip (DB ada)  : {skip_db}")
        print(f"  Skip (LLM fail): {skip_llm}")

        catat_sync(baru, skip_db + skip_llm, f"Sync {len(enabled_banks)} bank via LLM")

        if transaksi_list:
            log_file = save_to_logs(transaksi_list, total, skip_llm)
            print(f"\n📄 Log transaksi: {log_file}")

    # ── FASE 2: Payroll (Mandiri) ──────────────────────────────────────────
    if 'mandiri' in enabled_banks:
        print(f"\n{'='*60}")
        print("  SYNC PAYROLL — GAJI MASUK (Mandiri)")
        print(f"{'='*60}")

        payroll_emails = fetch_payroll_emails(service)

        if payroll_emails:
            total_p = len(payroll_emails)
            print(f"\n⚙️  Memproses {total_p} email payroll...")
            print(f"  {'#':>5}  {'Status':<10}  {'Tanggal':<12}  {'Pengirim':<24}  Jumlah")
            print(f"  {'-'*5}  {'-'*10}  {'-'*12}  {'-'*24}  {'-'*14}")

            baru_p = skip_db_p = skip_llm_p = 0
            for i, email in enumerate(payroll_emails, 1):
                if gmail_id_payroll_exists(email['id']):
                    print(f"  [{i:>4}/{total_p}]  ⏭️  DB skip   (sudah tersimpan)")
                    skip_db_p += 1
                    continue

                result = ekstrak_payroll(email, client)
                if result:
                    tgl = (result.get('tanggal') or '-')
                    pgm = (result.get('pengirim') or '-')[:24]
                    jml = format_rupiah(result.get('jumlah', 0))
                    print(f"  [{i:>4}/{total_p}]  ✅ OK        {tgl:<12}  {pgm:<24}  {jml}")
                    if simpan_payroll(result) == 'baru':
                        baru_p += 1
                else:
                    subject = (email.get('subject', '') or '')[:40]
                    print(f"  [{i:>4}/{total_p}]  ⚠️  LLM skip  {subject}")
                    skip_llm_p += 1

            print(f"\n  Tersimpan baru : {baru_p}")
            print(f"  Skip (DB ada)  : {skip_db_p}")
            print(f"  Skip (LLM fail): {skip_llm_p}")

    print(f"\n✅ Sync selesai! Database: data/livin_tracker.db")


def cmd_laporan():
    from src.database import get_statistik, init_db
    init_db()
    stats = get_statistik()
    grand = stats['grand']

    print("\n" + "=" * 55)
    print("  LIVIN TRACKER — LAPORAN PENGELUARAN")
    print("=" * 55)

    if not grand['total_transaksi']:
        print("\nBelum ada data. Jalankan: python main.py sync")
        return

    print(f"\n📊 RINGKASAN")
    print(f"  Total transaksi  : {grand['total_transaksi']} transaksi")
    print(f"  Total pengeluaran: {format_rupiah(grand['total_pengeluaran'])}")
    print(f"  Periode          : {grand['tanggal_pertama']} s/d {grand['tanggal_terakhir']}")

    print(f"\n📂 PER TIPE TRANSAKSI")
    print(f"  {'Tipe':<22} {'Jml':>5}  {'Total':>16}")
    print(f"  {'-'*22} {'-'*5}  {'-'*16}")
    for row in stats['per_tipe']:
        print(f"  {row['tipe']:<22} {row['jumlah']:>5}  {format_rupiah(row['total_nominal']):>16}")

    print(f"\n🏷️  PER KATEGORI")
    print(f"  {'Kategori':<22} {'Jml':>5}  {'Total':>16}")
    print(f"  {'-'*22} {'-'*5}  {'-'*16}")
    for row in stats['per_kategori']:
        print(f"  {row['kategori']:<22} {row['jumlah']:>5}  {format_rupiah(row['total_nominal']):>16}")

    print(f"\n📅 PER BULAN")
    print(f"  {'Bulan':<12} {'Jml':>5}  {'Total':>16}")
    print(f"  {'-'*12} {'-'*5}  {'-'*16}")
    for row in stats['per_bulan']:
        bulan = row['bulan'] or 'Tidak diketahui'
        print(f"  {bulan:<12} {row['jumlah']:>5}  {format_rupiah(row['total_nominal']):>16}")

    print()


def cmd_list(limit=50):
    from src.database import get_semua_transaksi, init_db
    init_db()
    transaksi = get_semua_transaksi(order='DESC')

    print("\n" + "=" * 90)
    print("  LIVIN TRACKER — DAFTAR TRANSAKSI (Terbaru)")
    print("=" * 90)

    if not transaksi:
        print("\nBelum ada data. Jalankan: python main.py sync")
        return

    print(f"\n{'#':<5} {'Tanggal':<12} {'Bank':<10} {'Tipe':<16} {'Merchant/Penerima':<23} {'Kategori':<18} {'Total':>14}")
    print(f"{'-'*5} {'-'*12} {'-'*10} {'-'*16} {'-'*23} {'-'*18} {'-'*14}")

    for t in transaksi[:limit]:
        bank     = (t.get('bank') or 'mandiri')[:9]
        merchant = (t['merchant_penerima'] or '')[:22]
        tipe     = (t['tipe'] or '')[:15]
        kategori = (t['kategori'] or '')[:17]
        tanggal  = t['tanggal'] or '-'
        print(f"{t['id']:<5} {tanggal:<12} {bank:<10} {tipe:<16} {merchant:<23} {kategori:<18} {format_rupiah(t['total']):>14}")

    if len(transaksi) > limit:
        print(f"\n  ... dan {len(transaksi) - limit} transaksi lainnya")
    print(f"\n  Total: {len(transaksi)} transaksi")
    print()


def cmd_kategori(args):
    if len(args) < 2:
        print("Penggunaan: python main.py kategori <id_transaksi> <kategori_baru>")
        return
    try:
        from src.database import update_kategori, init_db
        init_db()
        update_kategori(int(args[0]), args[1])
    except ValueError:
        print("ID transaksi harus berupa angka.")


def cmd_dashboard():
    import threading, webbrowser
    from src.dashboard import app
    from src.database import init_db
    init_db()

    port = 5050
    url  = f"http://localhost:{port}"
    print(f"\n🌐 Dashboard siap di: {url}")
    print(f"  ⚙️  Pengaturan:      {url}/settings")
    print("  Tekan Ctrl+C untuk berhenti.\n")

    threading.Thread(target=lambda: (
        __import__('time').sleep(1),
        webbrowser.open(url),
    ), daemon=True).start()

    app.run(port=port, debug=False, use_reloader=False, threaded=True)


def main():
    _load_env()
    args = sys.argv[1:]

    if not args or args[0] == 'help':
        print(__doc__)
        return

    cmd = args[0].lower()

    if   cmd == 'sync':       cmd_sync()
    elif cmd == 'dashboard':  cmd_dashboard()
    elif cmd == 'laporan':    cmd_laporan()
    elif cmd == 'list':       cmd_list()
    elif cmd == 'kategori':   cmd_kategori(args[1:])
    else:
        print(f"Perintah tidak dikenal: '{cmd}'")
        print("Gunakan: sync | dashboard | laporan | list | kategori")


if __name__ == '__main__':
    main()
