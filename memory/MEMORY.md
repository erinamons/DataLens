# DataLens 长期记忆

本文件用于给后续接手的 AI 或开发者快速恢复上下文。它记录项目定位、核心结构、用户偏好、关键教训和长期维护规则。

## 项目概况

- 项目名称：DataLens
- 项目路径：`D:\workbuddy\douyin-data`
- GitHub：`https://github.com/erinamons/DataLens.git`
- 主分支：`main`
- 定位：本地短视频内容运营数据工作台
- 核心目标：沉淀视频数据、方向测试、钩子话术、违规复盘、计划任务和账号矩阵，让运营决策有依据可复用。

## 技术结构

- 后端：FastAPI
- 数据库：SQLite
- 前端：原生 HTML/CSS/JavaScript
- 桌面入口：`main.py`
- 后端接口：`server.py`
- 数据库和查询逻辑：`database.py`
- 前端主页面：`web/index.html`
- 前端样式：`web/styles.css`
- 验证脚本：`test_verify.py`
- 打包配置：`DataLens.spec`

## 运行和验证

运行：

```powershell
pip install -r requirements.txt
python main.py
```

默认地址：

```text
http://127.0.0.1:8900
```

验证：

```powershell
python -m py_compile main.py server.py database.py config.py test_verify.py
python test_verify.py
```

## Git 和代理

本机 Git 路径：

```text
D:\Program Files\Git\cmd\git.exe
```

Codex 环境里普通 `git` 可能不在 PATH，优先用完整路径：

```powershell
& 'D:\Program Files\Git\cmd\git.exe' -C D:/workbuddy/douyin-data status
```

GitHub 推送需要显式走代理：

```text
127.0.0.1:9567
```

推送命令：

```powershell
& 'D:\Program Files\Git\cmd\git.exe' -C D:/workbuddy/douyin-data -c http.version=HTTP/1.1 -c http.proxy=http://127.0.0.1:9567 -c https.proxy=http://127.0.0.1:9567 push
```

## 用户偏好

- 用户希望直接执行，不喜欢只停留在建议。
- 回复尽量中文、简洁、明确。
- UI 要像专业运营工具，不要像营销落地页。
- 功能要关注实际操作体验：录入效率、筛选效率、视频预览、数据复盘、后续动作。
- 每次重要改动后要更新记忆文件。
- 提交 GitHub 前要检查无用文件、运行数据和敏感本地数据。

## 当前核心功能

- 视频库：录入、上传、播放、封面、收藏、搜索、筛选、排序、批量操作。
- 分析：概览、趋势、标签、关键词、热门视频、发布时间分析。
- 方向实验：审核状态、测试结论、效果标记、判定标准、失败原因、下次测试动作。
- 钩子知识库：话术、变体、适用方向、不适用场景、失败原因、复用经验。
- 计划管理：待办、进行、完成状态和每日任务。
- 账号矩阵：账号、平台、分组、方向、状态和矩阵健康度。
- 工具：CSV 导入导出、备份恢复、数据质量检查、运营报告导出。

## 不应提交的数据

以下内容属于本地运行数据或构建产物，不应提交到 Git：

```text
data/
uploads/
covers/
build/
dist/
__pycache__/
*.log
```

`.gitignore` 已经覆盖这些内容。

## 已知维护规则

- 改接口后同步检查前端调用和 `test_verify.py`。
- 改数据库字段后同步检查迁移逻辑、统计查询和导出逻辑。
- 上传视频、封面和数据库是用户本地数据，不能随意删除或覆盖。
- 前端目前集中在 `web/index.html`，功能继续增多后应考虑拆分 JS 模块。
- `PROJECT_NOTES.md` 面向项目交接说明，`memory/MEMORY.md` 面向长期上下文记忆，`memory/YYYY-MM-DD.md` 记录当天变更。

## 关键教训

- GitHub 推送在当前机器上不会自动走代理，需要显式传 `http.proxy` 和 `https.proxy`。
- D 盘 Git 安装后 Codex 终端可能仍无法直接识别 `git`，使用完整路径更稳定。
- 文档在 PowerShell 里显示中文乱码，通常是控制台编码问题，不代表 GitHub 显示异常。
- 提交前要用 `git status --short --ignored` 检查运行数据是否被忽略。
- 开发临时文件不要留在正式仓库，例如独立样式测试页和过期方案文档。
