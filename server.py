"""DataLens - Content Analytics Web Service"""

import uuid
import shutil
import subprocess
import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, Query, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from config import UPLOAD_DIR, COVER_DIR, WEB_INDEX, SERVER_HOST, SERVER_PORT, APP_TITLE
from config import DB_PATH
from database import (
    init_db,
    add_video, update_video, delete_video, delete_videos_batch, restore_video,
    update_video_path, update_cover_path, clear_video_path, clear_cover_path,
    get_video_path, get_cover_path, batch_update_videos,
    get_videos, get_video_count,
    get_referenced_media_paths,
    batch_add_tags, batch_remove_tags,
    export_csv, import_csv,
    get_all_tags, add_tag, delete_tag,
    get_all_violation_types, add_violation_type, delete_violation_type,
    get_tag_analysis, get_tag_trend,
    get_keyword_analysis, get_top_videos,
    get_dashboard_summary, get_cockpit_summary, get_violation_stats,
    get_plans, add_plan, update_plan, toggle_plan, delete_plan, copy_plans, export_plans_txt,
    get_all_directions, add_direction, update_direction, delete_direction,
    get_all_groups, add_group, update_group, delete_group,
    get_all_accounts, add_account, update_account, delete_account, get_account_stats,
    get_direction_analysis, get_direction_recommendations, get_direction_trend, get_matrix_summary, get_matrix_health, get_publish_time_analysis,
    get_interaction_hooks, add_interaction_hook, update_interaction_hook, delete_interaction_hook, create_hook_from_video,
    get_hook_versions, add_hook_version, delete_hook_version,
    get_hook_recommendations, get_comment_opportunities,
    get_data_quality, get_data_quality_tasks, get_audit_logs, get_test_batches, add_test_batch, get_hook_review,
    global_search,
)

app = FastAPI(title=APP_TITLE)
init_db()
app.mount("/web", StaticFiles(directory="web"), name="web")

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MIME_VIDEO = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska", ".webm": "video/webm", ".flv": "video/x-flv",
}
MIME_IMAGE = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}


def _unlink_file(path):
    if not path:
        return False
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False


def _cleanup_orphan_media():
    referenced = get_referenced_media_paths()
    deleted = []
    for directory in (UPLOAD_DIR, COVER_DIR):
        for path in directory.iterdir():
            if path.is_file() and str(path.resolve()) not in referenced:
                if _unlink_file(path):
                    deleted.append(str(path))
    return deleted


def _get_ffmpeg_exe():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        return found


