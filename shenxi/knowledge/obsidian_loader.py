import os


def scan_vault(vault_path: str) -> list[dict]:
    os.makedirs(vault_path, exist_ok=True)

    docs = []
    for root, _, files in os.walk(vault_path):
        for f in files:
            if f.endswith((".md", ".txt")):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, "r", encoding="utf-8") as fp:
                        content = fp.read()
                except Exception:
                    continue
                if content.strip():
                    rel_path = os.path.relpath(full_path, vault_path)
                    docs.append({
                        "path": full_path,
                        "name": rel_path,
                        "content": content,
                    })
    return docs


def get_file_count(docs: list[dict]) -> int:
    return len(docs)


def get_total_chars(docs: list[dict]) -> int:
    return sum(len(d["content"]) for d in docs)
