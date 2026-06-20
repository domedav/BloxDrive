import os
import aiohttp
import asyncio
import json
import uuid
import config
import random
from datetime import datetime, timedelta

class RobloxClient:
    """
    Handles uploading assets to Roblox via the Open Cloud API.
    Also handles resolving Asset IDs to CDN URLs for streaming.
    """
    _session = None

    def __init__(self, api_key=None, user_id=None, auth_token=None, account_id=None):
        self.api_key = api_key or config.ROBLOX_API_KEY
        self.user_id = user_id or config.ROBLOX_USER_ID
        self.headers = {
            "x-api-key": self.api_key
        }
        
        self.uploads_per_min = config.RATE_LIMIT_UPLOADS_PER_MIN
        self.downloads_per_min = config.RATE_LIMIT_DOWNLOADS_PER_MIN
        
        self.account_id = account_id

        # Cache auth token in memory to avoid reading from disk on every chunk
        self._auth_token = auth_token
        self._auth_loaded = auth_token is not None

        # Instance-level rate limiters
        self._upload_lock = asyncio.Lock()
        self._download_lock = asyncio.Lock()
        self._upload_timestamps = []
        self._download_timestamps = []

    @classmethod
    async def get_session(cls, headers=None):
        if cls._session is None or cls._session.closed:
            # We don't set global headers here so we can override per request if needed
            cls._session = aiohttp.ClientSession()
        return cls._session

    async def _wait_for_rate_limit(self):
        """Simple leaky bucket rate limiting with Lock."""
        async with self._upload_lock:
            now = datetime.now()
            # Keep only timestamps from the last 60 seconds
            self._upload_timestamps = [t for t in self._upload_timestamps if now - t < timedelta(seconds=60)]
            
            if len(self._upload_timestamps) >= self.uploads_per_min:
                wait_time = 60 - (now - self._upload_timestamps[0]).total_seconds()
                if wait_time > 0:
                    print(f"Rate limit approaching. Waiting {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                
                now = datetime.now()
                self._upload_timestamps = [t for t in self._upload_timestamps if now - t < timedelta(seconds=60)]

            self._upload_timestamps.append(datetime.now())
            
        await asyncio.sleep(random.uniform(1.0, 4.0))

    async def _wait_for_read_rate_limit(self):
        """Simple leaky bucket rate limiting for downloads with Lock."""
        async with self._download_lock:
            now = datetime.now()
            self._download_timestamps = [t for t in self._download_timestamps if now - t < timedelta(seconds=60)]
            
            if len(self._download_timestamps) >= self.downloads_per_min:
                wait_time = 60 - (now - self._download_timestamps[0]).total_seconds()
                if wait_time > 0:
                    print(f"Read rate limit approaching. Waiting {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                
                now = datetime.now()
                self._download_timestamps = [t for t in self._download_timestamps if now - t < timedelta(seconds=60)]

            self._download_timestamps.append(datetime.now())
            
        await asyncio.sleep(random.uniform(0.5, 2.0))

    async def upload_asset(self, filepath: str, name: str = None) -> str:
        """
        Uploads a PNG file as a Decal asset to Roblox.
        Returns the final Asset ID. Includes robust retry logic.
        """
        if not name:
            name = os.path.basename(filepath)

        url = "https://apis.roblox.com/assets/v1/assets"
        
        creation_context = {
            "creator": {
                "userId": self.user_id
            },
            "expectedPrice": 0
        }

        # Setup loop for retries (max 5 retries for 429 or network errors)
        max_retries = 5
        for attempt in range(max_retries):
            await self._wait_for_rate_limit()

            form_data = aiohttp.FormData()
            form_data.add_field('request', 
                                json.dumps({
                                    "assetType": "Decal",
                                    "displayName": name[:50],
                                    "description": "BloxDrive by domedav",
                                    "creationContext": creation_context
                                }),
                                content_type='application/json')
            
            # Read synchronously here is okay since it's a small chunk file, but we will offload the caller's read.
            with open(filepath, 'rb') as f:
                file_bytes = f.read()
                form_data.add_field('fileContent', file_bytes, filename=name, content_type='image/png')

            session = await self.get_session()
            
            try:
                async with session.post(url, data=form_data, headers=self.headers) as response:
                    if response.status == 429:
                        print(f"Hit 429 Too Many Requests (attempt {attempt+1}/{max_retries}). Backing off.")
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"Failed to upload asset: {response.status} - {text}")
                    
                    try:
                        data = await response.json()
                    except json.JSONDecodeError:
                        text = await response.text()
                        raise Exception(f"Failed to parse JSON response: {text}")

                    operation_id = data.get('operationId')
                    if not operation_id:
                        raise Exception(f"No operationId in response: {data}")

                    return await self._poll_operation(session, operation_id)
            except aiohttp.ClientError as e:
                print(f"Network error during upload (attempt {attempt+1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise Exception(f"Upload failed after {max_retries} attempts: {e}")
                await asyncio.sleep(5)
                
        raise Exception("Upload failed: Max retries exceeded.")

    async def _poll_operation(self, session, operation_id: str) -> str:
        """Polls the LRO endpoint until the asset is created."""
        url = f"https://apis.roblox.com/assets/v1/operations/{operation_id}"
        
        polls = 0
        max_polls = 30
        while polls < max_polls:
            polls += 1
            await asyncio.sleep(2)
            try:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 429:
                        await asyncio.sleep(5)
                        polls -= 1 # Don't burn a poll iteration on rate limit
                        continue

                    if response.status != 200:
                        raise Exception(f"Polling failed: {response.status}")
                    
                    try:
                        data = await response.json()
                    except json.JSONDecodeError:
                        text = await response.text()
                        raise Exception(f"Failed to parse JSON response: {text}")

                    if data.get('done'):
                        if 'response' in data and 'assetId' in data['response']:
                            return data['response']['assetId']
                        else:
                            raise Exception(f"Upload failed during processing: {data}")
            except aiohttp.ClientError as e:
                print(f"Network error during polling: {e}")
                await asyncio.sleep(5)
                polls -= 1
        
        raise Exception("Timed out waiting for asset creation.")

    async def resolve_cdn_url(self, asset_id: str) -> str:
        """
        Resolves an Asset ID to a direct rbxcdn.com URL.
        """
        if not self._auth_loaded:
            if os.path.exists('auth.json'):
                try:
                    with open('auth.json', 'r') as f:
                        data = json.load(f)
                        self._auth_token = data.get('token')
                except Exception:
                    pass
            self._auth_loaded = True
            
        cookies = {".ROBLOSECURITY": self._auth_token} if self._auth_token else {}
        
        max_retries = 3
        url = f"https://assetdelivery.roblox.com/v2/assetId/{asset_id}"
        session = await self.get_session()
        
        for attempt in range(max_retries):
            await self._wait_for_read_rate_limit()
            try:
                async with session.get(url, headers=self.headers, cookies=cookies) as response:
                    if response.status == 429:
                        print(f"Resolve CDN hit 429. Backing off (attempt {attempt+1}).")
                        await asyncio.sleep(5 * (attempt + 1))
                        continue
                        
                    if response.status != 200:
                        print(f"Asset delivery failed: {response.status}")
                        continue
                        
                    try:
                        data = await response.json()
                    except json.JSONDecodeError:
                        continue
                        
                    locations = data.get('locations', [])
                    if locations and len(locations) > 0:
                        cdn_url = locations[0].get('location')
                        
                        # XML resolution for decals
                        async with session.get(cdn_url) as cdn_resp:
                            if cdn_resp.status == 200:
                                content = await cdn_resp.read()
                                if b'<roblox xmlns:xmime=' in content[:50]:
                                    import re
                                    match = re.search(br'id=(\d+)', content)
                                    if match:
                                        image_id = match.group(1).decode()
                                        return await self.resolve_cdn_url(image_id)
                        return cdn_url
            except aiohttp.ClientError as e:
                print(f"Network error resolving CDN: {e}")
                await asyncio.sleep(2)
        
        return None
