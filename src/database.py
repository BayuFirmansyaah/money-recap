"""
Database manager untuk Livin Tracker.
Menggunakan SQLite untuk penyimpanan lokal.
"""

import re
import sqlite3
from pathlib import Path
from datetime import datetime

import sys as _sys

def _get_data_dir() -> Path:
    """
    Kembalikan direktori data yang tepat:
    - Development: <project_root>/data/
    - Frozen .exe:  direktori yang sama dengan .exe berada
    """
    if getattr(_sys, 'frozen', False):
        # PyInstaller: simpan data di folder yang sama dengan .exe
        return Path(_sys.executable).parent / 'data'
    return Path(__file__).parent.parent / 'data'


BASE_DIR = Path(__file__).parent.parent
DB_PATH  = _get_data_dir() / 'livin_tracker.db'

_MONTH_ABBR = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
}


def normalise_tanggal(s):
    """Normalise tanggal ke YYYY-MM-DD. Handles '2024-Dec-30' → '2024-12-30'."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s.strftime('%Y-%m-%d')
    s = str(s).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
        return s
    m = re.match(r'^(\d{4})-([A-Za-z]{3})-(\d{1,2})$', s)
    if m:
        y, mon, d = m.groups()
        num = _MONTH_ABBR.get(mon.lower())
        if num:
            return f"{y}-{num}-{d.zfill(2)}"
    return s or None


def get_connection():
    """Return koneksi SQLite dengan row_factory untuk akses kolom by name."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Buat tabel jika belum ada, jalankan migrasi kolom baru."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transaksi (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_id        TEXT UNIQUE NOT NULL,
                bank            TEXT DEFAULT 'mandiri',
                tipe            TEXT NOT NULL,
                merchant_penerima TEXT,
                kategori        TEXT DEFAULT 'Lainnya',
                nominal         REAL NOT NULL,
                biaya           REAL DEFAULT 0,
                total           REAL NOT NULL,
                tanggal         TEXT,
                jam             TEXT,
                no_referensi    TEXT,
                keterangan      TEXT,
                catatan_manual  TEXT,
                created_at      TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_tanggal ON transaksi(tanggal);
            CREATE INDEX IF NOT EXISTS idx_kategori ON transaksi(kategori);
            CREATE INDEX IF NOT EXISTS idx_tipe ON transaksi(tipe);

            -- Tabel log untuk tracking sync
            CREATE TABLE IF NOT EXISTS sync_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_at     TEXT DEFAULT (datetime('now', 'localtime')),
                jumlah_baru INTEGER DEFAULT 0,
                jumlah_skip INTEGER DEFAULT 0,
                keterangan  TEXT
            );

            -- Tabel payroll (gaji masuk dari Mandiri Cash Management)
            CREATE TABLE IF NOT EXISTS payroll (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_id        TEXT UNIQUE NOT NULL,
                tanggal         TEXT,
                jam             TEXT,
                pengirim        TEXT,
                bank_penerima   TEXT,
                no_rekening     TEXT,
                nama_penerima   TEXT,
                jumlah          REAL NOT NULL DEFAULT 0,
                berita          TEXT,
                berita_tambahan TEXT,
                email_timestamp INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_payroll_tanggal ON payroll(tanggal);

            -- Rekening Koran: satu baris per file PDF
            CREATE TABLE IF NOT EXISTS rk_statement (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_id        TEXT UNIQUE NOT NULL,
                filename        TEXT,
                no_rekening     TEXT,
                nama_produk     TEXT,
                cabang          TEXT,
                periode_mulai   TEXT,
                periode_akhir   TEXT,
                valuta          TEXT DEFAULT 'IDR',
                saldo_awal      REAL DEFAULT 0,
                mutasi_kredit   REAL DEFAULT 0,
                mutasi_debit    REAL DEFAULT 0,
                saldo_akhir     REAL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- Rekening Koran: detail per baris transaksi
            CREATE TABLE IF NOT EXISTS rk_transaksi (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                statement_id    INTEGER NOT NULL REFERENCES rk_statement(id) ON DELETE CASCADE,
                tanggal         TEXT,
                tanggal_valuta  TEXT,
                rincian         TEXT,
                no_referensi    TEXT,
                tipe            TEXT,
                jumlah          REAL DEFAULT 0,
                saldo           REAL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_rk_tanggal ON rk_transaksi(tanggal);

            -- Tabel daftar pembayaran tetap (cicilan, langganan, dsb)
            CREATE TABLE IF NOT EXISTS pembayaran (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nama            TEXT NOT NULL,
                kategori        TEXT DEFAULT 'Lainnya',
                nominal         REAL NOT NULL,
                tanggal_mulai   TEXT NOT NULL,
                durasi_bulan    INTEGER,
                hari_tagih      INTEGER DEFAULT 1,
                catatan         TEXT,
                status          TEXT DEFAULT 'aktif',
                created_at      TEXT DEFAULT (datetime('now', 'localtime'))
            );

            -- Tabel settings aplikasi (key-value store)
            CREATE TABLE IF NOT EXISTS app_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # Migrasi: tambah kolom bank jika belum ada (ALTER TABLE idempotent)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(transaksi)").fetchall()}
        if 'bank' not in existing:
            conn.execute("ALTER TABLE transaksi ADD COLUMN bank TEXT DEFAULT 'mandiri'")

    print(f"✅ Database siap: {DB_PATH}")


def simpan_transaksi(data):
    """
    Simpan satu transaksi. Skip jika gmail_id sudah ada (idempotent).
    Returns: 'baru' | 'duplikat' | 'error'
    """
    tanggal_str = normalise_tanggal(data.get('tanggal'))

    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO transaksi
                    (gmail_id, bank, tipe, merchant_penerima, kategori,
                     nominal, biaya, total, tanggal, jam,
                     no_referensi, keterangan)
                VALUES
                    (:gmail_id, :bank, :tipe, :merchant_penerima, :kategori,
                     :nominal, :biaya, :total, :tanggal, :jam,
                     :no_referensi, :keterangan)
            """, {
                'gmail_id': data['gmail_id'],
                'bank': data.get('bank', 'mandiri'),
                'tipe': data['tipe'],
                'merchant_penerima': data.get('merchant_penerima', ''),
                'kategori': data.get('kategori', 'Lainnya'),
                'nominal': data['nominal'],
                'biaya': data.get('biaya', 0),
                'total': data['total'],
                'tanggal': tanggal_str,
                'jam': data.get('jam', ''),
                'no_referensi': data.get('no_referensi', ''),
                'keterangan': data.get('keterangan', ''),
            })
        return 'baru'
    except sqlite3.IntegrityError:
        return 'duplikat'
    except Exception as e:
        print(f"  ⚠️  Error simpan transaksi: {e}")
        return 'error'


def gmail_id_exists(gmail_id):
    """Cek apakah gmail_id sudah ada di database."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM transaksi WHERE gmail_id = ?", (gmail_id,)
        ).fetchone()
    return row is not None


def gmail_id_payroll_exists(gmail_id):
    """Cek apakah gmail_id sudah ada di tabel payroll."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM payroll WHERE gmail_id = ?", (gmail_id,)
        ).fetchone()
    return row is not None


def simpan_payroll(data):
    """Simpan satu data payroll. Skip jika gmail_id sudah ada."""
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO payroll
                    (gmail_id, tanggal, jam, pengirim, bank_penerima,
                     no_rekening, nama_penerima, jumlah, berita,
                     berita_tambahan, email_timestamp)
                VALUES
                    (:gmail_id, :tanggal, :jam, :pengirim, :bank_penerima,
                     :no_rekening, :nama_penerima, :jumlah, :berita,
                     :berita_tambahan, :email_timestamp)
            """, {
                'gmail_id':        data['gmail_id'],
                'tanggal':         normalise_tanggal(data.get('tanggal')),
                'jam':             data.get('jam', ''),
                'pengirim':        data.get('pengirim', ''),
                'bank_penerima':   data.get('bank_penerima', ''),
                'no_rekening':     data.get('no_rekening', ''),
                'nama_penerima':   data.get('nama_penerima', ''),
                'jumlah':          float(data.get('jumlah', 0) or 0),
                'berita':          data.get('berita', ''),
                'berita_tambahan': data.get('berita_tambahan', ''),
                'email_timestamp': data.get('email_timestamp', 0),
            })
        return 'baru'
    except sqlite3.IntegrityError:
        return 'duplikat'
    except Exception as e:
        print(f"  ⚠️  Error simpan payroll: {e}")
        return 'error'


def get_payroll(order='DESC'):
    """Ambil semua data payroll."""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM payroll ORDER BY tanggal {order}, jam {order}"
        ).fetchall()
    return [dict(r) for r in rows]