def _video_duration_seconds(ffmpeg, path):
    cmd = [ffmpeg, "-hide_banner", "-i", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    text = proc.stderr or proc.stdout or ""
    marker = "Duration:"
    if marker not in text:
        return None
    raw = text.split(marker, 1)[1].split(",", 1)[0].strip()
    try:
        hh, mm, ss = raw.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    except Exception:
        return None


def _capture_cover_frame(ffmpeg, video_path, output_path, second):
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{max(second, 0.1):.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-vf",
        "scale='min(720,iw)':-2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    return proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _model_updates(model):
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def _parse_range_header(range_header, file_size):
    if not range_header or not range_header.startswith("bytes="):
        return None
    try:
        start_raw, end_raw = range_header.replace("bytes=", "", 1).split("-", 1)
        if start_raw == "":
            length = int(end_raw)
            start = max(file_size - length, 0)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
        if start < 0 or end < start or start >= file_size:
            raise ValueError
        return start, min(end, file_size - 1)
    except Exception:
        raise HTTPException(status_code=416, detail="Invalid range header")


# --- 请求模型 ---

class VideoIn(BaseModel):
    title: str = ""
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    favorite_count: int = 0
    share_count: int = 0
    publish_date: Optional[str] = None
    publish_time: Optional[str] = None
    completion_rate: float = 0
    duration: int = 0
    violation_type: str = ""
    violation_note: str = ""
    violation_status: str = "pending"
    tag_ids: list[int] = []
    direction_id: Optional[int] = None
    group_id: Optional[int] = None
    account_id: Optional[int] = None
    interaction_hook_id: Optional[int] = None
    comment_reason: str = ""
    comment_trigger_text: str = ""
    comment_reuse_advice: str = ""
    test_batch_id: Optional[int] = None


class VideoUpdate(VideoIn):
    id: int


class TagIn(BaseModel):
    name: str


class BatchTagOp(BaseModel):
    video_ids: list[int]
    tag_ids: list[int] = []


class BatchDeleteOp(BaseModel):
    video_ids: list[int]


class BatchVideoUpdateOp(BaseModel):
    video_ids: list[int]
    direction_id: Optional[int] = None
    group_id: Optional[int] = None
    account_id: Optional[int] = None
    interaction_hook_id: Optional[int] = None
    test_batch_id: Optional[int] = None
    violation_status: Optional[str] = None
    completion_rate: Optional[float] = None
    clear_fields: List[str] = []


class DirectionIn(BaseModel):
    name: str
    color: str = "#e94560"
    status: str = "待测试"
    is_lift: bool = False
    effect_level: str = "待观察"
    tags: str = ""
    note: str = ""
    criteria: str = ""


class DirectionUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    status: Optional[str] = None
    is_lift: Optional[bool] = None
    effect_level: Optional[str] = None
    tags: Optional[str] = None
    note: Optional[str] = None
    criteria: Optional[str] = None


class GroupIn(BaseModel):
    name: str
    direction_id: Optional[int] = None
    phone_list: str = ""


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    direction_id: Optional[int] = None
    phone_list: Optional[str] = None


class HookIn(BaseModel):
    name: str
    hook_type: str = "评论引导"
    target_comment: str = ""
    comment_type: str = "关键词"
    target_action: str = "评论"
    variants: str = ""
    trigger_text: str = ""
    reuse_advice: str = ""
    note: str = ""
    status: str = "可复用"
    applicable_directions: str = ""
    bad_scenarios: str = ""
    failure_reason: str = ""
    next_test_action: str = ""


class HookUpdate(BaseModel):
    name: Optional[str] = None
    hook_type: Optional[str] = None
    target_comment: Optional[str] = None
    comment_type: Optional[str] = None
    target_action: Optional[str] = None
    variants: Optional[str] = None
    trigger_text: Optional[str] = None
    reuse_advice: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None
    applicable_directions: Optional[str] = None
    bad_scenarios: Optional[str] = None
    failure_reason: Optional[str] = None
    next_test_action: Optional[str] = None


class HookVersionIn(BaseModel):
    version_name: str = ""
    phrase: str = ""
    note: str = ""
    status: str = "测试中"


class HookFromVideoIn(BaseModel):
    video_id: int
    name: Optional[str] = None
    hook_type: str = "评论引导"


class BatchIn(BaseModel):
    name: str
    note: str = ""


# --- 视频 API ---

@app.get("/api/videos")
def api_videos(
    tag_id: Optional[int] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = "publish_date",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    direction_id: Optional[int] = None,
    group_id: Optional[int] = None,
    violation: Optional[str] = None,
    account_id: Optional[int] = None,
):
    offset = (page - 1) * page_size
    videos = get_videos(tag_id, keyword, date_from, date_to,
                        sort_by, order, page_size, offset,
                        direction_id, group_id, violation, account_id)
    total = get_video_count(tag_id, keyword, date_from, date_to,
                            direction_id, group_id, violation, account_id)
    return {"videos": videos, "total": total, "page": page, "page_size": page_size}


@app.get("/api/videos/{video_id}")
def api_get_video(video_id: int):
    """获取单个视频详情"""
    from database import get_video_by_id
    v = get_video_by_id(video_id)
    if not v:
        return {"error": "视频不存在"}
    return v


@app.post("/api/videos")
def api_add_video(data: VideoIn):
    video_id = add_video(
        data.title, data.play_count, data.like_count,
        data.comment_count, data.share_count,
        data.publish_date, data.tag_ids,
        direction_id=data.direction_id, group_id=data.group_id,
        completion_rate=data.completion_rate, duration=data.duration,
        publish_time=data.publish_time,
        violation_type=data.violation_type, violation_note=data.violation_note,
        violation_status=data.violation_status,
        account_id=data.account_id,
        favorite_count=data.favorite_count,
        interaction_hook_id=data.interaction_hook_id,
        comment_reason=data.comment_reason,
        comment_trigger_text=data.comment_trigger_text,
        comment_reuse_advice=data.comment_reuse_advice,
        test_batch_id=data.test_batch_id,
    )
    return {"success": True, "id": video_id}


@app.put("/api/videos/{video_id}")
def api_update_video(video_id: int, data: VideoUpdate):
    update_video(
        video_id, data.title, data.play_count, data.like_count,
        data.comment_count, data.share_count,
        data.publish_date, data.tag_ids,
        direction_id=data.direction_id, group_id=data.group_id,
        account_id=data.account_id,
        completion_rate=data.completion_rate, duration=data.duration,
        publish_time=data.publish_time,
        violation_type=data.violation_type, violation_note=data.violation_note,
        violation_status=data.violation_status,
        favorite_count=data.favorite_count,
        interaction_hook_id=data.interaction_hook_id,
        comment_reason=data.comment_reason,
        comment_trigger_text=data.comment_trigger_text,
        comment_reuse_advice=data.comment_reuse_advice,
        test_batch_id=data.test_batch_id,
    )
    return {"success": True}


@app.patch("/api/videos/{video_id}")
def api_patch_video(video_id: int, data: dict):
    """行内编辑：只更新传入的字段"""
    allowed = {'play_count', 'like_count', 'comment_count', 'favorite_count', 'share_count',
               'completion_rate', 'duration', 'publish_time', 'violation_type', 'violation_note', 'violation_status',
               'account_id'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return {"success": False, "error": "无有效字段"}
    from database import patch_video
    patch_video(video_id, **fields)
    return {"success": True}


@app.delete("/api/videos/{video_id}")
def api_delete_video(video_id: int):
    paths = delete_video(video_id)
    if not paths:
        return {"success": False, "error": "视频不存在或已删除"}
    return {"success": True, "video_id": video_id}


@app.post("/api/videos/{video_id}/restore")
def api_restore_video(video_id: int):
    """恢复软删除的视频"""
    restore_video(video_id)
    return {"success": True}


@app.post("/api/videos/batch-delete")
def api_batch_delete(data: BatchDeleteOp):
    """批量软删除视频"""
    result = delete_videos_batch(data.video_ids)
    return {"success": True, "deleted": len(result), "video_ids": list(result.keys())}


@app.post("/api/media/cleanup")
def api_cleanup_media():
    """清理没有被未删除视频引用的上传文件和缩略图。"""
    deleted = _cleanup_orphan_media()
    return {"success": True, "deleted": len(deleted), "files": deleted}


@app.post("/api/videos/batch-tags")
def api_batch_tags(data: BatchTagOp, action: str = Query("add")):
    """批量打标签 / 移除标签"""
    if action == "remove":
        batch_remove_tags(data.video_ids, data.tag_ids)
    else:
        batch_add_tags(data.video_ids, data.tag_ids)
    return {"success": True}


@app.post("/api/videos/batch-update")
def api_batch_update_videos(data: BatchVideoUpdateOp):
    fields = _model_updates(data)
    fields.pop("video_ids", None)
    clear_fields = fields.pop("clear_fields", [])
    for field in clear_fields or []:
        if field in {"direction_id", "group_id", "account_id", "interaction_hook_id", "test_batch_id"}:
            fields[field] = None
    updated = batch_update_videos(data.video_ids, **fields)
    return {"success": True, "updated": updated}


# --- 文件上传 ---

@app.post("/api/videos/{video_id}/upload")
def api_upload_video(video_id: int, file: UploadFile = File(...)):
    """上传视频文件（自动清理旧文件）"""
    ext = Path(file.filename).suffix.lower() if file.filename else ".mp4"
    if ext not in ALLOWED_VIDEO_EXT:
        return {"success": False, "error": f"不支持 {ext} 格式"}
    # 清理旧文件
    old_path = get_video_path(video_id)
    if old_path and Path(old_path).exists():
        try:
            Path(old_path).unlink()
        except Exception:
            pass
    filename = f"{video_id}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = UPLOAD_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    update_video_path(video_id, str(save_path))
    return {"success": True, "filename": filename}


@app.post("/api/videos/{video_id}/cover")
def api_upload_cover(video_id: int, file: UploadFile = File(...)):
    """上传缩略图（自动清理旧文件）"""
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in ALLOWED_IMAGE_EXT:
        return {"success": False, "error": f"不支持 {ext} 格式"}
    # 清理旧缩略图
    old_path = get_cover_path(video_id)
    if old_path and Path(old_path).exists():
        try:
            Path(old_path).unlink()
        except Exception:
            pass
    filename = f"{video_id}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = COVER_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    update_cover_path(video_id, str(save_path))
    return {"success": True, "filename": filename}


@app.delete("/api/videos/{video_id}/upload")
def api_delete_uploaded_video(video_id: int):
    path = get_video_path(video_id)
    if not path:
        return {"success": False, "error": "视频文件不存在"}
    _unlink_file(path)
    clear_video_path(video_id)
    return {"success": True}


@app.delete("/api/videos/{video_id}/cover")
def api_delete_uploaded_cover(video_id: int):
    path = get_cover_path(video_id)
    if not path:
        return {"success": False, "error": "缩略图不存在"}
    _unlink_file(path)
    clear_cover_path(video_id)
    return {"success": True}


@app.post("/api/videos/{video_id}/transcode")
def api_transcode_video(video_id: int):
    path = get_video_path(video_id)
    if not path or not Path(path).exists():
        return {"success": False, "error": "视频文件不存在"}
    ffmpeg = _get_ffmpeg_exe()
    if not ffmpeg:
        return {"success": False, "error": "未找到 ffmpeg，无法转码"}

    src = Path(path)
    output = UPLOAD_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}_compat.mp4"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            _unlink_file(output)
            msg = (proc.stderr or proc.stdout or "转码失败").strip().splitlines()
            return {"success": False, "error": msg[-1] if msg else "转码失败"}
        update_video_path(video_id, str(output))
        if src.resolve() != output.resolve():
            _unlink_file(src)
        return {"success": True, "filename": output.name}
    except subprocess.TimeoutExpired:
        _unlink_file(output)
        return {"success": False, "error": "转码超时"}
    except Exception as exc:
        _unlink_file(output)
        return {"success": False, "error": f"转码失败: {exc}"}


@app.post("/api/videos/{video_id}/cover/auto")
def api_auto_cover(video_id: int):
    path = get_video_path(video_id)
    if not path or not Path(path).exists():
        return {"success": False, "error": "视频文件不存在"}
    ffmpeg = _get_ffmpeg_exe()
    if not ffmpeg:
        return {"success": False, "error": "未找到 ffmpeg，无法生成缩略图"}

    video_path = Path(path)
    duration = _video_duration_seconds(ffmpeg, video_path) or 10
    candidates = [
        min(max(duration * ratio, 0.5), max(duration - 0.2, 0.5))
        for ratio in (0.12, 0.2, 0.35, 0.5, 0.7)
    ]
    generated = []
    for idx, second in enumerate(candidates):
        candidate = COVER_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}_frame{idx}.jpg"
        if _capture_cover_frame(ffmpeg, video_path, candidate, second):
            generated.append((candidate.stat().st_size, candidate))

    if not generated:
        return {"success": False, "error": "缩略图生成失败"}

    generated.sort(reverse=True, key=lambda item: item[0])
    best = generated[0][1]
    final_path = COVER_DIR / f"{video_id}_{uuid.uuid4().hex[:8]}.jpg"
    best.replace(final_path)
    for _, candidate in generated[1:]:
        _unlink_file(candidate)

    old_path = get_cover_path(video_id)
    update_cover_path(video_id, str(final_path))
    if old_path and Path(old_path).resolve() != final_path.resolve():
        _unlink_file(old_path)
    return {"success": True, "filename": final_path.name}


@app.get("/api/videos/{video_id}/stream")
def api_stream_video(video_id: int, range: Optional[str] = Header(default=None)):
    """流式播放视频"""
    path = get_video_path(video_id)
    if not path or not Path(path).exists():
        return {"error": "视频不存在"}
    file_path = Path(path)
    file_size = file_path.stat().st_size
    mime = MIME_VIDEO.get(file_path.suffix.lower(), "video/mp4")
    byte_range = _parse_range_header(range, file_size)

    if byte_range:
        start, end = byte_range

        def iter_file_range():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1024 * 512, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file_range(),
            status_code=206,
            media_type=mime,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            },
        )

    def iter_file():
        with open(file_path, "rb") as f:
            while chunk := f.read(1024 * 512):
                yield chunk

    return StreamingResponse(
        iter_file(),
        media_type=mime,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
    )


