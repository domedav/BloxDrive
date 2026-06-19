import http.server
import socketserver
import webbrowser
import urllib.parse
import json
import os
import config

PORT = config.AUTH_PORT

class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # Read current settings to pre-fill if available
            settings_file = config.SETTINGS_FILE
            current_api_key = config.ROBLOX_API_KEY if config.ROBLOX_API_KEY != "YOUR_API_KEY_HERE" else ""
            current_user_id = config.ROBLOX_USER_ID if config.ROBLOX_USER_ID != "YOUR_ROBLOX_USER_ID_HERE" else ""
            
            html = f"""
            <html>
            <head><title>BloxDrive Setup Wizard</title></head>
            <body style="font-family: sans-serif; margin: 40px; background-color: #f4f4f9; color: #333; max-width: 600px; margin: 40px auto; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #0078d7; border-bottom: 2px solid #eee; padding-bottom: 10px;">BloxDrive Setup Wizard</h2>
                <p>Please configure your Roblox Open Cloud credentials to continue.</p>
                
                <form method="POST" action="/submit">
                    
                    <div style="margin-bottom: 20px;">
                        <label style="font-weight: bold; display: block; margin-bottom: 5px;">1. Roblox API Key</label>
                        <p style="font-size: 13px; color: #666; margin-top: 0;">
                            Create an API key with <b>Assets API -> Write</b> permissions at 
                            <a href="https://create.roblox.com/dashboard/credentials" target="_blank" style="color: #0078d7;">Creator Dashboard</a>.
                        </p>
                        <input type="text" name="api_key" value="{current_api_key}" required style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box;" placeholder="Paste API Key..."/>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <label style="font-weight: bold; display: block; margin-bottom: 5px;">2. Roblox User ID</label>
                        <p style="font-size: 13px; color: #666; margin-top: 0;">
                            Your numeric User ID from your <a href="https://www.roblox.com/home" target="_blank" style="color: #0078d7;">Profile URL</a>.
                        </p>
                        <input type="number" name="user_id" value="{current_user_id}" required style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box;" placeholder="e.g. 123456789"/>
                    </div>

                    <div style="margin-bottom: 30px;">
                        <label style="font-weight: bold; display: block; margin-bottom: 5px;">3. .ROBLOSECURITY Cookie</label>
                        <p style="font-size: 13px; color: #666; margin-top: 0;">
                            Required for bypassing asset upload quotas. Inspect Element -> Application/Storage -> Cookies.
                        </p>
                        <input type="password" name="token" required style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box;" placeholder="Paste .ROBLOSECURITY cookie..."/>
                    </div>

                    <button type="submit" style="width: 100%; padding: 12px; border-radius: 5px; border: none; background-color: #0078d7; color: white; cursor: pointer; font-weight: bold; font-size: 16px;">Save & Continue</button>
                </form>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
            
        elif self.path == '/success':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
            <html>
            <body style="font-family: sans-serif; text-align: center; margin-top: 100px; background-color: #f4f4f9;">
                <h2 style="color: #28a745;">Configuration Saved Successfully!</h2>
                <p>You can close this window and return to your terminal.</p>
                <p>BloxDrive will now start automatically.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/submit':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            parsed = urllib.parse.parse_qs(post_data)
            
            api_key = parsed.get('api_key', [''])[0].strip()
            user_id = parsed.get('user_id', [''])[0].strip()
            token = parsed.get('token', [''])[0].strip()
            
            if api_key and user_id and token:
                if not is_auth_valid(token):
                    self.send_error(400, "The .ROBLOSECURITY cookie provided is invalid or expired. Please check and try again.")
                    return

                # Save settings
                settings = {}
                if os.path.exists(config.SETTINGS_FILE):
                    with open(config.SETTINGS_FILE, 'r') as f:
                        settings = json.load(f)
                
                settings['ROBLOX_API_KEY'] = api_key
                settings['ROBLOX_USER_ID'] = user_id
                
                with open(config.SETTINGS_FILE, 'w') as f:
                    json.dump(settings, f, indent=4)
                    
                config.ROBLOX_API_KEY = api_key
                config.ROBLOX_USER_ID = user_id

                # Save token
                with open('auth.json', 'w') as f:
                    json.dump({'token': token}, f)
                
                print("Configuration and Auth Token successfully saved!")
                
                self.send_response(303)
                self.send_header('Location', '/success')
                self.end_headers()
                
                # Signal the server to shutdown after a short delay
                def kill_server():
                    import time
                    time.sleep(1)
                    self.server.shutdown()
                import threading
                threading.Thread(target=kill_server).start()
            else:
                self.send_error(400, "Missing required fields")

def is_auth_valid(token):
    if not token:
        return False
    try:
        import urllib.request
        req = urllib.request.Request("https://users.roblox.com/v1/users/authenticated")
        req.add_header("Cookie", f".ROBLOSECURITY={token}")
        response = urllib.request.urlopen(req, timeout=5)
        return response.getcode() == 200
    except Exception:
        return False

def force_reauth():
    print("Forcing re-authentication...")
    if os.path.exists('auth.json'):
        os.remove('auth.json')
    run_web_setup()

def run_web_setup():
    print(f"\nStarting Web Setup Wizard on port {PORT}...")
    print(f"Please open http://localhost:{PORT} in your browser to continue.")
    
    try:
        webbrowser.open(f'http://localhost:{PORT}')
    except Exception:
        pass
        
    try:
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True
            
        with ReusableTCPServer(("", PORT), AuthHandler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        if e.errno == 98:
            print(f"\n[!] Error: Port {PORT} is already in use!")
            print("It seems another instance of the BloxDrive Setup Wizard is already running.")
            print("Please open http://localhost:32666 in your browser to complete the setup,")
            print("or kill the existing process using the port and try again.")
            exit(1)
        else:
            print(f"\n[!] Failed to start Setup Wizard: {e}")
            exit(1)

def ensure_setup():
    """Checks if API Key, User ID, and Cookie are present and valid. If not, forces Web Setup."""
    import config
    needs_setup = False
    
    if not config.ROBLOX_API_KEY or config.ROBLOX_API_KEY == "YOUR_API_KEY_HERE":
        needs_setup = True
    elif not config.ROBLOX_USER_ID or config.ROBLOX_USER_ID == "YOUR_ROBLOX_USER_ID_HERE":
        needs_setup = True
        
    token = None
    if os.path.exists('auth.json'):
        try:
            with open('auth.json', 'r') as f:
                data = json.load(f)
                token = data.get('token')
        except json.JSONDecodeError:
            pass
            
    if not token or not is_auth_valid(token):
        needs_setup = True
        
    if needs_setup:
        print("\n" + "="*50)
        print("🔧 BloxDrive Setup Required 🔧")
        print("="*50)
        print("Your configuration is missing or your authentication token has expired.")
        run_web_setup()
    else:
        print("Authentication verified and active.")
        
    return True

if __name__ == "__main__":
    ensure_setup()
