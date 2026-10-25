"""
Assignment Tracker — Executive Edition
Features:
- Animated JS/CSS Real-Time Countdown Undo Banner (Auto-dismisses on expiration)
- Modern Linear/Vercel Dark UI Theme (Pro typography, subtle borders, micro-capsule badges)
- Real-Time Clock Integration (America/New_York EDT lock)
- Pre-Due-Date AI Scheduling: All tasks & test prep finish BEFORE due date
- Smart duration parser handling ranges (e.g., '10-20 mins/day' -> 15 mins)
- Multi-tenant Neon PostgreSQL storage with isolated user accounts
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, date, timedelta, time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text


# Timezone helper for Simsbury/Eastern Time
def get_local_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.utcnow() - timedelta(hours=4)


# -----------------------
# Streamlit Page Config & Professional CSS Overrides
# -----------------------
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* Global Typography & Deep Charcoal Canvas */
    html, body, .stApp {
        background-color: #030712 !important;
        color: #f3f4f6 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .main .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px;
    }

    /* Hide Streamlit Header, Footer, and Chrome */
    #MainMenu, header, footer {visibility: hidden;}
    div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}
    section[data-testid="stSidebar"], div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] {display: none !important;}

    /* Tab Navigation — Minimal Underline Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: transparent;
        border-bottom: 1px solid #1f2937;
        margin-bottom: 24px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 6px;
        color: #9ca3af;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 6px 16px;
        background-color: transparent;
        border: none;
    }

    .stTabs [aria-selected="true"] {
        background-color: #111827 !important;
        color: #f9fafb !important;
        border: 1px solid #374151 !important;
    }

    /* Professional Card Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0b0f19 !important;
        border: 1px solid #1f293d !important;
        border-radius: 10px !important;
        padding: 16px !important;
        margin-bottom: 14px !important;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    }

    /* Headers & Text Elements */
    .app-title {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f9fafb;
        letter-spacing: -0.03em;
        margin: 0;
    }

    .app-subtitle {
        font-size: 0.82rem;
        color: #6b7280;
        margin-top: 2px;
    }

    .date-banner {
        background-color: #0b0f19;
        border: 1px solid #1f293d;
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #9ca3af;
        text-align: right;
    }

    /* Micro Badges & Chips */
    .course-chip {
        background-color: #172554;
        color: #60a5fa;
        border: 1px solid #1e40af;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        display: inline-block;
    }

    .prio-high { color: #f87171; font-weight: 600; font-size: 0.75rem; }
    .prio-medium { color: #fbbf24; font-weight: 600; font-size: 0.75rem; }
    .prio-low { color: #34d399; font-weight: 600; font-size: 0.75rem; }

    .slot-badge {
        background: #111827;
        color: #38bdf8;
        border: 1px solid #1e293b;
        padding: 3px 8px;
        border-radius: 5px;
        font-family: monospace;
        font-size: 0.78rem;
        font-weight: 600;
    }

    /* AI Day Card Layout */
    .ai-day-card {
        background-color: #0b0f19;
        border: 1px solid #1f293d;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }

    .ai-day-title {
        color: #e5e7eb;
        font-size: 0.92rem;
        font-weight: 700;
        margin-bottom: 10px;
        border-bottom: 1px solid #111827;
        padding-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .busy-text {
        color: #6b7280;
        font-size: 0.78rem;
        margin-bottom: 8px;
    }

    /* Animated CSS Undo Banner */
    .undo-toast-box {
        position: relative;
        background-color: #0f172a;
        border: 1px solid #3b82f6;
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 16px;
        overflow: hidden;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .undo-progress-bar {
        position: absolute;
        bottom: 0;
        left: 0;
        height: 3px;
        background-color: #3b82f6;
        width: 100%;
        animation: countdown-anim 15s linear forwards;
    }

    @keyframes countdown-anim {
        from { width: 100%; }
        to { width: 0%; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------
# Streamlit Helpers & Dialog Decorator
# -----------------------
def safe_rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"):
    dialog_decorator = st.experimental_dialog
else:
    def dialog_decorator(title: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                st.subheader(title)
                return func(*args, **kwargs)
            return wrapper
        return decorator


DEFAULT_DOMAIN = "@simsburyschools.net"
STATUS_OPTIONS = ["Not Started", "In Progress", "Done"]
TYPE_OPTIONS = ["Homework", "Essay", "Presentation", "Test & Quizzes", "Other"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# -----------------------
# Database Engine Initialization
# -----------------------
def get_connection_url() -> str:
    url = ""
    if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        url = st.secrets["postgres"]["url"]
    elif "connections" in st.secrets and "neon" in st.secrets["connections"]:
        url = st.secrets["connections"]["neon"]["url"]
    else:
        raise ValueError("Missing PostgreSQL database URL in secrets configuration.")

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@st.cache_resource
def get_db_engine():
    db_url = get_connection_url()
    return create_engine(db_url, pool_pre_ping=True)


engine = get_db_engine()


def init_db():
    sql_users = text("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    sql_assignments = text("""
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            course TEXT,
            due_date TEXT,
            status TEXT,
            priority INTEGER,
            atype TEXT,
            eta TEXT,
            notes TEXT,
            created_at TEXT
        );
    """)
    with engine.begin() as conn:
        conn.execute(sql_users)
        conn.execute(sql_assignments)


try:
    init_db()
except Exception as e:
    st.error(f"Database Connection Error: {e}")


# -----------------------
# Helper Utilities
# -----------------------
def priority_to_label(val: Any) -> str:
    if pd.isna(val) or val is None:
        return "Medium"
    if isinstance(val, (int, float)):
        val_int = int(val)
        if val_int <= 3:
            return "Low"
        elif val_int <= 7:
            return "Medium"
        else:
            return "High"
    val_str = str(val).strip().title()
    if val_str in PRIORITY_OPTIONS:
        return val_str
    if val_str.isdigit():
        return priority_to_label(int(val_str))
    return "Medium"


def priority_to_int(label: str) -> int:
    mapping = {"Low": 2, "Medium": 5, "High": 9}
    return mapping.get(label, 5)


def parse_eta_to_mins(eta_raw: Any) -> int:
    if not eta_raw or pd.isna(eta_raw):
        return 30
    s = str(eta_raw).lower().strip()
    if not s:
        return 30

    nums = [int(n) for n in re.findall(r"\d+", s)]
    if not nums:
        return 30

    is_hours = "hr" in s or "hour" in s
    avg_val = sum(nums) // len(nums)

    if is_hours:
        return max(15, avg_val * 60)
    return max(10, avg_val)


def is_study_task(atype: str, title: str, notes: str) -> bool:
    content = f"{atype} {title} {notes}".lower()
    keywords = ["study", "studying", "review", "prep", "prepping", "practice", "flashcard", "quiz", "test", "exam"]
    return any(kw in content for kw in keywords)


def format_study_display_title(raw_title: str) -> str:
    t_lower = raw_title.lower()
    study_words = ["study", "review", "prep", "practice", "flashcard"]
    if any(w in t_lower for w in study_words):
        return raw_title
    return f"Study for {raw_title}"


def get_courses_config_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_courses_config_{user_id}"))


def get_schedule_config_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_schedule_config_{user_id}"))


def _pack_notes(notes_text: str, prev_status: str) -> str:
    return json.dumps({"text": notes_text, "prev_status": prev_status})


def _unpack_notes(raw_notes: Any) -> Tuple[str, str]:
    if not raw_notes or pd.isna(raw_notes):
        return ("", "Not Started")
    try:
        data = json.loads(str(raw_notes))
        if isinstance(data, dict):
            return (data.get("text", ""), data.get("prev_status", "Not Started"))
    except Exception:
        pass
    return (str(raw_notes), "Not Started")


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# -----------------------
# Authentication Handlers
# -----------------------
def sign_up_user(email: str, password: str) -> Dict[str, Any]:
    email_clean = email.lower().strip()
    user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email_clean))
    pw_hash = _hash_pw(password.strip())
    now_iso = get_local_now().isoformat()

    sql_check = text("SELECT id FROM users WHERE email = :email")
    sql_insert = text("""
        INSERT INTO users (id, email, password_hash, created_at)
        VALUES (:id, :email, :password_hash, :created_at)
    """)

    with engine.begin() as conn:
        existing = conn.execute(sql_check, {"email": email_clean}).fetchone()
        if existing:
            return {"error": "User with this email already exists."}
        conn.execute(sql_insert, {
            "id": user_id,
            "email": email_clean,
            "password_hash": pw_hash,
            "created_at": now_iso
        })

    return {"data": {"id": user_id, "email": email_clean}}


def sign_in_user(email: str, password: str) -> Dict[str, Any]:
    email_clean = email.lower().strip()
    pw_hash = _hash_pw(password.strip())

    sql_find = text("SELECT id, email, password_hash FROM users WHERE email = :email")

    with engine.connect() as conn:
        row = conn.execute(sql_find, {"email": email_clean}).fetchone()
        if not row:
            return {"error": "Invalid email or password."}
        if row.password_hash != pw_hash:
            return {"error": "Invalid email or password."}
        return {"data": {"id": row.id, "email": row.email}}


def sign_out_user() -> None:
    for key in ["user", "df_cached", "_ai_plan_result", "_completed_daily_slots", "_undo_slot_state"]:
        if key in st.session_state:
            del st.session_state[key]
    safe_rerun()


# -----------------------
# Database CRUD Operations
# -----------------------
def invalidate_cache():
    if "df_cached" in st.session_state:
        del st.session_state["df_cached"]


def _read_courses_file(user_id: str) -> List[str]:
    cfg_id = get_courses_config_id(user_id)
    sql = text("SELECT notes FROM assignments WHERE id = :id AND user_id = :uid")
    with engine.connect() as conn:
        row = conn.execute(sql, {"id": cfg_id, "uid": user_id}).fetchone()
        if row and row.notes:
            try:
                parsed = json.loads(row.notes)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
    return []


def _write_courses_file(user_id: str, courses: List[str]) -> None:
    if not user_id:
        return
    cfg_id = get_courses_config_id(user_id)
    sql = text("""
        INSERT INTO assignments (id, user_id, title, course, due_date, status, priority, atype, eta, notes, created_at)
        VALUES (:id, :user_id, '__SYSTEM_COURSES__', 'CONFIG', '', 'Not Started', 0, 'Other', '', :notes, :created_at)
        ON CONFLICT (id) DO UPDATE SET notes = EXCLUDED.notes, user_id = EXCLUDED.user_id;
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "id": cfg_id,
            "user_id": user_id,
            "notes": json.dumps(courses),
            "created_at": get_local_now().isoformat()
        })


