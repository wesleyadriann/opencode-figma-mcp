#!/usr/bin/env python3
"""
Figma MCP OAuth Flow — Gera access_token e refresh_token para o Figma MCP server.

Pré-requisitos:
  pip3 install cryptography --break-system-packages

Uso:
  python3 figma_oauth.py

Fluxo:
  1. Gera par PKCE (code_verifier + code_challenge S256)
  2. Imprime URL de autorização do Figma
  3. Inicia servidor HTTP na porta 38471 aguardando redirect
  4. Troca o authorization code por tokens (access_token + refresh_token)
  5. Salva tokens em ~/.figma_mcp_tokens.json

Parâmetros que podem precisar atualização:
  - CLIENT_ID / CLIENT_SECRET: extraídos do VS Code (ver passo-a-passo.md)
  - REDIRECT_PORT: porta do servidor local (deve casar com redirect_uri)
"""

import http.server
import urllib.parse
import hashlib
import base64
import secrets
import json
import urllib.request
import sys
import ssl
import os

# ============================================================
# CONFIGURAÇÃO — Atualize se necessário
# ============================================================
CLIENT_ID = "ecdiBvGKx5gcSXLEMO15CT"
CLIENT_SECRET = "<Extraído do state.vscdb>"
TOKEN_URL = "https://api.figma.com/v1/oauth/token"
AUTH_URL = "https://www.figma.com/oauth/mcp"
RESOURCE = "https://mcp.figma.com/mcp"
SCOPE = "mcp:connect"
REDIRECT_PORT = 38471
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/"
TOKENS_FILE = os.path.expanduser("~/.figma_mcp_tokens.json")

# SSL context — desabilita verificação para compatibilidade com Python Homebrew
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def generate_pkce():
    """Gera par PKCE: code_verifier (aleatório) e code_challenge (SHA256 + base64url)."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    return code_verifier, code_challenge


def build_auth_url(code_challenge, state):
    """Constrói a URL de autorização do Figma."""
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": SCOPE,
        "resource": RESOURCE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    })
    return f"{AUTH_URL}?{params}"


def wait_for_callback(port):
    """Inicia servidor HTTP e aguarda o redirect do Figma com o authorization code."""
    captured = {}

    class OAuthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                captured["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body style='font-family:monospace;padding:40px'>"
                    b"<h2>Token capturado!</h2>"
                    b"<p>Voce pode fechar esta aba.</p>"
                    b"</body></html>"
                )
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), OAuthHandler)
    server.timeout = 300  # 5 minutos
    server.handle_request()
    return captured.get("code")


def exchange_code_for_tokens(code, code_verifier):
    """Troca o authorization code por access_token e refresh_token."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": code_verifier,
        }
    ).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode())


def main():
    # 1. Gerar PKCE
    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(16)

    # 2. Construir URL de autorização
    auth_url = build_auth_url(code_challenge, state)

    print(f"\n{'=' * 60}")
    print("ABRA ESTA URL NO NAVEGADOR:")
    print(f"{'=' * 60}")
    print(f"\n{auth_url}\n")
    print(f"{'=' * 60}")
    print(f"Aguardando redirect na porta {REDIRECT_PORT}...")
    print(f"{'=' * 60}\n")
    sys.stdout.flush()

    # 3. Aguardar callback
    code = wait_for_callback(REDIRECT_PORT)
    if not code:
        print("Nenhum code recebido. Tente novamente.")
        sys.exit(1)

    print(f"\nCODE capturado: {code[:20]}...")
    print("\nTrocando code por token...")
    sys.stdout.flush()

    # 4. Trocar code por tokens
    try:
        tokens = exchange_code_for_tokens(code, code_verifier)
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            body = e.read().decode()[:500]
        print(f"Erro ao obter tokens: {e}")
        print(f"Detalhe: {body}")
        sys.exit(1)

    # 5. Exibir e salvar tokens
    print(f"\n{'=' * 60}")
    print("TOKENS OBTIDOS:")
    print(f"{'=' * 60}")
    print(json.dumps(tokens, indent=2))

    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"\nSalvo em {TOKENS_FILE}")

    # 6. Instrução para configurar no OpenCode
    access_token = tokens.get("access_token", "")
    print(f"\n{'=' * 60}")
    print("CONFIGURAÇÃO DO OPENCODE")
    print(f"{'=' * 60}")
    print(f"Adicione ao ~/.config/opencode/opencode.jsonc:")
    print(f"""
{{
  "mcp": {{
    "Figma": {{
      "type": "remote",
      "url": "https://mcp.figma.com/mcp",
      "enabled": true,
      "headers": {{
        "Authorization": "Bearer {access_token}"
      }},
      "oauth": false
    }}
  }}
}}""")
    print(f"\nDepois reinicie o OpenCode.")


if __name__ == "__main__":
    main()
