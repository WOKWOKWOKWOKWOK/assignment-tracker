"""
Assignment Tracker — Full Persisted Terminal Interface & Supabase Sync

Features:
- Terminal-style full-page authentication UI matching the dual-card stacked design
- Native single-table Supabase persistence (`assignments`)
- Auto-domain appending (@simsburyschools.net) with custom domain override support
- Full dark mode theme, hidden sidebar, and responsive assignment grid
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, date
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
# Config / persistence
# -----------------------
DATA_FILE = Path("data.json")
COURSES_FILE = Path("courses.json")
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
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
TYPE_OPTIONS = ["Essay", "Presentation", "Homework", "Test & Quizzes", "Other"]
SORT_OPTIONS = [
    "Spreadsheet Default Order",
    "Due Date (Soonest)",
    "Priority (High → Low)",
    "Created (Newest)",
]

st.set_page_config(page_title="Assignment Tracker", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")


# -----------------------
# Utility Helpers & Schema Encoding
# -----------------------
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
    """Generates a deterministic RFC UUID for the user's Cloud Course Config record."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_courses_config_{user_id}"))


def _pack_notes(notes_text: str, prev_status: str) -> str:
    """Packs auxiliary state cleanly into notes payload."""
    return json.dumps({
        "text": notes_text,
        "prev_status": prev_status
    })


def _unpack_notes(raw_notes: Any) -> Tuple[str, str]:
    """Extracts text notes and previous status with fallback."""
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
# Auth Helpers (Supabase)
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
# Supabase Cloud & Local Persistence Helpers
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
    """Reads course list directly from Supabase Cloud `assignments` table."""
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

    if not courses_list and sb and user_id:
        try:
            res = sb.table("assignments").select("course").eq("user_id", user_id).neq("title", "__SYSTEM_COURSES__").execute()
            if res and hasattr(res, "data") and res.data:
                c_set = set()
                for r in res.data:
                    c = r.get("course")
                    if isinstance(c, str) and c.strip() and c != "CONFIG":
                        c_set.add(c.strip().upper())
                courses_list = sorted(list(c_set))
        except Exception:
            pass

    if not courses_list and COURSES_FILE.exists() and user_id:
        try:
            with COURSES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    courses_list = data.get(user_id, [])
                elif isinstance(data, list):
                    courses_list = data
        except Exception:
            pass

    return courses_list


def _write_courses_file(user_id: str, courses: List[str]) -> None:
    """Saves course list directly to Supabase Cloud `assignments` table."""
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

    try:
        all_courses = {}
        if COURSES_FILE.exists():
            try:
                with COURSES_FILE.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if isinstance(existing, dict):
                        all_courses = existing
            except Exception:
                all_courses = {}
        all_courses[user_id] = courses
        with COURSES_FILE.open("w", encoding="utf-8") as f:
            json.dump(all_courses, f, indent=2)
    except Exception:
        pass


