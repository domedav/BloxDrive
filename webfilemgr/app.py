import sys
import os
import asyncio
from aiohttp import web, ClientSession
import json

# Add src to python path so we can import BloxDrive core
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager
from roblox import RobloxClient
from encoder import ImageCoder
from crypto import CryptoManager
import config

async def handle_list_files(request):
    db = DatabaseManager()
    files = db.list_files()
    
    # Format dates to string
    for f in files:
        f['created_at'] = f['created_at'].isoformat()
        
    return web.json_response(files)

async def handle_download(request):
    filename = request.match_info.get('filename')
    db = DatabaseManager()
    file_record = db.get_file(filename)
    
    if not file_record:
        return web.Response(status=404, text="File not found")
        
    response = web.StreamResponse()
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.headers['Content-Type'] = 'application/octet-stream'
    response.headers['Content-Length'] = str(file_record['size'])
    
    await response.prepare(request)
    
    chunks = db.get_chunks(file_record['id'])
    roblox = RobloxClient()
    
    async with ClientSession() as session:
        for chunk in chunks:
            cdn_url = chunk['cdn_url']
            if not cdn_url:
                cdn_url = await roblox.resolve_cdn_url(chunk['asset_id'])
                if cdn_url:
                    db.update_chunk_cdn_url(chunk['id'], cdn_url)
                else:
                    continue # Error
            
            # Fetch image
            async with session.get(cdn_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    
                    # Decrypt in thread to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    encrypted_data = await loop.run_in_executor(None, ImageCoder.decode, image_bytes)
                    decrypted_data = await loop.run_in_executor(None, CryptoManager.decrypt, encrypted_data)
                    
                    await response.write(decrypted_data)
                    
    return response

async def handle_delete(request):
    filename = request.match_info.get('filename')
    db = DatabaseManager()
    file_record = db.get_file(filename)
    if not file_record:
        return web.json_response({"error": "Not found"}, status=404)
        
    db.delete_file(filename)
    return web.json_response({"success": True})

async def handle_upload(request):
    reader = await request.multipart()
    # The frontend should send a 'path' field first, then the 'file'
    field = await reader.next()
    
    path_prefix = ""
    if field.name == 'path':
        path_prefix = (await field.read()).decode('utf-8')
        field = await reader.next()
        
    filename = field.filename
    if path_prefix:
        filename = f"{path_prefix}/{filename}".replace("//", "/")
        
    # Save to a temporary spool file
    os.makedirs(config.SPOOL_DIR, exist_ok=True)
    
    # Use a safe flat filename for the spool to avoid directory traversal
    safe_spool_name = filename.replace("/", "_")
    filepath = os.path.join(config.SPOOL_DIR, safe_spool_name)
    
    with open(filepath, 'wb') as f:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            f.write(chunk)
            
    # Trigger upload in background
    from main import upload_file
    
    async def run_upload():
        try:
            await upload_file(filepath, filename_override=filename)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)
                
    asyncio.create_task(run_upload())
    return web.json_response({"success": True})

async def handle_index(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'static', 'index.html'))

app = web.Application()
app.client_max_size = 1024 * 1024 * 1024 * 10 # 10GB limit

# API Routes
app.router.add_get('/api/files', handle_list_files)
app.router.add_get('/api/download/{filename:.*}', handle_download)
app.router.add_delete('/api/delete/{filename:.*}', handle_delete)
app.router.add_post('/api/upload', handle_upload)

# Serve Frontend
app.router.add_get('/', handle_index)
app.router.add_static('/static/', path=os.path.join(os.path.dirname(__file__), 'static'), name='static')

if __name__ == '__main__':
    port = config.WEB_PORT
    host = config.WEB_HOST
    print(f"Starting Web UI on http://{host}:{port}")
    web.run_app(app, host=host, port=port)
