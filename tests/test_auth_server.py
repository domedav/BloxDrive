import pytest
import sys
import os
import urllib.request
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from auth_server import is_auth_valid, force_reauth, ensure_setup, AuthHandler

def test_is_auth_valid(monkeypatch):
    class MockResponse:
        def getcode(self): return 200
    
    def mock_urlopen(req, timeout=5):
        assert ".ROBLOSECURITY=good_token" in req.get_header('Cookie')
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    assert is_auth_valid("good_token") is True
    
    # Test invalid
    def mock_urlopen_invalid(req, timeout=5):
        class MockInvalid:
            def getcode(self): return 401
        return MockInvalid()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_invalid)
    assert is_auth_valid("bad_token") is False
    
    # Test exception
    def mock_urlopen_exc(req, timeout=5):
        raise Exception("Network error")
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_exc)
    assert is_auth_valid("bad_token") is False

def test_ensure_setup_healthy(monkeypatch):
    class MockDB:
        def __init__(self):
            pass
        def get_healthy_accounts(self):
            return [{'id': 1, 'label': 'acc1', 'auth_token': 'good_token'}]
            
    monkeypatch.setattr('db.DatabaseManager', MockDB)
    monkeypatch.setattr('auth_server.is_auth_valid', lambda x: True)
    
    # Should return True without calling run_web_setup
    assert ensure_setup() is True

def test_ensure_setup_needs_setup(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def get_healthy_accounts(self):
            return []
            
    monkeypatch.setattr('db.DatabaseManager', MockDB)
    
    setup_called = []
    def mock_run_web_setup(mode="setup", old_account_id=None):
        setup_called.append(mode)
        
    monkeypatch.setattr('auth_server.run_web_setup', mock_run_web_setup)
    
    # With no auth.json it should require setup
    if os.path.exists('auth.json'):
        os.remove('auth.json')
        
    ensure_setup()
    assert "setup" in setup_called

def test_ensure_setup_replace_account(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def get_healthy_accounts(self):
            return [{'id': 1, 'label': 'acc1', 'auth_token': 'bad_token'}]
            
    monkeypatch.setattr('db.DatabaseManager', MockDB)
    monkeypatch.setattr('auth_server.is_auth_valid', lambda x: False)
    
    setup_called = []
    def mock_run_web_setup(mode="setup", old_account_id=None):
        setup_called.append((mode, old_account_id))
        
    monkeypatch.setattr('auth_server.run_web_setup', mock_run_web_setup)
    
    ensure_setup()
    assert ("replace_account", 1) in setup_called
