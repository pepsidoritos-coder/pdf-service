"""
PDF Service — Backend Flask Application Factory
"""
import os
from dotenv import load_dotenv
from flask import Flask, send_from_directory
from flask_cors import CORS
from backend.config import MAX_FILE_SIZE

load_dotenv()

# Pasta do frontend (relativa à raiz do projeto)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


def create_app():
    """Cria e configura a aplicação Flask."""
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

    # Serve o frontend na raiz
    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    # Registra blueprints
    from backend.routes.analyze import analyze_bp
    app.register_blueprint(analyze_bp)

    return app