def _read_schedule_file(user_id: str) -> List[Dict[str, Any]]:
    cfg_id = get_schedule_config_id(user_id)
    sql = text("SELECT notes FROM assignments WHERE id = :id AND user_id = :uid")
    with engine.connect() as conn:
        row = conn.execute(sql, {"id": cfg_id, "uid": user_id}).fetchone()
        if row and row.notes:
            try:
                parsed = json.loads(row.notes)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
    return []


def _write_schedule_file(user_id: str, schedule: List[Dict[str, Any]]) -> None:
    if not user_id:
        return
    cfg_id = get_schedule_config_id(user_id)
    sql = text("""
        INSERT INTO assignments (id, user_id, title, course, due_date, status, priority, atype, eta, notes, created_at)
        VALUES (:id, :user_id, '__SYSTEM_SCHEDULE__', 'CONFIG', '', 'Not Started', 0, 'Other', '', :notes, :created_at)
        ON CONFLICT (id) DO UPDATE SET notes = EXCLUDED.notes, user_id = EXCLUDED.user_id;
    """)
    with engine.begin() as conn:
        conn.execute(sql, {
            "id": cfg_id,
            "user_id": user_id,
            "notes": json.dumps(schedule),
            "created_at": get_local_now().isoformat()
        })


def fetch_assignments(user_id: str) -> pd.DataFrame:
    sql = text("""
        SELECT * FROM assignments 
        WHERE user_id = :uid 
          AND title NOT IN ('__SYSTEM_COURSES__', '__SYSTEM_SCHEDULE__')
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"uid": user_id})

    if df.empty:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority",
            "atype", "eta", "created_at", "notes", "prev_status"
        ])

    rows = []
    for _, r in df.iterrows():
        n_text, prev_st = _unpack_notes(r.get("notes"))
        rows.append({
            "id": str(r.get("id")),
            "user_id": str(r.get("user_id")),
            "title": str(r.get("title") or ""),
            "course": str(r.get("course") or "GENERAL").strip().upper(),
            "due_date": str(r.get("due_date") or ""),
            "status": str(r.get("status") or "Not Started"),
            "priority": priority_to_int(priority_to_label(r.get("priority"))),
            "atype": str(r.get("atype") or "Homework"),
            "eta": str(r.get("eta") or ""),
            "created_at": str(r.get("created_at") or ""),
            "notes": n_text,
            "prev_status": prev_st
        })

    return pd.DataFrame(rows)


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    if not rows_to_upsert:
        return

    sql = text("""
        INSERT INTO assignments (id, user_id, title, course, due_date, status, priority, atype, eta, notes, created_at)
        VALUES (:id, :user_id, :title, :course, :due_date, :status, :priority, :atype, :eta, :notes, :created_at)
        ON CONFLICT (id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            title = EXCLUDED.title,
            course = EXCLUDED.course,
            due_date = EXCLUDED.due_date,
            status = EXCLUDED.status,
            priority = EXCLUDED.priority,
            atype = EXCLUDED.atype,
            eta = EXCLUDED.eta,
            notes = EXCLUDED.notes,
            created_at = EXCLUDED.created_at;
    """)

    with engine.begin() as conn:
        for row in rows_to_upsert:
            n_text = str(row.get("notes", "")).strip()
            prev_st = str(row.get("prev_status", "Not Started"))
            packed = _pack_notes(n_text, prev_st)

            conn.execute(sql, {
                "id": str(row.get("id")),
                "user_id": str(row.get("user_id")),
                "title": str(row.get("title", "")).strip() or "Untitled Assignment",
                "course": str(row.get("course", "GENERAL")).strip().upper(),
                "due_date": str(row.get("due_date") or ""),
                "status": str(row.get("status", "Not Started")),
                "priority": priority_to_int(priority_to_label(row.get("priority"))),
                "atype": str(row.get("atype", "Homework")),
                "eta": str(row.get("eta", "")).strip(),
                "notes": packed,
                "created_at": str(row.get("created_at") or get_local_now().isoformat())
            })

    invalidate_cache()


def delete_assignment(assignment_id: str) -> None:
    sql = text("DELETE FROM assignments WHERE id = :id")
    with engine.begin() as conn:
        conn.execute(sql, {"id": assignment_id})
    invalidate_cache()


# -----------------------
# Real-Time Callbacks
# -----------------------
def on_checkbox_toggle(aid: str, row_dict: Dict[str, Any], widget_key: str):
    chk_val = st.session_state.get(widget_key, False)
    if chk_val:
        current_st = row_dict.get("status", "Not Started")
        if current_st != "Done":
            row_dict["prev_status"] = current_st
            st.session_state[f"prev_st_{aid}"] = current_st
        new_status = "Done"
    else:
        prev_st = st.session_state.get(f"prev_st_{aid}") or row_dict.get("prev_status", "In Progress")
        if prev_st == "Done" or not prev_st:
            prev_st = "In Progress"
        new_status = prev_st

    row_dict["status"] = new_status
    st.session_state[f"status_sel_{aid}"] = new_status
    upsert_assignments([row_dict])


def on_status_change(aid: str, row_dict: Dict[str, Any], widget_key: str):
    new_status = st.session_state.get(widget_key)
    if new_status:
        if new_status != "Done":
            row_dict["prev_status"] = new_status
            st.session_state[f"prev_st_{aid}"] = new_status
        row_dict["status"] = new_status
        st.session_state[f"chk_done_{aid}"] = (new_status == "Done")
        upsert_assignments([row_dict])


def on_priority_change(aid: str, row_dict: Dict[str, Any], widget_key: str):
    new_prio_label = st.session_state.get(widget_key)
    if new_prio_label:
        row_dict["priority"] = priority_to_int(new_prio_label)
        upsert_assignments([row_dict])


def on_daily_slot_check(slot_key: str, task_title: str):
    if "_completed_daily_slots" not in st.session_state:
        st.session_state["_completed_daily_slots"] = set()
    st.session_state["_completed_daily_slots"].add(slot_key)
    st.session_state["_undo_slot_state"] = {
        "slot_key": slot_key,
        "title": task_title,
        "time": get_local_now()
    }


def on_undo_daily_slot():
    undo_info = st.session_state.get("_undo_slot_state")
    if undo_info:
        s_key = undo_info["slot_key"]
        if "_completed_daily_slots" in st.session_state:
            st.session_state["_completed_daily_slots"].discard(s_key)
        for k in list(st.session_state.keys()):
            if s_key in k:
                st.session_state[k] = False
        del st.session_state["_undo_slot_state"]


# -----------------------
# Date & Time Helpers
# -----------------------
def parse_date_iso_or_empty(s: Any) -> Optional[date]:
    if s is None or pd.isna(s):
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, str):
        s = s.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
    return None


def parse_time_str(t_str: str) -> Optional[time]:
    if not t_str or pd.isna(t_str):
        return None
    t_str = str(t_str).strip().upper()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(t_str, fmt).time()
        except ValueError:
            pass
    return None


def format_mdy(d: Optional[date]) -> str:
    if not d:
        return get_local_now().date().strftime("%m/%d/%Y")
    return d.strftime("%m/%d/%Y")


def days_left(d: Optional[date]) -> Tuple[str, int]:
    if not d:
        return ("0d", 0)
    today = get_local_now().date()
    delta = (d - today).days
    return (f"{delta}d left" if delta >= 0 else f"{delta}d overdue", delta)


# -----------------------
# AI Time-Slot Scheduler Engine
# -----------------------
def generate_ai_study_plan(df_tasks: pd.DataFrame, schedule: List[Dict[str, Any]], max_daily_mins: int = 60) -> Dict[str, Any]:
    if df_tasks.empty:
        return {"status": "no_tasks", "plan": {}}

    incomplete = df_tasks[df_tasks["status"] != "Done"].copy()
    if incomplete.empty:
        return {"status": "all_done", "plan": {}}

    now_local = get_local_now()
    today = now_local.date()

    now_mins = now_local.hour * 60 + now_local.minute
    if now_mins % 5 != 0:
        now_mins += (5 - (now_mins % 5))

    task_queue = []

    for _, row in incomplete.iterrows():
        due_d = parse_date_iso_or_empty(row.get("due_date")) or (today + timedelta(days=7))
        days_until = (due_d - today).days
        if days_until < 0:
            days_until = 0

        prio_label = priority_to_label(row.get("priority"))
        importance_num = priority_to_int(prio_label)
        urgency_multiplier = 10.0 / max(1, days_until)
        ai_score = importance_num * urgency_multiplier

        eta_mins = parse_eta_to_mins(row.get("eta"))
        atype = str(row.get("atype") or "Homework")
        title = str(row.get("title") or "Untitled")
        notes = str(row.get("notes") or "")

        is_study = is_study_task(atype, title, notes)
        display_title = format_study_display_title(title) if is_study else title

        task_queue.append({
            "id": row.get("id"),
            "title": display_title,
            "course": row.get("course") or "GENERAL",
            "atype": atype,
            "due_date": due_d.strftime("%a %b %d"),
            "priority": prio_label,
            "score": ai_score,
            "eta_mins": eta_mins,
            "days_until": days_until,
            "is_study": is_study
        })

    task_queue.sort(key=lambda x: x["score"], reverse=True)

    plan = {DAYS_OF_WEEK[(today.weekday() + i) % 7]: {"busy": [], "slots": []} for i in range(7)}

    for i in range(7):
        day_date = today + timedelta(days=i)
        day_name = DAYS_OF_WEEK[day_date.weekday()]

        if day_date.weekday() in (5, 6):
            default_start_mins = 10 * 60
            DAY_END_MINS = 20 * 60
        else:
            default_start_mins = 15 * 60 + 30
            DAY_END_MINS = 21 * 60

        if i == 0:
            DAY_START_MINS = max(default_start_mins, now_mins)
        else:
            DAY_START_MINS = default_start_mins

        busy_intervals = []
        day_events = [s for s in schedule if s.get("day") == day_name]

        for ev in day_events:
            st_time = parse_time_str(ev.get("start"))
            end_time = parse_time_str(ev.get("end"))
            if st_time and end_time:
                st_m = st_time.hour * 60 + st_time.minute
                end_m = end_time.hour * 60 + end_time.minute
                busy_intervals.append((st_m, end_m))
                plan[day_name]["busy"].append(f"{ev.get('title')} ({ev.get('start')} - {ev.get('end')})")

        busy_intervals.sort(key=lambda x: x[0])

        free_slots = []
        curr = DAY_START_MINS
        for b_start, b_end in busy_intervals:
            if b_start > curr:
                slot_end = min(b_start, DAY_END_MINS)
                if slot_end > curr:
                    free_slots.append([curr, slot_end])
            curr = max(curr, b_end)
        if curr < DAY_END_MINS:
            free_slots.append([curr, DAY_END_MINS])

        day_scheduled_mins = 0
        remaining_tasks = []

        for t in task_queue:
            target_max_day = max(0, t["days_until"] - 1) if t["days_until"] > 0 else 0

            if i <= target_max_day and day_scheduled_mins < max_daily_mins:
                scheduled = False
                needed = t["eta_mins"]

                for slot in free_slots:
                    slot_len = slot[1] - slot[0]
                    if slot_len >= needed:
                        st_m = slot[0]
                        end_m = st_m + needed

                        start_str = time(st_m // 60, st_m % 60).strftime("%I:%M %p").lstrip("0")
                        end_str = time(end_m // 60, end_m % 60).strftime("%I:%M %p").lstrip("0")

                        plan[day_name]["slots"].append({
                            "slot_key": f"daily_{t['id']}_{day_date.isoformat()}",
                            "task_id": t["id"],
                            "day_date_str": day_date.isoformat(),
                            "time": f"{start_str} - {end_str}",
                            "title": t["title"],
                            "course": t["course"],
                            "priority": t["priority"],
                            "eta_mins": t["eta_mins"]
                        })

                        slot[0] = end_m
                        day_scheduled_mins += needed
                        scheduled = True
                        break

                if not scheduled:
                    remaining_tasks.append(t)
                elif t["is_study"]:
                    remaining_tasks.append(t)
            else:
                remaining_tasks.append(t)

        task_queue = remaining_tasks

    return {"status": "success", "plan": plan}


# -----------------------
# Terminal Auth Interface
# -----------------------
def render_terminal_auth_page():
    c_left, c_center, c_right = st.columns([1, 1.6, 1])

    with c_center:
        st.markdown(
            """
            <div style="background-color: #0b0f19; border: 1px solid #1f293d; border-radius: 12px; padding: 32px 28px; text-align: center; margin-bottom: 20px;">
                <div style="font-size: 1.8rem; font-weight: 800; color: #ffffff; letter-spacing: -0.02em;">Assignment Tracker</div>
                <div style="font-size: 0.85rem; color: #6b7280; margin-top: 4px;">Simsbury High School Portal</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div style="background-color: #0b0f19; border: 1px solid #1f293d; border-radius: 12px; padding: 24px 28px;">', unsafe_allow_html=True)

        mode = st.radio("Action Mode", ["Sign In", "Sign Up"], horizontal=True, label_visibility="collapsed", key="terminal_mode")

        raw_user_input = st.text_input(
            "Username or Email",
            placeholder="e.g. 30guptaa or username@simsburyschools.net",
            key="terminal_user"
        )

        password = st.text_input("Password", type="password", key="terminal_pw")
        typed_user = raw_user_input.strip()
        btn_label = "Sign In" if mode == "Sign In" else "Register Account"

        if st.button(btn_label, key="auth_submit_btn", use_container_width=True):
            email_val = typed_user
            if email_val and "@" not in email_val:
                email_val = f"{email_val}{DEFAULT_DOMAIN}"

            password_val = password.strip()

            if not email_val or not password_val:
                st.error("Please enter both credentials.")
            elif mode == "Sign Up":
                res = sign_up_user(email_val, password_val)
                if "error" in res:
                    st.error(f"Sign up failed: {res['error']}")
                else:
                    st.success(f"Registered {email_val}. You can now sign in.")
            else:
                res = sign_in_user(email_val, password_val)
                if "error" in res:
                    st.error(f"Sign in failed: {res['error']}")
                else:
                    st.session_state.user = res["data"]
                    u_id = res["data"]["id"]
                    invalidate_cache()
                    if not _read_courses_file(u_id):
                        st.session_state["_show_welcome_courses_modal"] = True
                    safe_rerun()

        st.markdown('</div>', unsafe_allow_html=True)


# -----------------------
# Grid Renderer Component
# -----------------------
def render_assignment_grid(df_grid: pd.DataFrame, key_prefix: str = "reg_"):
    if df_grid.empty:
        st.markdown("<div style='padding:50px 0; text-align:center; color:#4b5563; font-size:0.9rem;'>No assignments in this view.</div>", unsafe_allow_html=True)
        return

    df_sorted = df_grid.copy()
    df_sorted["due_parsed"] = df_sorted["due_date"].apply(parse_date_iso_or_empty)
    df_sorted = df_sorted.sort_values(by=["due_parsed", "priority"], ascending=[True, False]).drop(columns=["due_parsed"])

    cards_per_row = 3
    chunked_rows = [df_sorted.iloc[i:i + cards_per_row] for i in range(0, len(df_sorted), cards_per_row)]

    for row_df in chunked_rows:
        cols = st.columns(cards_per_row)
        for idx, (_, row) in enumerate(row_df.iterrows()):
            with cols[idx]:
                with st.container(border=True):
                    aid = row.get("id")
                    title = row.get("title") or "Untitled"
                    course = (row.get("course") or "MATH").upper()
                    atype = row.get("atype") or "Homework"
                    due_d = parse_date_iso_or_empty(row.get("due_date"))
                    due_text = format_mdy(due_d)
                    days_text, _ = days_left(due_d)

                    status = st.session_state.get(f"{key_prefix}status_sel_{aid}") or row.get("status") or "Not Started"
                    prio_label = priority_to_label(row.get("priority"))
                    prio_cls = f"prio-{prio_label.lower()}"
                    row_dict = row.to_dict()

                    c_top1, c_top2, c_top3, c_top4 = st.columns([0.4, 1.6, 1.2, 2.2])

                    with c_top1:
                        chk_key = f"{key_prefix}chk_done_{aid}"
                        st.checkbox(
                            "Done",
                            value=(status == "Done"),
                            key=chk_key,
                            label_visibility="collapsed",
                            on_change=on_checkbox_toggle,
                            args=(aid, row_dict, chk_key)
                        )

                    with c_top2:
                        st.markdown(f"<span class='course-chip'>{course}</span>", unsafe_allow_html=True)

                    with c_top3:
                        if st.button("Edit", key=f"{key_prefix}edit_btn_{aid}"):
                            st.session_state["_edit_assignment_id"] = aid
                            safe_rerun()

                    with c_top4:
                        sel_key = f"{key_prefix}status_sel_{aid}"
                        st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                            key=sel_key,
                            label_visibility="collapsed",
                            on_change=on_status_change,
                            args=(aid, row_dict, sel_key)
                        )

                    st.markdown(f"<div style='font-size:1.1rem; font-weight:700; color:#f9fafb; margin-top:8px;'>{title}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='color:#6b7280; font-size:0.78rem; margin-bottom:8px;'>{atype}</div>", unsafe_allow_html=True)

                    c_bot1, c_bot2 = st.columns([1.5, 1.8])
                    with c_bot1:
                        st.markdown(f"<div style='color:#9ca3af; font-size:0.78rem;'>Due {due_text} ({days_text})</div>", unsafe_allow_html=True)
                    with c_bot2:
                        st.markdown(f"<div class='{prio_cls}'>Priority: {prio_label}</div>", unsafe_allow_html=True)

                    eta = str(row.get("eta") or "").strip()
                    notes = str(row.get("notes") or "").strip()

                    if eta:
                        st.markdown(f"<div style='color:#6b7280; font-size:0.75rem; margin-top:4px;'>Est: {eta}</div>", unsafe_allow_html=True)

                    if notes:
                        note_preview = notes if len(notes) <= 90 else notes[:87] + "..."
                        st.markdown(f"<div style='color:#6b7280; font-size:0.75rem; margin-top:2px;'>{note_preview}</div>", unsafe_allow_html=True)


# -----------------------
# Modal Dialogs
# -----------------------
@dialog_decorator("Welcome! Setup Your Classes")
def show_welcome_courses_dialog(user_id: str):
    st.session_state["_show_welcome_courses_modal"] = False

    st.markdown("### Setup Your Courses")
    courses_input = st.text_area(
        "Enter your subjects (comma separated):",
        value="MATH, SCIENCE, ENGLISH, HISTORY",
    )

    if st.button("Save Schedule", key="save_initial_courses_btn"):
        parsed_courses = [c.strip().upper() for c in courses_input.replace("\n", ",").split(",") if c.strip()]
        if parsed_courses:
            _write_courses_file(user_id, parsed_courses)
            safe_rerun()


@dialog_decorator("Create New Assignment")
def show_add_assignment_dialog(user_id: str):
    st.session_state["_open_add_modal"] = False
    courses = _read_courses_file(user_id) or ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]

    with st.form("add_assignment_form"):
        title = st.text_input("Assignment Title", key="add_title")
        course_choice = st.selectbox("Course", options=[""] + courses, index=0, key="add_course_choice")
        course_free = st.text_input("Or custom course name", value="", key="add_course_free")
        status = st.selectbox("Status", STATUS_OPTIONS, index=0, key="add_status")
        due = st.date_input("Due Date", value=get_local_now().date(), key="add_due")
        importance_label = st.selectbox("Priority", PRIORITY_OPTIONS, index=1, key="add_prio_select")
        atype = st.selectbox("Type", TYPE_OPTIONS, index=0, key="add_atype")
        eta = st.text_input("Estimated Duration (e.g. 30 mins)", key="add_eta")
        notes = st.text_area("Notes", value="", key="add_notes")
        submitted_add = st.form_submit_button("Add Assignment")

        if submitted_add:
            course_val = (course_free.strip() or course_choice or "GENERAL").upper()
            new_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": title.strip() or "Untitled Assignment",
                "course": course_val.strip(),
                "due_date": due.isoformat() if isinstance(due, date) else None,
                "status": status,
                "priority": priority_to_int(importance_label),
                "atype": atype,
                "eta": eta.strip(),
                "created_at": get_local_now().isoformat(),
                "notes": notes.strip(),
                "prev_status": status if status != "Done" else "Not Started",
            }
            upsert_assignments([new_row])
            if course_free.strip():
                c_list = _read_courses_file(user_id)
                if course_free.strip().upper() not in c_list:
                    c_list.append(course_free.strip().upper())
                    _write_courses_file(user_id, c_list)
            safe_rerun()


