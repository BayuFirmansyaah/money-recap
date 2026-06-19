"""
Build script untuk membuat .exe menggunakan PyInstaller.

Penggunaan:
  python build.py           → build dengan spec file
  python build.py --clean   → hapus cache build sebelum build

Output: dist/LivinTracker.exe (Windows) atau dist/LivinTracker (Mac/Linux)

Pastikan sudah install PyInstaller:
  pip install pyinstaller>=6.0.0
"""

import subprocess
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent


def clean():
    """Hapus direktori build dan dist sebelumnya."""
    for d in ('build', 'dist', '__pycache__'):
        p = BASE_DIR / d
        if p.exists():
            shutil.rmtree(p)
            print(f"  🗑️  Dihapus: {p}")


def build():
    spec_file = BASE_DIR / 'livin_tracker.spec'
    if not spec_file.exists():
        print(f"❌ Spec file tidak ditemukan: {spec_file}")
        sys.exit(1)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        str(spec_file),
    ]

    print("🔨 Memulai build...")
    print(f"   Perintah: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(BASE_DIR))

    if result.returncode == 0:
        dist = BASE_DIR / 'dist'
        exe_files = list(dist.glob('LivinTracker*'))
        print(f"\n✅ Build selesai!")
        for f in exe_files:
            size_mb = f.stat().st_size / 1024 / 1024 if f.is_file() else 0
            print(f"   📦 Output: {f}" + (f" ({size_mb:.1f} MB)" if size_mb else ""))
        print(f"\n💡 Cara pakai di Windows:")
        print(f"   LivinTracker.exe dashboard  → buka web dashboard")
        print(f"   LivinTracker.exe sync        → sync email dari semua bank")
        print(f"   LivinTracker.exe laporan     → tampilkan laporan")
    else:
        print(f"\n❌ Build gagal (exit code {result.returncode})")
        sys.exit(result.returncode)


if __name__ == '__main__':
    if '--clean' in sys.argv:
        print("🧹 Membersihkan direktori build...")
        clean()

    build()
