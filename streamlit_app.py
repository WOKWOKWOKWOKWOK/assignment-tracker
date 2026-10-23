"""
Assignment Tracker — AI Weekly Schedule & 1-10 Importance Rating System

Features:
- AI Smart Planner that balances your weekly schedule & due dates
- 1-10 Importance rating sliders replacing Low/Medium/High
- Dedicated tabs for Assignments, Tests & Quizzes, and Weekly AI Schedule
- Clean UI without search/sort clutter
- 100% Supabase Cloud persistence
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# Hide Streamlit top toolbar, header, and footer overlays
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    from supabase import Client, create_client  # type: ignore
except Exception:
    Client = None
    create_client = None  # type: ignore


# -----------------------
# Streamlit Rerun & Dialog Helper
# -----------------------
def safe_rerun() -> None:
    """Universal rerun helper compatible across Streamlit versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


# Safe Modal Decorator Setup
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


# -----------------------
# Config / Persistence
# -----------------------
DATA_FILE = Path("data.json")
COURSES_FILE = Path("courses.json")
SCHEDULE_FILE = Path("schedule.json")
DEFAULT_DOMAIN = "@simsburyschools.net"

try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = None
    SUPABASE_KEY = None

sb: Optional["Client"] = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)  # type: ignore
    except Exception:
        sb = None

