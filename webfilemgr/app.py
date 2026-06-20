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
    response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(filename)}"'
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
                    raise web.HTTPInternalServerError(reason="Failed to resolve CDN URL. File may be corrupted.")
            
            # Fetch image
            async with session.get(cdn_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    
                    # Decrypt in thread to avoid blocking event loop
                    loop = asyncio.get_event_loop()
                    encrypted_data = await loop.run_in_executor(None, ImageCoder.decode, image_bytes)
                    decrypted_data = await loop.run_in_executor(None, CryptoManager.decrypt, encrypted_data)
                    
                    await response.write(decrypted_data)
                else:
                    raise web.HTTPInternalServerError(reason=f"Failed to fetch chunk. Status {resp.status}")
                    
    return response

async def handle_delete(request):
    filename = request.match_info.get('filename')
    is_folder = request.query.get('is_folder') == 'true'
    db = DatabaseManager()
    
    try:
        if is_folder:
            # Explicitly delete chunks for every file in the folder first,
            # in case ON DELETE CASCADE is not active on this DB.
            all_files = db.list_files()
            prefix = filename + "/"
            for f in all_files:
                if f['filename'].startswith(prefix):
                    db.delete_chunks(f['id'])
            db.delete_folder(filename)
            return web.json_response({"success": True})
            
        file_record = db.get_file(filename)
        if not file_record:
            return web.json_response({"error": "Not found"}, status=404)
            
        db.delete_chunks(file_record['id'])
        db.delete_file(filename)
        return web.json_response({"success": True})
    except Exception as e:
        print(f"Delete failed for '{filename}': {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_upload(request):
    reader = await request.multipart()
    
    path_prefix = ""
    filename = ""
    filepath = ""
    
    # Process fields dynamically
    while True:
        field = await reader.next()
        if not field:
            break
            
        if field.name == 'path':
            path_prefix = (await field.read()).decode('utf-8')
        elif field.name == 'file':
            filename = field.filename
            if path_prefix:
                filename = f"{path_prefix}/{filename}".replace("//", "/")
                
            os.makedirs(config.SPOOL_DIR, exist_ok=True)
            import uuid
            safe_spool_name = filename.replace("/", "_") + "_" + str(uuid.uuid4())
            filepath = os.path.join(config.SPOOL_DIR, safe_spool_name)
            
            with open(filepath, 'wb') as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
                    
    if not filepath:
        return web.json_response({"error": "No file uploaded"}, status=400)
            
    # If the file already exists, delete the old record so upload_file
    # doesn't silently refuse to overwrite it.
    db = DatabaseManager()
    existing = db.get_file(filename)
    if existing:
        db.delete_chunks(existing['id'])
        db.delete_file(filename)
    
    from main import upload_file
    
    try:
        await upload_file(filepath, filename_override=filename)
    except Exception as e:
        print(f"Upload failed: {e}")
        return web.json_response({"error": str(e)}, status=500)
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)
            
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
    if request.content_type == 'application/json':
        data = await request.json()
        items = data.get('items', [])
    else:
        data = await request.post()
        items_str = data.get('items', '[]')
        import json
        items = json.loads(items_str)
    
    db = DatabaseManager()
    files_to_download = {}
    
    for item in items:
        name = item['name']
        is_folder = item['is_folder']
        if is_folder:
            all_db_files = db.list_files()
            prefix = name + "/"
            for f in all_db_files:
                if f['filename'].startswith(prefix):
                    files_to_download[f['id']] = f
        else:
            f = db.get_file(name)
            if f: files_to_download[f['id']] = f
            
    import tempfile, zipfile
    from roblox import RobloxClient
    roblox = RobloxClient()
    
    # Create temp zip file
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    loop = asyncio.get_event_loop()
    
    async with ClientSession() as session:
        # Offload zip file creation
        def create_zip_archive():
            return zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)
        
        zipf = await loop.run_in_executor(None, create_zip_archive)
        
        try:
            for f in files_to_download.values():
                if f['filename'].endswith('.keep'):
                    continue # Skip .keep files, but keep legitimate 0 byte files!
                    
                chunks = db.get_chunks(f['id'])
                
                # Create empty file in zip if 0 bytes
                if f['size'] == 0:
                    await loop.run_in_executor(None, zipf.writestr, f['filename'], b'')
                    continue
                
                # Write chunks to a temporary file locally, then add to zip.
                # This avoids holding all chunk data in memory (OOM-safe).
                temp_chunk_file = temp_zip_path + f"_{f['id']}.tmp"
                try:
                    with open(temp_chunk_file, 'wb') as tcf:
                        for chunk in chunks:
                            cdn_url = chunk['cdn_url']
                            if not cdn_url:
                                cdn_url = await roblox.resolve_cdn_url(chunk['asset_id'])
                                if cdn_url: db.update_chunk_cdn_url(chunk['id'], cdn_url)
                                else: raise web.HTTPInternalServerError(reason="Chunk corrupted")
                            async with session.get(cdn_url) as resp:
                                if resp.status == 200:
                                    image_bytes = await resp.read()
                                    enc_data = await loop.run_in_executor(None, ImageCoder.decode, image_bytes)
                                    dec_data = await loop.run_in_executor(None, CryptoManager.decrypt, enc_data)
                                    tcf.write(dec_data)
                                else:
                                    raise web.HTTPInternalServerError(reason="Chunk download failed")
                                    
                    # Now write the completed file into the zip
                    await loop.run_in_executor(None, zipf.write, temp_chunk_file, f['filename'])
                finally:
                    if os.path.exists(temp_chunk_file):
                        os.remove(temp_chunk_file)
        finally:
            await loop.run_in_executor(None, zipf.close)
                                
    response = web.StreamResponse()
    response.headers['Content-Disposition'] = 'attachment; filename="BloxDrive.zip"'
    response.headers['Content-Type'] = 'application/zip'
    response.headers['Content-Length'] = str(os.path.getsize(temp_zip_path))
    
    await response.prepare(request)
    
    try:
        with open(temp_zip_path, 'rb') as f:
            while True:
                data = await loop.run_in_executor(None, f.read, 1024 * 1024)
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
