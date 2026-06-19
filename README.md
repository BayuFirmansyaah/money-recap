# Money Recap

Expense tracker otomatis yang mengambil data transaksi dari email notifikasi bank Indonesia via Gmail API dan mengekstrak detailnya menggunakan AI (OpenAI).

---

## Fitur

- Multi-bank — mendukung 9 bank (Mandiri, BCA, BRI, BNI, BSI, Jago, Blu, SeaBank, Allo Bank)
- Ekstraksi otomatis nominal, merchant, tanggal, dan kategori via OpenAI
- Dashboard web untuk visualisasi pengeluaran
- Parse PDF e-statement Mandiri (rekening koran)
- Tracking gaji masuk *(saat ini hanya Mandiri Livin — lihat catatan di bawah)*
- Konfigurasi credentials dan bank via halaman Settings
- Bisa di-build menjadi `.exe` untuk Windows

---

## Bank yang Didukung

| Bank | Email Notifikasi | Transaksi | Gaji Masuk |
|------|-----------------|:---------:|:----------:|
| Bank Mandiri (Livin) | `noreply.livin@bankmandiri.co.id` | Ya | Ya |
| Bank BCA | `bcaid@bca.co.id`, `e-statement@bca.co.id` | Ya | - |
| Bank BRI (BRImo) | `noreply@bri.co.id`, `bri_care@bri.co.id` | Ya | - |
| Bank BNI | `no-reply@bni.co.id`, `bnicall@bni.co.id` | Ya | - |
| Bank Syariah Indonesia (BSI) | `no-reply@bankbsi.co.id` | Ya | - |
| Bank Jago | `noreply@jago.com` | Ya | - |
| Blu by BCA Digital | `haloblu@blubybca.id` | Ya | - |
| SeaBank | `cs@seabank.co.id` | Ya | - |
| Allo Bank | `hi@allobank.com` | Ya | - |

**Catatan Payroll:** Fitur tracking gaji masuk saat ini hanya tersedia untuk pengguna **Mandiri Livin** (via email `mcm@bankmandiri.co.id` dari Mandiri Cash Management). Dukungan untuk bank lain akan ditambahkan di versi mendatang. Kontribusi sangat disambut.

---

## Instalasi

### Prasyarat

