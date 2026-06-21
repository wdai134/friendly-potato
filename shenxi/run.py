"""PyInstaller 入口 — 启动深析"""
import os
import sys
from streamlit.web import cli as stcli

def main():
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    internal = os.path.join(exe_dir, '_internal')
    os.chdir(internal)
    sys.argv = [
        "streamlit", "run", "app.py",
        "--server.address", "0.0.0.0",
        "--server.port", "8501",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]
    stcli.main()

if __name__ == "__main__":
    main()
