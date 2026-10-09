# Figma MCP no OpenCode — Passo a Passo

## Contexto

O OpenCode suporta MCP remoto, mas o Figma MCP usa **OAuth 2.0 com PKCE** (não aceita Personal Access Token). O fluxo abaixo intercepta o `client_id` e `client_secret` que o VS Code registrou via dynamic client registration, e depois faz o fluxo OAuth manualmente para obter um `access_token` válido.

---

## Passo 1 — Configurar o Figma MCP no VS Code

1. Abra o VS Code > `Cmd+Shift+P` > **Preferences: Open User Settings (JSON)**
2. Adicione ao arquivo `mcp.json` em `~/Library/Application Support/Code/User/mcp.json`:

```json
{
  "servers": {
    "figma": {
      "url": "https://mcp.figma.com/mcp",
      "type": "http"
    }
  },
  "inputs": []
}
```

3. Abra o VS Code, vá no chat do Copilot, e conecte o servidor Figma MCP
4. Faça login no Figma quando o popup OAuth aparecer
5. O VS Code vai registrar um client OAuth dinamicamente e armazenar os tokens criptografados

---

## Passo 2 — Extrair client_id e client_secret do VS Code

O VS Code armazena os secrets criptografados no SQLite `state.vscdb`, usando uma chave derivada do Keychain do macOS via PBKDF2.

### 2.1 — Obter a chave do Keychain

```bash
security find-generic-password -s "Code Safe Storage" -a "Code" -w
```

> Anote o valor retornado (base64). Se um popup aparecer pedindo permissão do Keychain, clique em "Always Allow".

### 2.2 — Descriptografar os secrets

Use o script Python abaixo para descriptografar o `state.vscdb`:

```python
import sqlite3, json, base64, os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

DB = os.path.expanduser('~/Library/Application Support/Code/User/globalStorage/state.vscdb')
keychain_password = os.environ['KEYCHAIN_KEY']  # valor do Passo 2.1

# Electron safeStorage: PBKDF2 com salt="saltysalt", 1003 iterações, chave 16 bytes
kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b'saltysalt', iterations=1003)
aes_key = kdf.derive(keychain_password.encode('utf-8'))

conn = sqlite3.connect(DB)
cur = conn.cursor()

def decrypt(enc_bytes, aes_key):
    if enc_bytes[:3] != b'v10':
        return None
    iv = enc_bytes[3:19]
    ct = enc_bytes[19:]
    d = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).decryptor()
    pt = d.update(ct) + d.finalize()
    unpad = sym_padding.PKCS7(128).unpadder()
    return (unpad.update(pt) + unpad.finalize()).decode('utf-8')

# Client Registration (contém client_id e client_secret)
cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE 'secret://dynamicAuthProvider:clientRegistration%'")
for k, v in cur.fetchall():
    enc = bytes(json.loads(v)['data'])
    decoded = decrypt(enc, aes_key)
    print(f'ClientRegistration: {decoded}')

# Tokens OAuth
cur.execute("SELECT key, value FROM ItemTable WHERE key LIKE 'secret://%' AND key LIKE '%isDynamicAuthProvider%' AND key NOT LIKE '%clientRegistration%'")
for k, v in cur.fetchall():
    enc = bytes(json.loads(v)['data'])
    decoded = decrypt(enc, aes_key)
    print(f'Tokens: {decoded}')

conn.close()
```

Anote o `client_id` e `client_secret` do resultado.

---

## Passo 3 — Fazer o fluxo OAuth manualmente com PKCE

Como o token extraído do VS Code pode estar expirado, o ideal é gerar um novo token usando o `client_id` e `client_secret` obtidos no Passo 2.

Use o script `figma_oauth.py` (incluído nesta pasta):

```bash
python3 figma_oauth.py
```

O script vai:
1. Gerar um par PKCE
2. Mostrar uma URL de autenticação do Figma
3. Escutar na porta `38471` aguardando o redirect
4. Trocar o code pelo `access_token` e `refresh_token`
5. Salvar os tokens em `~/.figma_mcp_tokens.json`

> **Atenção:** Se o Python do Homebrew der erro de SSL (`CERTIFICATE_VERIFY_FAILED`), o script já desabilita a verificação de certificado. Funciona para este caso.

---

## Passo 4 — Descobrir o endpoint de token (opcional)

Se precisar confirmar os endpoints OAuth do Figma MCP:

```bash
curl -s https://mcp.figma.com/.well-known/oauth-authorization-server | python3 -m json.tool
```

Retorna:
- `authorization_endpoint`: `https://www.figma.com/oauth/mcp`
- `token_endpoint`: `https://api.figma.com/v1/oauth/token`
- `registration_endpoint`: `https://api.figma.com/v1/oauth/mcp/register`

---

## Passo 5 — Configurar o OpenCode

Edite `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "Figma": {
      "type": "remote",
      "url": "https://mcp.figma.com/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer figu_SEU_ACCESS_TOKEN_AQUI"
      },
      "oauth": false
    }
  }
}
```

> `oauth: false` impede o OpenCode de tentar o fluxo OAuth automático (que falha porque o client não é "owned" pelo OpenCode).

---

## Passo 6 — Reiniciar o OpenCode

```bash
# Feche e reabra o opencode
```

### Verificar se conectou

```bash
tail -20 ~/.local/share/opencode/log/opencode.log | grep -i figma
```

Se não houver `needs_auth` ou `error`, o Figma MCP está funcionando.

---

## Resumo

| Item | Valor |
|------|-------|
| MCP URL | `https://mcp.figma.com/mcp` |
| OAuth Authorization URL | `https://www.figma.com/oauth/mcp` |
| Token Endpoint | `https://api.figma.com/v1/oauth/token` |
| Scope | `mcp:connect` |
| PKCE Method | `S256` |
| Redirect URI | `http://127.0.0.1:38471/` |
| client_id | `ecdiBvGKx5gcSXLEMO15CT` (do VS Code) |
| client_secret | Extraído do `state.vscdb` |

---

## Notas

- O `access_token` expira em ~90 dias (`expires_in: 7776000`)
- O `refresh_token` pode ser usado para renovar sem novo login
- O `client_id` e `client_secret` são fixos enquanto o VS Code não refizer o dynamic client registration
- Se o token expirar, rode o `figma_oauth.py` novamente
