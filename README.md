# DataLens

DataLens 是一个本地短视频内容数据管理工具。后端使用 FastAPI，数据存储在 SQLite，前端是 `web/index.html` 单文件页面，桌面入口由 `main.py` 启动本地服务后用浏览器 app 模式打开。

## 本地运行

```powershell
pip install -r requirements.txt
python main.py
```

默认服务地址是 `http://127.0.0.1:8900`。

## 验证

```powershell
python -m py_compile main.py server.py database.py config.py test_verify.py
python test_verify.py
```

`test_verify.py` 会使用临时数据库和临时上传目录，不会修改 `data/datalens.db` 或现有素材文件。

## 环境变量

- `DATALENS_SERVER_HOST`
- `DATALENS_SERVER_PORT`
- `DATALENS_BASE_DIR`
- `DATALENS_DATA_DIR`
- `DATALENS_DB_PATH`
- `DATALENS_UPLOAD_DIR`
- `DATALENS_COVER_DIR`

这些变量主要用于测试隔离、便携运行和打包后的数据目录调整。
