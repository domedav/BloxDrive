import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'webfilemgr'))

from app import handle_list_files, handle_delete, handle_rename, handle_create_folder, handle_raid_status

class MockRequest:
    def __init__(self, method="GET", match_info=None, query=None, json_data=None):
        self.method = method
        self.match_info = match_info or {}
        self.query = query or {}
        self._json_data = json_data
        
    async def json(self):
        return self._json_data

@pytest.mark.asyncio
async def test_list_files(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def list_files(self):
            import datetime
            return [{'id': 1, 'filename': 'test.txt', 'size': 100, 'created_at': datetime.datetime.now()}]
            
    monkeypatch.setattr('app.DatabaseManager', MockDB)
    req = MockRequest()
    resp = await handle_list_files(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert len(data) == 1
    assert data[0]['filename'] == 'test.txt'

@pytest.mark.asyncio
async def test_delete_file(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def get_file(self, name):
            return {'id': 1, 'filename': name, 'size': 100}
        def delete_chunks(self, file_id): pass
        def delete_file(self, name): pass
            
    monkeypatch.setattr('app.DatabaseManager', MockDB)
    req = MockRequest(match_info={'filename': 'test.txt'})
    resp = await handle_delete(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data['success'] is True

@pytest.mark.asyncio
async def test_rename_file(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def rename_file(self, old, new): pass
            
    monkeypatch.setattr('app.DatabaseManager', MockDB)
    req = MockRequest(json_data={'old_name': 'old.txt', 'new_name': 'new.txt', 'is_folder': False})
    resp = await handle_rename(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data['success'] is True

@pytest.mark.asyncio
async def test_create_folder(monkeypatch):
    class MockDB:
        def __init__(self): pass
        def get_file(self, name): return None
        def add_file(self, name, size): pass
        def update_mode(self, name, mode): pass
            
    monkeypatch.setattr('app.DatabaseManager', MockDB)
    req = MockRequest(json_data={'path': 'new_folder'})
    resp = await handle_create_folder(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data['success'] is True

@pytest.mark.asyncio
async def test_raid_status(monkeypatch):
    class MockPool:
        @property
        def raid_enabled(self): return True
        @property
        def n(self): return 2
        
    class MockDB:
        def __init__(self): pass
        def get_healthy_accounts(self):
            return [{'id': 1, 'label': 'acc1'}, {'id': 2, 'label': 'acc2'}]
            
    monkeypatch.setattr('app.RobloxPool', MockPool)
    monkeypatch.setattr('app.DatabaseManager', MockDB)
    
    req = MockRequest()
    resp = await handle_raid_status(req)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data['raid_enabled'] is True
    assert data['total_accounts'] == 2
    assert len(data['accounts']) == 2