def get_payroll_stats(year='', month=''):
    """Statistik payroll, opsional filter tahun/bulan."""
    conds, params = ["1=1"], []
    if year:
        conds.append("strftime('%Y', tanggal) = ?"); params.append(year)
    if month:
        conds.append("strftime('%m', tanggal) = ?"); params.append(month.zfill(2))
    where = " AND ".join(conds)

    with get_connection() as conn:
        grand = dict(conn.execute(f"""
            SELECT COUNT(*) total_payroll,
                   COALESCE(SUM(jumlah), 0) total_masuk,
                   COALESCE(AVG(jumlah), 0) rata_rata,
                   MIN(tanggal) tanggal_awal,
                   MAX(tanggal) tanggal_akhir
            FROM payroll WHERE {where}
        """, params).fetchone())

        per_bulan = [dict(r) for r in conn.execute(f"""
            SELECT strftime('%Y-%m', tanggal) bulan,
                   COUNT(*) jumlah, SUM(jumlah) total
            FROM payroll WHERE {where} AND tanggal IS NOT NULL AND tanggal != ''
            GROUP BY bulan ORDER BY bulan
        """, params).fetchall() if r['bulan']]

        per_pengirim = [dict(r) for r in conn.execute(f"""
            SELECT pengirim, COUNT(*) jumlah, SUM(jumlah) total
            FROM payroll WHERE {where} AND pengirim IS NOT NULL
            GROUP BY pengirim ORDER BY total DESC
        """, params).fetchall()]

        detail = [dict(r) for r in conn.execute(f"""
            SELECT id, tanggal, jam, pengirim, nama_penerima,
                   jumlah, berita, berita_tambahan
            FROM payroll WHERE {where}
            ORDER BY tanggal DESC, jam DESC LIMIT 200
        """, params).fetchall()]

    return {
        'grand': grand,
        'per_bulan': per_bulan,
        'per_pengirim': per_pengirim,
        'detail': detail,
    }


