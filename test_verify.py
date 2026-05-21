"""DataLens isolated verification script.

The script starts the FastAPI app against a temporary database and temporary
upload folders, so it never mutates the user's real data/datalens.db.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "http://127.0.0.1:8910"
errors = []


def request(method, path, data=None, headers=None):
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        headers = headers or {"Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            text = raw.decode("utf-8", errors="replace")
            return r.status, text, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read()
        text = raw.decode("utf-8", errors="replace")
        return e.code, text, {k.lower(): v for k, v in e.headers.items()}


def get(path, params=None):
    url = path if params is None else path + "?" + urllib.parse.urlencode(params)
    return request("GET", url)


def get_json(path, params=None):
    status, body, headers = get(path, params)
    return status, json.loads(body), headers


def post_json(path, data):
    status, body, _ = request("POST", path, data)
    return status, json.loads(body)


def put_json(path, data):
    status, body, _ = request("PUT", path, data)
    return status, json.loads(body)


def post_upload(path, files_dict):
    boundary = "----DataLensBoundary"
    body = b""
    for field, (fname, fdata, ftype) in files_dict.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{field}"; filename="{fname}"\r\n'.encode()
        body += f"Content-Type: {ftype}\r\n\r\n".encode()
        body += fdata if isinstance(fdata, bytes) else fdata.encode("utf-8")
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    status, text, _ = request(
        "POST",
        path,
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    return status, json.loads(text)


def delete_json(path):
    status, body, _ = request("DELETE", path)
    return status, json.loads(body)


def check(name, ok):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}")
    if not ok:
        errors.append(name)


def wait_ready(timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _, _ = get("/api/tags")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main():
    with tempfile.TemporaryDirectory(prefix="datalens_verify_") as tmp:
        root = Path(tmp)
        env = os.environ.copy()
        env.update(
            {
                "DATALENS_BASE_DIR": str(root),
                "DATALENS_DATA_DIR": str(root / "data"),
                "DATALENS_DB_PATH": str(root / "data" / "datalens.db"),
                "DATALENS_UPLOAD_DIR": str(root / "uploads"),
                "DATALENS_COVER_DIR": str(root / "covers"),
                "DATALENS_SERVER_PORT": "8910",
            }
        )
        proc = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=Path(__file__).resolve().parent,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not wait_ready():
                raise RuntimeError("server did not become ready")

            run_checks()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    print()
    if errors:
        print(f"=== {len(errors)} 个测试失败 ===")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print("=== 全部通过! ===")


def run_checks():
    # 1. 基础功能
    _, d = post_json("/api/tags", {"name": "测试方向A"})
    tag_a_id = d.get("id")
    check("创建标签A", d.get("success"))
    _, d = post_json("/api/tags", {"name": "测试方向B"})
    tag_b_id = d.get("id")
    check("创建标签B", d.get("success"))

    # 2. 录入视频
    _, d = post_json(
        "/api/videos",
        {
            "title": "测试视频标题",
            "play_count": 10000,
            "like_count": 500,
            "comment_count": 200,
            "favorite_count": 300,
            "share_count": 100,
            "publish_date": "2024-06-15",
            "tag_ids": [tag_a_id],
        },
    )
    vid = d.get("id")
    check("录入视频", d.get("success") and vid)

    # 3. 获取单个视频
    s, d, _ = get_json(f"/api/videos/{vid}")
    check("GET单个视频-200", s == 200)
    check("GET单个视频-标题正确", d.get("title") == "测试视频标题")
    check("GET单个视频-有标签", len(d.get("tags", [])) == 1)
    check("GET单个视频-有互动率", "interaction_rate" in d)
    check("GET单个视频-收藏数正确", d.get("favorite_count") == 300)
    check("GET单个视频-互动率含收藏", d.get("interaction_rate") == 11.0)
    check("GET单个视频-默认素材状态", d.get("material_status") == "已发布")

    _, review_data = post_json(
        f"/api/videos/{vid}/review",
        {
            "material_status": "可复用",
            "review_summary": "评论集中在祝福触发句",
            "reusable_point": "祝福式评论引导有效",
            "next_action": "下一批继续测试小红花话术",
            "comment_trigger_text": "看视频的您一定是个有福气的人",
        },
    )
    check("视频复盘保存成功", review_data.get("success"))
    _, d, _ = get_json(f"/api/videos/{vid}")
    check("视频复盘-素材状态更新", d.get("material_status") == "可复用")
    check("视频复盘-可复用点更新", d.get("reusable_point") == "祝福式评论引导有效")

    _, batch_data = post_json(
        "/api/test-batches",
        {
            "name": "祝福评论钩子测试",
            "goal": "提升评论率",
            "status": "测试中",
            "conclusion": "待观察",
            "next_action": "继续补 5 条",
        },
    )
    batch_id = batch_data.get("id")
    check("创建实验批次-增强字段", batch_data.get("success") and batch_id)
    _, batch_update = put_json(
        f"/api/test-batches/{batch_id}",
        {"status": "有效", "conclusion": "评论率明显提升"},
    )
    check("更新实验批次", batch_update.get("success"))
    _, decision_data, _ = get_json("/api/decision-center")
    check("决策中心API正常", "suggestions" in decision_data and "directions" in decision_data and "review" in decision_data)
    check("决策中心包含素材状态", "status_counts" in decision_data.get("review", {}))
    if decision_data.get("directions"):
        check("决策中心包含推荐原因", "decision_reason" in decision_data["directions"][0])

    _, douyin_data = post_json(
        "/api/creator/douyin/import-current",
        {
            "page_url": "https://creator.douyin.com/creator-micro/work-management/work-detail/7639627140002904165",
            "item_id": "7639627140002904165",
            "title": "创作者中心导入测试视频",
            "publish_date": "2026-05-17",
            "publish_time": "19:30",
            "play_count": 8888,
            "like_count": 666,
            "comment_count": 88,
            "favorite_count": 77,
            "share_count": 22,
            "completion_rate": 41.5,
            "avg_watch_seconds": 28,
            "bounce_2s_rate": 10.76,
            "completion_5s_rate": 72.88,
            "avg_watch_ratio": 70.99,
            "watch_trend": "已识别到观看趋势图",
            "drop_points": [{"second": 18, "label": "低谷1"}],
            "post_watch_search_terms": [
                {"rank": 1, "keyword": "马蜂窝的药用配方", "ratio": 45.4},
                {"rank": 2, "keyword": "马蜂窝的主治功效是什么", "ratio": 27.3},
            ],
        },
    )
    imported_id = douyin_data.get("video_id")
    check("创作者中心扩展导入成功", douyin_data.get("success") and imported_id)
    _, imported_video, _ = get_json(f"/api/videos/{imported_id}")
    check("创作者中心导入-播放量正确", imported_video.get("play_count") == 8888)
    check("创作者中心导入-素材状态待复盘", imported_video.get("material_status") == "待复盘")
    check("创作者中心导入-发布时间", imported_video.get("publish_date") == "2026-05-17")
    check("创作者中心导入-发布时间点", imported_video.get("publish_time") == "19:30")
    check("创作者中心导入-平均播放时长", imported_video.get("avg_watch_seconds") == 28)
    check("创作者中心导入-观后搜索词", "马蜂窝的药用配方" in imported_video.get("post_watch_search_terms", ""))

    _, douyin_second = post_json(
        "/api/creator/douyin/import-current",
        {
            "page_url": "https://creator.douyin.com/creator-micro/work-management/work-detail/7639627140002904999",
            "item_id": "7639627140002904999",
            "title": "创作者中心导入测试视频",
            "play_count": 1234,
            "completion_rate": 52.1,
        },
    )
    second_id = douyin_second.get("video_id")
    check("创作者中心导入-不同作品新建", douyin_second.get("success") and second_id and second_id != imported_id)

    _, douyin_second_update = post_json(
        "/api/creator/douyin/import-current",
        {
            "page_url": "https://creator.douyin.com/creator-micro/work-management/work-detail/7639627140002904999",
            "item_id": "7639627140002904999",
            "title": "创作者中心导入测试视频",
            "play_count": 2345,
            "completion_rate": 60.5,
        },
    )
    check("创作者中心导入-同作品更新", douyin_second_update.get("mode") == "updated" and douyin_second_update.get("video_id") == second_id)
    _, second_video, _ = get_json(f"/api/videos/{second_id}")
    check("创作者中心导入-同作品播放量更新", second_video.get("play_count") == 2345)

    # 4. 不存在的视频
    _, d, _ = get_json("/api/videos/99999")
    check("GET不存在视频-返回error", "error" in d)

    # 5. 封面上传（带旧文件清理）
    fake_img = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    _, d = post_upload(f"/api/videos/{vid}/cover", {"file": ("cover1.png", fake_img, "image/png")})
    check("首次封面上传", d.get("success"))
    cover1 = d.get("filename", "")
    _, d = post_upload(f"/api/videos/{vid}/cover", {"file": ("cover2.png", fake_img, "image/png")})
    check("二次封面上传(覆盖)", d.get("success"))
    check("两次文件名不同", d.get("filename", "") != cover1)

    fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512
    _, d = post_upload(f"/api/videos/{vid}/upload", {"file": ("sample.mp4", fake_video, "video/mp4")})
    check("视频文件上传", d.get("success"))

    # 6. 封面获取
    s, _, h = get(f"/api/videos/{vid}/cover")
    check("获取封面-200", s == 200)
    check("获取封面-图片类型", "image" in h.get("content-type", ""))

    s, _, h = request("GET", f"/api/videos/{vid}/stream", headers={"Range": "bytes=0-31"})
    check("视频流支持Range", s == 206)
    check("视频流返回Content-Range", "content-range" in h)

    # 7. 列表/筛选
    _, d, _ = get_json("/api/videos", {"page_size": 100})
    check("视频列表正常", "videos" in d and isinstance(d["videos"], list))
    _, d, _ = get_json("/api/videos", {"tag_id": tag_a_id, "page_size": 100})
    check("标签筛选正常", len(d["videos"]) >= 1)
    _, d, _ = get_json(
        "/api/videos",
        {"date_from": "2024-06-01", "date_to": "2024-06-30", "page_size": 100},
    )
    check("日期筛选正常", len(d["videos"]) >= 1)

    # 8. 编辑视频
    _, d = put_json(
        f"/api/videos/{vid}",
        {
            "id": vid,
            "title": "修改后的标题",
            "play_count": 20000,
            "like_count": 1000,
            "comment_count": 400,
            "favorite_count": 600,
            "share_count": 200,
            "publish_date": "2024-07-01",
            "tag_ids": [tag_a_id, tag_b_id],
        },
    )
    check("编辑视频", d.get("success"))
    _, d, _ = get_json(f"/api/videos/{vid}")
    check("编辑后标题正确", d.get("title") == "修改后的标题")
    check("编辑后收藏数正确", d.get("favorite_count") == 600)
    check("编辑后标签数=2", len(d.get("tags", [])) == 2)

    # 9. 批量打标/移除
    _, d = post_json("/api/videos/batch-tags?action=add", {"video_ids": [vid], "tag_ids": [tag_b_id]})
    check("批量打标签(已有也OK)", d.get("success"))
    _, d = post_json("/api/videos/batch-tags?action=remove", {"video_ids": [vid], "tag_ids": [tag_b_id]})
    check("批量移除标签", d.get("success"))
    _, d, _ = get_json(f"/api/videos/{vid}")
    check("移除后标签数=1", len(d.get("tags", [])) == 1)

    # 10. CSV / 分析
    s, _, h = get("/api/export/csv")
    check("CSV导出-200", s == 200)
    disp = h.get("content-disposition", "")
    check("CSV文件名含日期", "datalens_" in disp and ".csv" in disp)
    _, body, _ = get("/api/export/csv")
    check("CSV导出包含收藏列", "收藏数" in body)
    _, d, _ = get_json("/api/analysis/tag-trend", {"tag_id": tag_a_id})
    check("趋势API正常", isinstance(d.get("trend"), list))

    # 11. 删除/恢复/孤立素材清理
    _, d, _ = get_json(f"/api/videos/{vid}")
    cover_before = d.get("cover_path")
    check("删除前封面存在", cover_before and Path(cover_before).exists())
    _, body, _ = request("DELETE", f"/api/videos/{vid}")
    del_result = json.loads(body)
    check("删除视频成功", del_result.get("success"))
    check("软删除后封面仍保留以支持撤销", cover_before and Path(cover_before).exists())
    _, d, _ = get_json(f"/api/videos/{vid}")
    check("删除后GET返回error", "error" in d)
    _, d = post_json(f"/api/videos/{vid}/restore", {})
    check("恢复视频成功", d.get("success"))
    _, d, _ = get_json(f"/api/videos/{vid}")
    check("恢复后GET正常", d.get("id") == vid)
    _, d = delete_json(f"/api/videos/{vid}/upload")
    check("删除视频素材成功", d.get("success"))
    _, d = delete_json(f"/api/videos/{vid}/cover")
    check("删除封面成功", d.get("success"))
    request("DELETE", f"/api/videos/{vid}")
    _, d = post_json("/api/media/cleanup", {})
    check("孤立素材清理成功", d.get("success"))


if __name__ == "__main__":
    main()
