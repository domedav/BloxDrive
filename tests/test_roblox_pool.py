import pytest
import os
from unittest.mock import MagicMock, patch

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from roblox_pool import RobloxPool
from encoder import ImageCoder
from crypto import CryptoManager

# We don't want the mock_roblox_client fixture interfering because we want to mock specific methods for parity testing
pytestmark = pytest.mark.nomockroblox

class MockDatabaseManager:
    def __init__(self, accounts):
        self.accounts = accounts

    def get_healthy_accounts(self):
        return self.accounts

@pytest.fixture
def mock_db():
    accounts = [
        {'id': 1, 'api_key': 'key1', 'user_id': 'user1', 'auth_token': 'token1'},
        {'id': 2, 'api_key': 'key2', 'user_id': 'user2', 'auth_token': 'token2'},
        {'id': 3, 'api_key': 'key3', 'user_id': 'user3', 'auth_token': 'token3'}
    ]
    db = MockDatabaseManager(accounts)
    return db

@pytest.fixture
@patch('roblox_pool.DatabaseManager')
def pool(mock_db_class, mock_db):
    mock_db_class.return_value = mock_db
    # This will init RobloxPool with our mock db accounts
    return RobloxPool()

def test_pool_initialization(pool):
    assert pool.n == 3
    assert pool.raid_enabled is True
    assert set(pool.account_ids) == {1, 2, 3}
    assert 1 in pool.clients
    assert pool.clients[1].api_key == 'key1'

def test_get_stripe_assignment(pool):
    # Stripe 0: parity is index 0 -> account 1. Data -> accounts 2, 3
    stripe_0 = pool.get_stripe_assignment(0)
    assert stripe_0['parity'] == 1
    assert stripe_0['data'] == [2, 3]

    # Stripe 1: parity is index 1 -> account 2. Data -> accounts 1, 3
    stripe_1 = pool.get_stripe_assignment(1)
    assert stripe_1['parity'] == 2
    assert stripe_1['data'] == [1, 3]

    # Stripe 2: parity is index 2 -> account 3. Data -> accounts 1, 2
    stripe_2 = pool.get_stripe_assignment(2)
    assert stripe_2['parity'] == 3
    assert stripe_2['data'] == [1, 2]

def test_compute_parity():
    chunk1 = b"abc" # 97, 98, 99
    chunk2 = b"def" # 100, 101, 102
    parity = RobloxPool.compute_parity(chunk1, chunk2)
    expected_parity = bytes([97^100, 98^101, 99^102])
    assert parity == expected_parity

def test_compute_parity_uneven():
    chunk1 = b"abcd"
    chunk2 = b"de"
    parity = RobloxPool.compute_parity(chunk1, chunk2)
    # chunk2 is padded with zeros: b"de\x00\x00"
    expected_parity = bytes([
        chunk1[0] ^ chunk2[0],
        chunk1[1] ^ chunk2[1],
        chunk1[2] ^ 0,
        chunk1[3] ^ 0
    ])
    assert parity == expected_parity

def test_recover_chunk():
    chunk1 = b"hello"
    chunk2 = b"world"
    chunk3 = b"pad\x00\x00"
    parity = RobloxPool.compute_parity(chunk1, chunk2, chunk3)

    # Recover chunk2
    recovered_chunk2 = RobloxPool.recover_chunk([chunk1, chunk3], parity)
    # The recovered chunk will be padded to max length
    assert recovered_chunk2[:len(chunk2)] == chunk2

@pytest.mark.asyncio
async def test_fetch_chunk_data_fast_path(pool, tmp_path):
    # Setup
    plaintext = b"fast_path_data"
    encrypted = CryptoManager.encrypt(plaintext)
    encoded_image_path = str(tmp_path / "img1.png")
    ImageCoder.encode(encrypted, encoded_image_path)
    with open(encoded_image_path, 'rb') as f:
        encoded_image = f.read()

    chunk = {'id': 100, 'account_id': 1, 'asset_id': 'asset1', 'cdn_url': 'http://cdn/100'}

    mock_db_manager = MagicMock()

    class MockResponse:
        def __init__(self, content, status=200):
            self.content = content
            self.status = status
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def read(self): return self.content

    class MockSession:
        def __init__(self):
            self.closed = False
        def get(self, url):
            if url == 'http://cdn/100':
                return MockResponse(encoded_image)
            return MockResponse(b"not found", status=404)
        async def close(self):
            self.closed = True

    session = MockSession()

    data = await pool.fetch_chunk_data(chunk, mock_db_manager, session=session)
    assert data == plaintext

