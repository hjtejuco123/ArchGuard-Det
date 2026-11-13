"""HTTP endpoints for user registration and sign-in."""

from flask import Blueprint, jsonify, request
from services.auth_service import AuthService
from utils.validators import sanitize_text

auth_bp = Blueprint("auth", __name__)
_auth_service = AuthService()


@auth_bp.route("/register", methods=["POST"])
def register_account():
    payload = request.get_json(silent=True) or {}
    email = sanitize_text(payload.get("email", ""), max_length=160)
    full_name = sanitize_text(payload.get("full_name", ""), max_length=120)
    password = payload.get("password", "")
    try:
        result = _auth_service.register_user(email=email, full_name=full_name, password=password)
        return jsonify(result), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@auth_bp.route("/login", methods=["POST"])
def login_account():
    payload = request.get_json(silent=True) or {}
    email = sanitize_text(payload.get("email", ""), max_length=160)
    password = payload.get("password", "")
    try:
        result = _auth_service.authenticate(email=email, password=password)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401
