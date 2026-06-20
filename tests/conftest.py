import pytest
import os
import shutil
import uuid

@pytest.fixture(autouse=True)
def mock_roblox_client(request, monkeypatch):
    if 'nomockroblox' in request.keywords:
        return
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
    from roblox import RobloxClient
    
    mock_cdn = "/tmp/mock_roblox_cdn"
    os.makedirs(mock_cdn, exist_ok=True)
    
    async def mock_upload(self, filepath, name=None):
        asset_id = str(uuid.uuid4())
        shutil.copy(filepath, os.path.join(mock_cdn, asset_id))
        return asset_id
        
    async def mock_resolve(self, asset_id):
        return f"http://mock_cdn/{asset_id}"
        
    monkeypatch.setattr(RobloxClient, "upload_asset", mock_upload)
    monkeypatch.setattr(RobloxClient, "resolve_cdn_url", mock_resolve)
    
    # Mock aiohttp.ClientSession._request
    import aiohttp
    original_request = aiohttp.ClientSession._request
    
    class MockResponse:
        def __init__(self, content):
            self.status = 200
            self._content = content
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
        async def read(self):
            return self._content
        async def text(self):
            return self._content.decode()
        async def json(self):
            import json
            return json.loads(self._content)
            
    async def mock_request(self, method, str_or_url, **kwargs):
        url_str = str(str_or_url)
        if url_str.startswith("http://mock_cdn/"):
            asset_id = url_str.split("/")[-1]
            filepath = os.path.join(mock_cdn, asset_id)
            with open(filepath, 'rb') as f:
                content = f.read()
            return MockResponse(content)
        return await original_request(self, method, str_or_url, **kwargs)
        
    monkeypatch.setattr(aiohttp.ClientSession, "_request", mock_request)
    
    # Mock requests.get for fuse_app.py
    import requests
    original_requests_get = requests.get
    
    class MockRequestsResponse:
        def __init__(self, content):
            self.status_code = 200
            self.content = content
            
        def raise_for_status(self):
            pass
            
    def mock_requests_get(url, **kwargs):
        url_str = str(url)
        if url_str.startswith("http://mock_cdn/"):
            asset_id = url_str.split("/")[-1]
            filepath = os.path.join(mock_cdn, asset_id)
            with open(filepath, 'rb') as f:
                content = f.read()
            return MockRequestsResponse(content)
        return original_requests_get(url, **kwargs)
        
    monkeypatch.setattr(requests, "get", mock_requests_get)