@pytest.mark.asyncio
async def test_fetch_chunk_data_recovery_path(pool, tmp_path):
    # Setup 3 chunks (2 data, 1 parity)
    data1 = b"data_chunk_1_pad"
    data2 = b"data_chunk_2_pad"
    
    enc1 = CryptoManager.encrypt(data1)
    enc2 = CryptoManager.encrypt(data2)
    
    # Parity is computed over the encrypted data!
    parity_enc = RobloxPool.compute_parity(enc1, enc2)
    
    img1_path = str(tmp_path / "img1.png")
    img2_path = str(tmp_path / "img2.png")
    img_parity_path = str(tmp_path / "img_parity.png")
    ImageCoder.encode(enc1, img1_path)
    ImageCoder.encode(enc2, img2_path)
    ImageCoder.encode(parity_enc, img_parity_path)
    
    with open(img1_path, 'rb') as f:
        img1 = f.read()
    with open(img2_path, 'rb') as f:
        img2 = f.read()
    with open(img_parity_path, 'rb') as f:
        img_parity = f.read()

    # We want to fetch chunk 1, but it fails, triggering recovery.
    chunk_to_fetch = {'id': 101, 'account_id': 1, 'asset_id': 'asset_1', 'cdn_url': 'http://fail/101', 'size': len(data1), 'chunk_type': 'data'}
    
    mock_db_manager = MagicMock()
    mock_db_manager.get_stripe_for_chunk.return_value = {
        'stripe_index': 0,
        'members': [
            {'chunk_id': 101, 'account_id': 1, 'role': 'data'},
            {'chunk_id': 102, 'account_id': 2, 'role': 'data'},
            {'chunk_id': 103, 'account_id': 3, 'role': 'parity'}
        ]
    }

    # db connection mock to fetch other member chunks
    mock_cursor = MagicMock()
    def cursor_fetchone():
        # called twice: once for chunk 102, once for 103
        call_count = cursor_fetchone.call_count
        cursor_fetchone.call_count += 1
        if call_count == 0:
            return {'id': 102, 'account_id': 2, 'asset_id': 'asset_2', 'cdn_url': 'http://cdn/102', 'size': len(data2), 'chunk_type': 'data'}
        else:
            return {'id': 103, 'account_id': 3, 'asset_id': 'asset_3', 'cdn_url': 'http://cdn/103', 'size': 0, 'chunk_type': 'parity'}
    cursor_fetchone.call_count = 0
    mock_cursor.fetchone = cursor_fetchone
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_db_manager.get_connection.return_value = mock_conn

    class MockResponse:
        def __init__(self, content, status=200):
            self.content = content
            self.status = status
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def read(self): return self.content

    class MockSession:
        def __init__(self):
            self.closed = False
        def get(self, url):
            if url == 'http://fail/101':
                return MockResponse(b"", status=500)  # Primary fails
            elif url == 'http://cdn/102':
                return MockResponse(img2)             # Sibling data chunk
            elif url == 'http://cdn/103':
                return MockResponse(img_parity)       # Parity chunk
            return MockResponse(b"not found", status=404)
        async def close(self):
            self.closed = True

    session = MockSession()
    
    # We also mock RobloxClient.resolve_cdn_url just in case
    with patch.object(pool.clients[2], 'resolve_cdn_url', return_value='http://cdn/102'), \
         patch.object(pool.clients[3], 'resolve_cdn_url', return_value='http://cdn/103'):
         
        recovered_data = await pool.fetch_chunk_data(chunk_to_fetch, mock_db_manager, session=session)
    
    assert recovered_data == data1