STATUS_OPTIONS = ["Not Started", "In Progress", "Done"]
TYPE_OPTIONS = ["Homework", "Essay", "Presentation", "Test & Quizzes", "Other"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

st.set_page_config(page_title="Assignment Tracker", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")


# -----------------------
# Utility Helpers & Schema Encoding
# -----------------------
def _clean_priority(val: Any) -> int:
    """Converts legacy string priorities or raw inputs into a clean 1-10 integer."""
    if isinstance(val, (int, float)):
        return max(1, min(10, int(val)))
    val_str = str(val).strip()
    if val_str.isdigit():
        return max(1, min(10, int(val_str)))
    mapping = {"High": 9, "Medium": 5, "Low": 2}
    return mapping.get(val_str, 5)


def _to_dict(obj: Any) -> Optional[Dict[str, Any]]:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    for method_name in ("dict", "model_dump"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        try:
            return dict(obj.__dict__)
        except Exception:
            pass
    return None


def _wrap_result(res: Any) -> Dict[str, Any]:
    if isinstance(res, dict):
        mapped = _to_dict(res) or res
        return {
            "error": res.get("error") if isinstance(res, dict) else None,
            "data": res.get("data") if isinstance(res, dict) and "data" in res else mapped,
            "raw": mapped,
        }
    try:
        err = getattr(res, "error", None)
        data = getattr(res, "data", None)
        if data is None:
            mapped = _to_dict(res)
            if isinstance(mapped, dict):
                data = mapped
            else:
                data = None
        raw = _to_dict(res) or None
        return {"error": err, "data": data, "raw": raw}
    except Exception:
        return {"error": None, "data": None, "raw": None}


def get_courses_config_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_courses_config_{user_id}"))


def get_schedule_config_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_schedule_config_{user_id}"))


def _pack_notes(notes_text: str, prev_status: str) -> str:
    return json.dumps({
        "text": notes_text,
        "prev_status": prev_status
    })


def _unpack_notes(raw_notes: Any) -> Tuple[str, str]:
    if not raw_notes:
        return ("", "Not Started")
    try:
        data = json.loads(str(raw_notes))
        if isinstance(data, dict):
            return (
                data.get("text", ""),
                data.get("prev_status", "Not Started")
            )
    except Exception:
        pass
    return (str(raw_notes), "Not Started")


# -----------------------
# Auth Helpers
# -----------------------
def sign_up(email: str, password: str) -> Dict[str, Any]:
    auth = getattr(sb, "auth", None) if sb else None
    if auth is None:
        return {"error": "sb.auth not available", "data": None}
    try:
        if hasattr(auth, "sign_up"):
            try:
                res = auth.sign_up({"email": email, "password": password})
            except TypeError:
                res = auth.sign_up(email=email, password=password)
        elif hasattr(auth, "sign_up_with_password"):
            try:
                res = auth.sign_up_with_password({"email": email, "password": password})
            except TypeError:
                res = auth.sign_up_with_password(email=email, password=password)
        else:
            return {"error": "No supported sign-up method found", "data": None}
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_in(email: str, password: str) -> Dict[str, Any]:
    auth = getattr(sb, "auth", None) if sb else None
    if auth is None:
        return {"error": "sb.auth not available", "data": None}
    try:
        if hasattr(auth, "sign_in_with_password"):
            try:
                res = auth.sign_in_with_password({"email": email, "password": password})
            except TypeError:
                res = auth.sign_in_with_password(email=email, password=password)
        elif hasattr(auth, "sign_in"):
            try:
                res = auth.sign_in({"email": email, "password": password})
            except TypeError:
                res = auth.sign_in(email=email, password=password)
        else:
            return {"error": "No supported sign-in method found", "data": None}
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_out() -> None:
    try:
        auth = getattr(sb, "auth", None) if sb else None
        if auth is not None and hasattr(auth, "sign_out"):
            try:
                auth.sign_out()
            except Exception:
                pass
    except Exception:
        pass
    for key in ["user", "df_cached"]:
        if key in st.session_state:
            del st.session_state[key]
    safe_rerun()


def extract_user_from_auth_response(response: Any) -> Optional[Dict[str, Any]]:
    if response is None:
        return None

    def first_user_from_mapping(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for path in [
            ("data", "user"),
            ("data", "session", "user"),
            ("user",),
            ("session", "user"),
        ]:
            cur = obj
            ok = True
            for key in path:
                if not isinstance(cur, dict):
                    ok = False
                    break
                cur = cur.get(key)
                if cur is None:
                    ok = False
                    break
            if ok and isinstance(cur, dict):
                return cur
        return None

    if isinstance(response, dict):
        user = first_user_from_mapping(response)
        if user:
            return user
        raw = response.get("raw")
        if isinstance(raw, dict):
            user = first_user_from_mapping(raw)
            if user:
                return user
        data = response.get("data")
        if isinstance(data, dict):
            user = first_user_from_mapping(data)
            if user:
                return user

    for attr_name in ["user", "session", "data", "raw"]:
        try:
            obj = getattr(response, attr_name, None)
        except Exception:
            obj = None
        if obj is not None:
            if isinstance(obj, dict):
                user = first_user_from_mapping(obj)
                if user:
                    return user
            else:
                mapped = _to_dict(obj)
                if isinstance(mapped, dict):
                    user = first_user_from_mapping(mapped)
                    if user:
                        return user

    mapped = _to_dict(response)
    if isinstance(mapped, dict):
        user = first_user_from_mapping(mapped)
        if user:
            return user
    return None


def current_user() -> Optional[Dict[str, Any]]:
    try:
        auth = getattr(sb, "auth", None) if sb else None
        if auth is not None and hasattr(auth, "get_session"):
            session = auth.get_session()
            user = extract_user_from_auth_response(session)
            if user:
                return user
    except Exception:
        pass
    try:
        auth = getattr(sb, "auth", None) if sb else None
        if auth is not None and hasattr(auth, "get_user"):
            resp = auth.get_user()
            user = extract_user_from_auth_response(resp)
            if user:
                return user
    except Exception:
        pass
    if "user" in st.session_state:
        return st.session_state.user
    return None


# -----------------------
# Cloud Persistence Helpers
# -----------------------
def invalidate_cache():
    if "df_cached" in st.session_state:
        del st.session_state["df_cached"]


def _read_data_file() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_data_file(rows: List[Dict[str, Any]]) -> None:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)
        invalidate_cache()
    except Exception:
        pass


def _read_courses_file(user_id: str) -> List[str]:
    courses_list = []
    cfg_id = get_courses_config_id(user_id)

    if sb and user_id:
        try:
            res = sb.table("assignments").select("notes").eq("id", cfg_id).execute()
            if res and hasattr(res, "data") and res.data:
                raw_notes = res.data[0].get("notes")
                if raw_notes:
                    parsed = json.loads(raw_notes)
                    if isinstance(parsed, list):
                        courses_list = parsed
        except Exception:
            pass

    if not courses_list and COURSES_FILE.exists() and user_id:
        try:
            with COURSES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    courses_list = data.get(user_id, [])
        except Exception:
            pass

    return courses_list


def _write_courses_file(user_id: str, courses: List[str]) -> None:
    if not user_id:
        return
    cfg_id = get_courses_config_id(user_id)
    if sb:
        try:
            sb.table("assignments").upsert({
                "id": cfg_id,
                "user_id": user_id,
                "title": "__SYSTEM_COURSES__",
                "course": "CONFIG",
                "notes": json.dumps(courses),
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as err:
            st.error(f"Supabase write error: {err}")


def _read_schedule_file(user_id: str) -> List[Dict[str, Any]]:
    """Fetches user weekly schedule from Supabase."""
    cfg_id = get_schedule_config_id(user_id)
    if sb and user_id:
        try:
            res = sb.table("assignments").select("notes").eq("id", cfg_id).execute()
            if res and hasattr(res, "data") and res.data:
                raw_notes = res.data[0].get("notes")
                if raw_notes:
                    return json.loads(raw_notes)
        except Exception:
            pass
    return []


def _write_schedule_file(user_id: str, schedule: List[Dict[str, Any]]) -> None:
    """Saves user weekly schedule to Supabase."""
    if not user_id:
        return
    cfg_id = get_schedule_config_id(user_id)
    if sb:
        try:
            sb.table("assignments").upsert({
                "id": cfg_id,
                "user_id": user_id,
                "title": "__SYSTEM_SCHEDULE__",
                "course": "CONFIG",
                "notes": json.dumps(schedule),
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as err:
            st.error(f"Supabase write error: {err}")


def fetch_assignments(user_id: str) -> pd.DataFrame:
    """Fetches user assignments from Supabase Cloud (filtering out system configs)."""
    cfg_course_id = get_courses_config_id(user_id)
    cfg_sched_id = get_schedule_config_id(user_id)
    rows = []

    if sb and user_id:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id)\
                    .neq("title", "__SYSTEM_COURSES__")\
                    .neq("title", "__SYSTEM_SCHEDULE__").execute()
            if res and hasattr(res, "data") and res.data:
                for r in res.data:
                    rid = str(r.get("id"))
                    if rid in (cfg_course_id, cfg_sched_id):
                        continue

                    n_text, prev_st = _unpack_notes(r.get("notes"))
                    raw_course = r.get("course")

                    if isinstance(raw_course, list) and len(raw_course) > 0:
                        course_str = str(raw_course[0])
                    elif isinstance(raw_course, dict):
                        course_str = str(raw_course.get("name") or "GENERAL")
                    elif isinstance(raw_course, str):
                        course_str = raw_course
                    else:
                        course_str = "GENERAL"

                    rows.append({
                        "id": rid,
                        "user_id": str(r.get("user_id")),
                        "title": r.get("title") or "",
                        "course": course_str.strip().upper(),
                        "due_date": r.get("due_date") or "",
                        "status": r.get("status") or "Not Started",
                        "priority": _clean_priority(r.get("priority")),
                        "atype": r.get("atype") or "Homework",
                        "eta": r.get("eta") or "",
                        "created_at": r.get("created_at") or "",
                        "notes": n_text,
                        "prev_status": prev_st
                    })
        except Exception as err:
            st.error(f"Supabase fetch error: {err}")

    if not rows:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority",
            "atype", "eta", "created_at", "notes", "prev_status"
        ])

    df = pd.DataFrame(rows)
    for c in ["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes", "prev_status"]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    if not rows_to_upsert:
        return

    all_rows = _read_data_file()
    by_id = {r.get("id"): r for r in all_rows if isinstance(r, dict) and r.get("id") is not None}

    for row in rows_to_upsert:
        rid = row.get("id")
        clean = dict(row)

        clean["title"] = str(clean.get("title", "")).strip() or "Untitled Assignment"
        clean["course"] = str(clean.get("course", "GENERAL")).strip() or "GENERAL"
        clean["status"] = clean.get("status", "Not Started")
        clean["priority"] = _clean_priority(clean.get("priority"))
        clean["atype"] = clean.get("atype", "Homework")
        clean["eta"] = str(clean.get("eta", "")).strip()
        clean["notes"] = str(clean.get("notes", "")).strip()
        clean["prev_status"] = clean.get("prev_status", "Not Started")
        clean["user_id"] = clean.get("user_id", "")
        clean["created_at"] = clean.get("created_at") or datetime.utcnow().isoformat()

        by_id[rid] = clean

        db_row = {
            "id": rid,
            "user_id": clean.get("user_id"),
            "title": clean.get("title"),
            "course": clean.get("course"),
            "due_date": clean.get("due_date") or None,
            "status": clean.get("status"),
            "priority": clean.get("priority"),
            "atype": clean.get("atype"),
            "eta": clean.get("eta"),
            "notes": _pack_notes(clean.get("notes", ""), clean.get("prev_status", "Not Started")),
            "created_at": clean.get("created_at"),
        }

        if sb:
            try:
                sb.table("assignments").upsert(db_row).execute()
            except Exception as err:
                st.error(f"Supabase upsert error: {err}")

    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    if sb:
        try:
            sb.table("assignments").delete().eq("id", assignment_id).execute()
        except Exception as err:
            st.error(f"Supabase delete error: {err}")

    rows = _read_data_file()
    remaining = [r for r in rows if r.get("id") != assignment_id]
    _write_data_file(remaining)


# -----------------------
# Real-Time Callback Handlers
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
# Date Helpers
# -----------------------
def parse_date_iso_or_empty(s: Any) -> Optional[date]:
    if s is None:
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
# AI Planner Engine Algorithm
# -----------------------
def generate_ai_study_plan(df_tasks: pd.DataFrame, schedule: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    AI Logic: Analyzes open assignments, their 1-10 importance rating, due dates,
    and user's free blocks to construct an optimal study agenda for the next 7 days.
    """
    incomplete = df_tasks[df_tasks["status"] != "Done"].copy()
    if incomplete.empty:
        return {}

    today = date.today()
    task_queue = []

    for _, row in incomplete.iterrows():
        due_d = parse_date_iso_or_empty(row.get("due_date")) or (today + timedelta(days=7))
        days_until = max(1, (due_d - today).days)
        importance = _clean_priority(row.get("priority"))

        # AI Scoring Algorithm: Urgency (due date weight) * Importance (1-10 slider)
        urgency_multiplier = 10.0 / days_until
        ai_score = importance * urgency_multiplier

        eta_str = str(row.get("eta") or "30 mins").lower()
        eta_mins = 45
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
            "title": row.get("title"),
            "course": row.get("course"),
            "atype": row.get("atype"),
            "due_date": due_d.strftime("%a %b %d"),
            "importance": importance,
            "score": ai_score,
            "eta_mins": eta_mins,
            "days_until": days_until
        })

    # Sort queue by AI priority score descending
    task_queue.sort(key=lambda x: x["score"], reverse=True)

    # Distribute tasks into a 7-day timeline
    plan = {DAYS_OF_WEEK[(today.weekday() + i) % 7]: [] for i in range(7)}

    for t in task_queue:
        # Schedule task on the optimal day prior to due date
        best_day_offset = min(t["days_until"] - 1, 6)
        assigned_day = DAYS_OF_WEEK[(today.weekday() + best_day_offset) % 7]
        plan[assigned_day].append(t)

    return plan


# -----------------------
# CSS Styling & Layout Overrides
# -----------------------
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

    /* Hide Streamlit Sidebar Controls */
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

    /* Importance Badge Pill */
    .importance-badge {
        background-color: #311b92;
        color: #d1c4e9;
        border: 1px solid #512da8;
        border-radius: 6px;
        padding: 2px 8px;
        font-weight: 700;
        font-size: 0.78rem;
    }

    /* Custom Terminal Yellow Submit Button */
    button[key="auth_submit_btn"] {
        background-color: #1e293b !important;
        color: #fbbf24 !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
    }

    /* Header Title Styling */
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

    /* Calendar Banner Box */
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

    /* Course Badge Pill */
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
    </style>
    """,
    unsafe_allow_html=True,
)


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
                res = sign_up(email_val, password_val)
                if res.get("error"):
                    st.error(f"Sign up failed: {res.get('error')}")
                else:
                    st.success(f"Sign up successful for {email_val}! You can now sign in.")
            else:
                res = sign_in(email_val, password_val)
                err = res.get("error")
                data = res.get("data") if isinstance(res, dict) else getattr(res, "data", None)
                user_obj = extract_user_from_auth_response(res)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or (data.get("session") or {}).get("user")

                if err:
                    st.error(f"Sign in failed: {err}")
                elif not user_obj:
                    valid_uuid_string = str(uuid.uuid5(uuid.NAMESPACE_DNS, email_val))
                    st.session_state.user = {"id": valid_uuid_string, "email": email_val}
                    invalidate_cache()
                    safe_rerun()
                else:
                    st.session_state.user = user_obj
                    u_id = str(user_obj.get("id") or user_obj.get("sub") or str(uuid.uuid4()))
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

    # Sort strictly by Due Date (soonest) then Importance (highest 10 -> 1)
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
# Dialog Modals
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
        
        # 1-10 Importance Slider
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
        
        # 1-10 Importance Slider
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
# Auth Session Management & Main Execution
# -----------------------
user = current_user()

if not user:
    render_terminal_auth_page()
    st.stop()

user_id = str(user.get("id") or user.get("sub") or user.get("user_id") or str(uuid.uuid4()))
email = user.get("email") or (user.get("user_metadata") or {}).get("email") or "Logged In"

if not _read_courses_file(user_id) and "_show_welcome_courses_modal" not in st.session_state:
    st.session_state["_show_welcome_courses_modal"] = True

# State Flags & Safe Dialog Launchers
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
# Main Dashboard Header
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
            sign_out()
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

# TAB 3: Weekly Schedule & AI Auto-Planner
with tab_schedule:
    col_sched_left, col_sched_right = st.columns([1.2, 1.8])

    user_schedule = _read_schedule_file(user_id)

    with col_sched_left:
        st.markdown("### 🕒 Add Weekly Commitments")
        st.caption("Enter recurring events (e.g., Classes, Sports, Work) so the AI knows when you are busy.")

        with st.form("add_schedule_event_form"):
            s_day = st.selectbox("Day of Week", DAYS_OF_WEEK)
            s_title = st.text_input("Event Name", placeholder="e.g. Soccer Practice, Math Class")
            c_time1, c_time2 = st.columns(2)
            with c_time1:
                s_start = st.time_input("Start Time", value=datetime.strptime("15:30", "%H:%M").time())
            with c_time2:
                s_end = st.time_input("End Time", value=datetime.strptime("17:00", "%H:%M").time())

            if st.form_submit_button("➕ Add Commitment"):
                if s_title.strip():
                    user_schedule.append({
                        "id": str(uuid.uuid4()),
                        "day": s_day,
                        "title": s_title.strip(),
                        "start": s_start.strftime("%H:%M"),
                        "end": s_end.strftime("%H:%M")
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
            st.info("No recurring events added yet.")

    with col_sched_right:
        st.markdown("### 🤖 AI Daily Action Plan")
        st.caption("The AI scans your assignments, due dates, duration, and importance ratings to build your ideal schedule.")

        if st.button("✨ Generate AI Schedule Plan", key="btn_gen_ai_plan"):
            st.session_state["_ai_plan"] = generate_ai_study_plan(df_all, user_schedule)

        ai_plan = st.session_state.get("_ai_plan") or generate_ai_study_plan(df_all, user_schedule)

        if ai_plan:
            for day_name, tasks in ai_plan.items():
                st.markdown(f'<div class="ai-day-card"><div class="ai-day-title">📅 {day_name}</div>', unsafe_allow_html=True)
                
                # Show scheduled commitments for this day
                day_blocks = [s for s in user_schedule if s.get("day") == day_name]
                if day_blocks:
                    block_strs = [f"🚫 {b.get('title')} ({b.get('start')}-{b.get('end')})" for b in day_blocks]
                    st.caption("Busy: " + ", ".join(block_strs))

                if tasks:
                    for t in tasks:
                        st.markdown(
                            f"▫️ **{t['title']}** (`{t['course']}`) — Importance: **{t['importance']}/10** | Due: **{t['due_date']}** | Est: `{t['eta_mins']} mins`"
                        )
                else:
                    st.markdown("<span style='color:#64748b; font-size:0.85rem;'>No study tasks assigned for this day. Free time!</span>", unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.success("🎉 All tasks completed! No study sessions needed.")