- Python 3.10 atau lebih baru — [download](https://www.python.org/downloads/)
- API Key OpenAI — [daftar di sini](https://platform.openai.com/api-keys)
- Google OAuth credentials — lihat langkah 2 di bawah

### Langkah 1 — Clone & Install

```bash
git clone https://github.com/username/money-recap.git
cd money-recap
./install.sh
```

Script `install.sh` akan otomatis mengecek versi Python, membuat virtual environment, menginstall semua dependensi, dan menyiapkan database.

Setelah selesai, aktifkan virtual environment lalu jalankan:

```bash
# Mac/Linux:
source venv/bin/activate

# Windows (Git Bash):
source venv/Scripts/activate

python main.py dashboard
```

Browser akan otomatis terbuka ke `http://localhost:5050`.

### Langkah 2 — Buat Google OAuth Credentials

Aplikasi ini memerlukan akses read-only ke Gmail untuk mengambil email notifikasi bank.

1. Buka [Google Cloud Console](https://console.cloud.google.com/)
2. Buat project baru atau pilih yang sudah ada
3. Pilih **APIs & Services > Library**, cari **Gmail API**, klik **Enable**
4. Pergi ke **APIs & Services > Credentials**
5. Klik **+ Create Credentials > OAuth client ID**
6. Pilih Application type: **Desktop app**, beri nama bebas
7. Klik **Create**, lalu **Download JSON**
8. Simpan file tersebut — akan di-upload lewat halaman Settings

> Jika diminta mengisi OAuth consent screen, pilih **External**, isi nama app dan email. Tambahkan scope `https://www.googleapis.com/auth/gmail.readonly` dan tambahkan akun Gmail kamu sebagai **Test user**.

### Langkah 3 — Konfigurasi via Settings

Buka `http://localhost:5050/settings`.

**Google Credentials**
1. Buka file `credentials.json` yang didownload tadi dengan text editor
2. Salin seluruh isinya, paste di kolom "Upload credentials.json"
3. Klik Simpan Credentials

**OpenAI API Key**
1. Isi field API Key dengan key dari [OpenAI Platform](https://platform.openai.com/api-keys)
2. Pilih model — default `gpt-4o-mini` sudah cukup akurat dan hemat biaya
3. Klik Simpan AI Config

**Pilih Bank**
1. Centang bank yang email notifikasinya ada di Gmail kamu
2. Klik Simpan Pilihan Bank

### Langkah 4 — Sync Email Pertama Kali

```bash
python main.py sync
```

Saat pertama kali sync, browser akan membuka halaman login Google untuk memberikan izin akses Gmail. Setelah login, token disimpan otomatis ke database dan tidak perlu login lagi untuk sync berikutnya.

---

## Penggunaan

### Dashboard Web

```bash
python main.py dashboard
# Buka: http://localhost:5050
```

| Halaman | URL | Fungsi |
|---------|-----|--------|
| Dashboard | `/` | Ringkasan pengeluaran, grafik, tabel transaksi |
| Pembayaran | `/pembayaran` | Kelola cicilan dan langganan rutin |
| Rekening Koran | `/rekening-koran` | Data dari e-statement PDF |
| Settings | `/settings` | Konfigurasi OAuth, AI, dan bank |

### CLI

```bash
python main.py sync                              # sync semua bank aktif
python main.py laporan                           # tampilkan laporan ringkasan
python main.py list                              # daftar transaksi terbaru
python main.py kategori <id> "Nama Kategori"    # koreksi kategori manual
```

---

## Build Windows .exe

```bash
pip install pyinstaller
python build.py
# Output: dist/MoneyRecap.exe
```

Jalankan di Windows via Command Prompt:

```cmd
MoneyRecap.exe dashboard
MoneyRecap.exe sync
MoneyRecap.exe laporan
```

Data (SQLite) disimpan di folder `data/` di lokasi yang sama dengan file `.exe`.

---

## Konfigurasi Lanjutan

### File `.env` (opsional)

```env
OPENAI_API_KEY=sk-...
MANDIRI_PDF_PASSWORD=password_anda
```

Jika API key sudah disimpan via Settings di database, file `.env` tidak diperlukan.

### Menambah Bank Baru

Edit `src/banks/__init__.py`, tambahkan entri ke dict `BANKS`:

```python
'nama_bank': BankConfig(
    id='nama_bank',
    name='Nama Bank',
    senders=['noreply@namabank.co.id'],
    gmail_query='',
    subject_keywords='Notifikasi Transaksi',
    prompt_hint='Notifikasi transaksi dari Nama Bank.',
    tipe_transaksi=['Debit', 'Kredit', 'Transfer'],
),
```

---

## Struktur Project

```
money-recap/
├── main.py
├── build.py
├── livin_tracker.spec
├── requirements.txt
├── src/
│   ├── banks/__init__.py      # registry konfigurasi bank
│   ├── config.py              # config manager (DB-backed)
│   ├── database.py            # SQLite layer
│   ├── gmail_fetcher.py       # Gmail API + multi-bank fetcher
│   ├── llm_extractor.py       # ekstraksi transaksi via OpenAI
│   ├── dashboard.py           # Flask server + API routes
│   ├── pdf_extractor.py       # parser PDF rekening koran
│   └── parser.py              # regex parser (legacy)
├── templates/
│   ├── dashboard.html
│   ├── pembayaran.html
│   ├── rekening_koran.html
│   └── settings.html
├── data/                      # gitignored
└── logs/                      # gitignored
```

---

## Keamanan & Privasi

- Data transaksi hanya disimpan di SQLite lokal, tidak dikirim ke server manapun
- Akses Gmail read-only — tidak bisa mengirim atau menghapus email
- OAuth credentials dan API key tersimpan di SQLite lokal, tidak masuk ke git
- File `data/livin_tracker.db` berisi data keuangan dan API key — jangan dibagikan
- Isi email dikirim ke API OpenAI untuk diekstrak. Pertimbangkan model lokal jika ini menjadi masalah

---

## Kontribusi

Pull request disambut. Beberapa hal yang bisa dikerjakan:

- Payroll tracking untuk bank selain Mandiri *(prioritas tinggi)*
- Dukungan bank baru — cukup tambah entri di `src/banks/__init__.py`
- Dukungan LLM lokal (Ollama) sebagai alternatif OpenAI
- Export ke Excel/CSV
- Docker support

### Setup Development

```bash
git clone https://github.com/username/money-recap.git
cd money-recap
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py dashboard
```

---

## Lisensi

MIT License
