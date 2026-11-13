"""HTTP endpoints for authenticated customer orders."""

from flask import Blueprint, jsonify, request
from services.order_service import OrderService
from utils.security import require_auth
from utils.validators import validate_positive_int

order_bp = Blueprint("orders", __name__)
_order_service = OrderService()


@order_bp.route("/", methods=["GET"])
@require_auth
def list_my_orders():
    user_id = request.user_claims["user_id"]
    orders = _order_service.get_user_orders(user_id=user_id)
    return jsonify({"orders": orders}), 200


@order_bp.route("/", methods=["POST"])
@require_auth
def create_order():
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("product_id")
    quantity = payload.get("quantity")
    if not validate_positive_int(product_id) or not validate_positive_int(quantity):
        return jsonify({"error": "Valid product_id and quantity are required"}), 400
    user_id = request.user_claims["user_id"]
    try:
        order = _order_service.place_order(user_id=user_id, product_id=product_id, quantity=quantity)
        return jsonify({"order": order}), 201
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@order_bp.route("/<int:order_id>", methods=["GET"])
@require_auth
def get_order(order_id: int):
    user_id = request.user_claims["user_id"]
    try:
        order = _order_service.get_order_detail(order_id=order_id, requesting_user_id=user_id)
        return jsonify({"order": order}), 200
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
