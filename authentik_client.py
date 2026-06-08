import os
import requests
import urllib.parse
import urllib3

# Desativa avisos de SSL não verificado (caso use verify=False para o Authentik)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def obter_endpoints_authentik(metadata_url: str) -> dict:
    """
    Consome o endpoint .well-known/openid-configuration do Authentik para descobrir os endpoints OIDC.
    Em caso de falha, reconstrói os endpoints padrão a partir da URL.
    """
    try:
        resp = requests.get(metadata_url, timeout=10, verify=False)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    
    # Fallback básico baseado na estrutura padrão do Authentik
    base_url = metadata_url.split("/.well-known/")[0] if "/.well-known/" in metadata_url else metadata_url.rstrip("/")
    base_host = metadata_url.split("/application/o/")[0] if "/application/o/" in metadata_url else base_url
    return {
        "token_endpoint": f"{base_host}/application/o/token/",
        "userinfo_endpoint": f"{base_host}/application/o/userinfo/",
        "authorization_endpoint": f"{base_host}/application/o/authorize/"
    }

def obter_url_autorizacao(client_id: str, redirect_uri: str, metadata_url: str) -> str:
    """
    Gera a URL de autorização para o redirecionamento inicial.
    """
    endpoints = obter_endpoints_authentik(metadata_url)
    auth_endpoint = endpoints.get("authorization_endpoint")
    
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": "random_state_string"
    }
    return f"{auth_endpoint}?{urllib.parse.urlencode(params)}"

def obter_usuario_authentik(code: str, client_id: str, client_secret: str, redirect_uri: str, metadata_url: str) -> dict:
    """
    Realiza a troca do authorization code pelo token de acesso do Authentik e obtém os dados do usuário.
    """
    try:
        endpoints = obter_endpoints_authentik(metadata_url)
        token_endpoint = endpoints.get("token_endpoint")
        userinfo_endpoint = endpoints.get("userinfo_endpoint")
        
        # 1. Troca o código pelo token
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri
        }
        
        resp_token = requests.post(
            token_endpoint,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
            verify=False
        )
        
        if resp_token.status_code != 200:
            return {"ok": False, "erro": f"Troca de código falhou: HTTP {resp_token.status_code} - {resp_token.text}"}
            
        token_data = resp_token.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return {"ok": False, "erro": "Token obtido com sucesso, mas access_token está ausente na resposta."}
            
        # 2. Busca informações do usuário
        headers = {"Authorization": f"Bearer {access_token}"}
        resp_user = requests.get(
            userinfo_endpoint,
            headers=headers,
            timeout=10,
            verify=False
        )
        
        if resp_user.status_code != 200:
            return {"ok": False, "erro": f"Busca de informações do usuário falhou: HTTP {resp_user.status_code} - {resp_user.text}"}
            
        user_data = resp_user.json()
        
        username = (
            user_data.get("name")
            or user_data.get("preferred_username")
            or user_data.get("given_name")
            or user_data.get("email")
            or "USUARIO"
        )
        
        return {
            "ok": True,
            "usuario": username,
            "email": user_data.get("email"),
            "access_token": access_token,
            "raw_user_info": user_data
        }
        
    except Exception as e:
        return {"ok": False, "erro": f"Exceção na integração do Authentik: {str(e)}"}
