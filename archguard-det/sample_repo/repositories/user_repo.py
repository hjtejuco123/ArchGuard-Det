"""SQLite persistence repository for user accounts."""

import sqlite3
from utils.validators import sanitize_text


class UserRepository:
    """Data access layer for the users table."""

    def __init__(self, db_path: str = "ecommerce_baseline.db") -> None:
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'customer'
                )
                """
            )

    def create_user(self, email: str, full_name: str, password_hash: str) -> dict:
        clean_name = sanitize_text(full_name, max_length=120)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, full_name, password_hash) VALUES (?, ?, ?)",
                (email.lower().strip(), clean_name, password_hash),
            )
            return {
                "id": cursor.lastrowid,
                "email": email.lower().strip(),
                "full_name": clean_name,
                "role": "customer",
            }

    def find_by_email(self, email: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, full_name, password_hash, role FROM users WHERE email = ?",
                (email.lower().strip(),),
            ).fetchone()
            return dict(row) if row else None
