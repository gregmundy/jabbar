import base64
import hashlib
import http.server
import imaplib
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

AUTH_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
TOKEN_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"


class OAuth2Error(Exception):
    pass


def generate_pkce() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def build_xoauth2_string(user: str, access_token: str) -> str:
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"


def load_cached_tokens(token_file: str) -> dict | None:
    if not os.path.exists(token_file):
        return None
    with open(token_file) as f:
        return json.load(f)


def save_tokens(tokens: dict, token_file: str) -> None:
    with open(token_file, "w") as f:
        json.dump(tokens, f, indent=2)


def refresh_access_token(client_id: str, refresh_token: str) -> dict:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise OAuth2Error(f"Token refresh failed: {error_body}")


def authorize_browser(client_id: str, redirect_uri: str) -> dict:
    code_verifier, code_challenge = generate_pkce()
    auth_code_result = {}
    port = int(redirect_uri.split(":")[2].split("/")[0])

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if "code" in params:
                auth_code_result["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Jabbar: Authorization successful! You can close this tab.</h1>")
            else:
                auth_code_result["error"] = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization failed.</h1>")

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    auth_url = (
        AUTH_ENDPOINT + "?" + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        })
    )
    print(f"Opening browser for Microsoft login...")
    print(f"If browser doesn't open, go to:\n{auth_url}\n")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    if "code" not in auth_code_result:
        raise OAuth2Error(f"Browser authorization failed: {auth_code_result}")

    token_data = urllib.parse.urlencode({
        "client_id": client_id,
        "code": auth_code_result["code"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise OAuth2Error(f"Token exchange failed: {error_body}")


def get_oauth2_connection(account_config: dict) -> imaplib.IMAP4_SSL:
    client_id = account_config["client_id"]
    redirect_uri = account_config.get("redirect_uri", "http://localhost:8400/callback")
    token_file = account_config.get("token_file", ".hotmail_tokens.json")
    email_addr = account_config["email"]
    host = account_config["imap_host"]
    port = account_config.get("imap_port", 993)

    tokens = load_cached_tokens(token_file)

    if tokens and "refresh_token" in tokens:
        try:
            tokens = refresh_access_token(client_id, tokens["refresh_token"])
            save_tokens(tokens, token_file)
        except OAuth2Error:
            os.remove(token_file)
            tokens = None

    if not tokens:
        tokens = authorize_browser(client_id, redirect_uri)
        save_tokens(tokens, token_file)

    auth_string = build_xoauth2_string(email_addr, tokens["access_token"])
    conn = imaplib.IMAP4_SSL(host, port)
    conn.authenticate("XOAUTH2", lambda x: auth_string.encode())
    return conn
