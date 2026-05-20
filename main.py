"""DataLens - Content Analytics Desktop App"""

import sys
import os
import threading
import time
import subprocess

# 隐藏控制台（打包后）
if getattr(sys, 'frozen', False):
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

from config import SERVER_HOST, SERVER_PORT, APP_TITLE


def start_server():
    """后台启动 FastAPI"""
    import uvicorn
    from server import app
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")


def wait_for_server(url, timeout=30):
    """等待服务就绪"""
    import urllib.request
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(f"{url}/api/tags", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def launch_browser(url, title, width=1200, height=800):
    """用 Edge --app 模式打开，看起来像桌面应用"""
    edge_paths = [
        os.path.join(os.environ.get('ProgramFiles(x86)', ''),
                     'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(os.environ.get('ProgramFiles', ''),
                     'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    for edge in edge_paths:
        if os.path.exists(edge):
            subprocess.Popen([
                edge,
                f'--app={url}',
                f'--window-size={width},{height}',
                '--start-maximized',
            ])
            return True

    import webbrowser
    webbrowser.open(url)
    return False


def main():
    url = f"http://{SERVER_HOST}:{SERVER_PORT}"

    # 启动后台服务
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 等服务就绪
    if not wait_for_server(url):
        # 服务启动失败，可能是端口被占用，试试直接访问
        pass

    # 打开窗口
    launch_browser(url, APP_TITLE)

    # 保持主线程运行（服务是 daemon 线程）
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
