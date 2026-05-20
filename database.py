"""DataLens - Database Layer"""

import csv
import io
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from config import DB_PATH, DEFAULT_TAGS, DEFAULT_VIOLATION_TYPES, DATA_DIR

DB_FILE = Path(DB_PATH)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

_UNSET = object()


def _migrate_old_db():
    """旧版 db 文件名是 data.db，自动迁移到 datalens.db"""
    old_db = DATA_DIR / "data.db"
    if old_db.exists() and not DB_FILE.exists():
        old_db.rename(DB_FILE)


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    _migrate_old_db()
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                play_count INTEGER NOT NULL DEFAULT 0,
                like_count INTEGER NOT NULL DEFAULT 0,
                comment_count INTEGER NOT NULL DEFAULT 0,
                share_count INTEGER NOT NULL DEFAULT 0,
                favorite_count INTEGER NOT NULL DEFAULT 0,
                publish_date TEXT,
                video_path TEXT,
                cover_path TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS video_tags (
                video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (video_id, tag_id)
            );

            CREATE TABLE IF NOT EXISTS directions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#e94560',
                status TEXT DEFAULT '待测试',
                is_lift INTEGER NOT NULL DEFAULT 0,
                effect_level TEXT DEFAULT '待观察',
                tags TEXT DEFAULT '',
                note TEXT DEFAULT '',
                criteria TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                direction_id INTEGER REFERENCES directions(id) ON DELETE SET NULL,
                phone_list TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS violation_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL DEFAULT '抖音',
                direction_id INTEGER REFERENCES directions(id) ON DELETE SET NULL,
                group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT '运营中',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS interaction_hooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                hook_type TEXT NOT NULL DEFAULT '评论引导',
                target_comment TEXT DEFAULT '',
                comment_type TEXT DEFAULT '关键词',
                target_action TEXT DEFAULT '评论',
                variants TEXT DEFAULT '',
                trigger_text TEXT DEFAULT '',
                reuse_advice TEXT DEFAULT '',
                note TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT '可复用',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS test_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS hook_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hook_id INTEGER NOT NULL REFERENCES interaction_hooks(id) ON DELETE CASCADE,
                version_name TEXT NOT NULL DEFAULT '',
                phrase TEXT NOT NULL DEFAULT '',
                note TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT '测试中',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                action TEXT NOT NULL,
                summary TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
        """)

        # 兼容旧库：逐步添加列
        for col in ("video_path TEXT", "cover_path TEXT",
                    "favorite_count INTEGER NOT NULL DEFAULT 0",
                    "direction_id INTEGER REFERENCES directions(id) ON DELETE SET NULL",
                    "group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL",
                    "account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL",
                    "completion_rate REAL DEFAULT 0",
                    "duration INTEGER DEFAULT 0",
                    "publish_time TEXT",
                    "violation_type TEXT DEFAULT ''",
                    "violation_note TEXT DEFAULT ''",
                    "violation_status TEXT DEFAULT 'pending'",
                    "interaction_hook_id INTEGER REFERENCES interaction_hooks(id) ON DELETE SET NULL",
                    "test_batch_id INTEGER REFERENCES test_batches(id) ON DELETE SET NULL",
                    "comment_reason TEXT DEFAULT ''",
                    "comment_trigger_text TEXT DEFAULT ''",
                    "comment_reuse_advice TEXT DEFAULT ''",
                    "material_status TEXT DEFAULT '已发布'",
                    "review_summary TEXT DEFAULT ''",
                    "reusable_point TEXT DEFAULT ''",
                    "failure_reason TEXT DEFAULT ''",
                    "next_action TEXT DEFAULT ''",
                    "deleted_at TEXT"):
            try:
                conn.execute(f"ALTER TABLE videos ADD COLUMN {col}")
            except Exception:
                pass

        for col in (
            "status TEXT DEFAULT '待测试'",
            "is_lift INTEGER NOT NULL DEFAULT 0",
            "effect_level TEXT DEFAULT '待观察'",
            "tags TEXT DEFAULT ''",
            "note TEXT DEFAULT ''",
            "criteria TEXT DEFAULT ''",
        ):
            try:
                conn.execute(f"ALTER TABLE directions ADD COLUMN {col}")
            except Exception:
                pass

        for col in (
            "comment_type TEXT DEFAULT '关键词'",
            "target_action TEXT DEFAULT '评论'",
            "variants TEXT DEFAULT ''",
            "applicable_directions TEXT DEFAULT ''",
            "bad_scenarios TEXT DEFAULT ''",
            "failure_reason TEXT DEFAULT ''",
            "next_test_action TEXT DEFAULT ''",
        ):
            try:
                conn.execute(f"ALTER TABLE interaction_hooks ADD COLUMN {col}")
            except Exception:
                pass

        for col in (
            "direction_id INTEGER REFERENCES directions(id) ON DELETE SET NULL",
            "goal TEXT DEFAULT ''",
            "status TEXT DEFAULT '测试中'",
            "conclusion TEXT DEFAULT ''",
            "next_action TEXT DEFAULT ''",
        ):
            try:
                conn.execute(f"ALTER TABLE test_batches ADD COLUMN {col}")
            except Exception:
                pass

        try:
            conn.execute("UPDATE directions SET is_lift=1, effect_level='优秀', status='已通过' WHERE status='起量'")
            conn.execute("UPDATE directions SET effect_level='优秀' WHERE is_lift=1 AND (effect_level IS NULL OR effect_level='' OR effect_level='待观察')")
        except Exception:
            pass

        # 初始化预设标签
        for tag_name in DEFAULT_TAGS:
            conn.execute(
                "INSERT OR IGNORE INTO tags (name) VALUES (?)",
                (tag_name,),
            )

        # 初始化预设违规类型
        for vt_name in DEFAULT_VIOLATION_TYPES:
            conn.execute(
                "INSERT OR IGNORE INTO violation_types (name) VALUES (?)",
                (vt_name,),
            )

        # 创建性能索引（幂等）
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_videos_publish_date ON videos(publish_date);
            CREATE INDEX IF NOT EXISTS idx_videos_direction_id ON videos(direction_id);
            CREATE INDEX IF NOT EXISTS idx_videos_group_id ON videos(group_id);
            CREATE INDEX IF NOT EXISTS idx_videos_violation_status ON videos(violation_status);
            CREATE INDEX IF NOT EXISTS idx_videos_publish_time ON videos(publish_time);
            CREATE INDEX IF NOT EXISTS idx_videos_account_id ON videos(account_id);
            CREATE INDEX IF NOT EXISTS idx_videos_interaction_hook_id ON videos(interaction_hook_id);
            CREATE INDEX IF NOT EXISTS idx_videos_test_batch_id ON videos(test_batch_id);
            CREATE INDEX IF NOT EXISTS idx_videos_material_status ON videos(material_status);
            CREATE INDEX IF NOT EXISTS idx_test_batches_direction_id ON test_batches(direction_id);
        """)

    init_plans_table()


# --- 视频 CRUD ---

def add_video(title, play_count, like_count, comment_count, share_count,
              publish_date, tag_ids, direction_id=None, group_id=None,
              completion_rate=0, duration=0, publish_time=None,
              violation_type='', violation_note='', violation_status='pending',
              account_id=None, favorite_count=0, interaction_hook_id=None,
              comment_reason='', comment_trigger_text='', comment_reuse_advice='',
              test_batch_id=None, material_status='已发布', review_summary='',
              reusable_point='', failure_reason='', next_action=''):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO videos
               (title, play_count, like_count, comment_count, share_count,
                favorite_count, publish_date, direction_id, group_id, account_id,
                completion_rate, duration, publish_time,
                violation_type, violation_note, violation_status,
                interaction_hook_id, test_batch_id, comment_reason, comment_trigger_text, comment_reuse_advice,
                material_status, review_summary, reusable_point, failure_reason, next_action)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, play_count, like_count, comment_count, share_count,
             favorite_count, publish_date, direction_id, group_id, account_id,
             completion_rate, duration, publish_time,
             violation_type, violation_note, violation_status,
             interaction_hook_id, test_batch_id, comment_reason, comment_trigger_text, comment_reuse_advice,
             material_status, review_summary, reusable_point, failure_reason, next_action),
        )
        video_id = cur.lastrowid
        log_audit("video", video_id, "create", f"新增视频：{title}", conn)
        for tid in tag_ids:
            conn.execute(
                "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
                (video_id, tid),
            )
        return video_id


def update_video(video_id, title, play_count, like_count, comment_count,
                 share_count, publish_date, tag_ids, video_path=None,
                 cover_path=None, direction_id=None, group_id=None,
                 completion_rate=None, duration=None, publish_time=None,
                 violation_type=None, violation_note=None, violation_status=None,
                 account_id=None, favorite_count=None, interaction_hook_id=None,
                 comment_reason=None, comment_trigger_text=None, comment_reuse_advice=None,
                 test_batch_id=None, material_status=None, review_summary=None,
                 reusable_point=None, failure_reason=None, next_action=None):
    with get_db() as conn:
        conn.execute(
            """UPDATE videos SET
               title=?, play_count=?, like_count=?,
               comment_count=?, share_count=?, favorite_count=COALESCE(?, favorite_count), publish_date=?,
               video_path=COALESCE(?, video_path),
               cover_path=COALESCE(?, cover_path),
               direction_id=?, group_id=?, account_id=?,
               completion_rate=COALESCE(?, completion_rate),
               duration=COALESCE(?, duration),
               publish_time=COALESCE(?, publish_time),
               violation_type=COALESCE(?, violation_type),
               violation_note=COALESCE(?, violation_note),
               violation_status=COALESCE(?, violation_status),
               interaction_hook_id=?,
               test_batch_id=?,
               comment_reason=COALESCE(?, comment_reason),
               comment_trigger_text=COALESCE(?, comment_trigger_text),
               comment_reuse_advice=COALESCE(?, comment_reuse_advice),
               material_status=COALESCE(?, material_status),
               review_summary=COALESCE(?, review_summary),
               reusable_point=COALESCE(?, reusable_point),
               failure_reason=COALESCE(?, failure_reason),
               next_action=COALESCE(?, next_action)
               WHERE id=?""",
            (title, play_count, like_count, comment_count,
             share_count, favorite_count, publish_date, video_path, cover_path,
             direction_id, group_id, account_id,
             completion_rate, duration, publish_time,
             violation_type, violation_note, violation_status,
             interaction_hook_id, test_batch_id, comment_reason, comment_trigger_text, comment_reuse_advice,
             material_status, review_summary, reusable_point, failure_reason, next_action,
             video_id),
        )
        conn.execute("DELETE FROM video_tags WHERE video_id=?", (video_id,))
        for tid in tag_ids:
            conn.execute(
                "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
                (video_id, tid),
            )
        log_audit("video", video_id, "update", f"更新视频：{title}", conn)


def patch_video(video_id, **fields):
    """行内编辑：只更新指定字段"""
    if not fields:
        return
    sets = ', '.join(f'{k}=?' for k in fields)
    vals = list(fields.values()) + [video_id]
    with get_db() as conn:
        conn.execute(f"UPDATE videos SET {sets} WHERE id=?", vals)


def batch_update_videos(video_ids, **fields):
    allowed = {
        "direction_id", "group_id", "account_id", "interaction_hook_id",
        "test_batch_id", "violation_status", "completion_rate", "material_status"
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not video_ids or not clean:
        return 0
    ids = [int(v) for v in video_ids if str(v).isdigit()]
    if not ids:
        return 0
    sets = ", ".join([f"{k}=?" for k in clean.keys()])
    placeholders = ",".join("?" * len(ids))
    vals = list(clean.values()) + ids
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE videos SET {sets} WHERE id IN ({placeholders}) AND deleted_at IS NULL",
            vals,
        )
        log_audit("video", 0, "batch_update", f"批量更新视频：{len(ids)} 条", conn)
        return cur.rowcount