@app.get("/api/videos/{video_id}/cover")
def api_get_cover(video_id: int):
    """获取缩略图"""
    path = get_cover_path(video_id)
    if not path or not Path(path).exists():
        return {"error": "缩略图不存在"}
    file_path = Path(path)
    mime = MIME_IMAGE.get(file_path.suffix.lower(), "image/jpeg")
    return FileResponse(str(file_path), media_type=mime)


# --- CSV 导入导出 ---

@app.get("/api/export/csv")
def api_export_csv(
    tag_id: Optional[int] = None,
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ids: Optional[str] = None,
):
    """导出 CSV"""
    selected_ids = [v.strip() for v in ids.split(",") if v.strip()] if ids else None
    csv_text = export_csv(tag_id, keyword, date_from, date_to, selected_ids)
    today = date.today().strftime("%Y%m%d")
    return PlainTextResponse(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=datalens_{today}.csv"},
    )


@app.post("/api/import/csv")
def api_import_csv(file: UploadFile = File(...)):
    """导入 CSV"""
    content = file.file.read().decode("utf-8-sig")  # 处理 BOM
    result = import_csv(content)
    return result


# --- 标签 API ---

@app.get("/api/tags")
def api_tags():
    return {"tags": get_all_tags()}


@app.post("/api/tags")
def api_add_tag(data: TagIn):
    tag_id = add_tag(data.name)
    if tag_id is None:
        return {"success": False, "error": "标签已存在"}
    return {"success": True, "id": tag_id}


