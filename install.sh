#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────────
#  Money Recap — Install Script
#  Tested on: macOS, Ubuntu/Debian, Windows (Git Bash / WSL)
# ─────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}[OK]${RESET}    $1"; }
info() { echo -e "${CYAN}[INFO]${RESET}  $1"; }
warn() { echo -e "${YELLOW}[WARN]${RESET}  $1"; }
fail() { echo -e "${RED}[FAIL]${RESET}  $1"; exit 1; }

echo ""
echo -e "${BOLD}Money Recap — Setup${RESET}"
echo "────────────────────────────────────"
echo ""

# ── 1. Cek OS ─────────────────────────────────────────────────
OS="unknown"
case "$(uname -s)" in
    Darwin)  OS="macos"   ;;
    Linux)   OS="linux"   ;;
    MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac
info "OS terdeteksi: $OS"

# ── 2. Cek Python ─────────────────────────────────────────────
PYTHON=""

for cmd in python3 python python3.12 python3.11 python3.10; do
    if command -v "$cmd" &>/dev/null; then
        VER=$("$cmd" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)
        MAJOR=$("$cmd" -c 'import sys; print(sys.version_info[0])')
        MINOR=$("$cmd" -c 'import sys; print(sys.version_info[1])')
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo ""
    fail "Python 3.10+ tidak ditemukan.\n\
  Install Python dari https://www.python.org/downloads/\n\
  lalu jalankan ulang script ini."
fi

PYTHON_VER=$("$PYTHON" --version 2>&1)
ok "Python ditemukan: $PYTHON_VER ($PYTHON)"

# ── 3. Cek pip ────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null; then
    warn "pip tidak ditemukan, mencoba install..."
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || \
        fail "pip tidak bisa diinstall. Install manual: https://pip.pypa.io/en/stable/installation/"
fi
ok "pip tersedia"

# ── 4. Buat virtual environment ───────────────────────────────
VENV_DIR="venv"

if [ -d "$VENV_DIR" ]; then
    warn "Folder venv sudah ada, dilewati."
else
    info "Membuat virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Virtual environment dibuat di ./$VENV_DIR"
fi

# Tentukan path ke python dan pip dalam venv
if [ "$OS" = "windows" ]; then
    VENV_PYTHON="$VENV_DIR/Scripts/python"
    VENV_PIP="$VENV_DIR/Scripts/pip"
    ACTIVATE_CMD="venv\\Scripts\\activate"
else
    VENV_PYTHON="$VENV_DIR/bin/python"
    VENV_PIP="$VENV_DIR/bin/pip"
    ACTIVATE_CMD="source venv/bin/activate"
fi

# ── 5. Upgrade pip di dalam venv ──────────────────────────────
info "Upgrade pip..."
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
ok "pip diperbarui"

# ── 6. Install dependensi ─────────────────────────────────────
if [ ! -f "requirements.txt" ]; then
    fail "File requirements.txt tidak ditemukan. Pastikan kamu menjalankan script ini dari root project."
fi

info "Menginstall dependensi dari requirements.txt..."
"$VENV_PIP" install -r requirements.txt --quiet
ok "Semua dependensi terinstall"

# ── 7. Buat folder yang diperlukan ────────────────────────────
for dir in data logs credentials; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        ok "Folder '$dir' dibuat"
    fi
done

# ── 8. Buat .env jika belum ada ───────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        ok "File .env dibuat dari .env.example"
    else
        cat > .env << 'EOF'
# OpenAI API Key — bisa juga diset via halaman Settings di dashboard
OPENAI_API_KEY=

# Password PDF e-statement Mandiri (jika terenkripsi)
MANDIRI_PDF_PASSWORD=
EOF
        ok "File .env dibuat (kosong)"
    fi
else
    warn ".env sudah ada, dilewati."
fi

# ── 9. Inisialisasi database ──────────────────────────────────
info "Inisialisasi database..."
"$VENV_PYTHON" -c "from src.database import init_db; init_db()" 2>/dev/null && \
    ok "Database siap" || \
    warn "Inisialisasi database dilewati (akan dibuat otomatis saat pertama run)"

# ── Selesai ───────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────"
echo -e "${GREEN}${BOLD}Instalasi selesai!${RESET}"
echo ""
echo "Langkah selanjutnya:"
echo ""
echo "  1. Aktifkan virtual environment:"
echo "     $ACTIVATE_CMD"
echo ""
echo "  2. Jalankan dashboard:"
echo "     python main.py dashboard"
echo ""
echo "  3. Buka browser ke http://localhost:5050/settings"
echo "     lalu upload Google credentials.json dan set OpenAI API key."
echo ""
echo "  Untuk sync via terminal:"
echo "     python main.py sync"
echo ""
