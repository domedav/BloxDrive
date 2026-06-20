import pytest
import os
import json
import aiohttp
import asyncio
from aioresponses import aioresponses
from unittest.mock import patch, MagicMock

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from roblox import RobloxClient

pytestmark = pytest.mark.nomockroblox

class MockResponse:
    def __init__(self, status=200, json_data=None, text_data="", bytes_data=b""):
        self.status = status
        self._json = json_data
        self._text = text_data
        self._bytes = bytes_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if self._json is not None:
            return self._json
        import json
        return json.loads(self._text)

    async def text(self):
        return self._text

    async def read(self):
        return self._bytes

class MockSession:
    def __init__(self):
        self.routes = []

    def add_route(self, method, url, status=200, json_data=None, text_data="", bytes_data=b"", exception=None):
        self.routes.append((method, url, status, json_data, text_data, bytes_data, exception))

    def _match_route(self, method, url):
        url_str = str(url)
        for r_method, r_url, status, json_data, text_data, bytes_data, exception in self.routes:
            if r_method.upper() == method.upper() and url_str.startswith(r_url):
                if exception:
                    self.routes.remove((r_method, r_url, status, json_data, text_data, bytes_data, exception))
                    raise exception
                # Remove route if it was matched (consume it like aresponses)
                self.routes.remove((r_method, r_url, status, json_data, text_data, bytes_data, exception))
                return MockResponse(status, json_data, text_data, bytes_data)
        return MockResponse(404, text_data="Not Found")

    def get(self, url, **kwargs):
        return self._match_route('GET', url)

    def post(self, url, **kwargs):
        return self._match_route('POST', url)

    async def close(self):
        pass

@pytest.fixture
def aresponses(monkeypatch):
    session = MockSession()
    async def mock_get_session(*args, **kwargs):
        return session
    monkeypatch.setattr(RobloxClient, 'get_session', mock_get_session)
    return session

@pytest.fixture
def client():
    # Make sure we don't carry over the session between tests
    RobloxClient._session = None
    client = RobloxClient(api_key="test_api_key", user_id="test_user", auth_token="test_token")
    client.uploads_per_min = 1000  # high rate limit to prevent long delays in test
    client.downloads_per_min = 1000
    yield client

@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch):
    async def _sleep(*args, **kwargs):
        pass
    monkeypatch.setattr(asyncio, 'sleep', _sleep)

@pytest.mark.asyncio
async def test_upload_asset_success(client, aresponses, tmp_path):
    test_file = tmp_path / "test.png"
    test_file.write_bytes(b"fake image data")

    aresponses.add_route('POST', 
        "https://apis.roblox.com/assets/v1/assets",
        status=200,
        json_data={"operationId": "test_op_id"}
    )
    aresponses.add_route('GET', 
        "https://apis.roblox.com/assets/v1/operations/test_op_id",
        status=200,
        json_data={"done": True, "response": {"assetId": "123456789"}}
    )

    asset_id = await client.upload_asset(str(test_file), name="test_name")
    assert asset_id == "123456789"

@pytest.mark.asyncio
async def test_upload_asset_429_retry(client, aresponses, tmp_path):
    test_file = tmp_path / "test.png"
    test_file.write_bytes(b"fake image data")

    # First attempt: 429
    aresponses.add_route('POST', "https://apis.roblox.com/assets/v1/assets", status=429)
    # Second attempt: 200
    aresponses.add_route('POST', 
        "https://apis.roblox.com/assets/v1/assets",
        status=200,
        json_data={"operationId": "test_op_id"}
    )
    
    # Operation polling
    # First poll: 429
    aresponses.add_route('GET', "https://apis.roblox.com/assets/v1/operations/test_op_id", status=429)
    # Second poll: not done
    aresponses.add_route('GET', 
        "https://apis.roblox.com/assets/v1/operations/test_op_id",
        status=200,
        json_data={"done": False}
    )
    # Third poll: done
    aresponses.add_route('GET', 
        "https://apis.roblox.com/assets/v1/operations/test_op_id",
        status=200,
        json_data={"done": True, "response": {"assetId": "987654321"}}
    )

    asset_id = await client.upload_asset(str(test_file))
    assert asset_id == "987654321"
    
@pytest.mark.asyncio
async def test_upload_asset_max_retries(client, aresponses, tmp_path):
    test_file = tmp_path / "test.png"
    test_file.write_bytes(b"fake image data")

    # Always 429
    for _ in range(5):
        aresponses.add_route('POST', "https://apis.roblox.com/assets/v1/assets", status=429)

    with pytest.raises(Exception, match="Max retries exceeded"):
        await client.upload_asset(str(test_file))