def delete_video(video_id):
    """软删除视频：设置 deleted_at 而非真删"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT video_path, cover_path FROM videos WHERE id=? AND deleted_at IS NULL",
            (video_id,)
        ).fetchone()
        if not row:
            return {}
        conn.execute("UPDATE videos SET deleted_at=datetime('now','localtime') WHERE id=?", (video_id,))
        return dict(row)


def restore_video(video_id):
    """恢复软删除的视频"""
    with get_db() as conn:
        conn.execute("UPDATE videos SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL", (video_id,))


def delete_videos_batch(video_ids):
    """批量软删除，返回被删除的视频ID列表"""
    if not video_ids:
        return {}
    with get_db() as conn:
        placeholders = ",".join("?" * len(video_ids))
        rows = conn.execute(
            f"SELECT id, video_path, cover_path FROM videos WHERE id IN ({placeholders}) AND deleted_at IS NULL",
            video_ids,
        ).fetchall()
        if rows:
            conn.execute(
                f"UPDATE videos SET deleted_at=datetime('now','localtime') WHERE id IN ({placeholders}) AND deleted_at IS NULL",
                video_ids,
            )
        return {r["id"]: {"video_path": r["video_path"], "cover_path": r["cover_path"]} for r in rows}


def update_video_path(video_id, video_path):
    with get_db() as conn:
        conn.execute("UPDATE videos SET video_path=? WHERE id=?", (video_path, video_id))


def update_cover_path(video_id, cover_path):
    with get_db() as conn:
        conn.execute("UPDATE videos SET cover_path=? WHERE id=?", (cover_path, video_id))


def clear_video_path(video_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET video_path=NULL WHERE id=?", (video_id,))


def clear_cover_path(video_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET cover_path=NULL WHERE id=?", (video_id,))


def get_video_path(video_id):
    with get_db() as conn:
        row = conn.execute("SELECT video_path FROM videos WHERE id=? AND deleted_at IS NULL", (video_id,)).fetchone()
        return row["video_path"] if row else None


def get_video_by_id(video_id):
    """获取单个视频详情（含标签和互动率）"""
    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) "
                 "ELSE 0 END")
    with get_db() as conn:
        row = conn.execute(
            f"SELECT v.*, {rate_expr} as interaction_rate, a.name as account_name FROM videos v LEFT JOIN accounts a ON v.account_id = a.id WHERE v.id=? AND v.deleted_at IS NULL",
            (video_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        tag_rows = conn.execute("""
            SELECT t.id, t.name FROM tags t
            JOIN video_tags vt ON t.id = vt.tag_id
            WHERE vt.video_id = ?
        """, (video_id,)).fetchall()
        d["tags"] = [dict(t) for t in tag_rows]
        return d


def get_cover_path(video_id):
    with get_db() as conn:
        row = conn.execute("SELECT cover_path FROM videos WHERE id=? AND deleted_at IS NULL", (video_id,)).fetchone()
        return row["cover_path"] if row else None


def _build_conditions(tag_id, keyword, date_from, date_to,
                      direction_id=None, group_id=None, violation=None,
                      account_id=None, ids=None):
    conditions = ["v.deleted_at IS NULL"]
    params = []
    if ids:
        clean_ids = [int(v) for v in ids if str(v).isdigit()]
        if clean_ids:
            conditions.append(f"v.id IN ({','.join('?' * len(clean_ids))})")
            params.extend(clean_ids)
    if tag_id:
        conditions.append("v.id IN (SELECT video_id FROM video_tags WHERE tag_id=?)")
        params.append(tag_id)
    if keyword:
        conditions.append("v.title LIKE ?")
        params.append(f"%{keyword}%")
    if date_from:
        conditions.append("v.publish_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("v.publish_date <= ?")
        params.append(date_to)
    if direction_id:
        conditions.append("v.direction_id = ?")
        params.append(direction_id)
    if group_id:
        conditions.append("v.group_id = ?")
        params.append(group_id)
    if account_id:
        conditions.append("v.account_id = ?")
        params.append(account_id)
    if violation == 'violation':
        conditions.append("v.violation_type IS NOT NULL AND v.violation_type != ''")
    elif violation == 'none':
        conditions.append("(v.violation_type IS NULL OR v.violation_type = '')")
    elif violation:
        conditions.append("v.violation_type = ?")
        params.append(violation)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


def get_videos(tag_id=None, keyword=None, date_from=None, date_to=None,
               sort_by="publish_date", order="desc", limit=50, offset=0,
               direction_id=None, group_id=None, violation=None, account_id=None,
               ids=None):
    """获取视频列表，支持标签/日期范围/方向/组/违规/账号筛选和搜索"""
    where, params = _build_conditions(tag_id, keyword, date_from, date_to,
                                      direction_id, group_id, violation, account_id, ids)

    allowed_sort = {"publish_date", "play_count", "like_count",
                    "comment_count", "share_count", "favorite_count", "interaction_rate",
                    "created_at", "completion_rate", "duration"}
    if sort_by not in allowed_sort:
        sort_by = "publish_date"
    if order not in ("asc", "desc"):
        order = "desc"

    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) "
                 "ELSE 0 END")

    if sort_by == "interaction_rate":
        order_by = f"{rate_expr} {order}"
    elif sort_by == "completion_rate":
        order_by = f"v.completion_rate {order}"
    elif sort_by == "duration":
        order_by = f"v.duration {order}"
    else:
        order_by = f"v.{sort_by} {order}"

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT v.*, {rate_expr} as interaction_rate,
                   a.name as account_name
            FROM videos v
            LEFT JOIN accounts a ON v.account_id = a.id
            {where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            tag_rows = conn.execute("""
                SELECT t.id, t.name FROM tags t
                JOIN video_tags vt ON t.id = vt.tag_id
                WHERE vt.video_id = ?
            """, (r["id"],)).fetchall()
            d["tags"] = [dict(t) for t in tag_rows]
            result.append(d)

        return result


def get_video_count(tag_id=None, keyword=None, date_from=None, date_to=None,
                    direction_id=None, group_id=None, violation=None, account_id=None,
                    ids=None):
    where, params = _build_conditions(tag_id, keyword, date_from, date_to,
                                      direction_id, group_id, violation, account_id, ids)
    with get_db() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM videos v{where}", params).fetchone()[0]


def log_audit(entity_type, entity_id, action, summary='', conn=None):
    try:
        target = conn
        if target is not None:
            target.execute(
                "INSERT INTO audit_logs (entity_type, entity_id, action, summary) VALUES (?, ?, ?, ?)",
                (entity_type, entity_id, action, summary),
            )
        else:
            with get_db() as target:
                target.execute(
                    "INSERT INTO audit_logs (entity_type, entity_id, action, summary) VALUES (?, ?, ?, ?)",
                    (entity_type, entity_id, action, summary),
                )
    except Exception:
        pass


def get_audit_logs(limit=50, entity_type=None, entity_id=None):
    with get_db() as conn:
        conditions = []
        params = []
        if entity_type:
            conditions.append("entity_type=?")
            params.append(entity_type)
        if entity_id is not None:
            conditions.append("entity_id=?")
            params.append(entity_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM audit_logs{where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]


def get_data_quality():
    with get_db() as conn:
        checks = []
        def count(sql, params=()):
            return conn.execute(sql, params).fetchone()[0]

        checks.append({
            "key": "zero_play_with_actions",
            "title": "播放为0但有互动",
            "count": count("""SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL AND play_count=0
                              AND (like_count>0 OR comment_count>0 OR share_count>0 OR favorite_count>0)"""),
            "level": "danger",
            "filter": "zero_play_actions",
        })
        checks.append({
            "key": "completion_over_100",
            "title": "完播率超过100%",
            "count": count("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL AND completion_rate > 100"),
            "level": "danger",
            "filter": "completion_over_100",
        })
        checks.append({
            "key": "missing_direction",
            "title": "未绑定方向",
            "count": count("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL AND direction_id IS NULL"),
            "level": "warning",
            "filter": "missing_direction",
        })
        checks.append({
            "key": "missing_account",
            "title": "未绑定账号",
            "count": count("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL AND account_id IS NULL"),
            "level": "warning",
            "filter": "missing_account",
        })
        checks.append({
            "key": "missing_material",
            "title": "无视频素材",
            "count": count("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL AND (video_path IS NULL OR video_path='')"),
            "level": "info",
            "filter": "missing_material",
        })
        checks.append({
            "key": "high_comment_no_hook",
            "title": "高评论未绑定钩子",
            "count": len(get_comment_opportunities(100)),
            "level": "warning",
            "filter": "high_comment_no_hook",
        })
        total_issues = sum(c["count"] for c in checks)
        return {"checks": checks, "total_issues": total_issues}


def get_data_quality_tasks(limit=8):
    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) "
                 "ELSE 0 END")

    def rows_for(conn, where, params=None):
        params = params or []
        rows = conn.execute(f"""
            SELECT v.id, v.title, v.play_count, v.comment_count, v.publish_date,
                   v.direction_id, v.account_id, v.interaction_hook_id, v.test_batch_id,
                   v.comment_reason, v.comment_trigger_text,
                   {rate_expr} as interaction_rate
            FROM videos v
            WHERE v.deleted_at IS NULL AND {where}
            ORDER BY v.comment_count DESC, v.play_count DESC, v.id DESC
            LIMIT ?
        """, params + [limit]).fetchall()
        return [dict(r) for r in rows]

    with get_db() as conn:
        tasks = [
            {
                "key": "missing_direction",
                "title": "补方向",
                "desc": "这些视频还没绑定运营方向，影响方向复盘和推荐。",
                "action": "绑定方向",
                "videos": rows_for(conn, "v.direction_id IS NULL"),
            },
            {
                "key": "missing_hook",
                "title": "补互动钩子",
                "desc": "评论较多但没绑定钩子，建议沉淀成可复用话术。",
                "action": "绑定钩子",
                "videos": rows_for(conn, "v.comment_count > 0 AND v.interaction_hook_id IS NULL"),
            },
            {
                "key": "missing_batch",
                "title": "补测试批次",
                "desc": "未归入测试批次，后续不方便看同一轮测试效果。",
                "action": "绑定批次",
                "videos": rows_for(conn, "v.test_batch_id IS NULL"),
            },
            {
                "key": "missing_comment_reason",
                "title": "补评论原因",
                "desc": "有评论但缺少原因总结，无法复用触发评论的方式。",
                "action": "补原因",
                "videos": rows_for(conn, "v.comment_count > 0 AND (v.comment_reason IS NULL OR v.comment_reason='')"),
            },
            {
                "key": "completion_over_100",
                "title": "修正完播率",
                "desc": "完播率超过 100%，建议一键截断到 100 后再复盘。",
                "action": "查看",
                "videos": rows_for(conn, "v.completion_rate > 100"),
            },
        ]
        return {"tasks": tasks}


def get_test_batches():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT b.*,
                   d.name as direction_name,
                   d.color as direction_color,
                   COUNT(v.id) as video_count,
                   COALESCE(ROUND(AVG(v.play_count), 0), 0) as avg_play,
                   COALESCE(ROUND(AVG(v.comment_count), 1), 0) as avg_comments,
                   COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                       THEN v.comment_count * 100.0 / v.play_count ELSE 0 END), 2), 0) as avg_comment_rate,
                   COALESCE(MAX(v.play_count), 0) as max_play,
                   COUNT(CASE WHEN v.material_status='可复用' THEN 1 END) as reusable_count,
                   COUNT(CASE WHEN v.material_status='待复盘' THEN 1 END) as review_count
            FROM test_batches b
            LEFT JOIN directions d ON b.direction_id=d.id
            LEFT JOIN videos v ON v.test_batch_id=b.id AND v.deleted_at IS NULL
            GROUP BY b.id
            ORDER BY b.id DESC
        """).fetchall()
        return [dict(r) for r in rows]


