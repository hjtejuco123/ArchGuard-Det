"""Authentication business logic coordinating UserRepository and security helpers."""

from repositories.user_repo import UserRepository
from utils.security import generate_token, hash_password, verify_password
from utils.validators import sanitize_text, validate_email


class AuthService:
    """Handles user registration and credential verification."""

    def __init__(self, user_repo: UserRepository | None = None) -> None:
        self.user_repo = user_repo or UserRepository()

    def register_user(self, email: str, full_name: str, password: str) -> dict:
        if not validate_email(email):
            raise ValueError("Invalid email address")
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        existing = self.user_repo.find_by_email(email)
        if existing is not None:
            raise ValueError("Account already exists for this email")

        password_hash = hash_password(password)
        clean_name = sanitize_text(full_name, max_length=120)
        user = self.user_repo.create_user(email=email, full_name=clean_name, password_hash=password_hash)
        token = generate_token(user_id=user["id"], role=user["role"])
        return {"user": user, "token": token}

    def authenticate(self, email: str, password: str) -> dict:
        if not validate_email(email):
            raise ValueError("Invalid email address")
        user = self.user_repo.find_by_email(email)
        if user is None or not verify_password(password, user["password_hash"]):
            raise ValueError("Invalid email or password")

        token = generate_token(user_id=user["id"], role=user["role"])
        safe_user = {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
        }
        return {"user": safe_user, "token": token}