@dialog_decorator("Edit Assignment Details")
def show_edit_assignment_dialog(user_id: str, aid: str):
    df_current = fetch_assignments(user_id)
    assignment = df_current[df_current["id"] == aid].to_dict(orient="records") if not df_current.empty else []
    assignment_record = assignment[0] if assignment else None

    if not assignment_record:
        st.session_state["_edit_assignment_id"] = ""
        st.warning("Assignment no longer exists.")
        return

    st.session_state["_edit_assignment_id"] = ""
    courses = _read_courses_file(user_id) or ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]

    with st.form("edit_assignment_form"):
        title = st.text_input("Assignment Title", value=assignment_record.get("title", ""), key=f"edit_title_{aid}")
        course_choice = st.selectbox(
            "Course",
            options=[""] + courses,
            index=(0 if assignment_record.get("course", "") not in courses else courses.index(assignment_record.get("course", "")) + 1),
            key=f"edit_course_choice_{aid}",
        )
        course_free = st.text_input("Or custom course name", value=assignment_record.get("course", ""), key=f"edit_course_free_{aid}")
        status = st.selectbox(
            "Status",
            STATUS_OPTIONS,
            index=(STATUS_OPTIONS.index(assignment_record.get("status")) if assignment_record.get("status") in STATUS_OPTIONS else 0),
            key=f"edit_status_{aid}",
        )
        due_parsed = parse_date_iso_or_empty(assignment_record.get("due_date")) or get_local_now().date()
        due = st.date_input("Due Date", value=due_parsed, key=f"edit_due_{aid}")
        curr_prio_label = priority_to_label(assignment_record.get("priority"))
        importance_label = st.selectbox(
            "Priority",
            PRIORITY_OPTIONS,
            index=PRIORITY_OPTIONS.index(curr_prio_label),
            key=f"edit_prio_select_{aid}"
        )
        atype = st.selectbox(
            "Type",
            TYPE_OPTIONS,
            index=(TYPE_OPTIONS.index(assignment_record.get("atype")) if assignment_record.get("atype") in TYPE_OPTIONS else 0),
            key=f"edit_atype_{aid}",
        )
        eta = st.text_input("Estimated Duration", value=assignment_record.get("eta", ""), key=f"edit_eta_{aid}")
        notes = st.text_area("Notes", value=assignment_record.get("notes", ""), key=f"edit_notes_{aid}")

        c_save, c_del = st.columns([1, 1])
        with c_save:
            updated_click = st.form_submit_button("Save Changes")
        with c_del:
            delete_click = st.form_submit_button("Delete Assignment")

        if updated_click:
            course_val = (course_free.strip() or course_choice or "GENERAL").upper()
            updated = {
                "id": aid,
                "user_id": user_id,
                "title": title.strip(),
                "course": course_val.strip(),
                "due_date": due.isoformat() if isinstance(due, date) else None,
                "status": status,
                "priority": priority_to_int(importance_label),
                "atype": atype,
                "eta": eta.strip(),
                "notes": notes.strip(),
                "created_at": assignment_record.get("created_at") or get_local_now().isoformat(),
                "prev_status": status if status != "Done" else assignment_record.get("prev_status", "Not Started"),
            }
            upsert_assignments([updated])
            safe_rerun()

        if delete_click:
            delete_assignment(aid)
            safe_rerun()


