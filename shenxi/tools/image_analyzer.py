import base64
import requests
import config


def analyze_image(image_bytes: bytes, filename: str) -> str:
    try:
        base64_image = base64.b64encode(image_bytes).decode()
        resp = requests.post(
            f"{config.DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.DEEPSEEK_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请详细描述这张图片的内容。如果是文档或表格，请提取其中的文字信息。如果是设计图或产品图，请描述视觉特征和关键信息。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{_guess_mime(filename)};base64,{base64_image}",
                            },
                        },
                    ],
                }],
                "max_tokens": 2000,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        return f"（图片分析失败，状态码 {resp.status_code}）"
    except Exception:
        return "（图片分析超时，请重试）"


def _guess_mime(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    mimes = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp", "bmp": "bmp"}
    return mimes.get(ext, "png")
