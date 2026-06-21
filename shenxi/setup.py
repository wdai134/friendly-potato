"""深析 - 初始化配置脚本。运行一次即可。"""
from utils.key_obfuscator import encode_key


def main():
    print("=" * 50)
    print("  深析 - 初始化配置")
    print("=" * 50)

    deepseek_key = input("\n请输入 DeepSeek API Key: ").strip()
    if deepseek_key:
        encoded = encode_key(deepseek_key)
        _replace_in_config("DEEPSEEK_API_KEY", encoded)
        print("  DeepSeek Key 已配置")

    bocha_key = input("请输入博查 Search API Key（没有则回车跳过）: ").strip()
    if bocha_key:
        encoded = encode_key(bocha_key)
        _replace_in_config("BOCHA_API_KEY", encoded)
        print("  博查 Key 已配置")

    print("\n配置完成。双击 start.bat 启动深析。")


def _replace_in_config(key_name: str, encoded_value: str):
    path = "config.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    old = f'decode_key("REPLACE_WITH_ENCODED_KEY")'
    new = f'decode_key("{encoded_value}")'
    content = content.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
