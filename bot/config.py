"""Load configuration from .env / environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    root: Path
    api_id: int
    api_hash: str
    cmd_prefix: str
    session_path: Path
    session_string: str | None
    db_path: Path
    downloads_dir: Path
    waiting_time: float
    turso_database_url: str | None
    turso_auth_token: str | None


def load_config(root: Path | None = None) -> Config:
    root = root or Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    load_dotenv(env_file)

    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    cmd_prefix = os.getenv("CMD_PREFIX", ".").strip() or "."
    session_string = os.getenv("SESSION_STRING", "").strip() or None
    waiting_raw = os.getenv("WAITING_TIME", "3").strip() or "3"
    try:
        waiting_time = max(0.0, float(waiting_raw))
    except ValueError as exc:
        raise SystemExit("WAITING_TIME in .env must be a number (seconds).") from exc

    if not api_id_raw or not api_hash or api_hash == "your_api_hash_here":
        raise SystemExit(
            "Missing API credentials.\n"
            "1. Copy .env.example to .env\n"
            "2. Open https://my.telegram.org and create an app\n"
            "3. Put API_ID and API_HASH into .env\n"
            "4. For Koyeb: also set SESSION_STRING (run: python generate_session.py)\n"
            "5. Run: python main.py"
        )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("API_ID in .env must be a number.") from exc

    # Allow mounting a persistent volume on Koyeb via DATA_DIR=/data
    data_root = Path(os.getenv("DATA_DIR", "").strip() or (root / "data"))
    downloads_dir = data_root / "downloads"
    sessions_dir = root / "sessions"
    data_root.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        root=root,
        api_id=api_id,
        api_hash=api_hash,
        cmd_prefix=cmd_prefix,
        session_path=sessions_dir / "userbot",
        session_string=session_string,
        db_path=data_root / "userbot.db",
        downloads_dir=downloads_dir,
        waiting_time=waiting_time,
        turso_database_url=os.getenv("TURSO_DATABASE_URL", "").strip() or None,
        turso_auth_token=os.getenv("TURSO_AUTH_TOKEN", "").strip() or None,
    )
