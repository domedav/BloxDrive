import os
from roblox import RobloxClient
from db import DatabaseManager
from encoder import ImageCoder
from crypto import CryptoManager
import aiohttp
import asyncio

class RobloxPool:
    """Manages N RobloxClient instances for RAID-5 distribution."""

    def __init__(self):
        self.clients = {}    # account_id -> RobloxClient
        self.account_ids = []  # ordered list for stripe assignment
        self._load_from_db()

    def _load_from_db(self):
        """Loads healthy accounts from DB, creates RobloxClient per account."""
        db = DatabaseManager()
        accounts = db.get_healthy_accounts()
        from crypto import CryptoManager
        import base64
        for acc in accounts:
            account_id = acc['id']
            try:
                decrypted_token = CryptoManager.decrypt(base64.b64decode(acc['auth_token'])).decode('utf-8')
            except Exception:
                decrypted_token = ""
                
            client = RobloxClient(
                api_key=acc['api_key'],
                user_id=acc['user_id'],
                auth_token=decrypted_token,
                account_id=account_id
            )
            self.clients[account_id] = client
            self.account_ids.append(account_id)
            
        # Fallback to config if no accounts in DB (backward compatibility)
        if not self.account_ids:
            import config
            import json
            
            token = None
            if os.path.exists('auth.json'):
                try:
                    with open('auth.json', 'r') as f:
                        data = json.load(f)
                        token = data.get('token')
                        if token:
                            from crypto import CryptoManager
                            import base64
                            token = CryptoManager.decrypt(base64.b64decode(token)).decode('utf-8')
                except Exception:
                    pass
            
            # Using -1 for legacy fallback account
            client = RobloxClient(
                api_key=config.ROBLOX_API_KEY,
                user_id=config.ROBLOX_USER_ID,
                auth_token=token,
                account_id=-1
            )
            self.clients[-1] = client
            self.account_ids.append(-1)

    @property
    def n(self) -> int:
        """Number of active accounts."""
        return len(self.account_ids)

    @property
    def raid_enabled(self) -> bool:
        return self.n >= 2

    def get_stripe_assignment(self, stripe_index: int) -> dict:
        """Returns { 'data': [account_id, ...], 'parity': account_id } for a given stripe.
        Parity rotates: parity_account = account_ids[stripe_index % N]
        Data fills remaining N-1 accounts in order."""
        if not self.raid_enabled:
            return {'data': [self.account_ids[0]], 'parity': None}
            
        N = self.n
        parity_idx = stripe_index % N
        parity_account = self.account_ids[parity_idx]
        
        data_accounts = []
        for i in range(N):
            if i != parity_idx:
                data_accounts.append(self.account_ids[i])
                
        return {
            'data': data_accounts,
            'parity': parity_account
        }

    def get_client(self, account_id: int) -> RobloxClient:
        """Returns the RobloxClient for a specific account."""
        if account_id is None: # Legacy chunk
            account_id = -1
        return self.clients.get(account_id)

    @staticmethod
    def compute_parity(*data_chunks: bytes) -> bytes:
        """XOR all data chunks together to produce parity.
        Pads shorter chunks with zeros to match the longest."""
        if not data_chunks:
            return b""
            
        max_len = max(len(chunk) for chunk in data_chunks)
        parity = bytearray(max_len)
        
        for chunk in data_chunks:
            for i in range(len(chunk)):
                parity[i] ^= chunk[i]
                
        return bytes(parity)

    @staticmethod
    def recover_chunk(surviving_chunks: list[bytes], parity: bytes) -> bytes:
        """XOR all surviving chunks with parity to recover the missing one.
        Any zero-padding on the missing chunk will be correctly recovered as zeros."""
        # XOR is commutative and associative. Recovering a chunk is just
        # XORing all other chunks together with the parity chunk.
        all_chunks = list(surviving_chunks) + [parity]
        return RobloxPool.compute_parity(*all_chunks)

    async def fetch_chunk_data(self, chunk: dict, db: DatabaseManager, session: aiohttp.ClientSession = None) -> bytes:
        """Fetches and decrypts a chunk, falling back to parity reconstruction if needed."""
        # Fast path: try the assigned account
        client = self.get_client(chunk['account_id'])
        if client:
            try:
                cdn_url = chunk['cdn_url'] or await client.resolve_cdn_url(chunk['asset_id'])
                if not chunk['cdn_url'] and cdn_url:
                    db.update_chunk_cdn_url(chunk['id'], cdn_url)
                    
                if cdn_url:
                    # Fetch
                    close_session = False
                    if session is None:
                        session = aiohttp.ClientSession()
                        close_session = True
                        
                    try:
                        async with session.get(cdn_url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                encrypted = ImageCoder.decode(image_bytes)
                                return CryptoManager.decrypt(encrypted)
                    finally:
                        if close_session:
                            await session.close()
            except Exception as e:
                print(f"Error fetching chunk {chunk['id']} from account {chunk['account_id']}: {e}")
                # Fall through to recovery
        
        # Recovery path
        stripe = db.get_stripe_for_chunk(chunk['id'])
        if not stripe:
            raise IOError(f"Chunk {chunk['id']} unavailable and no RAID parity exists")
            
        print(f"Attempting RAID recovery for chunk {chunk['id']} (Stripe {stripe['stripe_index']})")
        
        surviving_data = []
        parity_data = None
        
        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True
            
        try:
            for member in stripe['members']:
                if member['chunk_id'] == chunk['id']:
                    continue
                    
                member_client = self.get_client(member['account_id'])
                if not member_client:
                    raise IOError(f"Cannot recover: missing client for account {member['account_id']}")
                    
                # We need the chunk record to get the asset_id
                # (stripe_members doesn't store asset_id, we must fetch from chunks)
                from contextlib import closing
                with closing(db.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as db_cursor:
                    db_cursor.execute("SELECT * FROM chunks WHERE id = %s", (member['chunk_id'],))
                    member_chunk = db_cursor.fetchone()
                
                cdn_url = member_chunk['cdn_url'] or await member_client.resolve_cdn_url(member_chunk['asset_id'])
                if not cdn_url:
                    raise IOError(f"Cannot recover: failed to resolve CDN for member chunk {member['chunk_id']}")
                    
                async with session.get(cdn_url) as resp:
                    if resp.status != 200:
                        raise IOError(f"Cannot recover: failed to download member chunk {member['chunk_id']}")
                    image_bytes = await resp.read()
                    
                # We decode but DO NOT decrypt yet! Parity is computed over ENCRYPTED data.
                decoded_encrypted = ImageCoder.decode(image_bytes)
                
                if member['role'] == 'parity':
                    parity_data = decoded_encrypted
                else:
                    surviving_data.append(decoded_encrypted)
                    
            if parity_data is None and chunk['chunk_type'] != 'parity':
                raise IOError("Cannot recover: parity chunk is missing")
                
            # Reconstruct encrypted data
            recovered_encrypted = self.recover_chunk(surviving_data, parity_data)
            
            # Trim recovered data to the original size + GCM/IV overhead
            # Overhead is 28 bytes. The size column stores plaintext size.
            actual_encrypted_size = chunk['size'] + 28
            recovered_encrypted = recovered_encrypted[:actual_encrypted_size]
            
            # Decrypt
            return CryptoManager.decrypt(recovered_encrypted)
            
        finally:
            if close_session:
                await session.close()