def bulk_simpan(transaksi_list):
    """Simpan banyak transaksi sekaligus. Returns (jumlah_baru, jumlah_skip)."""
    baru = skip = 0
    for t in transaksi_list:
        status = simpan_transaksi(t)
        if status == 'baru':
            baru += 1
        else:
            skip += 1
    return baru, skip


def catat_sync(jumlah_baru, jumlah_skip, keterangan=''):
    """Catat log sync ke database."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO sync_log (jumlah_baru, jumlah_skip, keterangan)
            VALUES (?, ?, ?)
        """, (jumlah_baru, jumlah_skip, keterangan))


def get_semua_transaksi(order='ASC'):
    """Ambil semua transaksi, urut dari terlama (ASC) atau terbaru (DESC)."""
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT * FROM transaksi
            ORDER BY tanggal {order}, jam {order}
        """).fetchall()
    return [dict(r) for r in rows]


def update_kategori(transaksi_id, kategori_baru):
    """Update kategori satu transaksi (untuk koreksi manual)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE transaksi SET kategori = ? WHERE id = ?",
            (kategori_baru, transaksi_id)
        )
    print(f"✅ Kategori transaksi #{transaksi_id} diubah ke '{kategori_baru}'")


def get_statistik():
    """Ambil statistik ringkasan untuk semua data."""
    with get_connection() as conn:
        # Total per tipe
        per_tipe = conn.execute("""
            SELECT tipe, COUNT(*) as jumlah, SUM(total) as total_nominal
            FROM transaksi GROUP BY tipe ORDER BY total_nominal DESC
        """).fetchall()

        # Total per kategori
        per_kategori = conn.execute("""
            SELECT kategori, COUNT(*) as jumlah, SUM(total) as total_nominal
            FROM transaksi GROUP BY kategori ORDER BY total_nominal DESC
        """).fetchall()

        # Total per bulan
        per_bulan = conn.execute("""
            SELECT strftime('%Y-%m', tanggal) as bulan,
                   COUNT(*) as jumlah,
                   SUM(total) as total_nominal
            FROM transaksi
            WHERE tanggal IS NOT NULL
            GROUP BY bulan ORDER BY bulan
        """).fetchall()

        # Grand total
        grand = conn.execute("""
            SELECT COUNT(*) as total_transaksi,
                   SUM(total) as total_pengeluaran,
                   MIN(tanggal) as tanggal_pertama,
                   MAX(tanggal) as tanggal_terakhir
            FROM transaksi
        """).fetchone()

    return {
        'per_tipe': [dict(r) for r in per_tipe],
        'per_kategori': [dict(r) for r in per_kategori],
        'per_bulan': [dict(r) for r in per_bulan],
        'grand': dict(grand),
    }


