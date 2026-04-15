from flask import Blueprint, jsonify, request
from datetime import timedelta
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    get_jwt, get_jwt_identity,
    jwt_required, get_jti
)
from pydantic import ValidationError
from src.models.Users import User
from src.schema.user_schema import UserLoginSchema, UserRegisterSchema
from src.models.TokenBlacklist import TokenBlacklist
from src.config.db_session import SessionLocal
from src.services.user_service import login_service, register_service


auth_bp = Blueprint("auth", __name__,  url_prefix='/api')

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = UserRegisterSchema(**request.json)
    except ValidationError as e:
        return jsonify({
            "error": "Invalid input: Password must be at least 6 characters.",
            "details": e.errors()
        }), 400
    
    session = SessionLocal()

    response_data, status_code = register_service(session, data)
    session.close()
    if "error" in response_data:
        return jsonify(response_data), 401 
    
    return jsonify(response_data), status_code



@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = UserLoginSchema(**request.json)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    session = SessionLocal()
    result = login_service(session, data)

    if "error" in result:
        return jsonify(result), 401 

    return jsonify(result), 200     



@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True) 
def refresh_token():
    session = SessionLocal()
    try:
        current_user_id = get_jwt_identity()
        jwt_payload = get_jwt()
        jti = jwt_payload["jti"]

        if session.query(TokenBlacklist).filter_by(jti=jti).first():
            return jsonify({"error": "Refresh token đã bị thu hồi"}), 401

        user = session.query(User).filter_by(UserID=current_user_id).first()
        if not user:
            return jsonify({"error": "Không tìm thấy user"}), 404

        new_access_token = create_access_token(
            identity=str(user.UserID),
            additional_claims={
                "username": user.UserName,
                "role": user.Role,
                "refresh_jti": jti 
            },
            expires_delta=timedelta(minutes=1)
        )

        return jsonify({
            "message": "Access token refreshed successfully",
            "access_token": new_access_token
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


@auth_bp.route('/logout', methods=['POST'])
@jwt_required() 
def logout():
    try:
        jwt_payload = get_jwt()
        
        jti_access = jwt_payload['jti']
        jti_refresh = jwt_payload.get('refresh_jti')
        
        session = SessionLocal()

        try:
            blacklisted_access = TokenBlacklist(jti=jti_access)
            session.add(blacklisted_access)

            if jti_refresh:
                blacklisted_refresh = TokenBlacklist(jti=jti_refresh)
                session.add(blacklisted_refresh)

            session.commit()

            return jsonify({"message": "Successfully logged out"}), 200

        except Exception as db_error:
            print(f"Database error: {db_error}")
            session.rollback()
            raise

    except Exception as e:
        print(f"LOGOUT ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    
    finally:
        session.close()