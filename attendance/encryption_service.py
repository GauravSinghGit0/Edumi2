"""
AES-256 encryption service using cryptography.Fernet.
Used exclusively to encrypt/decrypt face embeddings at rest.

Key generation (run once):
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
Store the result as FACE_ENCRYPTION_KEY in your .env file.
"""
import json
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
import logging

logger = logging.getLogger('attendance.encryption')


class FaceEncryptionService:
    """Thread-safe wrapper around Fernet symmetric encryption."""

    def __init__(self):
        key = getattr(settings, 'FACE_ENCRYPTION_KEY', None)
        if not key:
            raise RuntimeError(
                "FACE_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    def encrypt_embedding(self, embedding_list: list) -> bytes:
        """Serialize embedding list to JSON, then encrypt with AES-256."""
        json_bytes = json.dumps(embedding_list).encode('utf-8')
        return self._fernet.encrypt(json_bytes)

    def decrypt_embedding(self, encrypted_bytes: bytes) -> list:
        """Decrypt and deserialize an embedding back to a Python list."""
        try:
            if isinstance(encrypted_bytes, memoryview):
                encrypted_bytes = bytes(encrypted_bytes)
            decrypted = self._fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted.decode('utf-8'))
        except InvalidToken:
            logger.error("Decryption failed: invalid token or wrong key.")
            raise ValueError("Face embedding decryption failed — invalid key or corrupted data.")
        except Exception as exc:
            logger.error(f"Unexpected decryption error: {exc}")
            raise