# ─────────────────────────────────────────────────────────
#  PEMBAYARAN TETAP
# ─────────────────────────────────────────────────────────

def _add_months(year, month, n):
    """Tambah n bulan ke (year, month), return (year, month)."""
    month += n
    year  += (month - 1) // 12
    month  = (month - 1) % 12 + 1
    return year, month


def get_pembayaran(status=None):
    """Ambil semua item pembayaran, opsional filter status."""
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM pembayaran WHERE status = ? ORDER BY tanggal_mulai ASC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pembayaran ORDER BY status ASC, tanggal_mulai ASC"
            ).fetchall()
    return [dict(r) for r in rows]


def simpan_pembayaran(data):
    """Insert item pembayaran baru. Returns id baris baru."""
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO pembayaran
                (nama, kategori, nominal, tanggal_mulai, durasi_bulan,
                 hari_tagih, catatan, status)
            VALUES
                (:nama, :kategori, :nominal, :tanggal_mulai, :durasi_bulan,
                 :hari_tagih, :catatan, :status)
        """, {
            'nama':          data['nama'],
            'kategori':      data.get('kategori', 'Lainnya'),
            'nominal':       float(data['nominal']),
            'tanggal_mulai': normalise_tanggal(data['tanggal_mulai']),
            'durasi_bulan':  int(data['durasi_bulan']) if data.get('durasi_bulan') else None,
            'hari_tagih':    int(data.get('hari_tagih') or 1),
            'catatan':       data.get('catatan', ''),
            'status':        data.get('status', 'aktif'),
        })
    return cur.lastrowid


def update_pembayaran(item_id, data):
    """Update item pembayaran."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE pembayaran SET
                nama=:nama, kategori=:kategori, nominal=:nominal,
                tanggal_mulai=:tanggal_mulai, durasi_bulan=:durasi_bulan,
                hari_tagih=:hari_tagih, catatan=:catatan, status=:status
            WHERE id=:id
        """, {
            'id':            item_id,
            'nama':          data['nama'],
            'kategori':      data.get('kategori', 'Lainnya'),
            'nominal':       float(data['nominal']),
            'tanggal_mulai': normalise_tanggal(data['tanggal_mulai']),
            'durasi_bulan':  int(data['durasi_bulan']) if data.get('durasi_bulan') else None,
            'hari_tagih':    int(data.get('hari_tagih') or 1),
            'catatan':       data.get('catatan', ''),
            'status':        data.get('status', 'aktif'),
        })


def hapus_pembayaran(item_id):
    """Hapus item pembayaran."""
    with get_connection() as conn:
        conn.execute("DELETE FROM pembayaran WHERE id = ?", (item_id,))


def get_pembayaran_ringkasan(proyeksi_bulan=12):
    """
    Hitung total wajib bulan ini dan proyeksi N bulan ke depan.
    Returns dict: {total_bulan_ini, items_aktif, proyeksi: [{bulan, total}]}
    """
    from datetime import date as _date
    items  = get_pembayaran(status='aktif')
    today  = _date.today()
    cy, cm = today.year, today.month

    def is_active_in(item, year, month):
        mulai = item['tanggal_mulai']
        if not mulai:
            return False
        try:
            my, mm = int(mulai[:4]), int(mulai[5:7])
        except Exception:
            return False
        # Belum dimulai
        if (year, month) < (my, mm):
            return False
        # Sudah habis
        if item['durasi_bulan']:
            elapsed = (year - my) * 12 + (month - mm)
            if elapsed >= item['durasi_bulan']:
                return False
        return True

    total_bulan_ini = sum(
        i['nominal'] for i in items if is_active_in(i, cy, cm)
    )

    proyeksi = []
    for n in range(proyeksi_bulan):
        y, m = _add_months(cy, cm, n)
        bulan_str = f"{y}-{m:02d}"
        total = sum(i['nominal'] for i in items if is_active_in(i, y, m))
        proyeksi.append({'bulan': bulan_str, 'total': total})

    return {
        'total_bulan_ini': total_bulan_ini,
        'items_aktif':     len(items),
        'proyeksi':        proyeksi,
    }


# ─────────────────────────────────────────────────────────
#  REKENING KORAN
# ─────────────────────────────────────────────────────────

def gmail_id_rk_exists(gmail_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM rk_statement WHERE gmail_id = ?", (gmail_id,)
        ).fetchone()
    return row is not None


def simpan_rk_statement(gmail_id, data, transaksi_list):
    """
    Simpan satu statement + semua baris transaksinya.
    Returns: 'baru' | 'duplikat' | 'error'
    """
    try:
        with get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO rk_statement
                    (gmail_id, filename, no_rekening, nama_produk, cabang,
                     periode_mulai, periode_akhir, valuta,
                     saldo_awal, mutasi_kredit, mutasi_debit, saldo_akhir)
                VALUES
                    (:gmail_id, :filename, :no_rekening, :nama_produk, :cabang,
                     :periode_mulai, :periode_akhir, :valuta,
                     :saldo_awal, :mutasi_kredit, :mutasi_debit, :saldo_akhir)
            """, {
                'gmail_id':      gmail_id,
                'filename':      data.get('filename', ''),
                'no_rekening':   data.get('no_rekening', ''),
                'nama_produk':   data.get('nama_produk', ''),
                'cabang':        data.get('cabang', ''),
                'periode_mulai': data.get('periode_mulai', ''),
                'periode_akhir': data.get('periode_akhir', ''),
                'valuta':        data.get('valuta', 'IDR'),
                'saldo_awal':    float(data.get('saldo_awal') or 0),
                'mutasi_kredit': float(data.get('mutasi_kredit') or 0),
                'mutasi_debit':  float(data.get('mutasi_debit') or 0),
                'saldo_akhir':   float(data.get('saldo_akhir') or 0),
            })
            stmt_id = cur.lastrowid

            conn.executemany("""
                INSERT INTO rk_transaksi
                    (statement_id, tanggal, tanggal_valuta, rincian,
                     no_referensi, tipe, jumlah, saldo)
                VALUES
                    (:statement_id, :tanggal, :tanggal_valuta, :rincian,
                     :no_referensi, :tipe, :jumlah, :saldo)
            """, [{
                'statement_id':   stmt_id,
                'tanggal':        t.get('tanggal'),
                'tanggal_valuta': t.get('tanggal_valuta'),
                'rincian':        t.get('rincian', ''),
                'no_referensi':   t.get('no_referensi', ''),
                'tipe':           t.get('tipe', 'debit'),
                'jumlah':         float(t.get('jumlah') or 0),
                'saldo':          float(t.get('saldo') or 0),
            } for t in transaksi_list])

        return 'baru'
    except sqlite3.IntegrityError:
        return 'duplikat'
    except Exception as e:
        print(f"  ⚠️  Error simpan rk_statement: {e}")
        return 'error'


