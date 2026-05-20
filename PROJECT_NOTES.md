# Project Notes

本文档用于记录 DataLens 当前项目状态、开发约定和后续接手注意事项。

更完整的长期记忆见：

- `memory/MEMORY.md`
- `memory/2026-05-20.md`

## 项目定位

DataLens 是一个本地短视频内容运营数据工具，核心目标是把视频数据、方向测试、钩子话术、计划任务、账号矩阵和违规复盘沉淀成可持续复用的运营工作台。

## 当前技术结构

- 后端：FastAPI
- 数据库：SQLite
- 前端：`web/index.html` + `web/styles.css`
- 桌面入口：`main.py`
- 主要接口：`server.py`
- 数据访问和表结构：`database.py`

## 运行方式

```powershell
pip install -r requirements.txt
python main.py
```

默认地址：

```text
http://127.0.0.1:8900
```

## 验证方式

```powershell
python -m py_compile main.py server.py database.py config.py test_verify.py
python test_verify.py
```

## GitHub

仓库地址：

```text
https://github.com/erinamons/DataLens.git
```

当前主分支：

```text
main
```

本机 Git 安装路径：

```text
D:\Program Files\Git\cmd\git.exe
```

如果普通 `git` 命令不可用，可以使用完整路径：

```powershell
& 'D:\Program Files\Git\cmd\git.exe' -C D:/workbuddy/douyin-data status
```

## 代理推送

当前环境下 GitHub 推送需要显式走本机代理端口：

```text
127.0.0.1:9567
```

推送命令：

```powershell
& 'D:\Program Files\Git\cmd\git.exe' -C D:/workbuddy/douyin-data -c http.version=HTTP/1.1 -c http.proxy=http://127.0.0.1:9567 -c https.proxy=http://127.0.0.1:9567 push
```

## 不提交的数据

以下目录和文件属于本地运行数据或构建产物，不应提交：

```text
data/
uploads/
covers/
build/
dist/
__pycache__/
*.log
```

`.gitignore` 已经处理这些内容。

## 已清理的无用文件

已从仓库删除：

- `web/test_select.html`：独立样式测试页，项目未引用。
- `DataLens_UI升级开发方案.txt`：开发过程方案文档，已过期且运行时未引用。

## 当前核心功能

- 视频库：视频数据录入、上传、播放、封面、收藏、搜索、筛选、排序。
- 分析：数据概览、趋势、标签、关键词、热门视频、发布时间分析。
- 方向实验：测试结论、审核状态、效果标记、判定标准、失败原因、下次测试动作。
- 钩子知识库：话术沉淀、变体管理、适用方向、不适用场景、效果复盘。
- 计划管理：待办、进行、完成状态和每日任务。
- 账号矩阵：账号、分组、方向、平台和矩阵健康度。
- 工具：CSV 导入导出、备份恢复、数据质量检查、复盘报告导出。

## 后续开发注意事项

- 前端目前仍集中在 `web/index.html`，功能继续增多后应考虑拆分 JS 模块。
- 新功能优先补 `test_verify.py` 的接口验证，避免回归。
- 上传的视频、封面和数据库都是用户本地数据，开发时不要清空或覆盖。
- UI 风格应保持工具型、运营后台型，不做营销页风格。
- 更多菜单只放导航栏没有的页面，避免重复入口。
- 如果继续优化视频库，重点关注大图播放模式、右侧详情栏、筛选效率和录入流程。
- 如果继续优化知识库，重点关注钩子复用链路、失败原因沉淀和下次测试动作。
- 决策中心已经接入行动建议、方向决策榜、视频复盘、素材状态、实验批次和可复用经验；后续优化应优先提升筛选、批量复盘和更细的评分规则。
