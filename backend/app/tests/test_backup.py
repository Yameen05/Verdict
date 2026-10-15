import sqlite3

import pytest

from app.scripts.backup_sqlite import snapshot, verify


def test_online_wal_backup_restores_committed_data_and_detects_damage(tmp_path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, note TEXT)")
        live.execute("INSERT INTO accounts VALUES (1, 'preserved')")
        live.commit()
        destination = tmp_path / "recovery"
        snapshot({"verdict.db": source}, destination)
        verify(destination)
        with sqlite3.connect(destination / "verdict.db") as restored:
            assert restored.execute("SELECT note FROM accounts").fetchone() == ("preserved",)
        assert (destination / "verdict.db").stat().st_mode & 0o777 == 0o600
        with pytest.raises(FileExistsError):
            snapshot({"verdict.db": source}, destination)
        with (destination / "verdict.db").open("ab") as backup:
            backup.write(b"changed")
        with pytest.raises(ValueError, match="digest mismatch"):
            verify(destination)