@app.delete("/api/tags/{tag_id}")
def api_delete_tag(tag_id: int):
    delete_tag(tag_id)
    return {"success": True}


@app.get("/api/hooks")
def api_hooks():
    return {"hooks": get_interaction_hooks()}


@app.post("/api/hooks")
def api_add_hook(data: HookIn):
    hook_id = add_interaction_hook(
        data.name, data.hook_type, data.target_comment,
        data.trigger_text, data.reuse_advice, data.note, data.status,
        data.comment_type, data.target_action, data.variants,
        data.applicable_directions, data.bad_scenarios,
        data.failure_reason, data.next_test_action,
    )
    if hook_id is None:
        return {"success": False, "error": "钩子名称已存在"}
    return {"success": True, "id": hook_id}


@app.put("/api/hooks/{hook_id}")
def api_update_hook(hook_id: int, data: HookUpdate):
    ok = update_interaction_hook(
        hook_id, data.name, data.hook_type, data.target_comment,
        data.trigger_text, data.reuse_advice, data.note, data.status,
        data.comment_type, data.target_action, data.variants,
        data.applicable_directions, data.bad_scenarios,
        data.failure_reason, data.next_test_action,
    )
    return {"success": ok}


@app.get("/api/hooks/{hook_id}/versions")
def api_hook_versions(hook_id: int):
    return {"versions": get_hook_versions(hook_id)}