def add_test_batch(name, note='', direction_id=None, goal='', status='测试中',
                   conclusion='', next_action=''):
    with get_db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO test_batches
                   (name, note, direction_id, goal, status, conclusion, next_action)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, note, direction_id, goal, status, conclusion, next_action),
            )
            log_audit("batch", cur.lastrowid, "create", f"新增测试批次：{name}", conn)
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_test_batch(batch_id, name=None, note=None, direction_id=_UNSET,
                      goal=None, status=None, conclusion=None, next_action=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM test_batches WHERE id=?", (batch_id,)).fetchone()
        if not row:
            return False
        d = dict(row)
        conn.execute(
            """UPDATE test_batches SET name=?, note=?, direction_id=?, goal=?,
               status=?, conclusion=?, next_action=? WHERE id=?""",
            (name if name is not None else d["name"],
             note if note is not None else d.get("note", ""),
             direction_id if direction_id is not _UNSET else d.get("direction_id"),
             goal if goal is not None else d.get("goal", ""),
             status if status is not None else d.get("status", "测试中"),
             conclusion if conclusion is not None else d.get("conclusion", ""),
             next_action if next_action is not None else d.get("next_action", ""),
             batch_id),
        )
        log_audit("batch", batch_id, "update", f"更新测试批次：{name or d['name']}", conn)
        return True


def delete_test_batch(batch_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET test_batch_id=NULL WHERE test_batch_id=?", (batch_id,))
        cur = conn.execute("DELETE FROM test_batches WHERE id=?", (batch_id,))
        log_audit("batch", batch_id, "delete", f"删除测试批次：{batch_id}", conn)
        return cur.rowcount > 0


def update_video_review(video_id, material_status=None, review_summary=None,
                        reusable_point=None, failure_reason=None, next_action=None,
                        comment_reason=None, comment_trigger_text=None,
                        comment_reuse_advice=None):
    fields = {}
    for key, value in {
        "material_status": material_status,
        "review_summary": review_summary,
        "reusable_point": reusable_point,
        "failure_reason": failure_reason,
        "next_action": next_action,
        "comment_reason": comment_reason,
        "comment_trigger_text": comment_trigger_text,
        "comment_reuse_advice": comment_reuse_advice,
    }.items():
        if value is not None:
            fields[key] = value
    if not fields:
        return False
    patch_video(video_id, **fields)
    log_audit("video", video_id, "review", "更新视频复盘")
    return True


def get_review_center(limit=12):
    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) "
                 "ELSE 0 END")
    comment_rate_expr = ("CASE WHEN v.play_count > 0 "
                         "THEN ROUND(v.comment_count * 100.0 / v.play_count, 2) "
                         "ELSE 0 END")
    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT v.*, d.name as direction_name, d.color as direction_color,
                   h.name as hook_name, b.name as batch_name,
                   {rate_expr} as interaction_rate,
                   {comment_rate_expr} as comment_rate
            FROM videos v
            LEFT JOIN directions d ON v.direction_id=d.id
            LEFT JOIN interaction_hooks h ON v.interaction_hook_id=h.id
            LEFT JOIN test_batches b ON v.test_batch_id=b.id
            WHERE v.deleted_at IS NULL
            ORDER BY
                CASE
                    WHEN v.material_status='待复盘' THEN 0
                    WHEN v.comment_count >= 50 THEN 1
                    WHEN v.play_count >= 10000 THEN 2
                    WHEN v.violation_type IS NOT NULL AND v.violation_type != '' THEN 3
                    ELSE 4
                END,
                v.play_count DESC,
                v.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        status_rows = conn.execute("""
            SELECT COALESCE(NULLIF(material_status, ''), '已发布') as status, COUNT(*) as count
            FROM videos
            WHERE deleted_at IS NULL
            GROUP BY COALESCE(NULLIF(material_status, ''), '已发布')
            ORDER BY count DESC
        """).fetchall()

        reusable_rows = conn.execute(f"""
            SELECT v.*, d.name as direction_name, {rate_expr} as interaction_rate,
                   {comment_rate_expr} as comment_rate
            FROM videos v
            LEFT JOIN directions d ON v.direction_id=d.id
            WHERE v.deleted_at IS NULL
              AND (v.material_status='可复用' OR v.reusable_point != '' OR v.comment_trigger_text != '')
            ORDER BY v.play_count DESC, v.comment_count DESC
            LIMIT 8
        """).fetchall()

        return {
            "videos": [dict(r) for r in rows],
            "status_counts": [dict(r) for r in status_rows],
            "reusable_videos": [dict(r) for r in reusable_rows],
        }


def get_action_suggestions():
    suggestions = []
    with get_db() as conn:
        pending_review = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE deleted_at IS NULL
              AND (material_status='待复盘'
                   OR play_count >= 10000
                   OR comment_count >= 50)
        """).fetchone()[0]
        if pending_review:
            suggestions.append({
                "level": "high",
                "title": "优先复盘高价值视频",
                "desc": f"有 {pending_review} 条视频播放或评论表现突出，建议提炼可复用点。",
                "action": "查看复盘中心",
            })

        missing_direction = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE deleted_at IS NULL AND direction_id IS NULL
        """).fetchone()[0]
        if missing_direction:
            suggestions.append({
                "level": "medium",
                "title": "补齐方向标签",
                "desc": f"还有 {missing_direction} 条视频没有绑定方向，会影响方向决策榜。",
                "action": "去视频库筛选",
            })

        reusable = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE deleted_at IS NULL
              AND (material_status='可复用' OR reusable_point != '' OR comment_trigger_text != '')
        """).fetchone()[0]
        if reusable:
            suggestions.append({
                "level": "good",
                "title": "复用已验证素材",
                "desc": f"已沉淀 {reusable} 条可复用经验，可以优先安排同方向测试。",
                "action": "查看可复用",
            })

        violation_pending = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE deleted_at IS NULL
              AND violation_type IS NOT NULL AND violation_type != ''
              AND (violation_status IS NULL OR violation_status='' OR violation_status='pending')
        """).fetchone()[0]
        if violation_pending:
            suggestions.append({
                "level": "danger",
                "title": "处理未完成违规",
                "desc": f"有 {violation_pending} 条违规记录待处理，建议先沉淀失败原因。",
                "action": "去违规中心",
            })

    if not suggestions:
        suggestions.append({
            "level": "good",
            "title": "当前数据状态稳定",
            "desc": "可以继续录入新视频，并按批次测试新的方向和钩子。",
            "action": "继续录入",
        })
    return suggestions


def get_decision_center():
    directions = get_direction_recommendations(30)
    for d in directions:
        if d.get("status") == "已通过" and d.get("score", 0) >= 55:
            d["decision"] = "优先做"
        elif d.get("status") == "未过审":
            d["decision"] = "先停"
        elif d.get("video_count", 0) < 3:
            d["decision"] = "继续测"
        elif d.get("score", 0) >= 35:
            d["decision"] = "观察"
        else:
            d["decision"] = "降优先"
    directions.sort(key=lambda x: x.get("score", 0), reverse=True)
    review = get_review_center()
    return {
        "suggestions": get_action_suggestions(),
        "directions": directions,
        "review": review,
        "batches": get_test_batches(),
    }


def get_hook_review(hook_id):
    with get_db() as conn:
        hook = conn.execute("SELECT * FROM interaction_hooks WHERE id=?", (hook_id,)).fetchone()
        if not hook:
            return None
        rate_expr = ("CASE WHEN v.play_count > 0 THEN "
                     "ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) ELSE 0 END")
        videos = conn.execute(f"""
            SELECT v.*, {rate_expr} as interaction_rate,
                   d.name as direction_name, a.name as account_name
            FROM videos v
            LEFT JOIN directions d ON v.direction_id=d.id
            LEFT JOIN accounts a ON v.account_id=a.id
            WHERE v.deleted_at IS NULL AND v.interaction_hook_id=?
            ORDER BY v.comment_count DESC, v.play_count DESC
        """, (hook_id,)).fetchall()
        items = [dict(v) for v in videos]
        directions = {}
        accounts = {}
        for v in items:
            if v.get("direction_name"):
                directions[v["direction_name"]] = directions.get(v["direction_name"], 0) + 1
            if v.get("account_name"):
                accounts[v["account_name"]] = accounts.get(v["account_name"], 0) + 1
        hook_dict = dict(hook)
        metric = {
            "video_count": len(items),
            "avg_comment_rate": round(sum((v.get("comment_count") or 0) * 100.0 / (v.get("play_count") or 1) for v in items) / len(items), 2) if items else 0,
            "avg_comments": round(sum(v.get("comment_count") or 0 for v in items) / len(items), 1) if items else 0,
        }
        return {
            "hook": {**hook_dict, "decision": _hook_decision(metric), "effect_level": _hook_effect_level(metric)},
            "videos": items,
            "versions": get_hook_versions(hook_id),
            "best_video": items[0] if items else None,
            "directions": sorted([{"name": k, "count": v} for k, v in directions.items()], key=lambda x: x["count"], reverse=True),
            "accounts": sorted([{"name": k, "count": v} for k, v in accounts.items()], key=lambda x: x["count"], reverse=True),
        }


# --- 互动钩子库 ---

def get_interaction_hooks():
    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN (v.comment_count * 100.0 / v.play_count) "
                 "ELSE 0 END")
    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT h.*,
                   COUNT(v.id) as video_count,
                   COALESCE(ROUND(AVG(v.comment_count), 1), 0) as avg_comments,
                   COALESCE(ROUND(AVG({rate_expr}), 2), 0) as avg_comment_rate,
                   COALESCE(ROUND(AVG(v.play_count), 0), 0) as avg_play,
                   COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                       THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                       ELSE 0 END), 2), 0) as avg_interaction_rate,
                   MAX(v.comment_count) as best_comments,
                   (
                       SELECT v2.title
                       FROM videos v2
                       WHERE v2.interaction_hook_id=h.id AND v2.deleted_at IS NULL
                       ORDER BY v2.comment_count DESC, v2.play_count DESC
                       LIMIT 1
                   ) as best_video_title
            FROM interaction_hooks h
            LEFT JOIN videos v ON v.interaction_hook_id = h.id AND v.deleted_at IS NULL
            GROUP BY h.id
            ORDER BY avg_comment_rate DESC, avg_comments DESC, h.id DESC
        """).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["effect_level"] = _hook_effect_level(d)
            d["decision"] = _hook_decision(d)
            items.append(d)
        return items


def get_hook_versions(hook_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM hook_versions WHERE hook_id=? ORDER BY id DESC",
            (hook_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_hook_version(hook_id, version_name='', phrase='', note='', status='测试中'):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO hook_versions (hook_id, version_name, phrase, note, status)
               VALUES (?, ?, ?, ?, ?)""",
            (hook_id, version_name, phrase, note, status),
        )
        log_audit("hook", hook_id, "version_create", f"新增话术版本：{version_name or phrase[:20]}", conn)
        return cur.lastrowid


def delete_hook_version(version_id):
    with get_db() as conn:
        row = conn.execute("SELECT hook_id FROM hook_versions WHERE id=?", (version_id,)).fetchone()
        conn.execute("DELETE FROM hook_versions WHERE id=?", (version_id,))
        if row:
            log_audit("hook", row["hook_id"], "version_delete", "删除话术版本", conn)


def _hook_effect_level(h):
    rate = float(h.get("avg_comment_rate") or 0)
    avg = float(h.get("avg_comments") or 0)
    count = int(h.get("video_count") or 0)
    if count <= 0:
        return "待观察"
    if rate >= 5 or avg >= 500:
        return "爆款"
    if rate >= 3 or avg >= 200:
        return "优秀"
    if rate >= 1.5 or avg >= 80:
        return "良好"
    if rate >= 0.5 or avg >= 20:
        return "一般"
    return "差"


def _hook_decision(h):
    count = int(h.get("video_count") or 0)
    rate = float(h.get("avg_comment_rate") or 0)
    avg = float(h.get("avg_comments") or 0)
    if count <= 0:
        return {"label": "样本不足", "level": "muted", "reason": "还没有绑定视频，先用 1-3 条素材验证。"}
    if count < 3:
        return {"label": "继续观察", "level": "watch", "reason": f"当前只有 {count} 条样本，建议补到 3 条以上再定结论。"}
    if rate >= 5 or avg >= 500:
        return {"label": "继续复用", "level": "good", "reason": f"平均评论率 {rate}% / 均评 {avg}，优先做变体测试。"}
    if rate >= 1.5 or avg >= 80:
        return {"label": "继续观察", "level": "watch", "reason": f"有一定评论效果，平均评论率 {rate}% / 均评 {avg}。"}
    return {"label": "暂停使用", "level": "bad", "reason": f"评论表现偏弱，平均评论率 {rate}% / 均评 {avg}。"}


