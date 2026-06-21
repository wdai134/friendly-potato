from functools import wraps

ERROR_MESSAGES = {
    "ConnectionError": "网络连接失败，请检查网络后重试",
    "Timeout": "AI 正在深度思考，请稍等片刻...",
    "RateLimitError": "请求太频繁了，请稍后重试",
    "InvalidRequestError": "请求格式有误，请重新输入",
    "AuthenticationError": "API 密钥验证失败",
    "FileNotFoundError": "找不到指定文件",
    "ValueError": "输入数据格式不正确",
}


def translate_error(exc: Exception) -> str:
    """将技术异常翻译为大白话"""
    exc_name = type(exc).__name__
    if exc_name in ERROR_MESSAGES:
        return ERROR_MESSAGES[exc_name]
    return f"出了点小问题（{exc_name}），请稍后重试"


def safe_call(func):
    """装饰器：捕获异常并返回大白话"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {"error": True, "message": translate_error(e)}

    return wrapper
