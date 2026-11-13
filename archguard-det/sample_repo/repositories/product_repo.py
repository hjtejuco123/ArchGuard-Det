"""SQLite persistence repository for catalog products."""

import sqlite3
from utils.validators import sanitize_text


class ProductRepository:
    """Data access layer for the products table."""

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
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    price_cents INTEGER NOT NULL,
                    stock_qty INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def list_all(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, sku, name, price_cents, stock_qty FROM products ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def find_by_id(self, product_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, sku, name, price_cents, stock_qty FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()
            return dict(row) if row else None

    def create_product(self, sku: str, name: str, price_cents: int, stock_qty: int) -> dict:
        clean_sku = sanitize_text(sku, max_length=40).upper()
        clean_name = sanitize_text(name, max_length=140)
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO products (sku, name, price_cents, stock_qty) VALUES (?, ?, ?, ?)",
                (clean_sku, clean_name, price_cents, stock_qty),
            )
            return {
                "id": cursor.lastrowid,
                "sku": clean_sku,
                "name": clean_name,
                "price_cents": price_cents,
                "stock_qty": stock_qty,
            }

    def update_stock(self, product_id: int, new_stock: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE products SET stock_qty = ? WHERE id = ?",
                (new_stock, product_id),
            )
            return cursor.rowcount > 0