@dialog_decorator("Manage Courses")
def show_manage_courses_dialog(user_id: str):
    st.session_state["_open_manage_courses"] = False
    courses = _read_courses_file(user_id)
    to_remove = []

    if courses:
        for i, c in enumerate(courses):
            col_a, col_b = st.columns([6, 2])
            with col_a:
                st.write(f"• **{c}**")
            with col_b:
                if st.button("Remove", key=f"remove_course_{i}"):
                    to_remove.append(c)

    if to_remove:
        courses = [c for c in courses if c not in to_remove]
        _write_courses_file(user_id, courses)
        safe_rerun()

    st.markdown("---")
    new_course = st.text_input("Add a new course", key="new_course_field")
    if st.button("Add Course", key="add_course_button"):
        v = new_course.strip().upper()
        if v and v not in courses:
            courses.append(v)
            _write_courses_file(user_id, courses)
            safe_rerun()


# -----------------------
# Auth Session Control
# -----------------------
user = st.session_state.get("user")

if not user:
    render_terminal_auth_page()
    st.stop()

user_id = str(user.get("id"))
email = str(user.get("email", "User"))

if not _read_courses_file(user_id) and "_show_welcome_courses_modal" not in st.session_state:
    st.session_state["_show_welcome_courses_modal"] = True

