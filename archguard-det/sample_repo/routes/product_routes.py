"""HTTP endpoints for product catalog browsing and inventory administration."""

from flask import Blueprint, jsonify, request
from services.product_service import ProductService
from utils.security import require_auth
from utils.validators import sanitize_text

product_bp = Blueprint("products", __name__)
_product_service = ProductService()


@product_bp.route("/", methods=["GET"])
def public_list_products():
    limit = request.args.get("limit", default=50, type=int)
    products = _product_service.list_catalog(limit=limit)
    return jsonify({"products": products}), 200


@product_bp.route("/<int:product_id>", methods=["GET"])
def public_get_product(product_id: int):
    try:
        product = _product_service.get_product(product_id=product_id)
        return jsonify({"product": product}), 200
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@product_bp.route("/", methods=["POST"])
@require_auth
def create_product():
    payload = request.get_json(silent=True) or {}
    sku = sanitize_text(payload.get("sku", ""), max_length=40)
    name = sanitize_text(payload.get("name", ""), max_length=140)
    price = payload.get("price", 0.0)
    stock_qty = payload.get("stock_qty", 0)
    try:
        product = _product_service.add_product(
            sku=sku,
            name=name,
            price_dollars=price,
            stock_qty=stock_qty,
        )
        return jsonify({"product": product}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@product_bp.route("/<int:product_id>/restock", methods=["POST"])
@require_auth
def restock_product(product_id: int):
    payload = request.get_json(silent=True) or {}
    delta_qty = payload.get("delta_qty", 0)
    try:
        product = _product_service.restock_product(product_id=product_id, delta_qty=delta_qty)
        return jsonify({"product": product}), 200
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
