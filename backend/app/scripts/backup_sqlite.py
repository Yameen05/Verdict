"""Consistent online SQLite snapshots; run as a trusted host/container operator.

python -m app.scripts.backup_sqlite --output-dir /backups/verdict-YYYYMMDD
python -m app.scripts.backup_sqlite --verify /backups/verdict-YYYYMMDD

Backups contain password hashes, sessions, and personal state. Encrypt and copy
outside the host. Restore only with the app stopped; never copy live WAL files.
"""

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot(sources: dict[str, Path], destination: Path) -> None:
    # Never overwrite an earlier recovery point, even if it looks empty.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries = []
    for name, source in sources.items():
        if Path(name).name != name or not name.endswith(".db"):
            raise ValueError("Invalid backup filename")
        if not source.is_file():
            raise ValueError(f"Missing source database: {name}")
        target = destination / name
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(target) as backup:
                original.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"Backup integrity check failed: {name}")
                if backup.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError(f"Backup has foreign key violations: {name}")
        entries.append({"file": name, "sha256": _digest(target), "bytes": target.stat().st_size})
    manifest = {"created_at": datetime.now(UTC).isoformat(), "databases": entries}
    with (destination / "manifest.json").open("x") as stream:
        os.chmod(stream.name, 0o600)
        json.dump(manifest, stream, indent=2)


def verify(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    if not manifest["databases"]:
        raise ValueError("Empty backup")
    for entry in manifest["databases"]:
        name = entry["file"]
        if Path(name).name != name or not name.endswith(".db"):
            raise ValueError("Invalid backup filename")
        path = directory / name
        if _digest(path) != entry["sha256"]:
            raise ValueError(f"Backup digest mismatch: {name}")
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"Backup integrity check failed: {name}")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError(f"Backup has foreign key violations: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output-dir", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
        print("Backup hashes and SQLite integrity verified")
        return
    from app.config import get_settings
    settings = get_settings()
    prefix = "sqlite+aiosqlite:///"
    if not settings.database_url.startswith(prefix):
        raise SystemExit("This command supports SQLite only; use your database's backup tooling")
    sources = {"verdict.db": Path(settings.database_url[len(prefix):])}
    vectors = Path(settings.vector_db_path)
    if not settings.pinecone_api_key and vectors.is_file():
        sources["vectors.db"] = vectors
    snapshot(sources, args.output_dir)
    verify(args.output_dir)
    print("SQLite backup completed and verified; store an encrypted off-host copy")


if __name__ == "__main__":
    main()