def add_interaction_hook(name, hook_type='评论引导', target_comment='',
                         trigger_text='', reuse_advice='', note='', status='可复用',
                         comment_type='关键词', target_action='评论', variants='',
                         applicable_directions='', bad_scenarios='', failure_reason='',
                         next_test_action=''):
    with get_db() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO interaction_hooks
                   (name, hook_type, target_comment, comment_type, target_action, variants,
                    trigger_text, reuse_advice, note, status, applicable_directions, bad_scenarios,
                    failure_reason, next_test_action)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (name, hook_type, target_comment, comment_type, target_action, variants,
                 trigger_text, reuse_advice, note, status, applicable_directions, bad_scenarios,
                 failure_reason, next_test_action),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_interaction_hook(hook_id, name=None, hook_type=None, target_comment=None,
                            trigger_text=None, reuse_advice=None, note=None, status=None,
                            comment_type=None, target_action=None, variants=None,
                            applicable_directions=None, bad_scenarios=None, failure_reason=None,
                            next_test_action=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM interaction_hooks WHERE id=?", (hook_id,)).fetchone()
        if not row:
            return False
        h = dict(row)
        conn.execute(
            """UPDATE interaction_hooks SET
               name=?, hook_type=?, target_comment=?, comment_type=?, target_action=?, variants=?, trigger_text=?,
               reuse_advice=?, note=?, status=?, applicable_directions=?, bad_scenarios=?,
               failure_reason=?, next_test_action=?, updated_at=datetime('now','localtime')
               WHERE id=?""",
            (
                name if name is not None else h.get('name', ''),
                hook_type if hook_type is not None else h.get('hook_type', '评论引导'),
                target_comment if target_comment is not None else h.get('target_comment', ''),
                comment_type if comment_type is not None else h.get('comment_type', '关键词'),
                target_action if target_action is not None else h.get('target_action', '评论'),
                variants if variants is not None else h.get('variants', ''),
                trigger_text if trigger_text is not None else h.get('trigger_text', ''),
                reuse_advice if reuse_advice is not None else h.get('reuse_advice', ''),
                note if note is not None else h.get('note', ''),
                status if status is not None else h.get('status', '可复用'),
                applicable_directions if applicable_directions is not None else h.get('applicable_directions', ''),
                bad_scenarios if bad_scenarios is not None else h.get('bad_scenarios', ''),
                failure_reason if failure_reason is not None else h.get('failure_reason', ''),
                next_test_action if next_test_action is not None else h.get('next_test_action', ''),
                hook_id,
            ),
        )
        log_audit("hook", hook_id, "update", f"更新互动钩子：{name if name is not None else h.get('name', '')}", conn)
        return True


def delete_interaction_hook(hook_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET interaction_hook_id=NULL WHERE interaction_hook_id=?", (hook_id,))
        conn.execute("DELETE FROM interaction_hooks WHERE id=?", (hook_id,))
        log_audit("hook", hook_id, "delete", "删除互动钩子", conn)


def create_hook_from_video(video_id, name=None, hook_type='评论引导'):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id=? AND deleted_at IS NULL", (video_id,)).fetchone()
        if not row:
            return None
        v = dict(row)
        hook_name = name or (v.get('comment_trigger_text') or v.get('title') or '互动钩子')[:40]
        try:
            cur = conn.execute(
                """INSERT INTO interaction_hooks
                   (name, hook_type, target_comment, comment_type, target_action, variants, trigger_text, reuse_advice, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    hook_name,
                    hook_type,
                    '',
                    '关键词',
                    '评论',
                    '',
                    v.get('comment_trigger_text') or '',
                    v.get('comment_reuse_advice') or '',
                    v.get('comment_reason') or '',
                ),
            )
            hook_id = cur.lastrowid
        except sqlite3.IntegrityError:
            existing = conn.execute("SELECT id FROM interaction_hooks WHERE name=?", (hook_name,)).fetchone()
            hook_id = existing["id"] if existing else None
        if not hook_id:
            return None
        conn.execute("UPDATE videos SET interaction_hook_id=? WHERE id=?", (hook_id, video_id))
        return hook_id


def get_hook_recommendations(direction_id=None, limit=5):
    hooks = get_interaction_hooks()
    filtered = [h for h in hooks if h.get("status") != "停用"]
    if direction_id:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT DISTINCT interaction_hook_id
                FROM videos
                WHERE direction_id=? AND interaction_hook_id IS NOT NULL AND deleted_at IS NULL
            """, (direction_id,)).fetchall()
            used_ids = {r["interaction_hook_id"] for r in rows}
        if used_ids:
            filtered = [h for h in filtered if h.get("id") in used_ids]
    return filtered[:limit]


def get_comment_opportunities(limit=10):
    with get_db() as conn:
        row = conn.execute("""
            SELECT AVG(CASE WHEN play_count > 0 THEN comment_count * 100.0 / play_count ELSE 0 END)
            FROM videos WHERE deleted_at IS NULL AND play_count > 0
        """).fetchone()
        avg_rate = float(row[0] or 0)
        rows = conn.execute("""
            SELECT id, title, play_count, comment_count, publish_date,
                   ROUND(CASE WHEN play_count > 0 THEN comment_count * 100.0 / play_count ELSE 0 END, 2) as comment_rate,
                   comment_reason, comment_trigger_text, interaction_hook_id
            FROM videos
            WHERE deleted_at IS NULL AND play_count > 0 AND comment_count >= 10
              AND (interaction_hook_id IS NULL OR interaction_hook_id = 0)
            ORDER BY comment_rate DESC, comment_count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        items = []
        threshold = max(avg_rate * 1.8, 1.0)
        for r in rows:
            d = dict(r)
            if float(d.get("comment_rate") or 0) >= threshold:
                d["avg_comment_rate"] = round(avg_rate, 2)
                items.append(d)
        return items


def batch_add_tags(video_ids, tag_ids):
    """批量给视频打标签"""
    if not video_ids or not tag_ids:
        return
    with get_db() as conn:
        for vid in video_ids:
            for tid in tag_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO video_tags (video_id, tag_id) VALUES (?, ?)",
                    (vid, tid),
                )


def batch_remove_tags(video_ids, tag_ids):
    """批量移除视频标签"""
    if not video_ids or not tag_ids:
        return
    with get_db() as conn:
        vph = ",".join("?" * len(video_ids))
        tph = ",".join("?" * len(tag_ids))
        conn.execute(
            f"DELETE FROM video_tags WHERE video_id IN ({vph}) AND tag_id IN ({tph})",
            video_ids + tag_ids,
        )


# --- CSV 导入导出 ---

def export_csv(tag_id=None, keyword=None, date_from=None, date_to=None, ids=None):
    """导出视频数据为 CSV 字符串"""
    videos = get_videos(tag_id, keyword, date_from, date_to,
                        sort_by="publish_date", order="desc", limit=99999, offset=0,
                        ids=ids)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["标题", "播放量", "点赞数", "评论数", "收藏数", "分享数", "发布日期", "发布时间", "完播率", "时长(秒)", "违规类型", "违规备注", "素材方向"])
    for v in videos:
        tag_names = "、".join(t["name"] for t in v.get("tags", []))
        writer.writerow([v["title"], v["play_count"], v["like_count"],
                         v["comment_count"], v.get("favorite_count") or 0, v["share_count"],
                         v["publish_date"] or "",
                         v.get("publish_time") or "",
                         v.get("completion_rate") or 0,
                         v.get("duration") or 0,
                         v.get("violation_type") or "",
                         v.get("violation_note") or "",
                         tag_names])
    return output.getvalue()


def import_csv(csv_text):
    """从 CSV 文本导入，返回 {success, count, errors}"""
    reader = csv.DictReader(io.StringIO(csv_text))
    count = 0
    errors = []

    # 确保标签名映射
    tag_cache = {}

    def get_or_create_tag(name):
        if name in tag_cache:
            return tag_cache[name]
        with get_db() as conn:
            row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
            if row:
                tag_cache[name] = row["id"]
            else:
                cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
                tag_cache[name] = cur.lastrowid
            return tag_cache[name]

    for i, row in enumerate(reader, 2):
        try:
            title = (row.get("标题") or row.get("title") or "").strip()
            if not title:
                errors.append(f"第{i}行：标题为空，已跳过")
                continue

            play = int(row.get("播放量") or row.get("play_count") or 0)
            like = int(row.get("点赞数") or row.get("like_count") or 0)
            comment = int(row.get("评论数") or row.get("comment_count") or 0)
            favorite = int(row.get("收藏数") or row.get("favorite_count") or 0)
            share = int(row.get("分享数") or row.get("share_count") or 0)
            date = (row.get("发布日期") or row.get("publish_date") or "").strip()
            publish_time = (row.get("发布时间") or row.get("publish_time") or "").strip()
            completion_rate = float(row.get("完播率") or row.get("completion_rate") or 0)
            duration = int(row.get("时长(秒)") or row.get("duration") or 0)
            violation_type = (row.get("违规类型") or row.get("violation_type") or "").strip()
            violation_note = (row.get("违规备注") or row.get("violation_note") or "").strip()

            tag_str = (row.get("素材方向") or row.get("tags") or "").strip()
            tag_ids = []
            if tag_str:
                for tname in tag_str.replace("、", ",").split(","):
                    tname = tname.strip()
                    if tname:
                        tag_ids.append(get_or_create_tag(tname))

            add_video(title, play, like, comment, share, date, tag_ids,
                      completion_rate=completion_rate, duration=duration,
                      publish_time=publish_time or None,
                      violation_type=violation_type, violation_note=violation_note,
                      favorite_count=favorite)
            count += 1
        except Exception as e:
            errors.append(f"第{i}行：{e}")

    return {"success": True, "count": count, "errors": errors}


def get_referenced_media_paths():
    """返回当前数据库中仍被未删除视频引用的素材路径。"""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT video_path, cover_path
            FROM videos
            WHERE deleted_at IS NULL
        """).fetchall()
        paths = set()
        for row in rows:
            for key in ("video_path", "cover_path"):
                path = row[key]
                if path:
                    paths.add(str(Path(path).resolve()))
        return paths


# --- 标签 ---

def get_all_tags():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY id").fetchall()]


def add_tag(name):
    with get_db() as conn:
        try:
            cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def delete_tag(tag_id):
    with get_db() as conn:
        conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))


# --- 违规类型 ---

def get_all_violation_types():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM violation_types ORDER BY id").fetchall()]


def add_violation_type(name):
    with get_db() as conn:
        try:
            cur = conn.execute("INSERT INTO violation_types (name) VALUES (?)", (name,))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def delete_violation_type(vt_id):
    """删除违规类型，同时清空引用它的视频的 violation_type"""
    with get_db() as conn:
        row = conn.execute("SELECT name FROM violation_types WHERE id=?", (vt_id,)).fetchone()
        if not row:
            return
        name = row["name"]
        conn.execute("DELETE FROM violation_types WHERE id=?", (vt_id,))
        conn.execute(
            "UPDATE videos SET violation_type='', violation_note='' WHERE violation_type=?",
            (name,),
        )


# --- 分析 ---

def get_tag_analysis(date_from=None, date_to=None):
    """各标签的汇总统计，支持日期范围。未打标签的视频归入"未分类"。"""
    conditions = ["v.deleted_at IS NULL"]
    params = []
    if date_from:
        conditions.append("v.publish_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("v.publish_date <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        # 有标签的视频
        rows = conn.execute(f"""
            SELECT
                t.id as tag_id,
                t.name as tag_name,
                COUNT(v.id) as video_count,
                ROUND(AVG(v.play_count), 0) as avg_play,
                ROUND(AVG(v.like_count), 0) as avg_like,
                ROUND(AVG(v.comment_count), 0) as avg_comment,
                ROUND(AVG(v.share_count), 0) as avg_share,
                ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2) as avg_interaction_rate
            FROM tags t
            JOIN video_tags vt ON t.id = vt.tag_id
            JOIN videos v ON v.id = vt.video_id
            {where}
            GROUP BY t.id, t.name
            HAVING video_count > 0
            ORDER BY avg_play DESC
        """, params).fetchall()
        result = [dict(r) for r in rows]

        # 未分类的视频（没有关联任何标签）
        untagged_where = " WHERE v.id NOT IN (SELECT video_id FROM video_tags) AND v.deleted_at IS NULL"
        untagged_params = []
        if date_from:
            untagged_where += " AND v.publish_date >= ?"
            untagged_params.append(date_from)
        if date_to:
            untagged_where += " AND v.publish_date <= ?"
            untagged_params.append(date_to)
        untagged = conn.execute(f"""
            SELECT
                -1 as tag_id,
                '未分类' as tag_name,
                COUNT(v.id) as video_count,
                ROUND(AVG(v.play_count), 0) as avg_play,
                ROUND(AVG(v.like_count), 0) as avg_like,
                ROUND(AVG(v.comment_count), 0) as avg_comment,
                ROUND(AVG(v.share_count), 0) as avg_share,
                ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2) as avg_interaction_rate
            FROM videos v
            {untagged_where}
        """, untagged_params).fetchone()
        if untagged and untagged["video_count"] > 0:
            result.append(dict(untagged))

        result.sort(key=lambda x: x["avg_play"], reverse=True)
        return result


def get_tag_trend(tag_id, date_from=None, date_to=None):
    """按月统计某个标签的播放量趋势"""
    conditions = ["vt.tag_id = ?", "v.deleted_at IS NULL"]
    params = [tag_id]
    if date_from:
        conditions.append("v.publish_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("v.publish_date <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions)

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT
                SUBSTR(v.publish_date, 1, 7) as month,
                COUNT(v.id) as video_count,
                SUM(v.play_count) as total_play,
                ROUND(AVG(v.play_count), 0) as avg_play,
                ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2) as avg_interaction_rate
            FROM videos v
            JOIN video_tags vt ON v.id = vt.video_id
            {where} AND v.publish_date IS NOT NULL AND v.publish_date != ''
            GROUP BY SUBSTR(v.publish_date, 1, 7)
            ORDER BY month
        """, params).fetchall()
        return [dict(r) for r in rows]


def get_keyword_analysis():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                v.title,
                v.play_count,
                v.like_count,
                v.comment_count,
                v.share_count,
                CASE WHEN v.play_count > 0
                    THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2)
                    ELSE 0 END as interaction_rate
            FROM videos v
            WHERE v.deleted_at IS NULL
            ORDER BY v.play_count DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_top_videos(n=10, sort_by="play_count"):
    allowed = {"play_count", "like_count", "comment_count", "favorite_count", "share_count", "interaction_rate"}
    if sort_by not in allowed:
        sort_by = "play_count"

    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN ROUND((v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count, 2) "
                 "ELSE 0 END")

    order_by = rate_expr if sort_by == "interaction_rate" else f"v.{sort_by}"

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT v.*, {rate_expr} as interaction_rate
            FROM videos v
            WHERE v.deleted_at IS NULL
            ORDER BY {order_by} DESC
            LIMIT ?
        """, (n,)).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            tag_rows = conn.execute("""
                SELECT t.id, t.name FROM tags t
                JOIN video_tags vt ON t.id = vt.tag_id
                WHERE vt.video_id = ?
            """, (r["id"],)).fetchall()
            d["tags"] = [dict(t) for t in tag_rows]
            result.append(d)

        return result