@app.post("/api/hooks/{hook_id}/versions")
def api_add_hook_version(hook_id: int, data: HookVersionIn):
    version_id = add_hook_version(hook_id, data.version_name, data.phrase, data.note, data.status)
    return {"success": True, "id": version_id}


@app.delete("/api/hooks/versions/{version_id}")
def api_delete_hook_version(version_id: int):
    delete_hook_version(version_id)
    return {"success": True}


@app.delete("/api/hooks/{hook_id}")
def api_delete_hook(hook_id: int):
    delete_interaction_hook(hook_id)
    return {"success": True}


@app.post("/api/hooks/from-video")
def api_hook_from_video(data: HookFromVideoIn):
    hook_id = create_hook_from_video(data.video_id, data.name, data.hook_type)
    if not hook_id:
        return {"success": False, "error": "视频不存在"}
    return {"success": True, "id": hook_id}


@app.get("/api/hooks/recommendations")
def api_hook_recommendations(direction_id: Optional[int] = None, limit: int = 5):
    return {"hooks": get_hook_recommendations(direction_id, limit)}


@app.get("/api/hooks/opportunities")
def api_hook_opportunities(limit: int = 10):
    return {"videos": get_comment_opportunities(limit)}


@app.get("/api/hooks/{hook_id}/review")
def api_hook_review(hook_id: int):
    data = get_hook_review(hook_id)
    if not data:
        return {"success": False, "error": "钩子不存在"}
    data["success"] = True
    return data


@app.get("/api/data-quality")
def api_data_quality():
    return get_data_quality()


@app.get("/api/data-quality/tasks")
def api_data_quality_tasks(limit: int = 8):
    return get_data_quality_tasks(limit)


@app.get("/api/audit-logs")
def api_audit_logs(limit: int = 50, entity_type: Optional[str] = None, entity_id: Optional[int] = None):
    return {"logs": get_audit_logs(limit, entity_type, entity_id)}


@app.post("/api/data-quality/fix")
def api_data_quality_fix(data: dict):
    action = data.get("action")
    video_ids = data.get("video_ids") or []
    if action == "cap_completion_100":
        updated = batch_update_videos(video_ids, completion_rate=100)
        return {"success": True, "updated": updated}
    if action == "create_hooks":
        created = []
        for vid in video_ids:
            hook_id = create_hook_from_video(int(vid), None, "评论引导")
            if hook_id:
                created.append(hook_id)
        return {"success": True, "created": len(created), "hook_ids": created}
    return {"success": False, "error": "未知修复动作"}


@app.get("/api/test-batches")
def api_test_batches():
    return {"batches": get_test_batches()}


@app.post("/api/test-batches")
def api_add_test_batch(data: BatchIn):
    batch_id = add_test_batch(data.name, data.note)
    if batch_id is None:
        return {"success": False, "error": "测试批次已存在"}
    return {"success": True, "id": batch_id}


@app.get("/api/backup/db")
def api_backup_db():
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    src = Path(DB_PATH)
    dst = backup_dir / f"datalens_backup_{stamp}_{uuid.uuid4().hex[:6]}.db"
    shutil.copy2(src, dst)
    return FileResponse(str(dst), filename=dst.name, media_type="application/octet-stream")


@app.get("/api/backups")
def api_list_backups():
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(backup_dir.glob("*.db"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "modified": st.st_mtime})
    return {"backups": items}


@app.post("/api/backup/restore")
def api_restore_backup(data: dict):
    name = Path(str(data.get("name", ""))).name
    if not name.endswith(".db"):
        return {"success": False, "error": "无效备份文件"}
    backup = Path("data/backups") / name
    if not backup.exists():
        return {"success": False, "error": "备份不存在"}
    current = Path(DB_PATH)
    safety = Path("data/backups") / f"before_restore_{date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}.db"
    shutil.copy2(current, safety)
    shutil.copy2(backup, current)
    return {"success": True, "restored": name, "safety_backup": safety.name}


@app.get("/api/search")
def api_global_search(q: str = "", limit: int = 8):
    return global_search(q, limit)


