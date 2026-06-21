import http.server
import socketserver
import webbrowser
import urllib.parse
import json
import os
import config

PORT = config.AUTH_PORT

class AuthHandler(http.server.SimpleHTTPRequestHandler):
    setup_mode = "setup"
    old_account_id = None
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # Read current settings to pre-fill if available
            settings_file = config.SETTINGS_FILE
            current_api_key = config.ROBLOX_API_KEY if config.ROBLOX_API_KEY != "YOUR_API_KEY_HERE" else ""
            current_user_id = config.ROBLOX_USER_ID if config.ROBLOX_USER_ID != "YOUR_ROBLOX_USER_ID_HERE" else ""
            
            
            # If adding an account, we want empty fields and a label
            if AuthHandler.setup_mode in ["add_account", "replace_account"]:
                current_api_key = ""
                current_user_id = ""
                
                if AuthHandler.setup_mode == "replace_account":
                    title = "Replace Roblox Account (RAID Recovery)"
                    desc = "One of your Roblox accounts was banned or its token expired. Please add a new account to recover your data."
                else:
                    title = "Add Roblox Account (RAID)"
                    desc = "Please configure your new Roblox Open Cloud credentials to continue."
                    
                label_field = """
                    <div style="margin-bottom: 20px;">
                        <label style="font-weight: bold; display: block; margin-bottom: 5px;">0. Account Label (e.g. Account1)</label>
                        <input type="text" name="label" required style="width: 100%; padding: 10px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box;" placeholder="Account Label"/>
                    </div>
                """
            else:
                title = "BloxDrive Setup Wizard"
                desc = "Please configure your Roblox Open Cloud credentials to continue."
                label_field = '<input type="hidden" name="label" value="Primary"/>'

            html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>{title}</title>
            </head>
            <body style="font-family: sans-serif; margin: 40px; background-color: #f4f4f9; color: #333; max-width: 600px; margin: 40px auto; padding: 20px; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h2 style="color: #0078d7; border-bottom: 2px solid #eee; padding-bottom: 10px;">{title}</h2>
                <p>{desc}</p>
                
                <form method="POST" action="/submit">
                    {label_field}
                    
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
            <head>
                <meta charset="utf-8">
            </head>
            <body style="font-family: sans-serif; text-align: center; margin-top: 100px; background-color: #f4f4f9;">
                <h2 style="color: #28a745;">Configuration Saved Successfully!</h2>
                <p>You can close this window and return to your terminal.</p>
                <p>BloxDrive will now start automatically.</p>
                
                <div style="margin: 40px auto; max-width: 600px; text-align: left; background-color: #fff3cd; padding: 20px; border-radius: 8px; border: 1px solid #ffeeba;">
                    <h3 style="margin-top: 0; color: #856404;">🛡️ Protect your data with RAID-5</h3>
                    <p style="color: #856404; font-size: 14px;">BloxDrive supports multi-account redundancy. If you only have 1 account linked, your data is at risk if that account gets banned or deleted by Roblox.</p>
                    <p style="color: #856404; font-size: 14px;"><strong>Highly Recommended:</strong> Consider adding more Roblox accounts using the Web UI (RAID Settings) or by running <code>./bloxdrive.sh raid add</code> in your terminal. This will split your files across multiple accounts, ensuring no data is lost even if an account is banned!</p>
                </div>
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
            label = parsed.get('label', ['Primary'])[0].strip()
            
            if api_key and user_id and token:
                if not is_auth_valid(token):
                    self.send_error(400, "The .ROBLOSECURITY cookie provided is invalid or expired. Please check and try again.")
                    return

                # Save to database
                try:
                    from db import DatabaseManager
                    db = DatabaseManager()
                    # Check if DB has accounts table (it might not be initialized if first run, but DatabaseManager creates tables)
                    db.add_account(label, api_key, user_id, token)
                except Exception as e:
                    self.send_error(500, f"Database error: {e}")
                    return
                
                # We still save primary credentials to config.py for backwards compatibility
                if AuthHandler.setup_mode == "setup":
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

                    with open('auth.json', 'w') as f:
                        json.dump({'token': token}, f)
                        
                elif AuthHandler.setup_mode == "replace_account" and AuthHandler.old_account_id is not None:
                    try:
                        # Auto-setup: Remove the old dead account and launch recovery
                        db.remove_account(AuthHandler.old_account_id)
                        print(f"Removed dead account ID {AuthHandler.old_account_id}.")
                        
                        # Trigger async recovery in the background or next step
                        # Since we are in an HTTP handler, we can't easily wait for async, so we'll launch a subprocess
                        import subprocess
                        import sys
                        print("Automatically launching RAID recovery onto the new account...")
                        subprocess.Popen([sys.executable, "src/main.py", "raid", "recover"])
                    except Exception as e:
                        print(f"Failed to auto-recover: {e}")
                
                print(f"Configuration and Auth Token successfully saved for account '{label}'!")
                
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
    from db import DatabaseManager
    db = DatabaseManager()
    db.execute("DELETE FROM accounts") # Delete all accounts to force full setup
    run_setup(mode="setup")

def run_web_setup(mode="setup", old_account_id=None):
    AuthHandler.setup_mode = mode
    AuthHandler.old_account_id = old_account_id
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