def _video_with_tags(conn, row):
    """将视频行转换为 dict 并附加标签。"""
    d = dict(row)
    tag_rows = conn.execute("""
        SELECT t.id, t.name FROM tags t
        JOIN video_tags vt ON t.id = vt.tag_id
        WHERE vt.video_id = ?
    """, (row["id"],)).fetchall()
    d["tags"] = [dict(t) for t in tag_rows]
    return d


def get_dashboard_summary():
    """获取工作台汇总数据。"""
    today = date.today().isoformat()
    rate_expr = ("CASE WHEN v.play_count > 0 "
                 "THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count "
                 "ELSE 0 END")

    with get_db() as conn:
        totals_row = conn.execute(f"""
            SELECT
                COUNT(*) as video_count,
                COALESCE(SUM(play_count), 0) as total_play,
                COALESCE(ROUND(AVG(play_count), 0), 0) as avg_play,
                COALESCE(ROUND(AVG({rate_expr}), 2), 0) as avg_interaction_rate,
                COALESCE(ROUND(AVG(completion_rate), 2), 0) as avg_completion_rate
            FROM videos v WHERE v.deleted_at IS NULL
        """).fetchone()
        tag_count = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

        # 违规统计
        violation_count = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE violation_type IS NOT NULL AND violation_type != '' AND deleted_at IS NULL"
        ).fetchone()[0]

        plan_row = conn.execute("""
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(CASE WHEN done=1 THEN 1 ELSE 0 END), 0) as done,
                COALESCE(SUM(CASE WHEN done=0 THEN 1 ELSE 0 END), 0) as pending,
                COALESCE(SUM(CASE WHEN done=0 AND priority='高' THEN 1 ELSE 0 END), 0) as high_pending
            FROM plans
            WHERE plan_date=?
        """, (today,)).fetchone()

        top_rows = conn.execute(f"""
            SELECT v.*, ROUND({rate_expr}, 2) as interaction_rate
            FROM videos v WHERE v.deleted_at IS NULL
            ORDER BY v.play_count DESC
            LIMIT 5
        """).fetchall()
        top_videos = [_video_with_tags(conn, r) for r in top_rows]

        recent_rows = conn.execute(f"""
            SELECT v.*, ROUND({rate_expr}, 2) as interaction_rate
            FROM videos v WHERE v.deleted_at IS NULL
            ORDER BY v.created_at DESC, v.id DESC
            LIMIT 5
        """).fetchall()
        recent_videos = [_video_with_tags(conn, r) for r in recent_rows]

        todo_rows = conn.execute("""
            SELECT * FROM plans
            WHERE plan_date=? AND done=0
            ORDER BY CASE priority WHEN '高' THEN 1 WHEN '中' THEN 2 ELSE 3 END,
                     time_from, id
            LIMIT 6
        """, (today,)).fetchall()
        todo_plans = [dict(r) for r in todo_rows]

    tag_stats = get_tag_analysis()
    best_tag = None
    if tag_stats:
        best_tag = max(tag_stats, key=lambda t: t.get("avg_play") or 0)

    totals = dict(totals_row)
    plan_stats = dict(plan_row)
    plan_total = plan_stats["total"] or 0
    plan_done = plan_stats["done"] or 0
    completion_rate = round(plan_done * 100 / plan_total) if plan_total else 0

    insights = []
    if not totals["video_count"]:
        insights.append("先录入视频数据，工作台会自动生成内容洞察。")
    if plan_stats["high_pending"]:
        insights.append(f"今天还有 {plan_stats['high_pending']} 个高优先任务未完成，建议先处理。")
    if best_tag:
        insights.append(f"当前表现最好的方向是 {best_tag['tag_name']}，平均播放 {int(best_tag['avg_play'] or 0)}。")
    if totals["video_count"] and (totals["avg_interaction_rate"] or 0) < 2:
        insights.append("整体互动率偏低，可以优化标题、封面和互动引导。")
    if totals["video_count"] and (totals["avg_completion_rate"] or 0) < 25:
        insights.append("平均完播率低于 25%，建议缩短视频时长或优化前 3 秒钩子。")
    if violation_count > 0:
        pct = round(violation_count * 100 / totals["video_count"])
        insights.append(f"已有 {violation_count} 条视频标记违规（占比 {pct}%），建议重点关注违规原因避免重复踩坑。")
    if not insights:
        insights.append("当前内容库运行稳定，可以继续补充数据并观察方向变化。")

    return {
        "today": today,
        "totals": {
            "video_count": totals["video_count"] or 0,
            "total_play": totals["total_play"] or 0,
            "avg_play": totals["avg_play"] or 0,
            "avg_interaction_rate": totals["avg_interaction_rate"] or 0,
            "avg_completion_rate": totals["avg_completion_rate"] or 0,
            "tag_count": tag_count or 0,
            "violation_count": violation_count or 0,
        },
        "today_plans": {
            "total": plan_total,
            "done": plan_done,
            "pending": plan_stats["pending"] or 0,
            "completion_rate": completion_rate,
            "high_pending": plan_stats["high_pending"] or 0,
        },
        "best_tag": best_tag or {
            "tag_id": None,
            "tag_name": "-",
            "avg_play": 0,
            "avg_interaction_rate": 0,
            "video_count": 0,
        },
        "top_videos": top_videos,
        "recent_videos": recent_videos,
        "todo_plans": todo_plans,
        "insights": insights,
    }


def get_cockpit_summary():
    """运营驾驶舱数据"""
    today = date.today().isoformat()
    today_7 = (date.today() - timedelta(days=7)).isoformat()
    today_14 = (date.today() - timedelta(days=14)).isoformat()

    with get_db() as conn:
        # ── 顶部卡片数据 ──
        plan_row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) as done,
                   SUM(CASE WHEN done=0 THEN 1 ELSE 0 END) as pending
            FROM plans WHERE plan_date=?
        """, (today,)).fetchone()

        plan_total = plan_row[0] or 0
        plan_done = plan_row[1] or 0
        plan_pending = plan_row[2] or 0
        completion_rate = round(plan_done / plan_total * 100) if plan_total > 0 else 0

        target_row = conn.execute(
            "SELECT COALESCE(SUM(target_count), 0) FROM plans WHERE plan_date=?",
            (today,)
        ).fetchone()
        target_count = target_row[0] or 0

        violation_today = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND (violation_status IS NULL OR violation_status = 'pending'
                   OR violation_status = '')
              AND deleted_at IS NULL
        """).fetchone()[0]

        new_today = conn.execute("""
            SELECT COUNT(*) FROM videos WHERE created_at LIKE ? || '%' AND deleted_at IS NULL
        """, (today,)).fetchone()[0]

        # ── 运营提醒 ──
        alerts = []

        # 1) 方向播放下滑（近7天 vs 前7天）
        dir_recent = conn.execute("""
            SELECT d.id, d.name, ROUND(AVG(v.play_count), 0) as avg_play
            FROM directions d
            JOIN videos v ON v.direction_id = d.id AND v.publish_date >= ? AND v.deleted_at IS NULL
            GROUP BY d.id, d.name
        """, (today_7,)).fetchall()

        dir_earlier = conn.execute("""
            SELECT d.id, ROUND(AVG(v.play_count), 0) as avg_play
            FROM directions d
            JOIN videos v ON v.direction_id = d.id
                AND v.publish_date >= ? AND v.publish_date < ? AND v.deleted_at IS NULL
            GROUP BY d.id
        """, (today_14, today_7)).fetchall()

        earlier_map = {r[0]: r[1] for r in dir_earlier}
        for r in dir_recent:
            d_id, d_name, recent_avg = r
            earlier_avg = earlier_map.get(d_id, 0)
            if earlier_avg > 0 and recent_avg < earlier_avg * 0.7:
                alerts.append({
                    "type": "direction_decline", "level": "warning",
                    "title": "播放下滑",
                    "description": f"{d_name}近7天均播{int(recent_avg)}，比上7天下降{int((1 - recent_avg/earlier_avg)*100)}%，建议复盘标题/封面",
                })

        # 2) 组今日计划完成不足
        group_rows = conn.execute("""
            SELECT g.name, COUNT(p.id) as plan_total,
                   SUM(CASE WHEN p.done=1 THEN 1 ELSE 0 END) as plan_done,
                   COALESCE(SUM(p.target_count), 0) as target_total
            FROM groups g
            JOIN plans p ON p.group_id = g.id AND p.plan_date=?
            GROUP BY g.id, g.name
            HAVING plan_done < target_total OR (target_total = 0 AND plan_done < plan_total)
        """, (today,)).fetchall()
        for gr in group_rows:
            g_name, p_total, p_done, tgt = gr
            p_done = p_done or 0
            tgt = tgt or p_total
            if tgt > 0 and p_done < tgt:
                alerts.append({
                    "type": "group_behind", "level": "warning",
                    "title": "计划进度不足",
                    "description": f"{g_name}今日目标{int(tgt)}条，仅完成{int(p_done)}条",
                })

        # 3) 违规类型频次
        violation_freq = conn.execute("""
            SELECT violation_type, COUNT(*) as cnt
            FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND publish_date >= ? AND deleted_at IS NULL
            GROUP BY violation_type
            ORDER BY cnt DESC
        """, (today_7,)).fetchall()
        for vf in violation_freq:
            v_type, cnt = vf
            if cnt >= 3:
                alerts.append({
                    "type": "violation_freq", "level": "danger",
                    "title": "违规频次偏高",
                    "description": f"{v_type}近7天出现{cnt}次，建议排查素材来源",
                })

        # 4) 高优先待办
        high_pending = conn.execute("""
            SELECT COUNT(*) FROM plans WHERE plan_date=? AND done=0 AND priority='高'
        """, (today,)).fetchone()[0]
        if high_pending > 0:
            alerts.append({
                "type": "high_pending", "level": "info",
                "title": "高优先任务待完成",
                "description": f"今天还有{high_pending}个高优先任务未完成",
            })

        # 5) 最佳发布时段
        time_rows = conn.execute("""
            SELECT
                CAST(SUBSTR(publish_time, 1, 2) AS INTEGER) as hour,
                ROUND(AVG(completion_rate), 1) as avg_cr,
                COUNT(*) as cnt
            FROM videos
            WHERE completion_rate > 0 AND publish_time IS NOT NULL AND publish_time != ''
              AND deleted_at IS NULL
            GROUP BY hour
            HAVING cnt >= 3
            ORDER BY avg_cr DESC
        """).fetchall()
        if time_rows:
            best = time_rows[0]
            hour, avg_cr, cnt = best
            if hour >= 0:
                alerts.append({
                    "type": "best_time", "level": "success",
                    "title": "最佳发布时段",
                    "description": f"{hour}:00-{hour+1}:00发布的视频完播率更高（均值{avg_cr}%，{cnt}条数据）",
                })

        # 6) 今日无计划
        if plan_total == 0:
            alerts.append({
                "type": "no_data", "level": "info",
                "title": "今日暂无计划",
                "description": "建议先制定今日运营目标，拆分到各设备和方向",
            })

    return {
        "today": today,
        "cards": {
            "completion_rate": completion_rate,
            "target_count": target_count,
            "done_count": plan_done,
            "pending_count": plan_pending,
            "violation_pending": violation_today,
            "new_today": new_today,
        },
        "alerts": alerts,
    }