@pytest.mark.asyncio
async def test_upload_asset_network_error(client, aresponses, tmp_path):
    test_file = tmp_path / "test.png"
    test_file.write_bytes(b"fake image data")

    # Fail with exception
    aresponses.add_route('POST', "https://apis.roblox.com/assets/v1/assets", exception=aiohttp.ClientError("Test Network Error"))
    # Then success
    aresponses.add_route('POST', 
        "https://apis.roblox.com/assets/v1/assets",
        status=200,
        json_data={"operationId": "test_op_id"}
    )
    aresponses.add_route('GET', 
        "https://apis.roblox.com/assets/v1/operations/test_op_id",
        status=200,
        json_data={"done": True, "response": {"assetId": "111222333"}}
    )

    asset_id = await client.upload_asset(str(test_file))
    assert asset_id == "111222333"

@pytest.mark.asyncio
async def test_resolve_cdn_url_success(client, aresponses):
    aresponses.add_route('GET', 
        "https://assetdelivery.roblox.com/v2/assetId/123",
        status=200,
        json_data={"locations": [{"location": "https://cdn.example.com/asset123"}]}
    )
    # The method checks if it's a decal by doing a GET on the CDN url
    aresponses.add_route('GET', 
        "https://cdn.example.com/asset123",
        status=200,
        bytes_data=b"fake image binary data"
    )

    url = await client.resolve_cdn_url("123")
    assert url == "https://cdn.example.com/asset123"

@pytest.mark.asyncio
async def test_resolve_cdn_url_xml_decal(client, aresponses):
    # Setup mock for asset 123 (decal XML)
    aresponses.add_route('GET', 
        "https://assetdelivery.roblox.com/v2/assetId/123",
        status=200,
        json_data={"locations": [{"location": "https://cdn.example.com/xml_123"}]}
    )
    xml_content = b"""<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime">
        <Item class="Decal" >
            <Properties>
                <Content name="Texture"><url>http://www.roblox.com/asset/?id=456</url></Content>
            </Properties>
        </Item>
    </roblox>"""
    aresponses.add_route('GET', 
        "https://cdn.example.com/xml_123",
        status=200,
        bytes_data=xml_content
    )

    # Setup mock for resolved image asset 456
    aresponses.add_route('GET', 
        "https://assetdelivery.roblox.com/v2/assetId/456",
        status=200,
        json_data={"locations": [{"location": "https://cdn.example.com/actual_image_456"}]}
    )
    aresponses.add_route('GET', 
        "https://cdn.example.com/actual_image_456",
        status=200,
        bytes_data=b"fake image binary data"
    )

    url = await client.resolve_cdn_url("123")
    assert url == "https://cdn.example.com/actual_image_456"

@pytest.mark.asyncio
async def test_resolve_cdn_url_429_retry(client, aresponses):
    # First attempt: 429
    aresponses.add_route('GET', "https://assetdelivery.roblox.com/v2/assetId/123", status=429)
    # Second attempt: 200
    aresponses.add_route('GET', 
        "https://assetdelivery.roblox.com/v2/assetId/123",
        status=200,
        json_data={"locations": [{"location": "https://cdn.example.com/asset123"}]}
    )
    aresponses.add_route('GET', 
        "https://cdn.example.com/asset123",
        status=200,
        bytes_data=b"fake image binary data"
    )

    url = await client.resolve_cdn_url("123")
    assert url == "https://cdn.example.com/asset123"

@pytest.mark.asyncio
async def test_wait_for_rate_limit(client):
    client.uploads_per_min = 2
    
    # Track the duration of waiting
    import time
    start = time.time()
    await client._wait_for_rate_limit()
    await client._wait_for_rate_limit()
    # Third one should delay slightly because limit is 2
    # The actual sleep logic does: wait_time = 60 - (now - self._upload_timestamps[0]).total_seconds()
    # It also sleeps a random 1.0 to 4.0 sec at the end of each.
    # To test without making the test suite slow, we mock sleep but observe calls.
    pass

@pytest.mark.asyncio
async def test_wait_for_rate_limit_mocked(client, monkeypatch):
    sleep_calls = 0
    async def _sleep(*args):
        nonlocal sleep_calls
        sleep_calls += 1
    monkeypatch.setattr(asyncio, 'sleep', _sleep)

    client.uploads_per_min = 2
    
    await client._wait_for_rate_limit()
    await client._wait_for_rate_limit()
    
    # Setting an older timestamp manually to simulate time passage
    from datetime import datetime, timedelta
    client._upload_timestamps[0] = datetime.now() - timedelta(seconds=10)
    
    await client._wait_for_rate_limit()
    
    # It should have called asyncio.sleep multiple times (random sleep + rate limit delay)
    assert sleep_calls >= 3
