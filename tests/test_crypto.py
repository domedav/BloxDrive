import pytest
import os
from cryptography.exceptions import InvalidTag
from crypto import CryptoManager

def test_encrypt_decrypt_valid():
    data = b"Hello, World! This is a test string."
    ciphertext = CryptoManager.encrypt(data)
    assert ciphertext != data
    
    plaintext = CryptoManager.decrypt(ciphertext)
    assert plaintext == data

def test_encrypt_deterministic():
    data = b"Deterministic data test"
    ciphertext1 = CryptoManager.encrypt(data)
    ciphertext2 = CryptoManager.encrypt(data)
    assert ciphertext1 == ciphertext2

def test_encrypt_decrypt_empty():
    assert CryptoManager.encrypt(b"") == b""
    assert CryptoManager.decrypt(b"") == b""

def test_decrypt_invalid_mac():
    data = b"Sensitive data"
    ciphertext = CryptoManager.encrypt(data)
    
    # Tamper with the ciphertext (last byte is part of the MAC)
    tampered_ciphertext = bytearray(ciphertext)
    tampered_ciphertext[-1] ^= 0xFF
    
    with pytest.raises(ValueError):
        CryptoManager.decrypt(bytes(tampered_ciphertext))

def test_decrypt_tampered_iv():
    data = b"Sensitive data"
    ciphertext = CryptoManager.encrypt(data)
    
    # Tamper with the IV (first 12 bytes)
    tampered_ciphertext = bytearray(ciphertext)
    tampered_ciphertext[0] ^= 0xFF
    
    with pytest.raises(ValueError):
        CryptoManager.decrypt(bytes(tampered_ciphertext))

@pytest.mark.parametrize("size", [1, 15, 16, 31, 32, 1024, 1024 * 1024])
def test_encrypt_different_sizes(size):
    data = os.urandom(size)
    ciphertext = CryptoManager.encrypt(data)
    plaintext = CryptoManager.decrypt(ciphertext)
    assert plaintext == data