def get_violation_stats(days=30):
    """违规统计：类型分布、趋势、处理效率"""
    from_date = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # 总量概览
        total = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND deleted_at IS NULL
        """).fetchone()[0]

        pending = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND (violation_status IS NULL OR violation_status = 'pending'
                   OR violation_status = '')
              AND deleted_at IS NULL
        """).fetchone()[0]

        processed = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE violation_status = 'processed' AND deleted_at IS NULL
        """).fetchone()[0]

        ignored = conn.execute("""
            SELECT COUNT(*) FROM videos
            WHERE violation_status = 'ignored' AND deleted_at IS NULL
        """).fetchone()[0]

        # 类型分布
        type_dist = conn.execute("""
            SELECT violation_type, COUNT(*) as cnt
            FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND deleted_at IS NULL
            GROUP BY violation_type
            ORDER BY cnt DESC
        """).fetchall()

        # 日趋势（近N天）
        trend = conn.execute("""
            SELECT publish_date, COUNT(*) as cnt
            FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND publish_date >= ? AND deleted_at IS NULL
            GROUP BY publish_date
            ORDER BY publish_date
        """, (from_date,)).fetchall()

        # 待处理列表（最近10条）
        pending_list = conn.execute("""
            SELECT id, title, violation_type, violation_note, publish_date, created_at
            FROM videos
            WHERE violation_type IS NOT NULL AND violation_type != ''
              AND (violation_status IS NULL OR violation_status = 'pending'
                   OR violation_status = '')
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT 10
        """).fetchall()

    return {
        "total": total,
        "pending": pending,
        "processed": processed,
        "ignored": ignored,
        "type_distribution": [{"type": r[0], "count": r[1]} for r in type_dist],
        "trend": [{"date": r[0], "count": r[1]} for r in trend],
        "pending_list": [{
            "id": r[0], "title": r[1], "violation_type": r[2],
            "violation_note": r[3], "publish_date": r[4], "created_at": r[5]
        } for r in pending_list],
    }


# --- 计划 ---

def init_plans_table():
    """创建 plans 表"""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                time_from TEXT,
                time_to TEXT,
                priority TEXT NOT NULL DEFAULT '中',
                done INTEGER NOT NULL DEFAULT 0,
                plan_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        for col in ("group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL",
                    "target_count INTEGER DEFAULT 0",
                    "video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL",
                    "account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL",
                    "status TEXT DEFAULT 'todo'"):
            try:
                conn.execute(f"ALTER TABLE plans ADD COLUMN {col}")
            except Exception:
                pass
        # 修复 status/done 不一致数据
        conn.execute("UPDATE plans SET status='done' WHERE done=1 AND status != 'done'")
        conn.execute("UPDATE plans SET status='todo', done=0 WHERE done=0 AND status='done'")
        conn.execute("UPDATE plans SET status='todo' WHERE status IS NULL")
        # plans 相关索引（在列迁移之后创建）
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_plans_plan_date ON plans(plan_date);
            CREATE INDEX IF NOT EXISTS idx_plans_group_id ON plans(group_id);
            CREATE INDEX IF NOT EXISTS idx_plans_done ON plans(done);
            CREATE INDEX IF NOT EXISTS idx_plans_account_id ON plans(account_id);
        """)


def get_plans(plan_date=None, group_id=None, account_id=None):
    """获取指定日期的计划，按 time_from 排序，包含关联视频标题和账号名"""
    with get_db() as conn:
        conditions = []
        params = []
        if plan_date:
            conditions.append("p.plan_date=?")
            params.append(plan_date)
        if group_id:
            conditions.append("p.group_id=?")
            params.append(group_id)
        if account_id:
            conditions.append("p.account_id=?")
            params.append(account_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"""SELECT p.*, v.title as video_title, a.name as account_name
                FROM plans p
                LEFT JOIN videos v ON p.video_id = v.id
                LEFT JOIN accounts a ON p.account_id = a.id
                {where}
                ORDER BY p.plan_date DESC, p.time_from, p.id""",
            params).fetchall()
        return [dict(r) for r in rows]


def add_plan(title, time_from=None, time_to=None, priority='中', plan_date=None,
             group_id=None, target_count=0, video_id=None, account_id=None):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO plans (title, time_from, time_to, priority, plan_date, group_id, target_count, video_id, account_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, time_from, time_to, priority, plan_date, group_id, target_count, video_id, account_id),
        )
        return cur.lastrowid


def update_plan(plan_id, title=None, time_from=None, time_to=None, priority=None, group_id=_UNSET, target_count=None, video_id=_UNSET, account_id=_UNSET, status=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            return False
        d = dict(row)
        conn.execute(
            """UPDATE plans SET title=?, time_from=?, time_to=?, priority=?, group_id=?, target_count=?, video_id=?, account_id=?, status=?, done=?
               WHERE id=?""",
            (title if title is not None else d['title'],
             time_from if time_from is not None else d['time_from'],
             time_to if time_to is not None else d['time_to'],
             priority if priority is not None else d['priority'],
             group_id if group_id is not _UNSET else d.get('group_id'),
             target_count if target_count is not None else d.get('target_count', 0),
             video_id if video_id is not _UNSET else d.get('video_id'),
             account_id if account_id is not _UNSET else d.get('account_id'),
             status if status is not None else d.get('status', 'todo'),
             1 if (status if status is not None else d.get('status')) == 'done' else 0,
             plan_id),
        )
        return True


def toggle_plan(plan_id):
    """循环切换计划状态: todo -> doing -> done -> todo"""
    with get_db() as conn:
        row = conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not row:
            return
        cur = dict(row).get('status') or 'todo'
        order = ['todo', 'doing', 'done']
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else 'todo'
        conn.execute("UPDATE plans SET status=?, done=CASE WHEN ?='done' THEN 1 ELSE 0 END WHERE id=?",
                     (nxt, nxt, plan_id))


def delete_plan(plan_id):
    with get_db() as conn:
        conn.execute("DELETE FROM plans WHERE id=?", (plan_id,))


def copy_plans(source_date, target_date):
    if not source_date or not target_date:
        return 0
    with get_db() as conn:
        rows = conn.execute(
            """SELECT title, time_from, time_to, priority, group_id, target_count, video_id, account_id
               FROM plans WHERE plan_date=? ORDER BY time_from, id""",
            (source_date,),
        ).fetchall()
        for row in rows:
            d = dict(row)
            conn.execute(
                """INSERT INTO plans (title, time_from, time_to, priority, plan_date, group_id, target_count, video_id, account_id, status, done)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'todo', 0)""",
                (
                    d["title"],
                    d["time_from"],
                    d["time_to"],
                    d["priority"],
                    target_date,
                    d["group_id"],
                    d["target_count"],
                    d["video_id"],
                    d["account_id"],
                ),
            )
        return len(rows)


def export_plans_txt(plan_date=None):
    """导出计划为纯文本"""
    plans = get_plans(plan_date)
    if not plans:
        return "（暂无计划）"
    priority_map = {'高': '!!!', '中': '!!', '低': '!'}
    lines = []
    header = f"计划 - {plan_date or '全部'}"
    lines.append(header)
    lines.append("=" * len(header.encode('gbk', errors='replace')))
    for p in plans:
        status = dict(p).get('status') or ('done' if p['done'] else 'todo')
        status_map = {'todo': '[ ]', 'doing': '[~]', 'done': '[x]', 'cancelled': '[-]'}
        mark = status_map.get(status, '[ ]')
        pri = priority_map.get(p['priority'], '!')
        time_str = ''
        if p['time_from'] and p['time_to']:
            time_str = f" {p['time_from']}-{p['time_to']}"
        elif p['time_from']:
            time_str = f" {p['time_from']}-"
        lines.append(f"{mark} {pri} {p['title']}{time_str}")
    return '\n'.join(lines)


# --- 方向 ---

def get_all_directions():
    with get_db() as conn:
        rows = []
        for r in conn.execute("SELECT * FROM directions ORDER BY id").fetchall():
            d = dict(r)
            if d.get('status') == '起量':
                d['status'] = '已通过'
                d['is_lift'] = 1
                d['effect_level'] = '优秀'
            if not d.get('effect_level'):
                d['effect_level'] = '优秀' if d.get('is_lift') else '待观察'
            rows.append(d)
        return rows


def add_direction(name, color='#e94560', status='待测试', tags='', note='', criteria='', is_lift=0, effect_level='待观察'):
    with get_db() as conn:
        try:
            if status == '起量':
                status = '已通过'
                is_lift = 1
                effect_level = '优秀'
            if not effect_level:
                effect_level = '优秀' if is_lift else '待观察'
            cur = conn.execute(
                "INSERT INTO directions (name, color, status, is_lift, effect_level, tags, note, criteria) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (name, color, status, 1 if is_lift else 0, effect_level, tags, note, criteria),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_direction(direction_id, name=None, color=None, status=None, tags=None, note=None, criteria=None, is_lift=None, effect_level=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM directions WHERE id=?", (direction_id,)).fetchone()
        if not row:
            return False
        d = dict(row)
        lift_value = d.get('is_lift', 0) if is_lift is None else (1 if is_lift else 0)
        status_value = status if status is not None else d.get('status', '待测试')
        if status_value == '起量':
            status_value = '已通过'
            lift_value = 1
            if effect_level is None:
                effect_level = '优秀'
        effect_value = effect_level if effect_level is not None else d.get('effect_level', '')
        if not effect_value:
            effect_value = '优秀' if lift_value else '待观察'
        lift_value = 1 if effect_value in ('优秀', '爆款') else 0
        conn.execute(
            "UPDATE directions SET name=?, color=?, status=?, is_lift=?, effect_level=?, tags=?, note=?, criteria=? WHERE id=?",
            (name if name is not None else d['name'],
             color if color is not None else d['color'],
             status_value,
             lift_value,
             effect_value,
             tags if tags is not None else d.get('tags', ''),
             note if note is not None else d.get('note', ''),
             criteria if criteria is not None else d.get('criteria', ''),
             direction_id),
        )
        return True


def delete_direction(direction_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET direction_id=NULL WHERE direction_id=?", (direction_id,))
        conn.execute("UPDATE groups SET direction_id=NULL WHERE direction_id=?", (direction_id,))
        conn.execute("UPDATE accounts SET direction_id=NULL WHERE direction_id=?", (direction_id,))
        conn.execute("DELETE FROM directions WHERE id=?", (direction_id,))


# --- 设备组 ---

def get_all_groups():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT g.*, d.name as direction_name, d.color as direction_color
            FROM groups g
            LEFT JOIN directions d ON g.direction_id = d.id
            ORDER BY g.id
        """).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["phone_count"] = len([p for p in (d.get("phone_list") or "").split(",") if p.strip()])
            result.append(d)
        return result


def add_group(name, direction_id=None, phone_list=''):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO groups (name, direction_id, phone_list) VALUES (?, ?, ?)",
                (name, direction_id, phone_list),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_group(group_id, name=None, direction_id=_UNSET, phone_list=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
        if not row:
            return False
        d = dict(row)
        conn.execute(
            "UPDATE groups SET name=?, direction_id=?, phone_list=? WHERE id=?",
            (name if name is not None else d['name'],
             direction_id if direction_id is not _UNSET else d['direction_id'],
             phone_list if phone_list is not None else d['phone_list'],
             group_id),
        )
        return True


def delete_group(group_id):
    with get_db() as conn:
        conn.execute("UPDATE videos SET group_id=NULL WHERE group_id=?", (group_id,))
        conn.execute("UPDATE plans SET group_id=NULL WHERE group_id=?", (group_id,))
        conn.execute("UPDATE accounts SET group_id=NULL WHERE group_id=?", (group_id,))
        conn.execute("DELETE FROM groups WHERE id=?", (group_id,))


# --- 账号 CRUD ---

def get_all_accounts():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT a.*, d.name as direction_name, d.color as direction_color,
                   g.name as group_name
            FROM accounts a
            LEFT JOIN directions d ON a.direction_id = d.id
            LEFT JOIN groups g ON a.group_id = g.id
            ORDER BY a.id DESC
        """).fetchall()
        return [dict(r) for r in rows]


def add_account(name, platform='抖音', direction_id=None, group_id=None,
                status='运营中', note=''):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO accounts (name, platform, direction_id, group_id, status, note) VALUES (?, ?, ?, ?, ?, ?)",
                (name, platform, direction_id, group_id, status, note),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_account(account_id, name=None, platform=None, direction_id=_UNSET,
                   group_id=_UNSET, status=None, note=None):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            return False
        d = dict(row)
        conn.execute(
            """UPDATE accounts SET name=?, platform=?, direction_id=?, group_id=?, status=?, note=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
            (name if name is not None else d['name'],
             platform if platform is not None else d['platform'],
             direction_id if direction_id is not _UNSET else d['direction_id'],
             group_id if group_id is not _UNSET else d['group_id'],
             status if status is not None else d['status'],
             note if note is not None else d['note'],
             account_id),
        )
        return True


def delete_account(account_id):
    """停用账号（改为弃用状态），不真删"""
    with get_db() as conn:
        conn.execute("UPDATE accounts SET status='弃用', updated_at=datetime('now','localtime') WHERE id=?", (account_id,))


def get_account_stats():
    """每个账号的基础统计"""
    today = date.today().isoformat()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                a.id as account_id, a.name, a.platform, a.status,
                a.direction_id, a.group_id,
                d.name as direction_name,
                g.name as group_name,
                COUNT(v.id) as video_count,
                COALESCE(SUM(v.play_count), 0) as total_play,
                COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2), 0) as avg_interaction_rate,
                COALESCE(ROUND(AVG(v.completion_rate), 1), 0) as avg_completion_rate,
                COUNT(CASE WHEN v.violation_type IS NOT NULL AND v.violation_type != '' THEN 1 END) as violation_count,
                COUNT(CASE WHEN p.plan_date = ? AND p.account_id = a.id THEN 1 END) as today_plan_count,
                COUNT(CASE WHEN p.plan_date = ? AND p.account_id = a.id AND (p.status = 'done' OR p.done = 1) THEN 1 END) as today_done_count
            FROM accounts a
            LEFT JOIN directions d ON a.direction_id = d.id
            LEFT JOIN groups g ON a.group_id = g.id
            LEFT JOIN videos v ON v.account_id = a.id AND v.deleted_at IS NULL
            LEFT JOIN plans p ON p.account_id = a.id
            GROUP BY a.id
            ORDER BY a.id DESC
        """, (today, today)).fetchall()
        return [dict(r) for r in rows]


# --- 矩阵分析 ---

def get_direction_analysis(date_from=None, date_to=None):
    """按方向汇总统计，未分配方向的视频归入"未分配"。"""
    conditions = ["v.deleted_at IS NULL"]
    params = []
    if date_from:
        conditions.append("v.publish_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("v.publish_date <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT
                d.id as direction_id,
                d.name as direction_name,
                d.color as direction_color,
                COUNT(v.id) as video_count,
                COALESCE(ROUND(AVG(v.play_count), 0), 0) as avg_play,
                COALESCE(ROUND(AVG(v.like_count), 0), 0) as avg_like,
                COALESCE(ROUND(AVG(v.comment_count), 0), 0) as avg_comment,
                COALESCE(ROUND(AVG(v.share_count), 0), 0) as avg_share,
                COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2), 0) as avg_interaction_rate
            FROM directions d
            LEFT JOIN videos v ON v.direction_id = d.id
            {where.replace('v.', 'v.')}
            GROUP BY d.id, d.name, d.color
            ORDER BY avg_play DESC
        """, params).fetchall()
        result = [dict(r) for r in rows]

        # 未分配方向的视频
        unassigned_where = " WHERE v.direction_id IS NULL AND v.deleted_at IS NULL"
        unassigned_params = []
        if date_from:
            unassigned_where += " AND v.publish_date >= ?"
            unassigned_params.append(date_from)
        if date_to:
            unassigned_where += " AND v.publish_date <= ?"
            unassigned_params.append(date_to)
        unassigned = conn.execute(f"""
            SELECT
                -1 as direction_id,
                '未分配' as direction_name,
                '#888' as direction_color,
                COUNT(v.id) as video_count,
                COALESCE(ROUND(AVG(v.play_count), 0), 0) as avg_play,
                COALESCE(ROUND(AVG(v.like_count), 0), 0) as avg_like,
                COALESCE(ROUND(AVG(v.comment_count), 0), 0) as avg_comment,
                COALESCE(ROUND(AVG(v.share_count), 0), 0) as avg_share,
                COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2), 0) as avg_interaction_rate
            FROM videos v
            {unassigned_where}
        """, unassigned_params).fetchone()
        if unassigned and unassigned["video_count"] > 0:
            result.append(dict(unassigned))

        result.sort(key=lambda x: x["avg_play"] or 0, reverse=True)
        return result


def get_direction_recommendations(days=30):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                d.id as direction_id,
                d.name as direction_name,
                d.color as direction_color,
                COALESCE(d.status, '待测试') as status,
                COALESCE(d.is_lift, 0) as is_lift,
                COALESCE(d.effect_level, CASE WHEN COALESCE(d.is_lift, 0)=1 THEN '优秀' ELSE '待观察' END) as effect_level,
                COALESCE(d.tags, '') as tags,
                COALESCE(d.note, '') as note,
                COALESCE(d.criteria, '') as criteria,
                COUNT(v.id) as video_count,
                COALESCE(ROUND(AVG(v.play_count), 0), 0) as avg_play,
                COALESCE(MAX(v.play_count), 0) as max_play,
                COALESCE(ROUND(AVG(v.completion_rate), 2), 0) as avg_completion_rate,
                COALESCE(ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2), 0) as avg_interaction_rate,
                COUNT(CASE WHEN v.play_count >= 10000 THEN 1 END) as lift_video_count,
                COUNT(CASE WHEN v.violation_type IS NOT NULL AND v.violation_type != '' THEN 1 END) as violation_count
            FROM directions d
            LEFT JOIN videos v ON v.direction_id = d.id
                AND v.deleted_at IS NULL
                AND (v.publish_date IS NULL OR v.publish_date >= date('now', ?))
            GROUP BY d.id
        """, (f"-{int(days)} day",)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            score = (
                min((d["avg_play"] or 0) / 1000, 40)
                + min((d["avg_interaction_rate"] or 0) * 4, 25)
                + min((d["avg_completion_rate"] or 0) / 2, 20)
                + min((d["lift_video_count"] or 0) * 5, 15)
                - min((d["violation_count"] or 0) * 4, 20)
            )
            if d["status"] == "已通过":
                score += 8
            effect_bonus = {"无效": -10, "一般": 0, "良好": 5, "优秀": 10, "爆款": 18}.get(d.get("effect_level"), 0)
            score += effect_bonus
            if d["status"] in ("未过审", "淘汰", "暂停"):
                score -= 12
            d["score"] = round(max(score, 0), 1)
            result.append(d)
        return result


