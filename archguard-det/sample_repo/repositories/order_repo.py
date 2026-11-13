"""SQLite persistence repository for customer orders."""

import sqlite3
from utils.validators import validate_positive_int


class OrderRepository:
    """Data access layer for the orders table."""

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
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    total_cents INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'confirmed'
                )
                """
            )

    def create_order(self, user_id: int, product_id: int, quantity: int, total_cents: int) -> dict:
        if not validate_positive_int(quantity):
            raise ValueError("Quantity must be positive")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (user_id, product_id, quantity, total_cents, status)
                VALUES (?, ?, ?, ?, 'confirmed')
                """,
                (user_id, product_id, quantity, total_cents),
            )
            return {
                "id": cursor.lastrowid,
                "user_id": user_id,
                "product_id": product_id,
                "quantity": quantity,
                "total_cents": total_cents,
                "status": "confirmed",
            }

    def list_by_user(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, user_id, product_id, quantity, total_cents, status FROM orders WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def find_by_id(self, order_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, user_id, product_id, quantity, total_cents, status FROM orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            return dict(row) if row else None
