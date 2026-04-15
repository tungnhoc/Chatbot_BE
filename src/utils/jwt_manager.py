from flask_jwt_extended import JWTManager
from flask import jsonify
from src.models.TokenBlacklist import TokenBlacklist
from src.config.database import get_database_engine
from sqlalchemy.orm import sessionmaker

jwt = JWTManager()

def init_jwt(app):
    jwt.init_app(app)


    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        return jsonify({
            "message": "Token has expired",
            "error": "token_expired"
        }), 401


    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            "message": "Invalid or corrupted token",
            "error": "invalid_token"
        }), 401

    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({
            "message": "Missing or invalid Authorization header",
            "error": "authorization_header"
        }), 401
    

    @jwt.token_in_blocklist_loader
    def token_in_blocklist_callback(jwt_header, jwt_data):
        jti = jwt_data["jti"]

        engine = get_database_engine()
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            tokenn = session.query(TokenBlacklist).filter_by(jti=jti).scalar()
            return tokenn is not None  
        finally:
            session.close()