# State Modal Launchers
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""
if "_completed_daily_slots" not in st.session_state:
    st.session_state["_completed_daily_slots"] = set()

if st.session_state.get("_show_welcome_courses_modal", False):
    show_welcome_courses_dialog(user_id)

if st.session_state.get("_open_add_modal", False):
    show_add_assignment_dialog(user_id)

if st.session_state.get("_edit_assignment_id"):
    show_edit_assignment_dialog(user_id, st.session_state["_edit_assignment_id"])

if st.session_state.get("_open_manage_courses", False):
    show_manage_courses_dialog(user_id)


# -----------------------
# Main App Header
# -----------------------
col_header_left, col_header_right = st.columns([2, 3])

with col_header_left:
    st.markdown(
        f"""
        <div>
            <div class="app-title">Assignment Tracker</div>
            <div class="app-subtitle">{email}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_header_right:
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1.2, 1.2, 1.2, 0.9])
    with btn_col1:
        if st.button("Clear Done", key="toolbar_clear"):
            df_active = fetch_assignments(user_id)
            if not df_active.empty:
                done_ids = df_active[df_active["status"] == "Done"]["id"].tolist()
                for aid in done_ids:
                    delete_assignment(aid)
            safe_rerun()
    with btn_col2:
        if st.button("New Task", key="toolbar_add"):
            st.session_state["_open_add_modal"] = True
            safe_rerun()
    with btn_col3:
        if st.button("Courses", key="toolbar_courses"):
            st.session_state["_open_manage_courses"] = True
            safe_rerun()
    with btn_col4:
        if st.button("Sign Out", key="toolbar_signout"):
            sign_out_user()

today_str = get_local_now().strftime("%A, %B %d, %Y")
st.markdown(
    f'<div class="date-banner">Date: {today_str}</div>',
    unsafe_allow_html=True,
)

if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)

df_all = st.session_state.df_cached.copy()

# -----------------------
# Navigation Tabs
# -----------------------
tab_assignments, tab_tests, tab_schedule = st.tabs([
    "Assignments", 
    "Tests & Quizzes", 
    "Weekly Schedule & AI Planner"
])

# TAB 1: Regular Assignments
with tab_assignments:
    df_regular = df_all[df_all["atype"] != "Test & Quizzes"]
    render_assignment_grid(df_regular, key_prefix="reg_")

# TAB 2: Tests & Quizzes Only
with tab_tests:
    df_tests = df_all[df_all["atype"] == "Test & Quizzes"]
    render_assignment_grid(df_tests, key_prefix="tests_")

# TAB 3: Weekly Schedule & AI Time-Slot Planner
with tab_schedule:
    col_sched_left, col_sched_right = st.columns([1.2, 1.8])

    user_schedule = _read_schedule_file(user_id)

    with col_sched_left:
        st.markdown("<div style='font-weight:700; font-size:1.05rem; color:#f3f4f6;'>Weekly Commitments</div>", unsafe_allow_html=True)
        st.caption("Enter recurring busy blocks so the AI plans around them.")

        with st.form("add_schedule_event_form"):
            s_day = st.selectbox("Day of Week", DAYS_OF_WEEK)
            s_title = st.text_input("Event Name", placeholder="e.g. Robotics, Practice")
            c_time1, c_time2 = st.columns(2)
            with c_time1:
                s_start_raw = st.text_input("Start Time", value="3:30 PM", key="sched_start_input")
            with c_time2:
                s_end_raw = st.text_input("End Time", value="5:00 PM", key="sched_end_input")

            if st.form_submit_button("Add Block"):
                st_time = parse_time_str(s_start_raw)
                end_time = parse_time_str(s_end_raw)
                if s_title.strip() and st_time and end_time:
                    formatted_start = st_time.strftime("%I:%M %p").lstrip("0")
                    formatted_end = end_time.strftime("%I:%M %p").lstrip("0")
                    user_schedule.append({
                        "id": str(uuid.uuid4()),
                        "day": s_day,
                        "title": s_title.strip(),
                        "start": formatted_start,
                        "end": formatted_end
                    })
                    _write_schedule_file(user_id, user_schedule)
                    safe_rerun()

        st.markdown("---")
        if user_schedule:
            for idx, item in enumerate(user_schedule):
                col_item_a, col_item_b = st.columns([4, 1])
                with col_item_a:
                    st.markdown(f"<span style='color:#9ca3af; font-size:0.82rem;'>**{item.get('day')}**: {item.get('title')} ({item.get('start')} - {item.get('end')})</span>", unsafe_allow_html=True)
                with col_item_b:
                    if st.button("Remove", key=f"del_sched_{idx}"):
                        user_schedule.pop(idx)
                        _write_schedule_file(user_id, user_schedule)
                        safe_rerun()

    with col_sched_right:
        st.markdown("<div style='font-weight:700; font-size:1.05rem; color:#f3f4f6;'>AI Daily Action Plan</div>", unsafe_allow_html=True)
        st.caption("Optimized timeline across available days based on due dates & priority.")

        # Real-time JS-driven Undo Toast with Animated Progress Bar
        undo_state = st.session_state.get("_undo_slot_state")
        if undo_state:
            elapsed = (get_local_now() - undo_state["time"]).total_seconds()
            remaining_sec = max(0, 15 - elapsed)

            if remaining_sec > 0:
                u_col1, u_col2 = st.columns([4.2, 1])
                with u_col1:
                    st.markdown(
                        f"""
                        <div class="undo-toast-box">
                            <span style="font-size: 0.85rem; color: #f3f4f6;">Completed <b>{undo_state['title']}</b> for today</span>
                            <div class="undo-progress-bar" style="animation-duration: {remaining_sec}s;"></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with u_col2:
                    if st.button("Undo", key="btn_undo_slot", on_click=on_undo_daily_slot):
                        safe_rerun()

                # Invisible JS timer component to trigger page refresh precisely when 15s timer expires
                components.html(
                    f"""
                    <script>
                        setTimeout(function() {{
                            window.parent.postMessage({{type: 'streamlit:rerun'}}, '*');
                        }}, {int(remaining_sec * 1000)});
                    </script>
                    """,
                    height=0,
                )
            else:
                del st.session_state["_undo_slot_state"]

        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.5, 1.2, 1.3])

        with ctrl_col1:
            gen_plan_click = st.button("Re-Calculate Plan", key="btn_gen_ai_plan")

        with ctrl_col2:
            show_time_slots = st.toggle("Show Time Slots", value=True, key="toggle_show_time_slots")

        with ctrl_col3:
            max_daily_study = st.selectbox(
                "Max Work / Day",
                options=[45, 60, 90, 120, 180],
                index=1,
                format_func=lambda x: f"{x} mins max",
            )

        fresh_assignments = fetch_assignments(user_id)

        if gen_plan_click:
            st.session_state["_ai_plan_result"] = generate_ai_study_plan(
                fresh_assignments, user_schedule, max_daily_mins=max_daily_study
            )

        plan_res = st.session_state.get("_ai_plan_result") or generate_ai_study_plan(
            fresh_assignments, user_schedule, max_daily_mins=max_daily_study
        )

        status = plan_res.get("status")
        plan = plan_res.get("plan", {})

        if status == "no_tasks":
            st.info("No active assignments. Add items in the 'Assignments' or 'Tests & Quizzes' tab.")
        elif status == "all_done":
            st.success("All assignments marked completed.")
        elif status == "success" and plan:
            completed_set = st.session_state.get("_completed_daily_slots", set())

            for day_name, day_data in plan.items():
                if not isinstance(day_data, dict):
                    st.session_state["_ai_plan_result"] = generate_ai_study_plan(
                        fresh_assignments, user_schedule, max_daily_mins=max_daily_study
                    )
                    safe_rerun()
                    break

                st.markdown(f'<div class="ai-day-card"><div class="ai-day-title">{day_name}</div>', unsafe_allow_html=True)

                busy_list = day_data.get("busy", [])
                if busy_list:
                    st.markdown(f"<div class='busy-text'>Busy: {', '.join(busy_list)}</div>", unsafe_allow_html=True)

                raw_slots = day_data.get("slots", [])
                visible_slots = [s for s in raw_slots if s.get("slot_key") not in completed_set]

                if visible_slots:
                    for idx_slot, s in enumerate(visible_slots):
                        s_key = s.get("slot_key")
                        slot_prio = s.get("priority", priority_to_label(s.get("importance")))

                        c_chk, c_text = st.columns([0.35, 7.65])
                        with c_chk:
                            chk_widget_key = f"chk_{s_key}_{idx_slot}"
                            st.checkbox(
                                "Done Today",
                                value=False,
                                key=chk_widget_key,
                                label_visibility="collapsed",
                                on_change=on_daily_slot_check,
                                args=(s_key, s["title"])
                            )

                        with c_text:
                            if show_time_slots:
                                st.markdown(
                                    f"<span class='slot-badge'>{s['time']}</span> <b style='color:#f3f4f6;'>{s['title']}</b> <span class='course-chip'>{s['course']}</span> <span style='color:#9ca3af; font-size:0.78rem;'>• Priority: {slot_prio} ({s['eta_mins']}m)</span>",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f"<b style='color:#f3f4f6;'>{s['title']}</b> <span class='course-chip'>{s['course']}</span> <span style='color:#9ca3af; font-size:0.78rem;'>• Priority: {slot_prio} ({s['eta_mins']}m)</span>",
                                    unsafe_allow_html=True
                                )
                else:
                    st.markdown("<span style='color:#4b5563; font-size:0.82rem;'>No work scheduled for this day.</span>", unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)
