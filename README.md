# DataLens

DataLens 是一个本地短视频内容数据管理工具，用来沉淀视频数据、方向测试、钩子话术、违规原因、计划任务和账号矩阵表现。项目后端使用 FastAPI，数据存储在 SQLite，前端是本地 Web 管理界面。

## 主要功能

- 视频库管理：录入视频数据、上传视频、自动截取视频首帧、播放预览、收藏、搜索、筛选和排序。
- 数据分析：播放量、互动率、完播率、收藏数、方向趋势、标签表现、关键词表现和热门视频排行。
- 方向实验：记录测试方向、审核结论、效果标记、判定标准、失败原因和下次测试动作。
- 钩子知识库：沉淀评论引导、话术变体、适用方向、不适用场景、复用经验和效果对比。
- 运营决策中心：汇总行动建议、方向决策榜、待复盘视频、素材状态、实验批次和可复用经验。
- 视频复盘：记录复盘结论、可复用点、失败原因、触发评论的句子/画面和下次测试动作。
- 计划管理：按待办、进行、完成等状态管理内容测试任务。
- 账号矩阵：管理账号、平台、状态、计划完成度和账号表现。
- 工具能力：CSV 导入导出、备份恢复、数据质量检查、运营复盘报告导出。

## 技术栈

- Backend: FastAPI + SQLite
- Frontend: HTML + CSS + JavaScript
- Media: 本地上传视频、封面生成、视频转码辅助
- Runtime: Python 3

## 本地运行

先安装依赖：

```powershell
pip install -r requirements.txt
```

启动项目：

```powershell
python main.py
```

默认访问地址：

```text
http://127.0.0.1:8900
```

也可以直接运行后端：

```powershell
python server.py
```

## 验证

```powershell
python -m py_compile main.py server.py database.py config.py test_verify.py
python test_verify.py
```

`test_verify.py` 会使用临时数据目录，不会修改当前真实数据。

## 目录结构

```text
.
├── main.py                 # 桌面入口，启动本地服务并打开页面
├── server.py               # FastAPI 接口服务
├── database.py             # SQLite 表结构和数据访问
├── config.py               # 路径、端口和运行配置
├── web/
│   ├── index.html          # 前端主页面
│   └── styles.css          # 前端样式
├── requirements.txt        # Python 依赖
├── test_verify.py          # 接口和数据验证脚本
├── PROJECT_NOTES.md        # 项目接手记录和开发注意事项
├── memory/                 # 长期记忆和按日期工作日志
└── DataLens.spec           # PyInstaller 打包配置
```

运行时会生成以下目录，这些内容不会提交到 Git：

```text
data/       # SQLite 数据库和备份
uploads/    # 上传的视频文件
covers/     # 视频封面
build/      # 打包中间产物
dist/       # 打包输出
```

## 环境变量

可选环境变量：

```text
DATALENS_SERVER_HOST
DATALENS_SERVER_PORT
DATALENS_BASE_DIR
DATALENS_DATA_DIR
DATALENS_DB_PATH
DATALENS_UPLOAD_DIR
DATALENS_COVER_DIR
```

这些变量主要用于修改服务地址、数据目录、上传目录和测试隔离。

## 数据说明

项目默认把数据库、上传视频、封面和备份文件保存在本地目录，不会上传到 GitHub。这样可以保护本地素材和运营数据，也避免仓库体积过大。

如果需要迁移数据，可以使用系统里的备份恢复功能，或手动复制 `data/`、`uploads/`、`covers/` 目录。

## GitHub

当前仓库地址：

[https://github.com/erinamons/DataLens](https://github.com/erinamons/DataLens)
