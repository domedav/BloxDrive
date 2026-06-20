import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import os
import sys

# Ensure src is in the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from raid_migration import RaidMigration
from recovery import RaidRecovery

class DummyDB:
    def __init__(self):
        self.files = []
        self.chunks = {}
        self.stripes = {}
        self.healthy_accounts = []

    def list_files(self):
        return self.files

    def get_chunks(self, file_id):
        return self.chunks.get(file_id, [])

    def get_stripes_for_file(self, file_id):
        return self.stripes.get(file_id, [])

    def get_healthy_accounts(self):
        return self.healthy_accounts

class DummyPool:
    def __init__(self):
        self.n = 3
        self.raid_enabled = True
        self.account_ids = [1, 2, 3]
        self.fetch_chunk_data = AsyncMock(return_value=b"dummy_data")

@pytest.fixture
def mock_db():
    db = DummyDB()
    # Add a healthy file (no migration needed)
    db.files.append({'id': 1, 'filename': 'healthy.txt', 'size': 100})
    db.chunks[1] = [{'id': 10, 'account_id': 1, 'chunk_type': 'data'}]
    db.stripes[1] = [{
        'id': 99,
        'members': [{'account_id': 1}]
    }]
    
    # Add a file needing migration (missing account_id)
    db.files.append({'id': 2, 'filename': 'needs_migration.txt', 'size': 200})
    db.chunks[2] = [{'id': 20, 'account_id': None, 'chunk_type': None}]

    # Add a degraded file
    db.files.append({'id': 3, 'filename': 'degraded.txt', 'size': 300})
    db.chunks[3] = [
        {'id': 30, 'account_id': 1, 'chunk_type': 'data'},
        {'id': 31, 'account_id': 99, 'chunk_type': 'parity'} # 99 is missing from pool
    ]
    db.stripes[3] = [{
        'id': 100,
        'members': [{'account_id': 1}, {'account_id': 99}]
    }]

    # Add a lost file (2+ missing)
    db.files.append({'id': 4, 'filename': 'lost.txt', 'size': 400})
    db.chunks[4] = []
    db.stripes[4] = [{
        'id': 101,
        'members': [{'account_id': 98}, {'account_id': 99}]
    }]

    db.healthy_accounts = [
        {'id': 1, 'label': 'acc1'},
        {'id': 2, 'label': 'acc2'},
        {'id': 3, 'label': 'acc3'}
    ]
    return db

@pytest.fixture
def mock_pool():
    return DummyPool()

@pytest.mark.asyncio
@patch('raid_migration.DatabaseManager')
@patch('raid_migration.RobloxPool')
@patch('raid_migration.upload_file')
async def test_migrate_existing_files(mock_upload, mock_pool_cls, mock_db_cls, mock_db, mock_pool, capsys):
    mock_db_cls.return_value = mock_db
    mock_pool_cls.return_value = mock_pool
    mock_upload.return_value = None

    migration = RaidMigration()
    await migration.migrate_existing_files()

    # The file 'needs_migration.txt' should be migrated
    # The file 'healthy.txt' should not
    # The file 'degraded.txt' has valid chunk info but let's check its chunk_type.
    # We defined degraded.txt with chunk_type 'data' and 'parity', so needs_migration = False.
    
    mock_upload.assert_called_once()
    args, kwargs = mock_upload.call_args
    assert kwargs.get('filename_override') == 'needs_migration.txt'
    assert kwargs.get('file_id_override') == 2
    
    # Check output
    captured = capsys.readouterr()
    assert "Migrating 'needs_migration.txt'" in captured.out
    assert "Migrated 1 files to RAID-3" in captured.out

@pytest.mark.asyncio
@patch('recovery.DatabaseManager')
@patch('recovery.RobloxPool')
async def test_print_health(mock_pool_cls, mock_db_cls, mock_db, mock_pool, capsys):
    mock_db_cls.return_value = mock_db
    mock_pool_cls.return_value = mock_pool

    recovery = RaidRecovery()
    await recovery.print_health()

    captured = capsys.readouterr()
    assert "Total Configured Accounts: 3" in captured.out
    assert "Files Scanned: 4" in captured.out
    assert "Healthy: 1" in captured.out # healthy.txt
    assert "Degraded (1 Drive Failed): 1" in captured.out # degraded.txt
    assert "Lost (2+ Drives Failed): 1" in captured.out # lost.txt

@pytest.mark.asyncio
@patch('recovery.DatabaseManager')
@patch('recovery.RobloxPool')
@patch('raid_migration.RaidMigration._migrate_file')
async def test_interactive_recover(mock_migrate_file, mock_rec_pool_cls, mock_rec_db_cls, mock_db, mock_pool, capsys):
    mock_rec_db_cls.return_value = mock_db
    mock_rec_pool_cls.return_value = mock_pool
    mock_migrate_file.return_value = None

    recovery = RaidRecovery()
    await recovery.interactive_recover()

    # degraded.txt should be recovered
    mock_migrate_file.assert_called_once()
    args, kwargs = mock_migrate_file.call_args
    assert args[0]['filename'] == 'degraded.txt'

    captured = capsys.readouterr()
    assert "Found 1 degraded files" in captured.out
    assert "Recovering 'degraded.txt'..." in captured.out
    assert "Successfully rebuilt 1 out of 1 files." in captured.out

@pytest.mark.asyncio
@patch('raid_migration.DatabaseManager')
@patch('raid_migration.RobloxPool')
async def test_migrate_existing_files_disabled(mock_pool_cls, mock_db_cls, mock_db, mock_pool, capsys):
    mock_pool.raid_enabled = False
    mock_db_cls.return_value = mock_db
    mock_pool_cls.return_value = mock_pool

    migration = RaidMigration()
    await migration.migrate_existing_files()

    captured = capsys.readouterr()
    assert "RAID is not enabled" in captured.out

@pytest.mark.asyncio
@patch('recovery.DatabaseManager')
@patch('recovery.RobloxPool')
async def test_interactive_recover_disabled(mock_pool_cls, mock_db_cls, mock_db, mock_pool, capsys):
    mock_pool.raid_enabled = False
    mock_db_cls.return_value = mock_db
    mock_pool_cls.return_value = mock_pool

    recovery = RaidRecovery()
    await recovery.interactive_recover()

    captured = capsys.readouterr()
    assert "RAID is not enabled" in captured.out
