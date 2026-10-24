"""
Assignment Tracker — Fully Migrated to Neon PostgreSQL with AI Time-Slot Scheduler
Features:
- Neon PostgreSQL storage via SQLAlchemy + psycopg2-binary
- Multi-tenant user isolation for assignments, courses, and weekly commitments
- Balanced AI Study Planner: Spreads tasks across days to prevent overload
- Toggleable exact time-slot display vs. simple bullet view
- 12-Hour AM/PM Weekly Schedule Manager
- User authentication & automatic schema initialization
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, date, timedelta, time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# -----------------------
# Streamlit Page Config & CSS Overrides
# -----------------------
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Dark Theme Canvas */
    .stApp {
        background-color: #080c14 !important;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    .main .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px;
    }

    /* Hide Streamlit Header, Footer, and Navigation Sidebars */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important;}
    section[data-testid="stSidebar"],
    div[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }

    /* Tab Navigation Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid #1e293b;
        margin-bottom: 22px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 42px;
        white-space: pre;
        border-radius: 8px 8px 0 0;
        color: #94a3b8;
        font-weight: 600;
        font-size: 0.9rem;
        padding: 8px 20px;
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-bottom: none;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1e1b4b !important;
        color: #a5b4fc !important;
        border-color: #4f46e5 !important;
    }

    /* Card Box Container */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0c1322 !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        padding: 16px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    }

    /* Custom Submit Button */
    button[key="auth_submit_btn"] {
        background-color: #1e293b !important;
        color: #fbbf24 !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }

    /* Title & Banner Styling */
    .app-title {
        font-size: 2.1rem;
        font-weight: 900;
        color: #ffffff;
        margin: 0;
        letter-spacing: -0.02em;
    }

    .app-subtitle {
        font-size: 0.88rem;
        color: #64748b;
        margin-top: 4px;
    }

    .calendar-banner-box {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 10px 16px;
        text-align: center;
        color: #818cf8;
        font-weight: 600;
        font-size: 0.95rem;
        margin: 12px 0 20px 0;
    }

    .course-badge {
        background-color: #1e1b4b;
        color: #818cf8;
        border: 1px solid #312e81;
        border-radius: 6px;
        padding: 4px 10px;
        font-weight: 700;
        font-size: 0.75rem;
        letter-spacing: 0.04em;
        display: inline-block;
    }

    .card-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #ffffff;
        margin-top: 10px;
        margin-bottom: 2px;
    }

    .card-type {
        color: #f43f5e;
        font-size: 0.82rem;
        font-weight: 600;
        margin-bottom: 8px;
    }

    .card-hr {
        border: 0;
        border-top: 1px solid #1e293b;
        margin: 10px 0;
    }

    .due-date-text {
        color: #94a3b8;
        font-size: 0.82rem;
        font-weight: 500;
    }

    .days-badge {
        background-color: #1e293b;
        color: #cbd5e1;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    .prio-label {
        color: #818cf8;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
    }

    .meta-row {
        color: #94a3b8;
        font-size: 0.8rem;
        margin-top: 4px;
    }

    .ai-day-card {
        background-color: #0c1322;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 14px;
        margin-bottom: 12px;
    }

    .ai-day-title {
        color: #38bdf8;
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 8px;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 4px;
    }

    .time-slot-badge {
        background-color: #1e1b4b;
        color: #38bdf8;
        border: 1px solid #0284c7;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.82rem;
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
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# -----------------------
# Database Engine Initialization
# -----------------------
def get_connection_url() -> str:
    """Fetches connection string from secrets and formats driver for SQLAlchemy."""
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
    """Creates tables in Neon database automatically on first startup."""
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
# Utility Helpers & User Namespace IDs
# -----------------------
def _clean_priority(val: Any) -> int:
    if pd.isna(val) or val is None:
        return 5
    if isinstance(val, (int, float)):
        return max(1, min(10, int(val)))
    val_str = str(val).strip()
    if val_str.isdigit():
        return max(1, min(10, int(val_str)))
    mapping = {"High": 9, "Medium": 5, "Low": 2}
    return mapping.get(val_str, 5)


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
    now_iso = datetime.utcnow().isoformat()

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
    for key in ["user", "df_cached", "_ai_plan_result"]:
        if key in st.session_state:
            del st.session_state[key]
    safe_rerun()


# -----------------------
# Database CRUD Operations (Isolated Per User)
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
            "created_at": datetime.utcnow().isoformat()
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
            "created_at": datetime.utcnow().isoformat()
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
            "priority": _clean_priority(r.get("priority")),
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
                "priority": _clean_priority(row.get("priority")),
                "atype": str(row.get("atype", "Homework")),
                "eta": str(row.get("eta", "")).strip(),
                "notes": packed,
                "created_at": str(row.get("created_at") or datetime.utcnow().isoformat())
            })

    invalidate_cache()


def delete_assignment(assignment_id: str) -> None:
    sql = text("DELETE FROM assignments WHERE id = :id")
    with engine.begin() as conn:
        conn.execute(sql, {"id": assignment_id})
    invalidate_cache()


# -----------------------
# Real-Time Event Callbacks
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
    new_prio = st.session_state.get(widget_key)
    if new_prio is not None:
        row_dict["priority"] = int(new_prio)
        upsert_assignments([row_dict])


# -----------------------
# Date & Time Parsing Helpers
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
    for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p", "%H:%M:%S"):
        try:
            return datetime.strptime(t_str, fmt).time()
        except ValueError:
            pass
    return None


def format_mdy(d: Optional[date]) -> str:
    if not d:
        return datetime.today().strftime("%m/%d/%Y")
    return d.strftime("%m/%d/%Y")


def days_left(d: Optional[date]) -> Tuple[str, int]:
    if not d:
        return ("0d left", 0)
    today = date.today()
    delta = (d - today).days
    if delta < 0:
        return (f"{delta}d left", delta)
    if delta == 0:
        return ("0d left", 0)
    return (f"{delta}d left", delta)


# -----------------------
# Balanced AI Time-Slot Scheduler Engine (Work Spreading Enabled)
# -----------------------
def generate_ai_study_plan(df_tasks: pd.DataFrame, schedule: List[Dict[str, Any]], max_daily_mins: int = 60) -> Dict[str, Any]:
    if df_tasks.empty:
        return {"status": "no_tasks", "plan": {}}

    incomplete = df_tasks[df_tasks["status"] != "Done"].copy()
    if incomplete.empty:
        return {"status": "all_done", "plan": {}}

    today = date.today()
    task_queue = []

    for _, row in incomplete.iterrows():
        due_d = parse_date_iso_or_empty(row.get("due_date")) or (today + timedelta(days=7))
        days_until = (due_d - today).days
        if days_until < 1:
            days_until = 1

        importance = _clean_priority(row.get("priority"))
        urgency_multiplier = 10.0 / days_until
        ai_score = importance * urgency_multiplier

        eta_str = str(row.get("eta") or "30 mins").lower()
        eta_mins = 30
        if "hr" in eta_str or "hour" in eta_str:
            try:
                nums = ''.join(c for c in eta_str.split("h")[0] if c.isdigit() or c == '.')
                eta_mins = int(float(nums) * 60)
            except Exception:
                eta_mins = 60
        elif "min" in eta_str:
            try:
                nums = ''.join(c for c in eta_str if c.isdigit())
                eta_mins = int(nums)
            except Exception:
                eta_mins = 30

        task_queue.append({
            "id": row.get("id"),
            "title": row.get("title") or "Untitled",
            "course": row.get("course") or "GENERAL",
            "atype": row.get("atype") or "Homework",
            "due_date": due_d.strftime("%a %b %d"),
            "importance": importance,
            "score": ai_score,
            "eta_mins": max(15, eta_mins),
            "days_until": days_until
        })

    # Sort tasks by highest AI urgency/importance score
    task_queue.sort(key=lambda x: x["score"], reverse=True)

    plan = {DAYS_OF_WEEK[(today.weekday() + i) % 7]: {"busy": [], "slots": []} for i in range(7)}

    for i in range(7):
        day_date = today + timedelta(days=i)
        day_name = DAYS_OF_WEEK[day_date.weekday()]

        if day_date.weekday() in (5, 6):  # Weekend
            DAY_START_MINS = 10 * 60
            DAY_END_MINS = 20 * 60
        else:  # Weekday
            DAY_START_MINS = 15 * 60 + 30
            DAY_END_MINS = 21 * 60

        # Parse busy blocks for this day
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

        # Derive open study slots
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

        # Schedule tasks with a daily time limit cap to spread work out evenly
        day_scheduled_mins = 0
        remaining_tasks = []

        for t in task_queue:
            # Only schedule task if due date is today or later, AND daily study load hasn't exceeded cap
            if t["days_until"] >= i and day_scheduled_mins < max_daily_mins:
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
                            "time": f"{start_str} - {end_str}",
                            "title": t["title"],
                            "course": t["course"],
                            "importance": t["importance"],
                            "eta_mins": t["eta_mins"]
                        })

                        slot[0] = end_m
                        day_scheduled_mins += needed
                        scheduled = True
                        break

                if not scheduled:
                    remaining_tasks.append(t)
            else:
                remaining_tasks.append(t)

        task_queue = remaining_tasks

    return {"status": "success", "plan": plan}


# -----------------------
# Terminal Auth Interface
# -----------------------
def render_terminal_auth_page():
    c_left, c_center, c_right = st.columns([1, 1.8, 1])

    with c_center:
        st.markdown(
            """
            <div style="background-color: #0c1322; border: 1.5px solid #2563eb; border-radius: 12px; padding: 32px 24px; text-align: center; margin-bottom: 16px;">
                <div style="font-size: 2.2rem; font-weight: 800; color: #ffffff;">🛡️ Assignment Tracker</div>
                <div style="font-size: 0.92rem; color: #94a3b8; margin-top: 8px;">Simsbury High School Assignment Portal</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div style="background-color: #0c1322; border: 1px solid #1e293b; border-radius: 12px; padding: 24px 28px;">', unsafe_allow_html=True)

        mode = st.radio("Action Mode", ["Sign In", "Sign Up"], horizontal=True, label_visibility="collapsed", key="terminal_mode")

        raw_user_input = st.text_input(
            "Enter Username / Email:",
            placeholder="30guptaa or username@simsburyschools.net",
            key="terminal_user"
        )

        password = st.text_input("Password:", type="password", key="terminal_pw")
        typed_user = raw_user_input.strip()
        btn_label = "🔑 Sign In to Terminal" if mode == "Sign In" else "📝 Register Account"

        if st.button(btn_label, key="auth_submit_btn"):
            email_val = typed_user
            if email_val and "@" not in email_val:
                email_val = f"{email_val}{DEFAULT_DOMAIN}"

            password_val = password.strip()

            if not email_val or not password_val:
                st.error("Please enter both a username/email and a password.")
            elif mode == "Sign Up":
                res = sign_up_user(email_val, password_val)
                if "error" in res:
                    st.error(f"Sign up failed: {res['error']}")
                else:
                    st.success(f"Sign up successful for {email_val}! You can now sign in.")
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
        st.markdown("<div style='padding:60px 0; text-align:center; color:#64748b; font-size:1rem;'>🎉 No assignments found in this view.</div>", unsafe_allow_html=True)
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
                    importance_val = _clean_priority(row.get("priority"))
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
                        st.markdown(f"<span class='course-badge'>{course}</span>", unsafe_allow_html=True)

                    with c_top3:
                        if st.button("✏️ Edit", key=f"{key_prefix}edit_btn_{aid}"):
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

                    st.markdown(f"<div class='card-title'>{title}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='card-type'>📌 {atype}</div>", unsafe_allow_html=True)
                    st.markdown("<hr class='card-hr'/>", unsafe_allow_html=True)

                    c_bot1, c_bot2 = st.columns([1.5, 1.8])
                    with c_bot1:
                        st.markdown(
                            f"<div class='due-date-text'>📅 {due_text} <span class='days-badge'>{days_text}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with c_bot2:
                        st.markdown(f"<div class='prio-label'>IMPORTANCE: {importance_val}/10</div>", unsafe_allow_html=True)
                        prio_key = f"{key_prefix}prio_sel_{aid}"
                        st.slider(
                            "Importance",
                            min_value=1,
                            max_value=10,
                            value=importance_val,
                            key=prio_key,
                            label_visibility="collapsed",
                            on_change=on_priority_change,
                            args=(aid, row_dict, prio_key)
                        )

                    eta = str(row.get("eta") or "").strip()
                    notes = str(row.get("notes") or "").strip()

                    if eta:
                        st.markdown(f"<div class='meta-row'>⏱️ Duration: {eta}</div>", unsafe_allow_html=True)

                    if notes:
                        note_preview = notes if len(notes) <= 120 else notes[:117] + "..."
                        st.markdown(f"<div class='meta-row'>📝 {note_preview}</div>", unsafe_allow_html=True)


# -----------------------
# Modal Dialogs
# -----------------------
@dialog_decorator("Welcome! Setup Your Classes")
def show_welcome_courses_dialog(user_id: str):
    st.session_state["_show_welcome_courses_modal"] = False

    st.markdown("### 🎓 Welcome to Assignment Tracker!")
    st.write("Please list the subjects or classes you are taking this term:")

    courses_input = st.text_area(
        "Enter your classes (comma separated):",
        value="MATH, SCIENCE, ENGLISH, HISTORY",
        help="Example: MATH, SCIENCE, SPANISH, AP PHYSICS"
    )

    if st.button("Save Schedule & Start", key="save_initial_courses_btn"):
        parsed_courses = [c.strip().upper() for c in courses_input.replace("\n", ",").split(",") if c.strip()]
        if parsed_courses:
            _write_courses_file(user_id, parsed_courses)
            st.success("Classes saved successfully!")
            safe_rerun()


@dialog_decorator("Create New Assignment")
def show_add_assignment_dialog(user_id: str):
    st.session_state["_open_add_modal"] = False
    courses = _read_courses_file(user_id) or ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]

    with st.form("add_assignment_form"):
        title = st.text_input("Assignment Name", key="add_title")
        course_choice = st.selectbox("Subject / Course", options=[""] + courses, index=0, key="add_course_choice")
        course_free = st.text_input("Or type a new course name", value="", key="add_course_free")
        status = st.selectbox("Status", STATUS_OPTIONS, index=0, key="add_status")
        due = st.date_input("Due Date (MM/DD/YYYY)", value=date.today(), key="add_due")
        importance = st.slider("Importance / Priority Level (1 = Low, 10 = Critical)", min_value=1, max_value=10, value=5, key="add_prio_slider")
        atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=0, key="add_atype")
        eta = st.text_input("Estimated Duration (e.g., 45 mins, 2 hours)", key="add_eta")
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
                "priority": importance,
                "atype": atype,
                "eta": eta.strip(),
                "created_at": datetime.utcnow().isoformat(),
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
        title = st.text_input("Assignment Name", value=assignment_record.get("title", ""), key=f"edit_title_{aid}")
        course_choice = st.selectbox(
            "Subject / Course",
            options=[""] + courses,
            index=(0 if assignment_record.get("course", "") not in courses else courses.index(assignment_record.get("course", "")) + 1),
            key=f"edit_course_choice_{aid}",
        )
        course_free = st.text_input("Or type a course name", value=assignment_record.get("course", ""), key=f"edit_course_free_{aid}")
        status = st.selectbox(
            "Status",
            STATUS_OPTIONS,
            index=(STATUS_OPTIONS.index(assignment_record.get("status")) if assignment_record.get("status") in STATUS_OPTIONS else 0),
            key=f"edit_status_{aid}",
        )
        due_parsed = parse_date_iso_or_empty(assignment_record.get("due_date")) or date.today()
        due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed, key=f"edit_due_{aid}")
        importance = st.slider(
            "Importance Level (1-10)",
            min_value=1,
            max_value=10,
            value=_clean_priority(assignment_record.get("priority")),
            key=f"edit_prio_slider_{aid}"
        )
        atype = st.selectbox(
            "Assignment Type",
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
            delete_click = st.form_submit_button("🗑️ Delete Assignment")

        if updated_click:
            course_val = (course_free.strip() or course_choice or "GENERAL").upper()
            updated = {
                "id": aid,
                "user_id": user_id,
                "title": title.strip(),
                "course": course_val.strip(),
                "due_date": due.isoformat() if isinstance(due, date) else None,
                "status": status,
                "priority": importance,
                "atype": atype,
                "eta": eta.strip(),
                "notes": notes.strip(),
                "created_at": assignment_record.get("created_at") or datetime.utcnow().isoformat(),
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
    new_course = st.text_input("Add a new course", key="new_course_field", placeholder="e.g. AP CALCULUS")
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
col_header_left, col_header_right = st.columns([1.2, 3.8])

with col_header_left:
    st.markdown(
        """
        <div>
            <div class="app-title">📋 Assignment Tracker 📝</div>
            <div class="app-subtitle">Your Assignment Tracker.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_header_right:
    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5 = st.columns([1.2, 1.2, 1.3, 0.9, 2.2])
    with btn_col1:
        if st.button("🧹 Clear Completed", key="toolbar_clear"):
            df_active = fetch_assignments(user_id)
            if not df_active.empty:
                done_ids = df_active[df_active["status"] == "Done"]["id"].tolist()
                for aid in done_ids:
                    delete_assignment(aid)
            safe_rerun()
    with btn_col2:
        if st.button("➕ Add Assignment", key="toolbar_add"):
            st.session_state["_open_add_modal"] = True
            safe_rerun()
    with btn_col3:
        if st.button("📚 Change Courses", key="toolbar_courses"):
            st.session_state["_open_manage_courses"] = True
            safe_rerun()
    with btn_col4:
        if st.button("🚪 Sign Out", key="toolbar_signout"):
            sign_out_user()
    with btn_col5:
        st.markdown(
            f'<div style="background-color:#0f172a; border:1px solid #1e293b; border-radius:20px; padding:6px 14px; font-size:0.82rem; color:#94a3b8; display:inline-flex; align-items:center; gap:6px;">🟢 {email}</div>',
            unsafe_allow_html=True,
        )

today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(
    f'<div class="calendar-banner-box">📅 Today\'s Date: {today_str}</div>',
    unsafe_allow_html=True,
)

if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)

df_all = st.session_state.df_cached.copy()

# -----------------------
# Navigation Tabs
# -----------------------
tab_assignments, tab_tests, tab_schedule = st.tabs([
    "📋 Assignments", 
    "🧪 Tests & Quizzes", 
    "📅 Weekly Schedule & AI Planner"
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
        st.markdown("### 🕒 Add Weekly Commitments")
        st.caption("Enter recurring events in 12-hour AM/PM time so the AI knows when you are busy.")

        with st.form("add_schedule_event_form"):
            s_day = st.selectbox("Day of Week", DAYS_OF_WEEK)
            s_title = st.text_input("Event Name", placeholder="e.g. Soccer Practice, Math Class")
            c_time1, c_time2 = st.columns(2)
            with c_time1:
                s_start = st.time_input("Start Time", value=datetime.strptime("03:30 PM", "%I:%M %p").time())
            with c_time2:
                s_end = st.time_input("End Time", value=datetime.strptime("05:00 PM", "%I:%M %p").time())

            if st.form_submit_button("➕ Add Commitment"):
                if s_title.strip():
                    formatted_start = s_start.strftime("%I:%M %p").lstrip("0")
                    formatted_end = s_end.strftime("%I:%M %p").lstrip("0")
                    user_schedule.append({
                        "id": str(uuid.uuid4()),
                        "day": s_day,
                        "title": s_title.strip(),
                        "start": formatted_start,
                        "end": formatted_end
                    })
                    _write_schedule_file(user_id, user_schedule)
                    st.success("Commitment saved!")
                    safe_rerun()

        st.markdown("---")
        st.markdown("#### Your Active Weekly Blocks")
        if user_schedule:
            for idx, item in enumerate(user_schedule):
                col_item_a, col_item_b = st.columns([4, 1])
                with col_item_a:
                    st.markdown(f"**{item.get('day')}**: {item.get('title')} (`{item.get('start')} - {item.get('end')}`)")
                with col_item_b:
                    if st.button("🗑️", key=f"del_sched_{idx}"):
                        user_schedule.pop(idx)
                        _write_schedule_file(user_id, user_schedule)
                        safe_rerun()
        else:
            st.info("No recurring events added yet. Add your practice or work blocks above!")

    with col_sched_right:
        st.markdown("### 🤖 AI Daily Action Plan")
        st.caption("Schedules study tasks across available days based on due dates, importance, and busy blocks.")

        # Controls & Display Toggles
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1.5, 1.2, 1.3])

        with ctrl_col1:
            gen_plan_click = st.button("✨ Generate AI Schedule Plan", key="btn_gen_ai_plan")

        with ctrl_col2:
            show_time_slots = st.toggle("Show Time Slots", value=True, key="toggle_show_time_slots")

        with ctrl_col3:
            max_daily_study = st.selectbox(
                "Max Study / Day",
                options=[45, 60, 90, 120, 180],
                index=1,
                format_func=lambda x: f"{x} mins max",
                help="Spreads out work across multiple days so you aren't overwhelmed on a single day."
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
            st.info("ℹ️ You have no assignments created yet. Add assignments in the 'Assignments' or 'Tests & Quizzes' tab first!")
        elif status == "all_done":
            st.success("🎉 All assignments are marked as 'Done'! Nothing to schedule.")
        elif status == "success" and plan:
            for day_name, day_data in plan.items():
                if not isinstance(day_data, dict):
                    st.session_state["_ai_plan_result"] = generate_ai_study_plan(
                        fresh_assignments, user_schedule, max_daily_mins=max_daily_study
                    )
                    safe_rerun()
                    break

                st.markdown(f'<div class="ai-day-card"><div class="ai-day-title">📅 {day_name}</div>', unsafe_allow_html=True)

                busy_list = day_data.get("busy", [])
                if busy_list:
                    st.caption("Busy: " + ", ".join([f"🚫 {b}" for b in busy_list]))

                study_slots = day_data.get("slots", [])
                if study_slots:
                    for s in study_slots:
                        if show_time_slots:
                            st.markdown(
                                f"<span class='time-slot-badge'>⏰ {s['time']}</span> — **{s['title']}** (`{s['course']}`) | Importance: **{s['importance']}/10** ({s['eta_mins']} mins)",
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f"▫️ **{s['title']}** (`{s['course']}`) — Importance: **{s['importance']}/10** ({s['eta_mins']} mins)"
                            )
                else:
                    st.markdown("<span style='color:#64748b; font-size:0.85rem;'>No study tasks assigned for this day. Free time!</span>", unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)
