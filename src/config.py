"""
Config manager — semua settings aplikasi disimpan di database.
Fallback ke file/env untuk backward compatibility.
"""

import json
import os
from pathlib import Path
from typing import Any, List, Optional

# Lazy import get_connection untuk avoid circular import saat init_db belum dipanggil
def _conn():
    from src.database import get_connection
    return get_connection()


BASE_DIR = Path(__file__).parent.parent
_CREDENTIALS_FILE = BASE_DIR / 'credentials' / 'credentials.json'
_TOKEN_FILE = BASE_DIR / 'credentials' / 'token.pickle'


# ── Generic Key-Value Settings ────────────────────────────────────────────────

def get_setting(key: str, default: Any = None) -> Any:
    """Ambil setting dari database. Returns default jika tidak ada."""
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return json.loads(row['value'])
    except Exception:
        return default


def set_setting(key: str, value: Any) -> None:
    """Simpan/update setting ke database."""
    with _conn() as conn:
        conn.execute("""
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE
                SET value = excluded.value,
                    updated_at = datetime('now', 'localtime')
        """, (key, json.dumps(value, ensure_ascii=False)))


def delete_setting(key: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))


def get_all_settings() -> dict:
    """Ambil semua settings sebagai dict."""
    try:
        with _conn() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {r['key']: json.loads(r['value']) for r in rows}
    except Exception:
        return {}


# ── Google OAuth ──────────────────────────────────────────────────────────────

def get_google_client_config() -> Optional[dict]:
    """
    Ambil Google OAuth client config (isi credentials.json).
    Priority: DB → file (legacy backward compat).
    """
    db_val = get_setting('google_client_config')
    if db_val:
        return db_val

    if _CREDENTIALS_FILE.exists():
        with open(_CREDENTIALS_FILE, 'r') as f:
            return json.load(f)

    return None


def save_google_client_config(config: dict) -> None:
    """Simpan Google OAuth credentials ke database."""
    set_setting('google_client_config', config)


def get_google_token() -> Optional[dict]:
    """
    Ambil Google OAuth token sebagai dict.
    Priority: DB → token.pickle (legacy).
    """
    db_val = get_setting('google_token')
    if db_val:
        return db_val

    # Fallback: baca legacy token.pickle dan migrasikan ke DB
    if _TOKEN_FILE.exists():
        try:
            import pickle
            with open(_TOKEN_FILE, 'rb') as f:
                creds = pickle.load(f)
            token_dict = _creds_to_dict(creds)
            save_google_token(creds)  # migrate ke DB
            return token_dict
        except Exception:
            pass

    return None


def save_google_token(creds) -> None:
    """Simpan Google OAuth token ke database."""
    set_setting('google_token', _creds_to_dict(creds))


def revoke_google_token() -> None:
    """Hapus cached token (force re-auth)."""
    delete_setting('google_token')


def _creds_to_dict(creds) -> dict:
    return {
        'token':         creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri':     creds.token_uri,
        'client_id':     creds.client_id,
        'client_secret': creds.client_secret,
        'scopes':        list(creds.scopes) if creds.scopes else [],
        'expiry':        creds.expiry.isoformat() if creds.expiry else None,
    }


def dict_to_creds(data: dict):
    """Restore Credentials object dari dict yang disimpan di DB."""
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=data.get('scopes', []),
    )
    if data.get('expiry'):
        from datetime import datetime
        try:
            creds.expiry = datetime.fromisoformat(data['expiry'])
        except (ValueError, TypeError):
            pass
    return creds


def has_google_credentials() -> bool:
    return get_google_client_config() is not None


def has_google_token() -> bool:
    return get_google_token() is not None


def get_google_client_id() -> str:
    """Ambil client_id dari stored credentials untuk ditampilkan di UI."""
    config = get_google_client_config()
    if not config:
        return ''
    # credentials.json bisa punya key 'installed' atau 'web'
    for key in ('installed', 'web'):
        if key in config:
            return config[key].get('client_id', '')
    return ''


# ── AI Config ─────────────────────────────────────────────────────────────────

_DEFAULT_AI_CONFIG = {
    'provider': 'openai',
    'model': 'gpt-4o-mini',
    'api_key': '',
}


def get_ai_config() -> dict:
    """
    Ambil AI config: provider, model, api_key.
    Priority: DB → environment variable (legacy).
    """
    db_val = get_setting('ai_config')
    if db_val and db_val.get('api_key'):
        return {**_DEFAULT_AI_CONFIG, **db_val}

    # Fallback ke env
    env_key = os.environ.get('OPENAI_API_KEY', '')
    return {
        'provider': 'openai',
        'model':    'gpt-4o-mini',
        'api_key':  env_key,
    }


def save_ai_config(provider: str, model: str, api_key: str) -> None:
    set_setting('ai_config', {
        'provider': provider,
        'model':    model,
        'api_key':  api_key,
    })


def has_ai_api_key() -> bool:
    return bool(get_ai_config().get('api_key'))


def mask_api_key(key: str) -> str:
    if not key or len(key) < 8:
        return '***'
    return key[:7] + '...' + key[-4:]


# ── Bank Settings ─────────────────────────────────────────────────────────────

_DEFAULT_ENABLED_BANKS = ['mandiri']


def get_enabled_banks() -> List[str]:
    """
    Ambil daftar bank_id yang diaktifkan.
    Default: ['mandiri'] untuk backward compat.
    """
    db_val = get_setting('enabled_banks')
    if db_val is not None:
        return db_val
    return list(_DEFAULT_ENABLED_BANKS)


def set_enabled_banks(bank_ids: List[str]) -> None:
    set_setting('enabled_banks', bank_ids)
