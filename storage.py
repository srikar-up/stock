"""
State Persistence & Storage Module
Implements ultra-lightweight Firestore context tracking for Hugging Face Spaces.
Stores minimal tracking pointers (last_ticker, last_action, updated_at) with merge=True.
Includes seamless in-memory fallback for local development when credentials are not set.
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Firebase Firestore Imports (optional/graceful)
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_INSTALLED = True
except ImportError:
    FIREBASE_INSTALLED = False


class FirestoreContextManager:
    """
    Manages lightweight user conversation state across ephemeral container restarts.
    """

    def __init__(self, collection_name: str = "stock_bot_sessions"):
        self.collection_name = collection_name
        self.db = None
        self._in_memory_store: Dict[str, Dict[str, Any]] = {}
        self._init_firestore()

    def _init_firestore(self):
        """Initializes Firebase Admin SDK from FIREBASE_CREDENTIALS_JSON if available."""
        if not FIREBASE_INSTALLED:
            logger.info("firebase-admin not installed. Using in-memory state persistence.")
            return

        creds_env = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
        if not creds_env:
            logger.info("FIREBASE_CREDENTIALS_JSON not provided in environment. Using in-memory store.")
            return

        try:
            # Check if existing app is already initialized
            if not firebase_admin._apps:
                # Check direct path or path relative to script directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                alt_path = os.path.join(script_dir, creds_env)

                if os.path.isfile(creds_env):
                    cred = credentials.Certificate(creds_env)
                elif os.path.isfile(alt_path):
                    cred = credentials.Certificate(alt_path)
                else:
                    creds_dict = json.loads(creds_env)
                    cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred)

            self.db = firestore.client()
            logger.info("Successfully connected to Firebase Firestore.")
        except Exception as e:
            logger.warning(f"Failed to initialize Firestore: {e}. Falling back to in-memory store.")
            self.db = None

    def _sanitize_key(self, user_email: str) -> str:
        """Sanitizes user email to be a valid document ID."""
        return user_email.strip().lower().replace("/", "_")

    def get_user_context(self, user_email: str) -> Dict[str, Any]:
        """
        Retrieves user tracking pointers: last_ticker, last_action, updated_at.
        """
        sanitized_email = self._sanitize_key(user_email)

        # Firestore retrieval
        if self.db:
            try:
                doc_ref = self.db.collection(self.collection_name).document(sanitized_email)
                doc = doc_ref.get()
                if doc.exists:
                    return doc.to_dict() or {}
            except Exception as e:
                logger.error(f"Error reading context from Firestore: {e}")

        # In-memory fallback
        return self._in_memory_store.get(sanitized_email, {})

    def update_user_context(
        self,
        user_email: str,
        last_ticker: Optional[str] = None,
        last_action: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Overwrites tracking metadata pointers with merge=True to ensure zero row accumulation.
        """
        sanitized_email = self._sanitize_key(user_email)
        now_iso = datetime.now(timezone.utc).isoformat()

        update_payload: Dict[str, Any] = {
            "updated_at": now_iso,
        }
        if last_ticker:
            update_payload["last_ticker"] = last_ticker
        if last_action:
            update_payload["last_action"] = last_action

        # Firestore update
        if self.db:
            try:
                doc_ref = self.db.collection(self.collection_name).document(sanitized_email)
                doc_ref.set(update_payload, merge=True)
            except Exception as e:
                logger.error(f"Error persisting context to Firestore: {e}")

        # Maintain in-memory copy
        current = self._in_memory_store.get(sanitized_email, {})
        current.update(update_payload)
        self._in_memory_store[sanitized_email] = current
        return current
