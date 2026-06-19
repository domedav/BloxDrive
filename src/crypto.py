import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import config

# Convert the base64 string from config into a raw 32-byte key
_raw_key = base64.b64decode(config.ENCRYPTION_KEY)
_aesgcm = AESGCM(_raw_key)

class CryptoManager:
    @staticmethod
    def encrypt(data: bytes) -> bytes:
        """
        Encrypts data using AES-256-GCM.
        Uses a deterministic IV based on the sha256 hash of the data.
        This preserves deduplication (identical chunks produce identical ciphertext).
        """
        if not data:
            return b""
            
        # 12-byte IV for GCM
        iv = hashlib.sha256(data).digest()[:12]
        
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
            
        iv = data[:12]
        ciphertext = data[12:]
        
        # Decrypt the data
        return _aesgcm.decrypt(iv, ciphertext, None)
