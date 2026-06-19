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
            html = """
            <html>
            <head><title>BloxDrive Authentication</title></head>
            <body style="font-family: sans-serif; margin: 40px; background-color: #f4f4f9;">
                <h2 style="color: #333;">BloxDrive Authentication</h2>
                <p>To use BloxDrive, you must authenticate using your Roblox account.</p>
                <ol style="line-height: 1.6; font-size: 14px;">
                    <li>Click the button below to open Roblox in a new tab.</li>
                    <li>Log in to your account if you aren't already.</li>
                    <li>Right click anywhere on the page, select <b>"Inspect"</b> (or press F12).</li>
                    <li>Go to the <b>"Application"</b> (Chrome/Edge) or <b>"Storage"</b> (Firefox) tab.</li>
                    <li>On the left sidebar, expand <b>"Cookies"</b> and select <b>"https://www.roblox.com"</b>.</li>
                    <li>Find the cookie named <b>.ROBLOSECURITY</b>, double click its value to copy it, and paste it below.</li>
                </ol>
                <button type="button" onclick="window.open('https://www.roblox.com', '_blank')" style="padding: 10px 20px; border-radius: 5px; border: 1px solid #ccc; background-color: #e0e0e0; cursor: pointer; margin-bottom: 20px; font-weight: bold;">Open Roblox</button>
                <form method="POST" action="/submit">
                    <input type="password" name="token" style="width: 400px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;" placeholder="Paste .ROBLOSECURITY cookie here..."/>
                    <button type="submit" style="padding: 10px 20px; border-radius: 5px; border: none; background-color: #0078d7; color: white; cursor: pointer; font-weight: bold;">Save Token</button>
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
            <body style="font-family: sans-serif; margin: 40px; background-color: #f4f4f9;">
                <h2 style="color: #28a745;">Authentication token saved!</h2>
                <p>You can close this window and return to your terminal.</p>
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
            token = parsed.get('token', [''])[0].strip()
            
            if token:
                with open('auth.json', 'w') as f:
                    json.dump({'token': token}, f)
                print("Token successfully saved to auth.json")
                
                self.send_response(303)
                self.send_header('Location', '/success')
                self.end_headers()
                
                # Signal the server to shutdown
                def kill_server():
                    self.server.shutdown()
                import threading
                threading.Thread(target=kill_server).start()
            else:
                self.send_error(400, "Token missing")

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
    get_auth_token()

def get_auth_token():
    if os.path.exists('auth.json'):
        with open('auth.json', 'r') as f:
            data = json.load(f)
            token = data.get('token')
            if token and is_auth_valid(token):
                print("Authentication verified and active.")
                return token
            else:
                print("Token is invalid or expired. Asking for new token...")
            
    print(f"Starting auth server on port {PORT}...")
    webbrowser.open(f'http://localhost:{PORT}')
    
    # We use a custom subclass to avoid "Address already in use" if the server restarts
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True
        
    with ReusableTCPServer(("", PORT), AuthHandler) as httpd:
        httpd.serve_forever()
        
    with open('auth.json', 'r') as f:
        data = json.load(f)
        token = data.get('token')
        if token and is_auth_valid(token):
            print("Authentication verified and active.")
            return token
        else:
            print("Provided token is still invalid. You may need to authenticate again.")
            return None

if __name__ == "__main__":
    token = get_auth_token()
    print("Auth flow complete. Token ready.")
