# Prompt: Configurar Figma MCP no OpenCode via OAuth

Cole este prompt em uma LLM (ChatGPT, Claude, etc.) para que ela te guie pelo fluxo completo.

---

## Prompt

```
Preciso configurar o Figma MCP server no OpenCode (opencode.ai). O Figma MCP usa OAuth 2.0 com PKCE e não aceita Personal Access Tokens.

Siga estes passos me guiando em cada um:

### 1. Descobrir os endpoints OAuth do Figma MCP
Faça um GET para:
https://mcp.figma.com/.well-known/oauth-authorization-server

Anote:
- authorization_endpoint
- token_endpoint
- registration_endpoint
- scopes_supported
- code_challenge_methods_supported

### 2. Extrair client_id e client_secret do VS Code
O VS Code já tem o Figma MCP configurado com dynamic client registration. Os secrets estão criptografados no SQLite state.vscdb.

No macOS:
- A chave de criptografia está no Keychain: `security find-generic-password -s "Code Safe Storage" -a "Code" -w`
- O banco está em: ~/Library/Application Support/Code/User/globalStorage/state.vscdb
- Electron safeStorage usa PBKDF2 (SHA1, salt="saltysalt", 1003 iterações, 16 bytes) para derivar a chave AES-128-CBC
- Os dados criptografados têm prefixo "v10" + 16 bytes IV + ciphertext AES-CBC com padding PKCS7
- Procure pelas chaves: `secret://dynamicAuthProvider:clientRegistration:*` para client_id/client_secret

Gere um script Python que:
- Leia a chave do Keychain via subprocess
- Derive a chave AES via PBKDF2
- Abra o state.vscdb
- Descriptografe e extraia client_id e client_secret

### 3. Gerar um novo access_token via fluxo OAuth PKCE
Crie um script Python que:
- Gere um code_verifier e code_challenge (S256) aleatórios
- Construa a URL de autorização com os parâmetros:
  - client_id (do passo 2)
  - response_type=code
  - code_challenge
  - code_challenge_method=S256
  - scope=mcp:connect
  - resource=https://mcp.figma.com/mcp
  - redirect_uri=http://127.0.0.1:38471/
  - state (aleatório)
- Inicie um servidor HTTP na porta 38471 esperando o redirect
- Imprima a URL para o usuário abrir no navegador
- Ao receber o code, faça POST para o token_endpoint com:
  - grant_type=authorization_code
  - code
  - redirect_uri
  - client_id
  - client_secret (do passo 2)
  - code_verifier
- Salve os tokens em ~/.figma_mcp_tokens.json

IMPORTANTE: Use ssl.create_default_context() com check_hostname=False e verify_mode=CERT_NONE para evitar erros de SSL com Python do Homebrew.

### 4. Configurar o OpenCode
Edite ~/.config/opencode/opencode.jsonc adicionando:

{
  "mcp": {
    "Figma": {
      "type": "remote",
      "url": "https://mcp.figma.com/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer <access_token_do_passo_3>"
      },
      "oauth": false
    }
  }
}

oauth: false é crítico para o OpenCode não tentar o fluxo OAuth automático.

### 5. Reiniciar e verificar
Reinicie o OpenCode e verifique os logs:
tail -20 ~/.local/share/opencode/log/opencode.log | grep -i figma

Não deve haver "needs_auth" ou "error".

Me guie passo a passo, pedindo confirmação entre cada etapa.
```
