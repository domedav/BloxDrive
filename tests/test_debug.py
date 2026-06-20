import pytest
from unittest.mock import patch, AsyncMock
from raid_migration import RaidMigration
from recovery import RaidRecovery
import asyncio

class DummyPool:
    def __init__(self):
        self.fetch_chunk_data = AsyncMock(return_value=b"dummy_data")

@patch('raid_migration.DatabaseManager')
@patch('raid_migration.RobloxPool')
@patch('raid_migration.upload_file')
@pytest.mark.asyncio
async def test_debug(mock_upload, mock_pool_cls, mock_db_cls):
    mock_pool = DummyPool()
    mock_pool_cls.return_value = mock_pool
    from raid_migration import RaidMigration
    m = RaidMigration()
    print("M.POOL:", m.pool)
    print("M.POOL.FETCH:", m.pool.fetch_chunk_data)

