import os
import aiohttp
import asyncio
import json
import uuid
import config
from datetime import datetime, timedelta

class RobloxClient:
    """
    Handles uploading assets to Roblox via the Open Cloud API.
    Also handles resolving Asset IDs to CDN URLs for streaming.
    """
    def __init__(self):
        self.api_key = config.ROBLOX_API_KEY
        self.user_id = config.ROBLOX_USER_ID
        self.headers = {
            "x-api-key": self.api_key
        }
        
        # Rate Limiting
        self.uploads_per_min = config.RATE_LIMIT_UPLOADS_PER_MIN
        self.upload_timestamps = []

    async def _wait_for_rate_limit(self):
        """Simple leaky bucket rate limiting."""
        now = datetime.now()
        # Keep only timestamps from the last 60 seconds
        self.upload_timestamps = [t for t in self.upload_timestamps if now - t < timedelta(seconds=60)]
        
        if len(self.upload_timestamps) >= self.uploads_per_min:
            wait_time = 60 - (now - self.upload_timestamps[0]).total_seconds()
            if wait_time > 0:
                print(f"Rate limit approaching. Waiting {wait_time:.2f} seconds...")
                await asyncio.sleep(wait_time)
            
            # Clean up again after waiting
            now = datetime.now()
            self.upload_timestamps = [t for t in self.upload_timestamps if now - t < timedelta(seconds=60)]

        self.upload_timestamps.append(datetime.now())

    async def upload_asset(self, filepath: str, name: str = None) -> str:
        """
        Uploads a PNG file as a Decal asset to Roblox.
        Returns the final Asset ID.
        """
        await self._wait_for_rate_limit()

        if not name:
            name = os.path.basename(filepath)

        url = "https://apis.roblox.com/assets/v1/assets"
        
        # The CreationContext requires expectedPrice = 0 for free uploads
        creation_context = {
            "creator": {
                "userId": self.user_id
            },
            "expectedPrice": 0
        }

        form_data = aiohttp.FormData()
        form_data.add_field('request', 
                            json.dumps({
                                "assetType": "Decal",
                                "displayName": name[:50], # Max 50 chars
                                "description": "BloxDrive by domedav",
                                "creationContext": creation_context
                            }),
                            content_type='application/json')
        
        with open(filepath, 'rb') as f:
            form_data.add_field('fileContent', f.read(), filename=name, content_type='image/png')

        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, data=form_data) as response:
                if response.status == 429:
                    print("Hit 429 Too Many Requests. Backing off.")
                    await asyncio.sleep(10)
                    return await self.upload_asset(filepath, name)
                
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Failed to upload asset: {response.status} - {text}")
                
                data = await response.json()
                operation_id = data.get('operationId')
                if not operation_id:
                    raise Exception(f"No operationId in response: {data}")

                return await self._poll_operation(session, operation_id)

    async def _poll_operation(self, session, operation_id: str) -> str:
        """Polls the LRO endpoint until the asset is created."""
        url = f"https://apis.roblox.com/assets/v1/operations/{operation_id}"
        
        for _ in range(30): # Max 30 polls (approx 1 minute)
            await asyncio.sleep(2)
            async with session.get(url) as response:
                if response.status == 429:
                    await asyncio.sleep(5)
                    continue

                if response.status != 200:
                    raise Exception(f"Polling failed: {response.status}")
                
                data = await response.json()
                if data.get('done'):
                    if 'response' in data and 'assetId' in data['response']:
                        return data['response']['assetId']
                    else:
                        raise Exception(f"Upload failed during processing: {data}")
        
        raise Exception("Timed out waiting for asset creation.")

    async def resolve_cdn_url(self, asset_id: str) -> str:
        """
        Resolves an Asset ID to a direct rbxcdn.com URL.
        Note: The assetdelivery API does not require Open Cloud auth, it uses standard web requests.
        """
        import auth_server
        token = auth_server.get_auth_token()
        cookies = {".ROBLOSECURITY": token} if token else {}
        
        url = f"https://assetdelivery.roblox.com/v2/assetId/{asset_id}"
        async with aiohttp.ClientSession(headers=self.headers, cookies=cookies) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Asset delivery failed: {response.status}")
                    # Sometimes requires retry or format change
                    return None
                data = await response.json()
                locations = data.get('locations', [])
                if locations and len(locations) > 0:
                    cdn_url = locations[0].get('location')
                    
                    # If this is a decal, the CDN URL returns an XML file instead of the raw image
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
                return None
