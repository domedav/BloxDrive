import pytest
import sys
import os
import argparse
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
import main

def test_main_mount(monkeypatch):
    mock_mount = MagicMock()
    monkeypatch.setattr('main.mount_drive', mock_mount)
    
    with patch('sys.argv', ['main.py', 'mount', '/tmp/test_mnt']):
        main.main()
        
    mock_mount.assert_called_once_with('/tmp/test_mnt')

def test_main_upload(monkeypatch):
    mock_upload = AsyncMock()
    monkeypatch.setattr('main.upload_file', mock_upload)
    
    with patch('sys.argv', ['main.py', 'upload', 'test.txt']):
        main.main()
        
    mock_upload.assert_called_once_with('test.txt')

def test_main_auth(monkeypatch):
    mock_reauth = MagicMock()
    monkeypatch.setattr('auth_server.force_reauth', mock_reauth)
    
    with patch('sys.argv', ['main.py', 'auth']):
        main.main()
        
    mock_reauth.assert_called_once()

def test_main_raid_status(monkeypatch):
    mock_health = AsyncMock()
    monkeypatch.setattr('recovery.RaidRecovery.print_health', mock_health)
    
    with patch('sys.argv', ['main.py', 'raid', 'status']):
        main.main()
        
    mock_health.assert_called_once()
