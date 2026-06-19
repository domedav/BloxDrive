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
    is_folder = request.query.get('is_folder') == 'true'
    db = DatabaseManager()
    
    if is_folder:
        db.delete_folder(filename)
        return web.json_response({"success": True})
        
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
    import uuid
    safe_spool_name = filename.replace("/", "_") + "_" + str(uuid.uuid4())
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

async def handle_rename(request):
    data = await request.json()
    old_name = data.get('old_name')
    new_name = data.get('new_name')
    is_folder = data.get('is_folder', False)
    
    db = DatabaseManager()
    if is_folder:
        db.rename_folder(old_name, new_name)
    else:
        db.rename_file(old_name, new_name)
    return web.json_response({"success": True})

async def handle_create_folder(request):
    data = await request.json()
    path = data.get('path')
    if not path:
        return web.json_response({"error": "Path required"}, status=400)
    
    # We create a dummy .keep file to instantiate the folder
    dummy_file = f"{path}/.keep"
    db = DatabaseManager()
    if not db.get_file(dummy_file):
        db.add_file(dummy_file, 0)
        import stat
        db.update_mode(dummy_file, stat.S_IFDIR | 0o755)
    return web.json_response({"success": True})

async def handle_download_zip(request):
    data = await request.json()
    items = data.get('items', [])
    
    db = DatabaseManager()
    files_to_download = []
    
    for item in items:
        name = item['name']
        is_folder = item['is_folder']
        if is_folder:
            all_db_files = db.list_files()
            prefix = name + "/"
            for f in all_db_files:
                if f['filename'].startswith(prefix):
                    files_to_download.append(f)
        else:
            f = db.get_file(name)
            if f: files_to_download.append(f)
            
    import tempfile, zipfile
    from roblox import RobloxClient
    roblox = RobloxClient()
    
    # Create temp zip file
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    async with ClientSession() as session:
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            for f in files_to_download:
                if f['size'] == 0:
                    continue # Skip .keep
                    
                chunks = db.get_chunks(f['id'])
                
                with zipf.open(f['filename'], 'w', force_zip64=True) as z_file:
                    for chunk in chunks:
                        cdn_url = chunk['cdn_url']
                        if not cdn_url:
                            cdn_url = await roblox.resolve_cdn_url(chunk['asset_id'])
                            if cdn_url: db.update_chunk_cdn_url(chunk['id'], cdn_url)
                            else: continue
                        async with session.get(cdn_url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                loop = asyncio.get_event_loop()
                                enc_data = await loop.run_in_executor(None, ImageCoder.decode, image_bytes)
                                dec_data = await loop.run_in_executor(None, CryptoManager.decrypt, enc_data)
                                z_file.write(dec_data)
                                
    response = web.StreamResponse()
    response.headers['Content-Disposition'] = 'attachment; filename="BloxDrive.zip"'
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Length'] = str(os.path.getsize(temp_zip_path))
    
    await response.prepare(request)
    
    try:
        with open(temp_zip_path, 'rb') as f:
            while True:
                data = f.read(1024 * 1024)
                if not data:
                    break
                await response.write(data)
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
            
    return response

async def handle_index(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), 'static', 'index.html'))

app = web.Application()
app.client_max_size = 1024 * 1024 * 1024 * 10 # 10GB limit

# API Routes
app.router.add_get('/api/files', handle_list_files)
app.router.add_get('/api/download/{filename:.*}', handle_download)
app.router.add_delete('/api/delete/{filename:.*}', handle_delete)
app.router.add_post('/api/upload', handle_upload)
app.router.add_post('/api/rename', handle_rename)
app.router.add_post('/api/create_folder', handle_create_folder)
app.router.add_post('/api/download_zip', handle_download_zip)

# Serve Frontend
app.router.add_get('/', handle_index)
app.router.add_static('/static/', path=os.path.join(os.path.dirname(__file__), 'static'), name='static')

if __name__ == '__main__':
    port = config.WEB_PORT
    host = config.WEB_HOST
    print(f"Starting Web UI on http://{host}:{port}")
    web.run_app(app, host=host, port=port)