@app.get("/api/export/report")
def api_export_report():
    cockpit = get_cockpit_summary()
    directions = get_direction_recommendations(30)
    hooks = get_interaction_hooks()
    top_videos = get_top_videos(10, "play_count")
    quality = get_data_quality_tasks(5).get("tasks", [])
    today = date.today().isoformat()
    lines = [
        f"# 运营复盘报告 {today}",
        "",
        "## 总览",
        f"- 视频总数：{cockpit.get('totals', {}).get('video_count', 0)}",
        f"- 总播放：{cockpit.get('totals', {}).get('total_play', 0)}",
        f"- 平均互动率：{cockpit.get('totals', {}).get('avg_interaction_rate', 0)}%",
        "",
        "## 推荐方向",
    ]
    for d in directions[:8]:
        lines.append(f"- {d.get('direction_name')}：均播 {d.get('avg_play', 0)}，互动 {d.get('avg_interaction_rate', 0)}%，效果 {d.get('effect_level', '待观察')}")
    lines += ["", "## 钩子复盘"]
    for h in hooks[:8]:
        decision = h.get("decision") or {}
        lines.append(f"- {h.get('name')}：{h.get('effect_level')} / {decision.get('label', '待判断')}，均评 {h.get('avg_comments', 0)}，评论率 {h.get('avg_comment_rate', 0)}%")
    lines += ["", "## Top 视频"]
    for v in top_videos:
        lines.append(f"- {v.get('title')}：播放 {v.get('play_count', 0)}，评论 {v.get('comment_count', 0)}，互动 {v.get('interaction_rate', 0)}%")
    best_dirs = [d for d in directions if d.get("video_count", 0) > 0][:3]
    reusable_hooks = [h for h in hooks if (h.get("decision") or {}).get("label") == "继续复用"][:3]
    issue_tasks = [t for t in quality if t.get("videos")]
    lines += ["", "## 下一步建议动作"]
    if best_dirs:
        lines.append("- 继续测试方向：" + "、".join(d.get("direction_name", "") for d in best_dirs if d.get("direction_name")))
    if reusable_hooks:
        lines.append("- 优先复用钩子：" + "、".join(h.get("name", "") for h in reusable_hooks if h.get("name")))
    if issue_tasks:
        lines.append("- 优先补齐数据：" + "、".join(f"{t.get('title')}({len(t.get('videos', []))})" for t in issue_tasks))
    if not (best_dirs or reusable_hooks or issue_tasks):
        lines.append("- 暂无明显风险项，建议继续录入新素材并保持方向/钩子标注。")
    text = "\n".join(lines)
    return Response(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=operation_report_{today}.md"},
    )


@app.get("/api/export/hooks")
def api_export_hooks():
    payload = json.dumps(get_interaction_hooks(), ensure_ascii=False, indent=2)
    return Response(
        payload,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=hooks_{date.today().isoformat()}.json"},
    )


@app.get("/api/export/directions")
def api_export_directions():
    payload = json.dumps(get_all_directions(), ensure_ascii=False, indent=2)
    return Response(
        payload,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=directions_{date.today().isoformat()}.json"},
    )


# --- 违规类型 API ---

@app.get("/api/violation-types")
def api_violation_types():
    return {"types": get_all_violation_types()}


@app.post("/api/violation-types")
def api_add_violation_type(data: TagIn):
    vt_id = add_violation_type(data.name)
    if vt_id is None:
        return {"success": False, "error": "违规类型已存在"}
    return {"success": True, "id": vt_id}


@app.delete("/api/violation-types/{vt_id}")
def api_delete_violation_type(vt_id: int):
    delete_violation_type(vt_id)
    return {"success": True}


# --- 工作台 API ---

@app.get("/api/dashboard")
def api_dashboard():
    return get_dashboard_summary()


@app.get("/api/cockpit")
def api_cockpit():
    return get_cockpit_summary()


@app.get("/api/violation-stats")
def api_violation_stats(days: int = 30):
    return get_violation_stats(days)


@app.get("/api/matrix-health")
def api_matrix_health():
    return get_matrix_health()


@app.get("/api/publish-time-analysis")
def api_publish_time_analysis(days: int = 30):
    return get_publish_time_analysis(days)


# --- 分析 API ---

@app.get("/api/analysis/tag-stats")
def api_tag_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    return {"stats": get_tag_analysis(date_from, date_to)}


