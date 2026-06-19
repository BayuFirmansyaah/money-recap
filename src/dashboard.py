"""
Flask dashboard untuk Livin Tracker.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import sys as _sys

def _get_base_dir() -> Path:
    """Kembalikan base dir yang tepat untuk dev vs frozen .exe."""
    if getattr(_sys, 'frozen', False):
        return Path(_sys._MEIPASS)  # PyInstaller temp dir
    return Path(__file__).parent.parent

BASE_DIR = _get_base_dir()

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _where(year, month, tipe, kategori):
    conds, params = ["1=1"], []
    if year:
        conds.append("strftime('%Y', tanggal) = ?");    params.append(year)
    if month:
        conds.append("strftime('%m', tanggal) = ?");    params.append(month.zfill(2))
    if tipe:
        conds.append("tipe = ?");                       params.append(tipe)
    if kategori:
        conds.append("kategori = ?");                   params.append(kategori)
    return " AND ".join(conds), params


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    from src.database import get_connection
    with get_connection() as conn:
        years = [r[0] for r in conn.execute("""
            SELECT DISTINCT y FROM (
                SELECT strftime('%Y', tanggal) y FROM transaksi WHERE tanggal IS NOT NULL
                UNION
                SELECT strftime('%Y', tanggal) y FROM payroll   WHERE tanggal IS NOT NULL
            ) ORDER BY y DESC
        """).fetchall() if r[0]]
        types = [r[0] for r in conn.execute(
            "SELECT DISTINCT tipe FROM transaksi WHERE tipe IS NOT NULL ORDER BY tipe"
        ).fetchall()]
        categories = [r[0] for r in conn.execute(
            "SELECT DISTINCT kategori FROM transaksi WHERE kategori IS NOT NULL ORDER BY kategori"
        ).fetchall()]
        banks = [r[0] for r in conn.execute(
            "SELECT DISTINCT bank FROM transaksi WHERE bank IS NOT NULL ORDER BY bank"
        ).fetchall()]
    return render_template('dashboard.html', years=years, types=types,
                           categories=categories, banks=banks)


@app.route('/pembayaran')
def page_pembayaran():
    from src.database import init_db
    init_db()
    return render_template('pembayaran.html')


@app.route('/rekening-koran')
def page_rekening_koran():
    from src.database import init_db
    init_db()
    return render_template('rekening_koran.html')


@app.route('/settings')
def page_settings():
    return render_template('settings.html')


# ── API: Transaksi ────────────────────────────────────────────────────────────

@app.route('/api/data')
def api_data():
    from src.database import get_connection
    year     = request.args.get('year', '')
    month    = request.args.get('month', '')
    tipe     = request.args.get('tipe', '')
    kategori = request.args.get('kategori', '')
    bank     = request.args.get('bank', '')

    where, params = _where(year, month, tipe, kategori)
    if bank:
        where += " AND bank = ?"
        params.append(bank)

    with get_connection() as conn:
        kpi = dict(conn.execute(f"""
            SELECT COUNT(*) total_transaksi,
                   COALESCE(SUM(total), 0) total_pengeluaran,
                   COALESCE(AVG(total), 0) rata_rata,
                   MIN(tanggal) tanggal_awal, MAX(tanggal) tanggal_akhir
            FROM transaksi WHERE {where}
        """, params).fetchone())

        per_bulan = [dict(r) for r in conn.execute(f"""
            SELECT strftime('%Y-%m', tanggal) bulan, COUNT(*) jumlah, SUM(total) total
            FROM transaksi WHERE {where} AND tanggal IS NOT NULL
            GROUP BY bulan ORDER BY bulan
        """, params).fetchall()]

        per_kategori = [dict(r) for r in conn.execute(f"""
            SELECT kategori, COUNT(*) jumlah, COALESCE(SUM(total), 0) total
            FROM transaksi WHERE {where}
            GROUP BY kategori ORDER BY total DESC LIMIT 10
        """, params).fetchall()]

        per_tipe = [dict(r) for r in conn.execute(f"""
            SELECT tipe, COUNT(*) jumlah, COALESCE(SUM(total), 0) total
            FROM transaksi WHERE {where}
            GROUP BY tipe ORDER BY total DESC
        """, params).fetchall()]

        per_bank = [dict(r) for r in conn.execute(f"""
            SELECT bank, COUNT(*) jumlah, COALESCE(SUM(total), 0) total
            FROM transaksi WHERE {where}
            GROUP BY bank ORDER BY total DESC
        """, params).fetchall()]

        top_merchant = [dict(r) for r in conn.execute(f"""
            SELECT merchant_penerima, COUNT(*) jumlah, COALESCE(SUM(total), 0) total
            FROM transaksi
            WHERE {where} AND merchant_penerima IS NOT NULL AND merchant_penerima != ''
            GROUP BY merchant_penerima ORDER BY total DESC LIMIT 8
        """, params).fetchall()]

        transaksi = [dict(r) for r in conn.execute(f"""
            SELECT id, tanggal, jam, bank, tipe, merchant_penerima, kategori,
                   nominal, biaya, total, no_referensi, keterangan
            FROM transaksi WHERE {where}
            ORDER BY tanggal DESC, jam DESC LIMIT 500
        """, params).fetchall()]

        pay_where, pay_params = _where(year, month, '', '')
        per_bulan_masuk = [dict(r) for r in conn.execute(f"""
            SELECT strftime('%Y-%m', tanggal) bulan,
                   COUNT(*) jumlah, SUM(jumlah) total
            FROM payroll WHERE {pay_where} AND tanggal IS NOT NULL AND tanggal != ''
            GROUP BY bulan ORDER BY bulan
        """, pay_params).fetchall()]

    return jsonify({
        'kpi': kpi,
        'per_bulan': per_bulan,
        'per_bulan_masuk': per_bulan_masuk,
        'per_kategori': per_kategori,
        'per_tipe': per_tipe,
        'per_bank': per_bank,
        'top_merchant': top_merchant,
        'transaksi': transaksi,
    })


@app.route('/api/payroll')
def api_payroll():
    from src.database import get_payroll_stats
    return jsonify(get_payroll_stats(
        request.args.get('year', ''),
        request.args.get('month', ''),
    ))


# ── API: Pembayaran ───────────────────────────────────────────────────────────

@app.route('/api/pembayaran', methods=['GET'])
def api_pembayaran_list():
    from src.database import get_pembayaran, get_pembayaran_ringkasan
    items     = get_pembayaran(status=request.args.get('status') or None)
    ringkasan = get_pembayaran_ringkasan(proyeksi_bulan=12)
    return jsonify({'items': items, 'ringkasan': ringkasan})


@app.route('/api/pembayaran', methods=['POST'])
def api_pembayaran_create():
    from src.database import simpan_pembayaran
    data = request.get_json()
    if not data or not data.get('nama') or not data.get('nominal'):
        return jsonify({'error': 'nama dan nominal wajib diisi'}), 400
    return jsonify({'id': simpan_pembayaran(data)}), 201


@app.route('/api/pembayaran/<int:item_id>', methods=['PUT'])
def api_pembayaran_update(item_id):
    from src.database import update_pembayaran
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Body kosong'}), 400
    update_pembayaran(item_id, data)
    return jsonify({'ok': True})


@app.route('/api/pembayaran/<int:item_id>', methods=['DELETE'])
def api_pembayaran_delete(item_id):
    from src.database import hapus_pembayaran
    hapus_pembayaran(item_id)
    return jsonify({'ok': True})


# ── API: Rekening Koran ───────────────────────────────────────────────────────

@app.route('/api/rekening-koran')
def api_rekening_koran():
    from src.database import get_rk_data, get_rk_statements
    data = get_rk_data(
        request.args.get('year') or None,
        request.args.get('month') or None,
    )
    return jsonify({'statements': get_rk_statements(), **data})


# ── API: Settings ─────────────────────────────────────────────────────────────

@app.route('/api/settings/google', methods=['GET'])
def api_settings_google_get():
    from src.config import has_google_credentials, has_google_token, get_google_client_id
    return jsonify({
        'has_credentials': has_google_credentials(),
        'has_token':       has_google_token(),
        'client_id':       get_google_client_id(),
    })


@app.route('/api/settings/google', methods=['POST'])
def api_settings_google_post():
    from src.config import save_google_client_config, delete_setting
    data = request.get_json()
    if not data or not data.get('credentials_json'):
        return jsonify({'error': 'credentials_json wajib diisi'}), 400
    try:
        raw = data['credentials_json']
        config = json.loads(raw) if isinstance(raw, str) else raw
        save_google_client_config(config)
        delete_setting('google_token')  # reset token agar re-auth
        return jsonify({'ok': True})
    except (json.JSONDecodeError, ValueError) as e:
        return jsonify({'error': f'JSON tidak valid: {e}'}), 400


@app.route('/api/settings/google/revoke', methods=['POST'])
def api_settings_google_revoke():
    from src.config import revoke_google_token
    revoke_google_token()
    return jsonify({'ok': True})


@app.route('/api/settings/ai', methods=['GET'])
def api_settings_ai_get():
    from src.config import get_ai_config, mask_api_key
    cfg = get_ai_config()
    return jsonify({
        'provider':    cfg.get('provider', 'openai'),
        'model':       cfg.get('model', 'gpt-4o-mini'),
        'has_api_key': bool(cfg.get('api_key')),
        'masked_key':  mask_api_key(cfg.get('api_key', '')),
    })


@app.route('/api/settings/ai', methods=['POST'])
def api_settings_ai_post():
    from src.config import save_ai_config, get_ai_config
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Body kosong'}), 400

    # Jika api_key tidak dikirim (kosong), pertahankan yang lama
    existing = get_ai_config()
    api_key = data.get('api_key') or existing.get('api_key', '')

    save_ai_config(
        provider=data.get('provider', 'openai'),
        model=data.get('model', 'gpt-4o-mini'),
        api_key=api_key,
    )
    return jsonify({'ok': True})


@app.route('/api/settings/banks', methods=['GET'])
def api_settings_banks_get():
    from src.config import get_enabled_banks
    from src.banks import get_all_banks
    enabled = get_enabled_banks()
    banks = [
        {'id': b.id, 'name': b.name, 'enabled': b.id in enabled,
         'senders': b.senders, 'tipe_transaksi': b.tipe_transaksi}
        for b in get_all_banks()
    ]
    return jsonify({'banks': banks, 'enabled': enabled})


@app.route('/api/settings/banks', methods=['POST'])
def api_settings_banks_post():
    from src.config import set_enabled_banks
    data = request.get_json()
    if not data or 'enabled' not in data:
        return jsonify({'error': 'Field enabled wajib diisi'}), 400
    set_enabled_banks(data['enabled'])
    return jsonify({'ok': True})


# ── API: Sync (SSE) ───────────────────────────────────────────────────────────

@app.route('/api/sync/<sync_type>')
def api_sync(sync_type):
    if sync_type not in ('pengeluaran', 'pemasukan', 'harian', 'rekening_koran'):
        return jsonify({'error': 'Invalid sync type'}), 400

    def generate():
        def sse(data):
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            try:
                from dotenv import load_dotenv; load_dotenv()
            except ImportError:
                pass

            from src.gmail_fetcher import (
                get_gmail_service, fetch_all_banks_emails,
                fetch_payroll_emails, fetch_rk_emails,
            )
            from src.database import (
                init_db, gmail_id_exists, simpan_transaksi,
                gmail_id_payroll_exists, simpan_payroll,
            )
            from src.llm_extractor import ekstrak_transaksi, ekstrak_payroll, get_openai_client
            from src.config import get_enabled_banks

            init_db()
            yield sse({'type': 'log', 'text': 'Menghubungkan ke Gmail...'})
            service = get_gmail_service()
            yield sse({'type': 'log', 'text': 'Gmail terhubung ✓'})

            yield sse({'type': 'log', 'text': 'Menyiapkan AI client...'})
            client = get_openai_client()
            yield sse({'type': 'log', 'text': 'AI client siap ✓'})

            today    = date.today()
            tomorrow = today + timedelta(days=1)
            today_q  = f'after:{today.strftime("%Y/%m/%d")} before:{tomorrow.strftime("%Y/%m/%d")}'

            tb = ts = 0

            # ── PENGELUARAN ──────────────────────────────────────
            if sync_type in ('pengeluaran', 'harian'):
                enabled_banks = get_enabled_banks()
                label = f'hari ini ({today})' if sync_type == 'harian' else '(semua)'
                yield sse({'type': 'log',
                           'text': f'Mencari email dari {len(enabled_banks)} bank {label}...'})

                extra  = today_q if sync_type == 'harian' else ''
                emails = fetch_all_banks_emails(service, enabled_banks, extra_query=extra)
                n      = len(emails)
                yield sse({'type': 'log', 'text': f'Ditemukan {n} email pengeluaran'})

                baru = skip_db = skip_llm = 0
                for i, email in enumerate(emails, 1):
                    bank_id = email.get('bank_id', 'mandiri')
                    if gmail_id_exists(email['id']):
                        skip_db += 1; ts += 1
                    else:
                        r = ekstrak_transaksi(email, client, bank_id=bank_id)
                        if r and simpan_transaksi(r) == 'baru':
                            baru += 1; tb += 1
                        else:
                            skip_llm += 1; ts += 1
                    pct = int(i / n * 100) if n else 100
                    yield sse({'type': 'progress', 'pct': pct, 'current': i, 'total': n,
                               'text': f'Baru: {baru} · Skip DB: {skip_db} · Skip LLM: {skip_llm}'})

                yield sse({'type': 'log', 'cls': 'ok',
                           'text': f'Pengeluaran selesai — {baru} baru, {skip_db+skip_llm} diskip ✓'})

            # ── PEMASUKAN ────────────────────────────────────────
            if sync_type in ('pemasukan', 'harian'):
                label    = f'hari ini ({today})' if sync_type == 'harian' else '(semua)'
                yield sse({'type': 'log', 'text': f'Mencari email payroll {label}...'})
                extra    = today_q if sync_type == 'harian' else ''
                payrolls = fetch_payroll_emails(service, extra_query=extra)
                m        = len(payrolls)
                yield sse({'type': 'log', 'text': f'Ditemukan {m} email payroll'})

                baru = skip_db = skip_llm = 0
                for i, email in enumerate(payrolls, 1):
                    if gmail_id_payroll_exists(email['id']):
                        skip_db += 1; ts += 1
                    else:
                        r = ekstrak_payroll(email, client)
                        if r and simpan_payroll(r) == 'baru':
                            baru += 1; tb += 1
                        else:
                            skip_llm += 1; ts += 1
                    pct = int(i / m * 100) if m else 100
                    yield sse({'type': 'progress', 'pct': pct, 'current': i, 'total': m,
                               'text': f'Baru: {baru} · Skip DB: {skip_db} · Skip LLM: {skip_llm}'})

                yield sse({'type': 'log', 'cls': 'ok',
                           'text': f'Payroll selesai — {baru} baru, {skip_db+skip_llm} diskip ✓'})

            # ── REKENING KORAN ───────────────────────────────────
            if sync_type == 'rekening_koran':
                import os
                password = os.environ.get('MANDIRI_PDF_PASSWORD', '')
                if not password:
                    yield sse({'type': 'error',
                               'message': 'MANDIRI_PDF_PASSWORD tidak ditemukan di .env'})
                    return

                from src.database import gmail_id_rk_exists, simpan_rk_statement
                from src.pdf_extractor import ekstrak_rk

                yield sse({'type': 'log', 'text': 'Mencari email rekening koran...'})
                rk_emails = fetch_rk_emails(service)
                n = len(rk_emails)
                yield sse({'type': 'log', 'text': f'Ditemukan {n} email rekening koran'})

                baru = skip_db = err = 0
                for i, email in enumerate(rk_emails, 1):
                    if gmail_id_rk_exists(email['id']):
                        skip_db += 1; ts += 1
                    else:
                        try:
                            result = ekstrak_rk(email['pdf_bytes'], password, email['filename'])
                            simpan_rk_statement(email['id'], result['statement'], result['transaksi'])
                            baru += 1; tb += 1
                        except Exception as ex:
                            err += 1
                            yield sse({'type': 'log', 'cls': 'warn',
                                       'text': f'  ⚠ Gagal proses {email["filename"]}: {ex}'})
                    pct = int(i / n * 100) if n else 100
                    yield sse({'type': 'progress', 'pct': pct, 'current': i, 'total': n,
                               'text': f'Baru: {baru} · Skip: {skip_db} · Gagal: {err}'})

                yield sse({'type': 'log', 'cls': 'ok',
                           'text': f'Rekening Koran selesai — {baru} baru, {skip_db} skip, {err} gagal ✓'})

            yield sse({'type': 'done', 'baru': tb, 'skip': ts})

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':    'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection':       'keep-alive',
        },
    )