def fetch_assignments(user_id: str) -> pd.DataFrame:
    """Fetches user assignments from Supabase Cloud (filtering out config records)."""
    cfg_id = get_courses_config_id(user_id)
    rows = []

    if sb and user_id:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id).neq("title", "__SYSTEM_COURSES__").execute()
            if res and hasattr(res, "data") and res.data:
                for r in res.data:
                    if str(r.get("id")) == cfg_id:
                        continue

                    n_text, prev_st = _unpack_notes(r.get("notes"))
                    raw_course = r.get("course")

                    if isinstance(raw_course, list) and len(raw_course) > 0:
                        course_str = str(raw_course[0])
                    elif isinstance(raw_course, dict):
                        course_str = str(raw_course.get("name") or raw_course.get("title") or "GENERAL")
                    elif isinstance(raw_course, str):
                        course_str = raw_course
                    else:
                        course_str = str(raw_course) if raw_course else "GENERAL"

                    rows.append({
                        "id": str(r.get("id")),
                        "user_id": str(r.get("user_id")),
                        "title": r.get("title") or "",
                        "course": course_str.strip().upper(),
                        "due_date": r.get("due_date") or "",
                        "status": r.get("status") or "Not Started",
                        "priority": r.get("priority") or "Medium",
                        "atype": r.get("atype") or "Homework",
                        "eta": r.get("eta") or "",
                        "created_at": r.get("created_at") or "",
                        "notes": n_text,
                        "prev_status": prev_st
                    })
        except Exception as err:
            st.error(f"Supabase fetch error: {err}")

    if not rows:
        local_rows = _read_data_file()
        if isinstance(local_rows, list):
            for r in local_rows:
                if str(r.get("user_id")) == str(user_id) and r.get("title") != "__SYSTEM_COURSES__":
                    n_text, prev_st = _unpack_notes(r.get("notes"))
                    rows.append({
                        "id": str(r.get("id")),
                        "user_id": str(r.get("user_id")),
                        "title": r.get("title") or "",
                        "course": str(r.get("course") or "GENERAL").strip().upper(),
                        "due_date": r.get("due_date") or "",
                        "status": r.get("status") or "Not Started",
                        "priority": r.get("priority") or "Medium",
                        "atype": r.get("atype") or "Homework",
                        "eta": r.get("eta") or "",
                        "created_at": r.get("created_at") or "",
                        "notes": n_text,
                        "prev_status": prev_st
                    })

    if not rows:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority",
            "atype", "eta", "created_at", "notes", "prev_status"
        ])

    df = pd.DataFrame(rows)
    for c in [
        "id", "user_id", "title", "course", "due_date", "status", "priority",
        "atype", "eta", "created_at", "notes", "prev_status"
    ]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    """Upserts assignments directly into Supabase Cloud `assignments` table while preserving notes and eta."""
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
        clean["priority"] = clean.get("priority", "Medium")
        clean["atype"] = clean.get("atype", "Homework")
        clean["eta"] = str(clean.get("eta", "")).strip()
        clean["notes"] = str(clean.get("notes", "")).strip()
        clean["prev_status"] = clean.get("prev_status", "Not Started")
        clean["user_id"] = clean.get("user_id", "")
        clean["created_at"] = clean.get("created_at") or datetime.utcnow().isoformat()

        if rid in by_id:
            existing = by_id[rid]
            if isinstance(existing, dict):
                for key, value in clean.items():
                    if value is not None:
                        existing[key] = value
            by_id[rid] = existing
        else:
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
def on_checkbox_toggle(aid: str, row_dict: Dict[str, Any]):
    chk_val = st.session_state.get(f"chk_done_{aid}", False)

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


def on_status_change(aid: str, row_dict: Dict[str, Any]):
    new_status = st.session_state.get(f"status_sel_{aid}")
    if new_status:
        if new_status != "Done":
            row_dict["prev_status"] = new_status
            st.session_state[f"prev_st_{aid}"] = new_status
        row_dict["status"] = new_status
        st.session_state[f"chk_done_{aid}"] = (new_status == "Done")
        upsert_assignments([row_dict])


def on_priority_change(aid: str, row_dict: Dict[str, Any]):
    new_prio = st.session_state.get(f"prio_sel_{aid}")
    if new_prio:
        row_dict["priority"] = new_prio
        upsert_assignments([row_dict])


# -----------------------
# Date / Sort Helpers
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


