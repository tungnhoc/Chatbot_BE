import os
from dotenv import load_dotenv

# Load environment variables FIRST before importing other modules
# that might require them natively during import.
load_dotenv()

from flask import Flask
from flask_cors import CORS
from src.routes.upload_routes import upload_bp
from src.routes.chat_routes import chat_bp
from src.routes.auth_routes import auth_bp
from src.utils.jwt_manager import init_jwt
from src.utils.redis_listener import start_redis_watcher_thread
app = Flask(__name__)

CORS(app)

app.config['JWT_SECRET_KEY'] = os.getenv('FLASK_JWT_SECRET_KEY')
init_jwt(app)

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200

app.register_blueprint(auth_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(chat_bp)
start_redis_watcher_thread()

import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

