import os
import base64
import hashlib
import hmac
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
import config

try:
    _raw_key = base64.b64decode(config.ENCRYPTION_KEY)
    _aesgcm = AESGCM(_raw_key)
except Exception as e:
    import sys
    print(f"FATAL: Failed to initialize encryption with ENCRYPTION_KEY from config: {e}", file=sys.stderr)
    sys.exit(1)

class CryptoManager:
    @staticmethod
    def encrypt(data: bytes) -> bytes:
        """
        Encrypts data using AES-256-GCM.
        Uses a convergent encryption IV based on HMAC-SHA256 of the data.
        This preserves deduplication securely (identical chunks produce identical ciphertext)
        without exposing the IV derivation to attackers.
        """
        if not data:
            return b""
            
        # 12-byte IV for GCM using HMAC to prevent chosen-plaintext IV collision attacks
        iv = hmac.new(_raw_key, data, hashlib.sha256).digest()[:12]
        
        # Encrypt the data
        ciphertext = _aesgcm.encrypt(iv, data, None)
        
        # Prepend the IV to the ciphertext so we can decrypt it later
        return iv + ciphertext

    @staticmethod
    def decrypt(data: bytes) -> bytes:
        """
        Decrypts data using AES-256-GCM.
        Extracts the 12-byte IV from the front of the data.
        """
        if not data:
            return b""
            
        if len(data) < 28: # 12 byte IV + 16 byte GCM tag
            raise ValueError(f"Ciphertext too short: {len(data)} bytes")
            
        iv = data[:12]
        ciphertext = data[12:]
        
        # Decrypt the data
        try:
            return _aesgcm.decrypt(iv, ciphertext, None)
        except InvalidTag as e:
            raise ValueError("Decryption failed: data is corrupt or tampered") from e