def sort_df(df: pd.DataFrame, sort_by: str) -> pd.DataFrame:
    if df.empty:
        return df
    if sort_by == "Due Date (Soonest)":
        df["due_parsed"] = df["due_date"].apply(parse_date_iso_or_empty)
        return df.sort_values(by=["due_parsed"], na_position="last").drop(columns=["due_parsed"])
    if sort_by == "Priority (High → Low)":
        order = {"High": 0, "Medium": 1, "Low": 2, "": 3}
        df["p_rank"] = df["priority"].map(lambda v: order.get(str(v), 3))
        return df.sort_values(by=["p_rank"]).drop(columns=["p_rank"])
    if sort_by == "Created (Newest)":
        df["created_at_parsed"] = pd.to_datetime(df["created_at"], errors="coerce")
        return df.sort_values(by=["created_at_parsed"], ascending=False).drop(columns=["created_at_parsed"])
    return df


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
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px;
    }

    /* Completely Hide Streamlit Sidebar & Sidebar Toggle Button */
    section[data-testid="stSidebar"],
    div[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }

    /* Header Cards Styling for Terminal Auth UI */
    .auth-header-card {
        background-color: #0c1322;
        border: 1.5px solid #2563eb;
        border-radius: 12px;
        padding: 32px 24px;
        text-align: center;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.15);
    }

    .auth-header-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        letter-spacing: -0.02em;
    }

    .auth-header-subtitle {
        font-size: 0.92rem;
        color: #94a3b8;
        margin-top: 8px;
    }

    /* Terminal Input Container Box */
    .auth-form-card {
        background-color: #0c1322;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 24px 28px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
    }

    /* Custom Terminal Yellow/Dark Submit Button */
    button[key="auth_submit_btn"] {
        background-color: #1e293b !important;
        color: #fbbf24 !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        padding: 8px 16px !important;
        margin-top: 10px !important;
        width: max-content !important;
    }

    button[key="auth_submit_btn"]:hover {
        background-color: #334155 !important;
        border-color: #fbbf24 !important;
    }

    /* Auto-flex Grid Layout across all screens */
    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 12px !important;
    }

    div[data-testid="column"] {
        min-width: 330px !important;
        flex: 1 1 330px !important;
    }

    /* Header Title Styling */
    .app-title {
        font-size: 2.1rem;
        font-weight: 900;
        color: #ffffff;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 8px;
        letter-spacing: -0.02em;
    }

    .app-subtitle {
        font-size: 0.88rem;
        color: #64748b;
        margin-top: 4px;
    }

    /* Unclipped User Email Pill */
    .status-engine-pill {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 20px;
        padding: 6px 14px;
        font-size: 0.82rem;
        color: #94a3b8;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-weight: 500;
        white-space: nowrap !important;
        overflow: visible !important;
        width: max-content !important;
    }

    .green-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
    }

    /* Force All Streamlit Buttons To Display Unclipped Text */
    .stButton > button {
        white-space: nowrap !important;
        overflow: visible !important;
        text-overflow: clip !important;
        font-size: 0.82rem !important;
        padding: 5px 10px !important;
        width: 100% !important;
    }

    button[key="toolbar_clear"] {
        background-color: #064e3b !important;
        color: #34d399 !important;
        border: 1px solid #059669 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    button[key="toolbar_add"] {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    button[key="toolbar_courses"] {
        background-color: #1e293b !important;
        color: #818cf8 !important;
        border: 1px solid #312e81 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }

    button[key="toolbar_signout"] {
        background-color: #450a0a !important;
        color: #fca5a5 !important;
        border: 1px solid #9f1239 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
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
        margin: 16px 0 20px 0;
    }

    /* Card Box Container */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        padding: 14px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    }

    /* Edit Button Styling inside Card */
    button[key^="edit_btn_"] {
        padding: 2px 8px !important;
        font-size: 0.8rem !important;
        min-height: 32px !important;
        background-color: #1e1b4b !important;
        border: 1px solid #312e81 !important;
        color: #818cf8 !important;
        border-radius: 6px !important;
        min-width: 58px !important;
    }

    /* Circular Completion Checkbox */
    div[data-testid="stCheckbox"] {
        margin-top: 4px;
    }

    div[data-testid="stCheckbox"] input[type="checkbox"] {
        border-radius: 50% !important;
        width: 18px;
        height: 18px;
        accent-color: #10b981;
        cursor: pointer;
    }

    /* Subject Badge Pill */
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
        white-space: nowrap !important;
    }

    .card-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #ffffff;
        margin-top: 10px;
        margin-bottom: 2px;
        letter-spacing: -0.02em;
    }

    .card-type {
        color: #f43f5e;
        font-size: 0.82rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 4px;
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
        display: flex;
        align-items: center;
        gap: 6px;
        margin-top: 4px;
        white-space: nowrap !important;
    }

    .days-badge {
        background-color: #1e293b;
        color: #cbd5e1;
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 0.75rem;
        font-weight: 600;
        white-space: nowrap !important;
    }

    .prio-label {
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-align: right;
        margin-top: 8px;
        white-space: nowrap !important;
    }

    /* Selectbox Overrides */
    div[data-baseweb="select"] {
        border-radius: 8px !important;
        font-size: 0.82rem !important;
        min-width: 110px !important;
    }

    div[data-baseweb="select"] > div {
        padding-left: 6px !important;
        padding-right: 20px !important;
        white-space: nowrap !important;
    }

    .status-not-started div[data-baseweb="select"] {
        background-color: #2a0812 !important;
        border: 1px solid #9f1239 !important;
        color: #fca5a5 !important;
    }

    .status-in-progress div[data-baseweb="select"] {
        background-color: #2e1b04 !important;
        border: 1px solid #854d0e !important;
        color: #fde047 !important;
    }

    .status-done div[data-baseweb="select"] {
        background-color: #032b1d !important;
        border: 1px solid #065f46 !important;
        color: #34d399 !important;
    }

    .prio-low div[data-baseweb="select"] {
        border: 1px solid #059669 !important;
        color: #34d399 !important;
        background-color: #022c22 !important;
    }

    .prio-medium div[data-baseweb="select"] {
        border: 1px solid #d97706 !important;
        color: #fde047 !important;
        background-color: #2e1b04 !important;
    }

    .prio-high div[data-baseweb="select"] {
        border: 1px solid #dc2626 !important;
        color: #fca5a5 !important;
        background-color: #2a0812 !important;
    }

    .meta-row {
        color: #94a3b8;
        font-size: 0.8rem;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------
# Terminal Auth Interface (Full Screen Stacked Cards)
# -----------------------
def render_terminal_auth_page():
    c_left, c_center, c_right = st.columns([1, 1.8, 1])

    with c_center:
        # Top Blue Outlined Banner Box
        st.markdown(
            """
            <div class="auth-header-card">
                <div class="auth-header-title">🛡️ Assignment Tracker</div>
                <div class="auth-header-subtitle">Simsbury High School Assignment Portal</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Bottom Input Container Box
        st.markdown('<div class="auth-form-card">', unsafe_allow_html=True)
        
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
# Dialog Modals
# -----------------------
@dialog_decorator("Welcome! Setup Your Classes")
def show_welcome_courses_dialog(user_id: str):
    st.session_state["_show_welcome_courses_modal"] = False

    st.markdown("### 🎓 Welcome to Assignment Tracker!")
    st.write("Please list the subjects or classes you are taking this term (comma separated or line by line):")

    courses_input = st.text_area(
        "Enter your classes:",
        value="MATH, SCIENCE, ENGLISH, HISTORY",
        help="Example: MATH, SCIENCE, SPANISH, AP PHYSICS"
    )

    if st.button("Save Schedule & Start", key="save_initial_courses_btn"):
        parsed_courses = [c.strip().upper() for c in courses_input.replace("\n", ",").split(",") if c.strip()]
        if parsed_courses:
            _write_courses_file(user_id, parsed_courses)
            st.success("Classes saved successfully!")
            safe_rerun()
        else:
            st.warning("Please enter at least one class.")


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
        priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=1, key="add_priority")
        atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=0, key="add_atype")
        eta = st.text_input("Estimated Duration (e.g., 30 mins)", key="add_eta")
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
                "priority": priority,
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
        priority = st.selectbox(
            "Priority Level",
            PRIORITY_OPTIONS,
            index=(PRIORITY_OPTIONS.index(assignment_record.get("priority")) if assignment_record.get("priority") in PRIORITY_OPTIONS else 1),
            key=f"edit_priority_{aid}",
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
                "priority": priority,
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


@dialog_decorator("Manage / Change Courses")
def show_manage_courses_dialog(user_id: str):
    st.session_state["_open_manage_courses"] = False

    st.subheader("📚 Your Active Classes")
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
    else:
        st.info("No active classes found. Add your subjects below.")

    if to_remove:
        courses = [c for c in courses if c not in to_remove]
        _write_courses_file(user_id, courses)
        safe_rerun()

    st.markdown("---")
    new_course = st.text_input("Add a new course", key="new_course_field", placeholder="e.g. AP CALCULUS")
    if st.button("Add Course", key="add_course_button"):
        v = new_course.strip().upper()
        if v:
            if v not in courses:
                courses.append(v)
                _write_courses_file(user_id, courses)
                safe_rerun()
            else:
                st.warning("That class already exists.")


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
# Main Dashboard Workspace
# -----------------------
col_header_left, col_header_right = st.columns([1.0, 4.0])

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
            f'<div class="status-engine-pill"><span class="green-dot"></span> {email}</div>',
            unsafe_allow_html=True,
        )

today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(
    f'<div class="calendar-banner-box">📅 Today\'s Date: {today_str}</div>',
    unsafe_allow_html=True,
)

col_search, col_sort = st.columns([3, 1.5])
with col_search:
    search_q = st.text_input("Search tasks or subjects...", key="main_search", label_visibility="collapsed", placeholder="Search tasks or subjects...")
with col_sort:
    sort_by = st.selectbox("Sort By:", SORT_OPTIONS, index=0, key="main_sort")

if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda r: q in str(r.get("title", "")).lower() or q in str(r.get("course", "")).lower() or q in str(r.get("atype", "")).lower(), axis=1)]

df = sort_df(df, sort_by)

if df.empty:
    st.markdown("<div style='padding:60px 0; text-align:center; color:#64748b; font-size:1rem;'>🎉 No assignments found, enjoy.</div>", unsafe_allow_html=True)
else:
    cards_per_row = 3
    chunked_rows = [df.iloc[i:i + cards_per_row] for i in range(0, len(df), cards_per_row)]

    for row_df in chunked_rows:
        cols = st.columns(cards_per_row)
        for idx, (_, row) in enumerate(row_df.iterrows()):
            with cols[idx]:
                with st.container(border=True):
                    aid = row.get("id")
                    title = row.get("title") or "Untitled"
                    course = (row.get("course") or "MATH").upper()
                    atype = row.get("atype") or "Essay"
                    due_d = parse_date_iso_or_empty(row.get("due_date"))
                    due_text = format_mdy(due_d)
                    days_text, _ = days_left(due_d)

                    status = st.session_state.get(f"status_sel_{aid}") or row.get("status") or "Not Started"
                    priority = row.get("priority") or "Low"
                    row_dict = row.to_dict()

                    status_class = "status-not-started"
                    if status == "In Progress":
                        status_class = "status-in-progress"
                    elif status == "Done":
                        status_class = "status-done"

                    prio_class = "prio-low"
                    if priority == "Medium":
                        prio_class = "prio-medium"
                    elif priority == "High":
                        prio_class = "prio-high"

                    c_top1, c_top2, c_top3, c_top4 = st.columns([0.4, 1.6, 1.2, 2.2])

                    with c_top1:
                        chk_key = f"chk_done_{aid}"
                        st.checkbox(
                            "Done",
                            value=(status == "Done"),
                            key=chk_key,
                            label_visibility="collapsed",
                            on_change=on_checkbox_toggle,
                            args=(aid, row_dict)
                        )

                    with c_top2:
                        st.markdown(f"<span class='course-badge'>{course}</span>", unsafe_allow_html=True)

                    with c_top3:
                        if st.button("✏️ Edit", key=f"edit_btn_{aid}"):
                            st.session_state["_edit_assignment_id"] = aid
                            safe_rerun()

                    with c_top4:
                        st.markdown(f"<div class='{status_class}'>", unsafe_allow_html=True)
                        sel_key = f"status_sel_{aid}"
                        st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                            key=sel_key,
                            label_visibility="collapsed",
                            on_change=on_status_change,
                            args=(aid, row_dict)
                        )
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown(f"<div class='card-title'>{title}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='card-type'><span>📌</span> {atype}</div>", unsafe_allow_html=True)
                    st.markdown("<hr class='card-hr'/>", unsafe_allow_html=True)

                    c_bot1, c_bot2 = st.columns([1.5, 1.8])
                    with c_bot1:
                        st.markdown(
                            f"<div class='due-date-text'><span>📅</span> {due_text} <span class='days-badge'>{days_text}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with c_bot2:
                        prio_col1, prio_col2 = st.columns([0.9, 1.5])
                        with prio_col1:
                            st.markdown("<div class='prio-label'>PRIORITY:</div>", unsafe_allow_html=True)
                        with prio_col2:
                            st.markdown(f"<div class='{prio_class}'>", unsafe_allow_html=True)
                            prio_key = f"prio_sel_{aid}"
                            st.selectbox(
                                "Priority",
                                PRIORITY_OPTIONS,
                                index=PRIORITY_OPTIONS.index(priority) if priority in PRIORITY_OPTIONS else 0,
                                key=prio_key,
                                label_visibility="collapsed",
                                on_change=on_priority_change,
                                args=(aid, row_dict)
                            )
                            st.markdown("</div>", unsafe_allow_html=True)

                    eta = str(row.get("eta") or "").strip()
                    notes = str(row.get("notes") or "").strip()

                    if eta:
                        st.markdown(f"<div class='meta-row'>⏱️ {eta}</div>", unsafe_allow_html=True)

                    if notes:
                        note_preview = notes if len(notes) <= 140 else notes[:137] + "..."
                        st.markdown(f"<div class='meta-row'>📝 {note_preview}</div>", unsafe_allow_html=True)
