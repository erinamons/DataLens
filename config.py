"""DataLens - Content Analytics Platform Configuration"""

import sys
import os
from pathlib import Path

# ── 项目根目录 ──
# PyInstaller onefile: 运行时 exe 旁边（用户数据持久化）
# 开发环境: 基于本文件位置
if os.environ.get("DATALENS_BASE_DIR"):
    BASE_DIR = Path(os.environ["DATALENS_BASE_DIR"]).resolve()
elif getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# ── PyInstaller 资源目录（web 等打包文件） ──
if getattr(sys, 'frozen', False):
    _MEIPASS = Path(sys._MEIPASS)
    WEB_DIR = _MEIPASS / "web"
else:
    WEB_DIR = BASE_DIR / "web"

WEB_INDEX = WEB_DIR / "index.html"

# ── 服务 ──
SERVER_HOST = os.environ.get("DATALENS_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("DATALENS_SERVER_PORT", "8900"))
APP_TITLE = os.environ.get("DATALENS_APP_TITLE", "DataLens")

# ── 数据目录（exe 旁边，持久化） ──
DATA_DIR = Path(os.environ.get("DATALENS_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = os.environ.get("DATALENS_DB_PATH", str(DATA_DIR / "datalens.db"))

# ── 视频上传目录 ──
UPLOAD_DIR = Path(os.environ.get("DATALENS_UPLOAD_DIR", str(BASE_DIR / "uploads"))).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── 封面图目录 ──
COVER_DIR = Path(os.environ.get("DATALENS_COVER_DIR", str(BASE_DIR / "covers"))).resolve()
COVER_DIR.mkdir(parents=True, exist_ok=True)

# ── 预设标签（空 — 用户自行添加） ──
DEFAULT_TAGS = []

# ── 预设违规类型 ──
DEFAULT_VIOLATION_TYPES = ["限流", "下架", "警告", "封禁", "审核中"]
