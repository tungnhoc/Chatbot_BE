from datetime import timedelta
from flask_jwt_extended import (
    create_access_token, create_refresh_token
)
from werkzeug.security import generate_password_hash, check_password_hash
from src.models.Users import User
from flask_jwt_extended import decode_token

def register_service(session, data):
    try:
        email = data.email
        password = data.password
        username = data.username if data.username else email

        if not email or not password:
            return {"error": "Missing email or password"}, 400

        if User.get_by_emails(session, email):
            return {"error": "Email already exists"}, 409

        new_user = User(
            UserName=username,
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
        password = data.password
        email = getattr(data, "email", None)
        username = getattr(data, "username", None)

        if not email and not username:
            return {"error": "Missing username or email"}

        user = None
        if email:
            user = User.get_by_emails(session, email)
        if not user and username:
            user = session.query(User).filter_by(UserName=username).first()

        if not user or not user.check_password(password):
            return {"error": "Invalid credentials"}

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
            expires_delta=timedelta(hours=1)
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
