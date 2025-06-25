import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from models import UserDB, User
import logging

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, secret_key: str = "your-secret-key-change-in-production"):
        self.secret_key = secret_key
        self.algorithm = "HS256"
        self.token_expire_hours = 24

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

    def create_access_token(self, user_id: int, username: str) -> str:
        """Create a JWT access token"""
        expire = datetime.utcnow() + timedelta(hours=self.token_expire_hours)
        payload = {
            "user_id": user_id,
            "username": username,
            "exp": expire,
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None

    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[UserDB]:
        """Authenticate a user with username and password"""
        user = db.query(UserDB).filter(UserDB.username == username).first()
        if not user:
            return None
        
        if not self.verify_password(password, user.password_hash):
            return None
            
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        
        return user

    def get_user_by_id(self, db: Session, user_id: int) -> Optional[UserDB]:
        """Get user by ID"""
        return db.query(UserDB).filter(UserDB.id == user_id).first()

    def create_default_admin(self, db: Session) -> UserDB:
        """Create default admin user if none exists"""
        existing_admin = db.query(UserDB).filter(UserDB.username == "admin").first()
        if existing_admin:
            return existing_admin
            
        # Create default admin with password "mobile"
        admin_user = UserDB(
            username="admin",
            password_hash=self.hash_password("mobile"),
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        logger.info("Created default admin user")
        return admin_user

    def change_password(self, db: Session, user_id: int, current_password: str, new_password: str) -> bool:
        """Change user password"""
        user = self.get_user_by_id(db, user_id)
        if not user:
            return False
            
        if not self.verify_password(current_password, user.password_hash):
            return False
            
        user.password_hash = self.hash_password(new_password)
        db.commit()
        
        logger.info(f"Password changed for user {user.username}")
        return True 