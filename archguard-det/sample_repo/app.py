"""Application entrypoint wiring Flask blueprints across the 3-tier architecture."""

from flask import Flask, jsonify

from config import AppConfig
from routes.auth_routes import auth_bp
from routes.order_routes import order_bp
from routes.product_routes import product_bp


def create_app() -> Flask:
    """Construct and configure the baseline e-commerce Flask application."""
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = AppConfig.DATABASE_PATH
    app.config["SECRET_KEY"] = AppConfig.SECRET_KEY

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(order_bp, url_prefix="/api/orders")
    app.register_blueprint(product_bp, url_prefix="/api/products")

    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "ok", "service": "ecommerce-baseline"}), 200

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5050, debug=AppConfig.DEBUG)
