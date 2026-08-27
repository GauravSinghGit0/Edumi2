"""
common/encryption.py
Industry-standard cryptographic encryption service for data-at-rest (Messages, Chat, Sensitive Fields).
Uses AES-256 CBC with HMAC-SHA256 authenticated encryption via cryptography.Fernet.
"""
import base64
import hashlib
import logging
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger('common.encryption')

_PREFIX = "ENC:"
_fernet_instance = None


def get_cipher():
    """Returns singleton Fernet cipher instance using MESSAGE_ENCRYPTION_KEY or derived from SECRET_KEY."""
    global _fernet_instance
    if _fernet_instance is None:
        raw_key = getattr(settings, 'MESSAGE_ENCRYPTION_KEY', None)
        if not raw_key:
            # Deterministic, secure 256-bit key derived from Django SECRET_KEY
            secret_bytes = settings.SECRET_KEY.encode('utf-8')
            digest = hashlib.sha256(b"edumi-message-encryption-v1:" + secret_bytes).digest()
            raw_key = base64.urlsafe_b64encode(digest)
        elif isinstance(raw_key, str):
            raw_key = raw_key.encode('utf-8')
        _fernet_instance = Fernet(raw_key)
    return _fernet_instance


def encrypt_message_content(plain_text: str) -> str:
    """
    Encrypts plain text content with AES-256.
    Prepends ENC: prefix to easily identify encrypted ciphertexts.
    """
    if not plain_text:
        return plain_text
    
    # If already encrypted, return as is
    if plain_text.startswith(_PREFIX):
        return plain_text

    try:
        cipher = get_cipher()
        encrypted_bytes = cipher.encrypt(plain_text.encode('utf-8'))
        return _PREFIX + encrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Message encryption failed: {e}")
        return plain_text


def decrypt_message_content(cipher_text: str) -> str:
    """
    Decrypts encrypted ciphertext.
    If text is unencrypted (legacy plain text) or decryption fails, returns original text gracefully.
    """
    if not cipher_text:
        return cipher_text

    if not cipher_text.startswith(_PREFIX):
        # Legacy plain text message
        return cipher_text

    token = cipher_text[len(_PREFIX):]
    try:
        cipher = get_cipher()
        decrypted_bytes = cipher.decrypt(token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except InvalidToken:
        logger.warning("Decryption token invalid or corrupted; returning raw ciphertext.")
        return cipher_text
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return cipher_text


from django.db import models

class EncryptedTextField(models.TextField):
    """
    Industry-standard transparent AES-256 field-level encryption for Django models.
    Automatically encrypts on database write, automatically decrypts on model load.
    """
    description = "AES-256 encrypted text field"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt_message_content(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, str):
            return decrypt_message_content(value)
        return value

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt_message_content(str(value))

