"""Order processing business logic."""

from repositories.order_repo import OrderRepository
from repositories.product_repo import ProductRepository
from utils.validators import validate_positive_int


class OrderService:
    """Coordinates inventory checks and order creation."""

    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        product_repo: ProductRepository | None = None,
    ) -> None:
        self.order_repo = order_repo or OrderRepository()
        self.product_repo = product_repo or ProductRepository()

    def place_order(self, user_id: int, product_id: int, quantity: int) -> dict:
        if not validate_positive_int(user_id):
            raise ValueError("Invalid user ID")
        if not validate_positive_int(product_id):
            raise ValueError("Invalid product ID")
        if not validate_positive_int(quantity):
            raise ValueError("Quantity must be greater than zero")

        product = self.product_repo.find_by_id(product_id)
        if product is None:
            raise LookupError("Product not found")
        if product["stock_qty"] < quantity:
            raise ValueError("Insufficient inventory")

        updated_stock = product["stock_qty"] - quantity
        self.product_repo.update_stock(product_id=product_id, new_stock=updated_stock)
        total_cents = product["price_cents"] * quantity
        return self.order_repo.create_order(
            user_id=user_id,
            product_id=product_id,
            quantity=quantity,
            total_cents=total_cents,
        )

    def get_user_orders(self, user_id: int) -> list[dict]:
        if not validate_positive_int(user_id):
            raise ValueError("Invalid user ID")
        return self.order_repo.list_by_user(user_id)

    def get_order_detail(self, order_id: int, requesting_user_id: int) -> dict:
        if not validate_positive_int(order_id):
            raise ValueError("Invalid order ID")
        order = self.order_repo.find_by_id(order_id)
        if order is None:
            raise LookupError("Order not found")
        if order["user_id"] != requesting_user_id:
            raise PermissionError("Order belongs to another user")
        return order