def run_cli_setup(mode="setup", old_account_id=None):
    print("\n" + "="*50)
    print("🖥️  CLI Setup Wizard 🖥️")
    print("="*50)
    if mode in ["add_account", "replace_account"]:
        if mode == "replace_account":
            print("Replace Roblox Account (RAID Recovery)")
            print("One of your Roblox accounts was banned or its token expired. Please add a new account to recover your data.")
        else:
            print("Add Roblox Account (RAID)")
            print("Please configure your new Roblox Open Cloud credentials to continue.")
        label = input("0. Account Label (e.g. Account1): ").strip()
        while not label:
            label = input("Label is required. Account Label: ").strip()
    else:
        print("BloxDrive Setup Wizard")
        print("Please configure your Roblox Open Cloud credentials to continue.")
        label = "Primary"
        
    import config
    current_api_key = config.ROBLOX_API_KEY if config.ROBLOX_API_KEY != "YOUR_API_KEY_HERE" else ""
    current_user_id = config.ROBLOX_USER_ID if config.ROBLOX_USER_ID != "YOUR_ROBLOX_USER_ID_HERE" else ""
    
    if mode in ["add_account", "replace_account"]:
        current_api_key = ""
        current_user_id = ""

    print("\n1. Roblox API Key")
    print("Create an API key with Assets API -> Write permissions at Creator Dashboard.")
    api_key_prompt = f"API Key [{current_api_key}]: " if current_api_key else "API Key: "
    api_key = input(api_key_prompt).strip()
    if not api_key:
        api_key = current_api_key
    while not api_key:
        api_key = input("API Key is required: ").strip()

    print("\n2. Roblox User ID")
    print("Your numeric User ID from your Profile URL.")
    user_id_prompt = f"User ID [{current_user_id}]: " if current_user_id else "User ID: "
    user_id = input(user_id_prompt).strip()
    if not user_id:
        user_id = current_user_id
    while not user_id:
        user_id = input("User ID is required: ").strip()

    print("\n3. .ROBLOSECURITY Cookie")
    print("Required for bypassing asset upload quotas. Inspect Element -> Application/Storage -> Cookies.")
    token = input("Cookie: ").strip()
    while not token:
        token = input("Cookie is required: ").strip()

    if not is_auth_valid(token):
        print("\n[!] Error: The .ROBLOSECURITY cookie provided is invalid or expired. Please check and try again.")
        return run_cli_setup(mode, old_account_id)

    # Save to database
    try:
        from db import DatabaseManager
        db = DatabaseManager()
        db.add_account(label, api_key, user_id, token)
    except Exception as e:
        print(f"\n[!] Database error: {e}")
        return

    # Backwards compatibility config
    if mode == "setup":
        settings = {}
        if os.path.exists(config.SETTINGS_FILE):
            import json
            with open(config.SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
        
        settings['ROBLOX_API_KEY'] = api_key
        settings['ROBLOX_USER_ID'] = user_id
        
        import json
        with open(config.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
            
        config.ROBLOX_API_KEY = api_key
        config.ROBLOX_USER_ID = user_id

        with open('auth.json', 'w') as f:
            json.dump({'token': token}, f)
            
    elif mode == "replace_account" and old_account_id is not None:
        try:
            db.remove_account(old_account_id)
            print(f"Removed dead account ID {old_account_id}.")
            
            import subprocess
            import sys
            print("Automatically launching RAID recovery onto the new account...")
            subprocess.Popen([sys.executable, "src/main.py", "raid", "recover"])
        except Exception as e:
            print(f"Failed to auto-recover: {e}")
    
    print(f"\n✅ Configuration and Auth Token successfully saved for account '{label}'!")
    return

def run_setup(mode="setup", old_account_id=None):
    print("\nHow would you like to complete the setup?")
    print("1) Web Browser (Recommended)")
    print("2) Command Line Interface (CLI)")
    try:
        choice = input("Enter choice (1/2) [1]: ").strip()
    except EOFError:
        choice = "1"
    
    if choice == "2":
        run_cli_setup(mode, old_account_id)
    else:
        run_web_setup(mode, old_account_id)

def ensure_setup():
    """Checks if API Key, User ID, and Cookie are present and valid. If not, forces Web/CLI Setup."""
    from db import DatabaseManager
    try:
        db = DatabaseManager()
        accounts = db.get_healthy_accounts()
    except Exception:
        accounts = []
        
    needs_setup = len(accounts) == 0
    failed_account = None
        
    if needs_setup:
        # Fallback check for legacy auth.json + config
        import config
        has_config = config.ROBLOX_API_KEY and config.ROBLOX_API_KEY != "YOUR_API_KEY_HERE"
        has_token = False
        if os.path.exists('auth.json'):
            try:
                with open('auth.json', 'r') as f:
                    data = json.load(f)
                    has_token = is_auth_valid(data.get('token'))
            except Exception:
                pass
                
        if has_config and has_token:
            needs_setup = False
    else:
        # We have accounts in the DB. Let's verify ALL of them.
        for acc in accounts:
            if not is_auth_valid(acc['auth_token']):
                failed_account = acc
                break
            
    if needs_setup:
        print("\n" + "="*50)
        print("🔧 BloxDrive Setup Required 🔧")
        print("="*50)
        print("Your configuration is missing or your authentication token has expired.")
        run_setup(mode="setup")
    elif failed_account:
        print("\n" + "="*50)
        print(f"🚨 CRITICAL: Account Failure Detected! 🚨")
        print("="*50)
        print(f"Account '{failed_account['label']}' (ID: {failed_account['id']}) is no longer accessible!")
        print("The authentication token has expired or the account was banned.")
        print("To prevent data loss, please provide a replacement account now.")
        run_setup(mode="replace_account", old_account_id=failed_account['id'])
    else:
        print("Authentication verified and active for all accounts.")
        
    return True

if __name__ == "__main__":
    ensure_setup()