def get_direction_trend(direction_id, date_from=None, date_to=None, granularity='month'):
    """按日/周/月统计某个方向的表现趋势"""
    conditions = ["v.direction_id = ?", "v.deleted_at IS NULL"]
    params = [direction_id]
    if date_from:
        conditions.append("v.publish_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("v.publish_date <= ?")
        params.append(date_to)
    where = " WHERE " + " AND ".join(conditions)
    bucket_expr = {
        "day": "v.publish_date",
        "week": "strftime('%Y-W%W', v.publish_date)",
        "month": "SUBSTR(v.publish_date, 1, 7)",
    }.get(granularity, "SUBSTR(v.publish_date, 1, 7)")

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT
                {bucket_expr} as period,
                COUNT(v.id) as video_count,
                SUM(v.play_count) as total_play,
                ROUND(AVG(v.play_count), 0) as avg_play,
                ROUND(AVG(v.completion_rate), 2) as avg_completion_rate,
                ROUND(AVG(CASE WHEN v.play_count > 0
                    THEN (v.like_count + v.comment_count + v.share_count + COALESCE(v.favorite_count, 0)) * 100.0 / v.play_count
                    ELSE 0 END), 2) as avg_interaction_rate
            FROM videos v
            {where} AND v.publish_date IS NOT NULL AND v.publish_date != ''
            GROUP BY {bucket_expr}
            ORDER BY period
        """, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["month"] = d["period"]
            result.append(d)
        return result


def get_matrix_summary():
    """矩阵运营总览数据"""
    today = date.today().isoformat()
    with get_db() as conn:
        directions = [dict(r) for r in conn.execute("SELECT * FROM directions ORDER BY id").fetchall()]
        groups = get_all_groups()

        total_phones = sum(g.get("phone_count", 0) for g in groups)

        # 各方向的视频统计
        dir_stats = conn.execute("""
            SELECT d.id, d.name, d.color, COUNT(v.id) as video_count,
                   COALESCE(SUM(v.play_count), 0) as total_play
            FROM directions d
            LEFT JOIN videos v ON v.direction_id = d.id AND v.deleted_at IS NULL
            GROUP BY d.id, d.name, d.color
            ORDER BY d.id
        """).fetchall()
        direction_stats = [dict(r) for r in dir_stats]

        # 各组的视频统计
        grp_stats = conn.execute("""
            SELECT g.id, g.name, d.name as direction_name, d.color as direction_color,
                   COUNT(v.id) as video_count,
                   COALESCE(SUM(v.play_count), 0) as total_play
            FROM groups g
            LEFT JOIN directions d ON g.direction_id = d.id
            LEFT JOIN videos v ON v.group_id = g.id AND v.deleted_at IS NULL
            GROUP BY g.id, g.name, d.name, d.color
            ORDER BY g.id
        """).fetchall()
        group_stats = [dict(r) for r in grp_stats]

        # 已分配方向的视频占比
        total_videos = conn.execute("SELECT COUNT(*) FROM videos WHERE deleted_at IS NULL").fetchone()[0]
        assigned_videos = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE direction_id IS NOT NULL AND deleted_at IS NULL"
        ).fetchone()[0]
        assigned_rate = round(assigned_videos * 100 / total_videos) if total_videos else 0

        # 最佳方向
        best_dir = None
        if direction_stats:
            active = [d for d in direction_stats if d["video_count"] > 0]
            if active:
                best_dir = max(active, key=lambda x: x["total_play"] or 0)

        # ── 今日计划统计（按组） ──
        group_plan_rows = conn.execute("""
            SELECT g.id as group_id, g.name as group_name,
                   COUNT(p.id) as plan_total,
                   COALESCE(SUM(CASE WHEN p.done=1 THEN 1 ELSE 0 END), 0) as plan_done,
                   COALESCE(SUM(p.target_count), 0) as target_total
            FROM groups g
            LEFT JOIN plans p ON p.group_id = g.id AND p.plan_date=?
            GROUP BY g.id, g.name
            ORDER BY g.id
        """, (today,)).fetchall()
        group_plan_stats = [dict(r) for r in group_plan_rows]

        # 按方向统计计划
        dir_plan_rows = conn.execute("""
            SELECT d.id as direction_id, d.name as direction_name,
                   COUNT(p.id) as plan_total,
                   COALESCE(SUM(CASE WHEN p.done=1 THEN 1 ELSE 0 END), 0) as plan_done,
                   COALESCE(SUM(p.target_count), 0) as target_total
            FROM directions d
            LEFT JOIN groups g ON g.direction_id = d.id
            LEFT JOIN plans p ON p.group_id = g.id AND p.plan_date=?
            GROUP BY d.id, d.name
            ORDER BY d.id
        """, (today,)).fetchall()
        direction_plan_stats = [dict(r) for r in dir_plan_rows]

        # 未分配组的计划
        ungrouped_plan = conn.execute("""
            SELECT COUNT(*) as plan_total,
                   COALESCE(SUM(CASE WHEN done=1 THEN 1 ELSE 0 END), 0) as plan_done,
                   COALESCE(SUM(target_count), 0) as target_total
            FROM plans WHERE plan_date=? AND group_id IS NULL
        """, (today,)).fetchone()

        # 今日总计划
        today_plan_total = conn.execute(
            "SELECT COUNT(*) FROM plans WHERE plan_date=?", (today,)
        ).fetchone()[0]
        today_plan_done = conn.execute(
            "SELECT COUNT(*) FROM plans WHERE plan_date=? AND done=1", (today,)
        ).fetchone()[0]
        today_target_total = conn.execute(
            "SELECT COALESCE(SUM(target_count), 0) FROM plans WHERE plan_date=?", (today,)
        ).fetchone()[0]

    return {
        "overview": {
            "total_directions": len(directions),
            "total_groups": len(groups),
            "total_phones": total_phones,
            "assigned_rate": assigned_rate,
        },
        "directions": directions,
        "groups": groups,
        "direction_stats": direction_stats,
        "group_stats": group_stats,
        "best_direction": best_dir,
        "group_plan_stats": group_plan_stats,
        "direction_plan_stats": direction_plan_stats,
        "ungrouped_plan": dict(ungrouped_plan) if ungrouped_plan else {"plan_total": 0, "plan_done": 0, "target_total": 0},
        "today_plans": {"total": today_plan_total, "done": today_plan_done, "target_total": today_target_total},
    }


def get_matrix_health():
    """矩阵健康评分：各组/方向的综合健康评估"""
    today = date.today().isoformat()
    today_7 = (date.today() - timedelta(days=7)).isoformat()

    with get_db() as conn:
        groups = conn.execute("SELECT id, name, direction_id FROM groups ORDER BY id").fetchall()
        directions = conn.execute("SELECT id, name FROM directions ORDER BY id").fetchall()

        group_health = []
        for g in groups:
            gid = g['id']
            # 计划完成率（近7天）
            plan_row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN done=1 THEN 1 ELSE 0 END) as done_cnt,
                       COALESCE(SUM(target_count), 0) as targets
                FROM plans WHERE group_id=? AND plan_date>=?
            """, (gid, today_7)).fetchone()
            plan_total = plan_row[0] or 0
            plan_done = plan_row[1] or 0
            plan_score = round(plan_done / plan_total * 100) if plan_total > 0 else 50

            # 违规率（近7天）
            v_total = conn.execute("""
                SELECT COUNT(*) FROM videos WHERE group_id=? AND publish_date>=? AND deleted_at IS NULL
            """, (gid, today_7)).fetchone()[0]
            v_violation = conn.execute("""
                SELECT COUNT(*) FROM videos
                WHERE group_id=? AND publish_date>=?
                  AND violation_type IS NOT NULL AND violation_type != ''
                  AND deleted_at IS NULL
            """, (gid, today_7)).fetchone()[0]
            violation_rate = round(v_violation / v_total * 100) if v_total > 0 else 0
            violation_score = max(0, 100 - violation_rate * 20)  # 每次违规扣20分

            # 平均互动率
            avg_ir = conn.execute("""
                SELECT COALESCE(AVG(
                    CASE WHEN play_count > 0
                    THEN ROUND((like_count + comment_count + share_count + COALESCE(favorite_count, 0)) * 100.0 / play_count, 2)
                    ELSE 0 END
                ), 0) FROM videos
                WHERE group_id=? AND publish_date>=? AND deleted_at IS NULL
            """, (gid, today_7)).fetchone()[0]
            interaction_score = min(100, round(avg_ir * 10))  # 10%互动率=满分

            # 产出量（近7天视频数）
            output_score = min(100, v_total * 14)  # 7条=满分

            # 综合评分（加权平均）
            health_score = round(plan_score * 0.35 + violation_score * 0.25 +
                                 interaction_score * 0.25 + output_score * 0.15)
            health_score = max(0, min(100, health_score))

            if health_score >= 80:
                level = "优秀"
                color = "#16a34a"
            elif health_score >= 60:
                level = "良好"
                color = "#3b82f6"
            elif health_score >= 40:
                level = "一般"
                color = "#f59e0b"
            else:
                level = "需改善"
                color = "#dc2626"

            group_health.append({
                "id": gid, "name": g['name'],
                "direction_id": g['direction_id'],
                "health_score": health_score, "level": level, "color": color,
                "plan_score": plan_score, "plan_total": plan_total, "plan_done": plan_done,
                "violation_score": round(violation_score),
                "violation_count": v_violation, "video_count": v_total,
                "interaction_score": round(interaction_score),
                "avg_interaction_rate": round(avg_ir, 2),
                "output_score": round(output_score),
            })

        # 方向级汇总
        dir_health = []
        for d in directions:
            did = d['id']
            dir_groups = [gh for gh in group_health if gh['direction_id'] == did]
            if not dir_groups:
                continue
            avg_health = round(sum(g['health_score'] for g in dir_groups) / len(dir_groups))
            total_videos = sum(g['video_count'] for g in dir_groups)
            total_violations = sum(g['violation_count'] for g in dir_groups)

            if avg_health >= 80:
                level, color = "优秀", "#16a34a"
            elif avg_health >= 60:
                level, color = "良好", "#3b82f6"
            elif avg_health >= 40:
                level, color = "一般", "#f59e0b"
            else:
                level, color = "需改善", "#dc2626"

            dir_health.append({
                "id": did, "name": d['name'],
                "health_score": avg_health, "level": level, "color": color,
                "group_count": len(dir_groups),
                "total_videos": total_videos,
                "total_violations": total_violations,
                "groups": dir_groups,
            })

        # 整体健康评分
        overall = round(sum(g['health_score'] for g in group_health) / len(group_health)) if group_health else 0

    return {
        "overall_score": overall,
        "overall_level": "优秀" if overall >= 80 else "良好" if overall >= 60 else "一般" if overall >= 40 else "需改善",
        "groups": group_health,
        "directions": dir_health,
    }


