import base64

def encode_key(key: str) -> str:
    return base64.b64encode(key.encode()).decode()

def decode_key(encoded: str) -> str:
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return ""