@app.get("/api/analysis/tag-trend")
def api_tag_trend(
    tag_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    return {"trend": get_tag_trend(tag_id, date_from, date_to)}


@app.get("/api/analysis/keyword-stats")
def api_keyword_stats():
    return {"videos": get_keyword_analysis()}


@app.get("/api/analysis/top-videos")
def api_top_videos(
    n: int = Query(default=10, le=50),
    sort_by: str = "play_count",
):
    return {"videos": get_top_videos(n, sort_by)}


# --- 计划 API ---

class PlanIn(BaseModel):
    title: str = ""
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    priority: str = "中"
    plan_date: str = ""
    group_id: Optional[int] = None
    target_count: int = 0
    video_id: Optional[int] = None
    account_id: Optional[int] = None


class PlanUpdate(BaseModel):
    title: Optional[str] = None
    time_from: Optional[str] = None
    time_to: Optional[str] = None
    priority: Optional[str] = None
    group_id: Optional[int] = None
    target_count: Optional[int] = None
    video_id: Optional[int] = None
    account_id: Optional[int] = None
    status: Optional[str] = None


class PlanCopyIn(BaseModel):
    source_date: str
    target_date: str


@app.get("/api/plans")
def api_get_plans(plan_date: Optional[str] = None, group_id: Optional[int] = None, account_id: Optional[int] = None):
    return {"plans": get_plans(plan_date, group_id, account_id)}


@app.post("/api/plans")
def api_add_plan(data: PlanIn):
    pid = add_plan(data.title, data.time_from, data.time_to,
                   data.priority, data.plan_date, data.group_id, data.target_count, data.video_id, data.account_id)
    return {"success": True, "id": pid}


@app.put("/api/plans/{plan_id}")
def api_update_plan(plan_id: int, data: PlanUpdate):
    ok = update_plan(plan_id, **_model_updates(data))
    if not ok:
        return {"success": False, "error": "计划不存在"}
    return {"success": True}


@app.post("/api/plans/{plan_id}/toggle")
def api_toggle_plan(plan_id: int):
    toggle_plan(plan_id)
    return {"success": True}


@app.post("/api/plans/copy")
def api_copy_plans(data: PlanCopyIn):
    copied = copy_plans(data.source_date, data.target_date)
    return {"success": True, "copied": copied}


@app.delete("/api/plans/{plan_id}")
def api_delete_plan(plan_id: int):
    delete_plan(plan_id)
    return {"success": True}


@app.get("/api/plans/export/txt")
def api_export_plans_txt(plan_date: Optional[str] = None):
    from datetime import date as _date
    txt = export_plans_txt(plan_date or _date.today().isoformat())
    fname = f"plans_{(plan_date or _date.today().isoformat())}.txt"
    return PlainTextResponse(
        txt,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# --- 方向 API ---

@app.get("/api/directions")
def api_directions():
    return {"directions": get_all_directions()}


@app.post("/api/directions")
def api_add_direction(data: DirectionIn):
    d_id = add_direction(data.name, data.color, data.status, data.tags, data.note, data.criteria, data.is_lift, data.effect_level)
    if d_id is None:
        return {"success": False, "error": "方向已存在"}
    return {"success": True, "id": d_id}


@app.put("/api/directions/{direction_id}")
def api_update_direction(direction_id: int, data: DirectionUpdate):
    ok = update_direction(direction_id, data.name, data.color, data.status, data.tags, data.note, data.criteria, data.is_lift, data.effect_level)
    if not ok:
        return {"success": False, "error": "方向不存在"}
    return {"success": True}


@app.delete("/api/directions/{direction_id}")
def api_delete_direction(direction_id: int):
    delete_direction(direction_id)
    return {"success": True}


@app.post("/api/dev/seed-matrix-demo")
def api_seed_matrix_demo():
    demo_dirs = [
        {
            "name": "演示-探店测评",
            "color": "#5b8def",
            "status": "已通过",
            "effect": "爆款",
            "tags": "高互动, 可复制, 强开头",
            "criteria": "3条内均播破5000，互动率大于3%，无违规则继续放量",
            "note": "标题和前三秒钩子有效，适合继续拆模板。",
            "plays": [3200, 5200, 8800, 14600, 21800, 17600],
        },
        {
            "name": "演示-剧情反转",
            "color": "#16a34a",
            "status": "测试中",
            "effect": "良好",
            "tags": "完播高, 需稳定更新",
            "criteria": "连续两周互动率不低于2.5%，完播率不低于28%",
            "note": "播放增长稳定，但爆发点还需要继续测脚本节奏。",
            "plays": [1800, 2600, 4100, 5300, 6100, 7600],
        },
        {
            "name": "演示-口播干货",
            "color": "#f59e0b",
            "status": "已通过",
            "effect": "优秀",
            "tags": "低成本, 批量产出",
            "criteria": "均播稳定在4000以上，收藏评论有明显增长",
            "note": "适合规模化，但需要更多选题库支撑。",
            "plays": [2200, 3900, 4800, 6600, 7200, 8100],
        },
        {
            "name": "演示-硬广素材",
            "color": "#dc2626",
            "status": "未过审",
            "effect": "无效",
            "tags": "审核风险, 转化弱",
            "criteria": "违规或低互动则暂停",
            "note": "审核风险偏高，建议先改表达方式。",
            "plays": [900, 1200, 800, 1100, 700, 650],
        },
    ]
    created_dirs = 0
    created_videos = 0
    today = date.today()
    for item in demo_dirs:
        direction = next((d for d in get_all_directions() if d["name"] == item["name"]), None)
        if direction:
            d_id = direction["id"]
            update_direction(d_id, color=item["color"], status=item["status"], tags=item["tags"], note=item["note"], criteria=item["criteria"], effect_level=item["effect"])
        else:
            d_id = add_direction(item["name"], item["color"], item["status"], item["tags"], item["note"], item["criteria"], effect_level=item["effect"])
            created_dirs += 1
        for idx, play in enumerate(item["plays"]):
            publish_date = (today - timedelta(days=(len(item["plays"]) - idx - 1) * 6)).isoformat()
            title = f"{item['name']} 样例素材 {idx + 1}"
            existing = get_videos(keyword=title, limit=1, offset=0)
            if existing:
                continue
            likes = max(1, int(play * (0.035 + idx * 0.002)))
            comments = max(0, int(play * (0.006 + idx * 0.001)))
            shares = max(0, int(play * 0.004))
            favorites = max(0, int(play * 0.01))
            completion = min(62, 20 + idx * 5 + (8 if item["effect"] in ("优秀", "爆款") else 0))
            violation = "审核风险" if item["status"] == "未过审" and idx >= 2 else ""
            add_video(
                title=title,
                play_count=play,
                like_count=likes,
                comment_count=comments,
                share_count=shares,
                favorite_count=favorites,
                publish_date=publish_date,
                tag_ids=[],
                direction_id=d_id,
                completion_rate=completion,
                duration=35 + idx * 3,
                publish_time="19:30",
                violation_type=violation,
                violation_note="演示数据：用于观察未过审风险" if violation else "",
            )
            created_videos += 1
    return {"success": True, "created_directions": created_dirs, "created_videos": created_videos}


# --- 设备组 API ---

@app.get("/api/groups")
def api_groups():
    return {"groups": get_all_groups()}


@app.post("/api/groups")
def api_add_group(data: GroupIn):
    g_id = add_group(data.name, data.direction_id, data.phone_list)
    if g_id is None:
        return {"success": False, "error": "组已存在"}
    return {"success": True, "id": g_id}


@app.put("/api/groups/{group_id}")
def api_update_group(group_id: int, data: GroupUpdate):
    ok = update_group(group_id, **_model_updates(data))
    if not ok:
        return {"success": False, "error": "组不存在"}
    return {"success": True}


@app.delete("/api/groups/{group_id}")
def api_delete_group(group_id: int):
    delete_group(group_id)
    return {"success": True}


# --- 账号 API ---

class AccountIn(BaseModel):
    name: str
    platform: str = '抖音'
    direction_id: Optional[int] = None
    group_id: Optional[int] = None
    status: str = '运营中'
    note: str = ''


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    platform: Optional[str] = None
    direction_id: Optional[int] = None
    group_id: Optional[int] = None
    status: Optional[str] = None
    note: Optional[str] = None


@app.get("/api/accounts")
def api_accounts():
    return {"accounts": get_all_accounts()}


@app.post("/api/accounts")
def api_add_account(data: AccountIn):
    account_id = add_account(data.name, data.platform, data.direction_id, data.group_id, data.status, data.note)
    if account_id is None:
        return {"success": False, "error": "账号已存在"}
    return {"success": True, "id": account_id}


@app.put("/api/accounts/{account_id}")
def api_update_account(account_id: int, data: AccountUpdate):
    ok = update_account(account_id, **_model_updates(data))
    if not ok:
        return {"success": False, "error": "账号不存在"}
    return {"success": True}


@app.delete("/api/accounts/{account_id}")
def api_delete_account(account_id: int):
    delete_account(account_id)
    return {"success": True}


@app.get("/api/account-stats")
def api_account_stats():
    return {"stats": get_account_stats()}


# --- 矩阵分析 API ---

@app.get("/api/matrix/summary")
def api_matrix_summary():
    return get_matrix_summary()


@app.get("/api/matrix/direction-stats")
def api_direction_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    return {"stats": get_direction_analysis(date_from, date_to)}


@app.get("/api/matrix/direction-recommendations")
def api_direction_recommendations(days: int = 30):
    return {"directions": get_direction_recommendations(days)}


@app.get("/api/matrix/direction-trend")
def api_direction_trend(
    direction_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    granularity: str = "month",
):
    return {"trend": get_direction_trend(direction_id, date_from, date_to, granularity)}


# --- 前端 ---

@app.get("/")
async def index():
    return FileResponse(str(WEB_INDEX))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