def get_publish_time_analysis(days=30):
    """发布时间分析：按小时/星期统计播放量、互动率、完播率"""
    from_date = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # 按小时分析
        hourly = conn.execute("""
            SELECT
                CAST(SUBSTR(publish_time, 1, 2) AS INTEGER) as hour,
                COUNT(*) as cnt,
                COALESCE(ROUND(AVG(play_count), 0), 0) as avg_play,
                COALESCE(AVG(CASE WHEN play_count > 0
                    THEN ROUND((like_count + comment_count + share_count + COALESCE(favorite_count, 0)) * 100.0 / play_count, 2)
                    ELSE 0 END), 0) as avg_ir,
                COALESCE(AVG(completion_rate), 0) as avg_cr
            FROM videos
            WHERE publish_time IS NOT NULL AND publish_time != ''
              AND publish_date >= ? AND deleted_at IS NULL
            GROUP BY hour
            ORDER BY hour
        """, (from_date,)).fetchall()

        # 按星期分析
        weekday = conn.execute("""
            SELECT
                CASE CAST(strftime('%w', publish_date) AS INTEGER)
                    WHEN 0 THEN '周日' WHEN 1 THEN '周一' WHEN 2 THEN '周二'
                    WHEN 3 THEN '周三' WHEN 4 THEN '周四' WHEN 5 THEN '周五' WHEN 6 THEN '周六'
                END as day_name,
                CAST(strftime('%w', publish_date) AS INTEGER) as day_num,
                COUNT(*) as cnt,
                COALESCE(ROUND(AVG(play_count), 0), 0) as avg_play,
                COALESCE(AVG(CASE WHEN play_count > 0
                    THEN ROUND((like_count + comment_count + share_count + COALESCE(favorite_count, 0)) * 100.0 / play_count, 2)
                    ELSE 0 END), 0) as avg_ir
            FROM videos
            WHERE publish_date >= ? AND deleted_at IS NULL
            GROUP BY day_name, day_num
            ORDER BY day_num
        """, (from_date,)).fetchall()

        # 最佳时段
        best_hour = None
        best_cr = 0
        for r in hourly:
            if r[0] is not None and r[4] > best_cr:
                best_hour = r[0]
                best_cr = r[4]

        best_play_hour = None
        best_play = 0
        for r in hourly:
            if r[0] is not None and r[2] > best_play:
                best_play_hour = r[0]
                best_play = r[2]

    return {
        "hourly": [{"hour": r[0], "count": r[1], "avg_play": r[2], "avg_ir": r[3], "avg_cr": r[4]}
                   for r in hourly if r[0] is not None],
        "weekday": [{"day": r[0], "count": r[1], "avg_play": r[2], "avg_ir": r[3]}
                    for r in weekday],
        "best_completion_hour": best_hour,
        "best_completion_rate": best_cr,
        "best_play_hour": best_play_hour,
        "best_play_avg": best_play,
        "tips": _generate_time_tips(hourly, weekday, best_hour, best_play_hour),
    }


def _generate_time_tips(hourly, weekday, best_cr_hour, best_play_hour):
    """生成发布时间洞察"""
    tips = []

    # 有数据量>=3的时段才给出建议
    significant_hours = [(r[0], r[1], r[2], r[4]) for r in hourly if r[0] is not None and r[1] >= 3]

    if significant_hours:
        # 完播率最佳
        if best_cr_hour is not None:
            tips.append(f"{best_cr_hour}:00-{best_cr_hour+1}:00 完播率最高，建议将高质量内容安排在此时段发布")

        # 播放量最佳
        if best_play_hour is not None:
            tips.append(f"{best_play_hour}:00-{best_play_hour+1}:00 播放量最佳，适合发布有潜力冲量的内容")

        # 低谷时段
        low_hours = [(h, cnt) for h, cnt, _, _ in significant_hours if cnt >= 3]
        if len(low_hours) >= 3:
            avg_cnt = sum(c for _, c in low_hours) / len(low_hours)
            lows = [f"{h}:00" for h, c in low_hours if c < avg_cnt * 0.5]
            if lows:
                tips.append(f"低谷时段: {', '.join(lows)}，该时段发布效果较差，可避开")

    # 星期分析
    significant_days = [(r[0], r[1], r[2]) for r in weekday if r[1] >= 2]
    if significant_days:
        best_day = max(significant_days, key=lambda x: x[2])
        worst_day = min(significant_days, key=lambda x: x[2])
        if best_day[0] != worst_day[0]:
            tips.append(f"{best_day[0]}发布效果最好（均播{best_day[2]}），{worst_day[0]}效果最差（均播{worst_day[2]}）")

    return tips


def global_search(keyword, limit=8):
    q = (keyword or "").strip()
    if not q:
        return {"videos": [], "directions": [], "hooks": [], "plans": [], "accounts": []}
    like = f"%{q}%"
    with get_db() as conn:
        rate_expr = ("CASE WHEN play_count > 0 THEN "
                     "ROUND((like_count + comment_count + share_count + COALESCE(favorite_count, 0)) * 100.0 / play_count, 2) "
                     "ELSE 0 END")
        videos = conn.execute(f"""
            SELECT id, title, play_count, comment_count, publish_date, {rate_expr} as interaction_rate
            FROM videos
            WHERE deleted_at IS NULL AND (
                title LIKE ? OR comment_reason LIKE ? OR comment_trigger_text LIKE ? OR comment_reuse_advice LIKE ?
            )
            ORDER BY play_count DESC, id DESC
            LIMIT ?
        """, (like, like, like, like, limit)).fetchall()
        directions = conn.execute("""
            SELECT id, name, status, effect_level, tags, note
            FROM directions
            WHERE name LIKE ? OR tags LIKE ? OR note LIKE ? OR criteria LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (like, like, like, like, limit)).fetchall()
        hooks = conn.execute("""
            SELECT id, name, status, target_comment, trigger_text, reuse_advice, applicable_directions, next_test_action
            FROM interaction_hooks
            WHERE name LIKE ? OR target_comment LIKE ? OR trigger_text LIKE ? OR variants LIKE ?
               OR applicable_directions LIKE ? OR next_test_action LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (like, like, like, like, like, like, limit)).fetchall()
        plans = conn.execute("""
            SELECT id, title, plan_date, priority, status
            FROM plans
            WHERE title LIKE ?
            ORDER BY plan_date DESC, id DESC
            LIMIT ?
        """, (like, limit)).fetchall()
        accounts = conn.execute("""
            SELECT id, name, platform, status, note
            FROM accounts
            WHERE name LIKE ? OR platform LIKE ? OR note LIKE ?
            ORDER BY id DESC
            LIMIT ?
        """, (like, like, like, limit)).fetchall()
        return {
            "videos": [dict(r) for r in videos],
            "directions": [dict(r) for r in directions],
            "hooks": [dict(r) for r in hooks],
            "plans": [dict(r) for r in plans],
            "accounts": [dict(r) for r in accounts],
        }
