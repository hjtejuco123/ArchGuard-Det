"""Product catalog business logic."""

from repositories.product_repo import ProductRepository
from utils.validators import sanitize_text, validate_positive_int, validate_price


class ProductService:
    """Service layer managing catalog queries and inventory updates."""

    def __init__(self, product_repo: ProductRepository | None = None) -> None:
        self.product_repo = product_repo or ProductRepository()

    def list_catalog(self, limit: int = 50) -> list[dict]:
        bounded_limit = limit if validate_positive_int(limit) and limit <= 100 else 50
        return self.product_repo.list_all(limit=bounded_limit)

    def get_product(self, product_id: int) -> dict:
        if not validate_positive_int(product_id):
            raise ValueError("Product ID must be positive")
        product = self.product_repo.find_by_id(product_id)
        if product is None:
            raise LookupError("Product not found")
        return product

    def add_product(self, sku: str, name: str, price_dollars: float, stock_qty: int) -> dict:
        clean_sku = sanitize_text(sku, max_length=40)
        clean_name = sanitize_text(name, max_length=140)
        if not clean_sku or not clean_name:
            raise ValueError("SKU and product name are required")
        if not validate_price(price_dollars):
            raise ValueError("Price must be non-negative")
        if isinstance(stock_qty, bool) or not isinstance(stock_qty, int) or stock_qty < 0:
            raise ValueError("Stock quantity must be zero or greater")
        price_cents = int(round(float(price_dollars) * 100))
        return self.product_repo.create_product(
            sku=clean_sku,
            name=clean_name,
            price_cents=price_cents,
            stock_qty=stock_qty,
        )

    def restock_product(self, product_id: int, delta_qty: int) -> dict:
        product = self.get_product(product_id)
        if not validate_positive_int(delta_qty):
            raise ValueError("Restock quantity must be positive")
        new_stock = product["stock_qty"] + delta_qty
        self.product_repo.update_stock(product_id=product_id, new_stock=new_stock)
        product["stock_qty"] = new_stock
        return product
