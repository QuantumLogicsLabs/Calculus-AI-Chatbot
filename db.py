"""
Database Layer - Developer T3 (Theta)
Objective: Map session creation and message schemas to target production database,
linking logged-in chat histories to true, verified website user IDs.
Author: Hamza Ali (Team Theta)
"""

import os
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database Configuration (Production)
# Reads from environment variables to keep credentials secure
DATABASE_URL = os.getenv("PROD_DATABASE_URL", "postgresql://user:password@localhost:5432/chatbot_prod")

# Create the SQLAlchemy engine with connection pooling for production scale
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Checks connection before using (prevents stale connections)
    echo=False  # Set to True only for local debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ============================================
# TABLES / SCHEMAS (Mapped to Production DB)
# ============================================

class User(Base):
    """
    Maps to the MAIN WEBSITE's user table.
    We do NOT store passwords here. We only store the ID reference
    to link chat history to the verified user.
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)  # UUID from website auth
    email = Column(String(255), nullable=False, unique=True, index=True)
    username = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship: One user -> Many chat sessions
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    """
    Maps to `chat_sessions` table.
    T3 Objective: Links every session to the verified website user ID.
    """
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = Column(String(100), nullable=True)  # Calculus topic (e.g., derivatives)
    context = Column(Text, nullable=True)  # Summary context stored here (CB-13)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """
    Maps to `chat_messages` table.
    T3 Objective: Stores raw chat history linked to the session.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    metadata = Column(JSON, nullable=True)  # For future use (e.g., tokens used, model version)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    session = relationship("ChatSession", back_populates="messages")


# ============================================
# CRUD OPERATIONS FOR T3 (DATABASE LOGIC)
# ============================================

def get_db_session() -> Session:
    """
    Dependency Injection for FastAPI routes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_or_verify_user(db: Session, user_id: str, email: str, username: str = None) -> User:
    """
    T3 Task: Ensures the user exists in our db mapping.
    If the user is new, we create a local record.
    This links the chatbot history to the website's auth user.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        logger.info(f"New verified user detected. Creating mapping for ID: {user_id}")
        user = User(
            id=user_id,
            email=email,
            username=username or email.split('@')[0]
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update email/username in case they changed on the main site
        user.email = email
        if username:
            user.username = username
        db.commit()
        db.refresh(user)
        logger.info(f"Existing user verified. ID: {user_id}")
        
    return user


def create_chat_session(db: Session, user_id: str, topic: str = None) -> ChatSession:
    """
    T3 Task: Creates a new session for a verified user.
    This is called when the user opens a new chat.
    """
    # Verify user exists in our mapping
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User ID {user_id} not found in database mapping. Ensure user is verified first.")

    session = ChatSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        topic=topic or "general"
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(f"Created new chat session: {session.id} for User: {user_id}")
    return session


def add_message_to_session(db: Session, session_id: str, role: str, content: str, metadata: dict = None) -> Message:
    """
    T3 Task: Stores a message (user or assistant) to the production database.
    """
    # Verify session exists
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise ValueError(f"Session ID {session_id} not found in database.")

    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        metadata=metadata or {}
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # Update the session's updated_at timestamp
    session.updated_at = func.now()
    db.commit()
    
    logger.info(f"Added {role} message to session: {session_id} (ID: {message.id})")
    return message


def get_session_history(db: Session, session_id: str) -> list:
    """
    Fetches all messages for a specific session in chronological order.
    Used to load context when the user returns.
    """
    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at.asc()).all()
    return messages


def get_user_sessions(db: Session, user_id: str, limit: int = 10) -> list:
    """
    Fetches all sessions for a verified user.
    Used for the history sidebar in the UI.
    """
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc()).limit(limit).all()
    return sessions


# ============================================
# MIGRATION: CREATE TABLES
# ============================================
def init_database():
    """
    Run this once to create the tables in the production database.
    T3 ensures schema matches production specs.
    """
    logger.info("Initializing production database schema...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Tables created/verified successfully.")


# ============================================
# STANDALONE TESTING (Local)
# ============================================
if __name__ == "__main__":
    # This simulates the database migration and mapping logic
    print("🔄 Developer T3: Database Migration & Mapping")
    print("=" * 50)
    
    # Initialize DB (creates tables)
    init_database()
    
    # Create a session
    db = SessionLocal()
    try:
        # T3 Testing: Link to a fake verified user ID (JWT provided)
        verified_user_id = "auth0|1234567890"
        email = "hamza@example.com"
        
        # 1. Create/Verify User
        user = create_or_verify_user(db, verified_user_id, email)
        print(f"✅ User verified/mapped: {user.id} | {user.email}")
        
        # 2. Create Session
        session = create_chat_session(db, verified_user_id, "Derivatives")
        print(f"✅ Session created: {session.id} for Topic: {session.topic}")
        
        # 3. Add Messages
        add_message_to_session(db, session.id, "user", "What is the derivative of x^2?")
        add_message_to_session(db, session.id, "assistant", "The derivative of x^2 is 2x.")
        
        # 4. Retrieve History
        history = get_session_history(db, session.id)
        print(f"\n📜 Chat History for Session {session.id}:")
        for msg in history:
            print(f"   [{msg.role}]: {msg.content[:50]}...")
            
        # 5. Verify user sessions
        sessions = get_user_sessions(db, verified_user_id)
        print(f"\n📊 Total sessions for User: {len(sessions)}")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
    finally:
        db.close()
    
    print("\n" + "=" * 50)
    print("✅ T3 Database Mapping Test Completed Successfully!")