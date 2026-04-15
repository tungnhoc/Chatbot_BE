from datetime import timedelta
from flask_jwt_extended import (
    create_access_token, create_refresh_token
)
from src.models.Users import User
from flask_jwt_extended import decode_token
from src.utils.predict_password import predict_password_strength

def register_service(session, data):
    try:
        email = data.email
        password = data.password
        # strength = predict_password_strength(password)

        # if strength == "WEAK":
        #     return {
        #         "error": "Password too weak. Please enter a stronger password."
        #     }, 400
        
        
        if not email or not password:
            return {"error": "Missing email or password"}, 400
 
        if User.get_by_emails(session, email):
            return {"error": "Email already exists"}, 409 
        new_user = User(
            UserName=email,
            Email=email,
            Role="user"
        )
        new_user.set_password(password)
        new_user.save(session)
        
        return {"message": "User registered successfully"}, 201

    except Exception as e:
        session.rollback()
        return {"error": str(e)}, 500

def login_service(session, data):
    try:
        email = data.email
        password = data.password

        user = User.get_by_emails(session, email)
        if not user or not user.check_password(password):
            return {"error": "Invalid email or password"}

        refresh_token = create_refresh_token(identity=str(user.UserID))
        jti_refresh = decode_token(refresh_token)["jti"]

        additional_claims = {
            "username": user.UserName,
            "role": user.Role,
            "refresh_jti": jti_refresh
        }

        access_token = create_access_token(
            identity=str(user.UserID),
            additional_claims=additional_claims,
            expires_delta=timedelta(minutes=10)
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.UserID,
                "email": user.Email,
                "username": user.UserName,
                "role": user.Role
            }
        }

    except Exception as e:
        session.rollback()
        return {"error": str(e)}