def get_rk_statements():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rk_statement ORDER BY periode_mulai DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_rk_data(year='', month=''):
    """KPI + per_bulan + transaksi untuk dashboard rekening koran."""
    conds, params = ["1=1"], []
    if year:
        conds.append("strftime('%Y', t.tanggal) = ?"); params.append(year)
    if month:
        conds.append("strftime('%m', t.tanggal) = ?"); params.append(month.zfill(2))
    where = " AND ".join(conds)

    with get_connection() as conn:
        kpi = dict(conn.execute(f"""
            SELECT
                COUNT(*) total_transaksi,
                COALESCE(SUM(CASE WHEN tipe='debit'  THEN jumlah ELSE 0 END), 0) total_debit,
                COALESCE(SUM(CASE WHEN tipe='kredit' THEN jumlah ELSE 0 END), 0) total_kredit
            FROM rk_transaksi t WHERE {where}
        """, params).fetchone())

        # Saldo terkini dari statement terbaru
        latest = conn.execute(
            "SELECT saldo_akhir, periode_akhir FROM rk_statement ORDER BY periode_akhir DESC LIMIT 1"
        ).fetchone()
        kpi['saldo_terkini']    = latest['saldo_akhir'] if latest else 0
        kpi['periode_terkini']  = latest['periode_akhir'] if latest else None

        per_bulan = [dict(r) for r in conn.execute(f"""
            SELECT strftime('%Y-%m', t.tanggal) bulan,
                   SUM(CASE WHEN tipe='debit'  THEN jumlah ELSE 0 END) total_debit,
                   SUM(CASE WHEN tipe='kredit' THEN jumlah ELSE 0 END) total_kredit,
                   COUNT(*) jumlah
            FROM rk_transaksi t
            WHERE {where} AND t.tanggal IS NOT NULL AND t.tanggal != ''
            GROUP BY bulan ORDER BY bulan
        """, params).fetchall()]

        transaksi = [dict(r) for r in conn.execute(f"""
            SELECT t.id, t.tanggal, t.tanggal_valuta, t.rincian,
                   t.no_referensi, t.tipe, t.jumlah, t.saldo,
                   s.periode_mulai, s.periode_akhir
            FROM rk_transaksi t
            JOIN rk_statement s ON s.id = t.statement_id
            WHERE {where}
            ORDER BY t.tanggal DESC, t.id DESC LIMIT 1000
        """, params).fetchall()]

        years = [r[0] for r in conn.execute("""
            SELECT DISTINCT strftime('%Y', tanggal) y
            FROM rk_transaksi WHERE tanggal IS NOT NULL AND tanggal != ''
            ORDER BY y DESC
        """).fetchall() if r[0]]

    return {'kpi': kpi, 'per_bulan': per_bulan, 'transaksi': transaksi, 'years': years}
