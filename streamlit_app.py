"""
Assignment Tracker — Dark Matrix Overlay UI

This version keeps 100% of the Supabase auth and local JSON fallback persistence
logic intact while updating the UI to match the compact dark matrix theme.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

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

# Modal decorator setup replacing invalid st.modal
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

st.set_page_config(page_title="Assignment Tracker", page_icon="📋", layout="wide")

# -----------------------
# Utility helpers
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


# -----------------------
# Auth helpers
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
# Persistence
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


def _read_courses_file() -> List[str]:
    if not COURSES_FILE.exists():
        return ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]
    try:
        with COURSES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if data else ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]
    except Exception:
        return ["MATH", "SCIENCE", "ENGLISH", "HISTORY"]


def _write_courses_file(courses: List[str]) -> None:
    try:
        with COURSES_FILE.open("w", encoding="utf-8") as f:
            json.dump(courses, f, indent=2)
    except Exception:
        pass


def fetch_assignments(user_id: str) -> pd.DataFrame:
    rows = _read_data_file()
    if not isinstance(rows, list):
        rows = []
    rows = [r for r in rows if r.get("user_id") == user_id]
    if not rows:
        return pd.DataFrame(columns=["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"])
    df = pd.DataFrame(rows)
    for c in ["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    all_rows = _read_data_file()
    by_id = {r.get("id"): r for r in all_rows if isinstance(r, dict)}
    for row in rows_to_upsert:
        rid = row.get("id")
        if rid in by_id:
            by_id[rid].update(row)
        else:
            by_id[rid] = row
    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    rows = _read_data_file()
    remaining = [r for r in rows if r.get("id") != assignment_id]
    _write_data_file(remaining)


# -----------------------
# Date / sort helpers
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
        return "10/15/2026"
    return d.strftime("%m/%d/%Y")


def days_left(d: Optional[date]) -> Tuple[str, int]:
    if not d:
        return ("0d left", 0)
    today = date.today()
    delta = (d - today).days
    if delta < 0:
        return ("Overdue", delta)
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
# CSS Styling (Matches Image Overlay)
# -----------------------
st.markdown(
    """
    <style>
    /* Dark Theme Canvas */
    .stApp {
        background-color: #0b0f19 !important;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    .main .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 3rem !important;
        max-width: 1280px;
    }

    /* Sidebar Dark Theme */
    .stSidebar > div:first-child {
        background-color: #0d121f !important;
        border-right: 1px solid #1e293b;
    }

    /* Title Styling */
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

    /* Toolbar Badges & Actions */
    .status-engine-pill {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 20px;
        padding: 6px 14px;
        font-size: 0.8rem;
        color: #94a3b8;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-weight: 500;
    }

    .green-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        display: inline-block;
    }

    /* Top Action Buttons Custom Look */
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

    /* Card Box Styling */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        padding: 14px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    }

    /* Inside Card Elements */
    .course-badge {
        background-color: #1e1b4b;
        color: #818cf8;
        border: 1px solid #312e81;
        border-radius: 6px;
        padding: 2px 8px;
        font-weight: 700;
        font-size: 0.72rem;
        letter-spacing: 0.04em;
        display: inline-block;
    }

    .card-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #ffffff;
        margin-top: 8px;
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
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-align: right;
        margin-top: 6px;
    }

    /* Selectbox inside card tweaks */
    div[data-baseweb="select"] {
        background-color: #0b0f19 !important;
        border-radius: 8px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Modal Dialogs
# -----------------------
@dialog_decorator("Create New Assignment")
def show_add_assignment_dialog(user_id: str):
    courses = _read_courses_file()
    with st.form("add_assignment_form"):
        title = st.text_input("Assignment Name", key="add_title")
        course_choice = st.selectbox("Subject / Course", options=[""] + courses, index=0, key="add_course_choice")
        course_free = st.text_input("Or type a course name", value="", key="add_course_free")
        status = st.selectbox("Status", STATUS_OPTIONS, index=0, key="add_status")
        due = st.date_input("Due Date (MM/DD/YYYY)", value=date.today(), key="add_due")
        priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=1, key="add_priority")
        atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=0, key="add_atype")
        eta = st.text_input("Estimated Duration (e.g., 30 mins)", key="add_eta")
        notes = st.text_area("Notes", value="", key="add_notes")
        submitted_add = st.form_submit_button("Add to Layout")

        if submitted_add:
            course_val = (course_free.strip() or course_choice or "MATH").upper()
            new_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": title.strip() or "12345",
                "course": course_val.strip(),
                "due_date": due.isoformat() if isinstance(due, date) else "",
                "status": status,
                "priority": priority,
                "atype": atype,
                "eta": eta.strip(),
                "created_at": datetime.utcnow().isoformat(),
                "notes": notes.strip(),
            }
            upsert_assignments([new_row])
            if course_free.strip():
                c_list = _read_courses_file()
                if course_free.strip().upper() not in c_list:
                    c_list.append(course_free.strip().upper())
                    _write_courses_file(c_list)
            st.session_state["_open_add_modal"] = False
            safe_rerun()


@dialog_decorator("Edit Assignment Details")
def show_edit_assignment_dialog(user_id: str, aid: str):
    rows = _read_data_file()
    assignment = next((r for r in rows if r.get("id") == aid), None)
    if not assignment:
        st.error("Assignment not found.")
        return

    courses = _read_courses_file()
    with st.form("edit_assignment_form"):
        title = st.text_input("Assignment Name", value=assignment.get("title", ""), key=f"edit_title_{aid}")
        course_choice = st.selectbox("Subject / Course", options=[""] + courses, index=0, key=f"edit_course_choice_{aid}")
        course_free = st.text_input("Or type a course name", value=assignment.get("course", ""), key=f"edit_course_free_{aid}")
        status = st.selectbox("Status", STATUS_OPTIONS, index=(STATUS_OPTIONS.index(assignment.get("status")) if assignment.get("status") in STATUS_OPTIONS else 0), key=f"edit_status_{aid}")
        due_parsed = parse_date_iso_or_empty(assignment.get("due_date")) or date.today()
        due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed, key=f"edit_due_{aid}")
        priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=(PRIORITY_OPTIONS.index(assignment.get("priority")) if assignment.get("priority") in PRIORITY_OPTIONS else 1), key=f"edit_priority_{aid}")
        atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=(TYPE_OPTIONS.index(assignment.get("atype")) if assignment.get("atype") in TYPE_OPTIONS else 0), key=f"edit_atype_{aid}")
        eta = st.text_input("Estimated Duration", value=assignment.get("eta", ""), key=f"edit_eta_{aid}")
        notes = st.text_area("Notes", value=assignment.get("notes", ""), key=f"edit_notes_{aid}")
        
        c_save, c_del = st.columns([1, 1])
        with c_save:
            updated_click = st.form_submit_button("Save Changes")
        with c_del:
            delete_click = st.form_submit_button("🗑️ Delete Assignment")

        if updated_click:
            course_val = (course_free.strip() or course_choice or "MATH").upper()
            updated = {
                "id": aid,
                "user_id": user_id,
                "title": title.strip(),
                "course": course_val.strip(),
                "due_date": due.isoformat() if isinstance(due, date) else "",
                "status": status,
                "priority": priority,
                "atype": atype,
                "eta": eta.strip(),
                "created_at": assignment.get("created_at") or datetime.utcnow().isoformat(),
                "notes": notes.strip(),
            }
            upsert_assignments([updated])
            st.session_state["_edit_assignment_id"] = ""
            safe_rerun()

        if delete_click:
            delete_assignment(aid)
            st.session_state["_edit_assignment_id"] = ""
            safe_rerun()


@dialog_decorator("Manage Classes")
def show_manage_courses_dialog():
    st.subheader("Your Classes")
    courses = _read_courses_file()
    to_remove = []
    for i, c in enumerate(courses):
        col_a, col_b = st.columns([6, 2])
        with col_a:
            st.write(f"• **{c}**")
        with col_b:
            if st.button("Remove", key=f"remove_course_{i}"):
                to_remove.append(c)

    if to_remove:
        courses = [c for c in courses if c not in to_remove]
        _write_courses_file(courses)
        st.session_state["_open_manage_courses"] = False
        safe_rerun()

    st.markdown("---")
    new_course = st.text_input("Add a new course", key="new_course_field")
    if st.button("Add Course", key="add_course_button"):
        v = new_course.strip().upper()
        if v:
            if v not in courses:
                courses.append(v)
                _write_courses_file(courses)
                st.session_state["_open_manage_courses"] = False
                safe_rerun()
            else:
                st.warning("That class already exists.")


# -----------------------
# Sidebar Sign In / Sign Up (Supabase Auth)
# -----------------------
user = current_user()

if user:
    email = user.get("email") or (user.get("user_metadata") or {}).get("email")
    st.sidebar.write(f"Signed in as:\n**{email or user.get('id') or 'unknown'}**")
    if st.sidebar.button("Sign out", key="sidebar_signout"):
        sign_out()
else:
    st.sidebar.header("Sign in / Sign up")
    mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"])
    with st.sidebar.form("auth_form"):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_pw")
        submitted = st.form_submit_button(mode)
        if submitted:
            email = email.strip()
            password = password.strip()
            if mode == "Sign up":
                res = sign_up(email, password)
                if res.get("error"):
                    st.sidebar.error(f"Sign up failed: {res.get('error')}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required.")
            else:
                res = sign_in(email, password)
                err = res.get("error")
                data = res.get("data") if isinstance(res, dict) else getattr(res, "data", None)
                user_obj = extract_user_from_auth_response(res)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or (data.get("session") or {}).get("user")
                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not user_obj:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or Supabase config.")
                else:
                    st.session_state.user = user_obj
                    safe_rerun()

# Stop if not signed in
user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user ID from the signed-in user.")
    st.stop()

# -----------------------
# State Flags & Dialog Triggers
# -----------------------
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""

if st.session_state.get("_open_add_modal", False):
    show_add_assignment_dialog(user_id)

if st.session_state.get("_edit_assignment_id"):
    show_edit_assignment_dialog(user_id, st.session_state["_edit_assignment_id"])

if st.session_state.get("_open_manage_courses", False):
    show_manage_courses_dialog()

# -----------------------
# Top Header & Actions
# -----------------------
col_header_left, col_header_right = st.columns([2.5, 2])

with col_header_left:
    st.markdown(
        """
        <div>
            <div class="app-title">📋 Assignment Tracker 📝</div>
            <div class="app-subtitle">Live application syncing instantly with your spreadsheet tracker system. Best Google Sheets Overlay!</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_header_right:
    btn_col1, btn_col2, btn_col3 = st.columns([1.2, 1.3, 1.4])
    with btn_col1:
        if st.button("🧹 Clear Completed", key="toolbar_clear"):
            rows = _read_data_file()
            remaining = [r for r in rows if not (r.get("user_id") == user_id and r.get("status") == "Done")]
            _write_data_file(remaining)
            safe_rerun()
    with btn_col2:
        if st.button("➕ Add Assignment", key="toolbar_add"):
            st.session_state["_open_add_modal"] = True
            safe_rerun()
    with btn_col3:
        st.markdown(
            '<div class="status-engine-pill"><span class="green-dot"></span> Secure Link Engine</div>',
            unsafe_allow_html=True,
        )

# -----------------------
# Calendar Banner
# -----------------------
today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(
    f'<div class="calendar-banner-box">📅 Today\'s Matrix Operations Calendar: {today_str}</div>',
    unsafe_allow_html=True,
)

# -----------------------
# Search & Sort Toolbar
# -----------------------
col_search, col_sort = st.columns([3, 1.5])
with col_search:
    search_q = st.text_input("Search tasks or subjects...", key="main_search", label_visibility="collapsed", placeholder="Search tasks or subjects...")
with col_sort:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0, key="main_sort")

# -----------------------
# Assignment Cards Grid
# -----------------------
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

# Search Filter
if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda r: q in str(r.get("title", "")).lower() or q in str(r.get("course", "")).lower() or q in str(r.get("atype", "")).lower(), axis=1)]

# Sort
df = sort_df(df, sort_by)

if df.empty:
    st.markdown("<div style='padding:60px 0; text-align:center; color:#64748b; font-size:1rem;'>🎉 No assignments found — your matrix is clear.</div>", unsafe_allow_html=True)
else:
    # Render 3 cards per row
    cards_per_row = 3
    chunked_rows = [df.iloc[i:i + cards_per_row] for i in range(0, len(df), cards_per_row)]

    for row_df in chunked_rows:
        cols = st.columns(cards_per_row)
        for idx, (_, row) in enumerate(row_df.iterrows()):
            with cols[idx]:
                with st.container(border=True):
                    aid = row.get("id")
                    title = row.get("title") or "12345"
                    course = (row.get("course") or "MATH").upper()
                    atype = row.get("atype") or "Essay"
                    due_d = parse_date_iso_or_empty(row.get("due_date"))
                    due_text = format_mdy(due_d)
                    days_text, _ = days_left(due_d)
                    status = row.get("status") or "Not Started"
                    priority = row.get("priority") or "Low"
                    row_dict = row.to_dict()

                    # Top Card Row: Radio circle, Subject Badge, Edit button, Status selector
                    c_top1, c_top2, c_top3, c_top4 = st.columns([0.4, 1.8, 0.9, 1.8])
                    with c_top1:
                        st.markdown("<span style='font-size:16px; color:#475569;'>◯</span>", unsafe_allow_html=True)
                    with c_top2:
                        st.markdown(f"<span class='course-badge'>{course}</span>", unsafe_allow_html=True)
                    with c_top3:
                        if st.button("✏️ Edit", key=f"edit_btn_{aid}"):
                            st.session_state["_edit_assignment_id"] = aid
                            safe_rerun()
                    with c_top4:
                        new_status = st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                            key=f"status_sel_{aid}",
                            label_visibility="collapsed",
                        )
                        if new_status != status:
                            row_dict["status"] = new_status
                            upsert_assignments([row_dict])
                            safe_rerun()

                    # Card Title
                    st.markdown(f"<div class='card-title'>{title}</div>", unsafe_allow_html=True)

                    # Assignment Type with Pin
                    st.markdown(f"<div class='card-type'><span>📌</span> {atype}</div>", unsafe_allow_html=True)

                    # Divider
                    st.markdown("<hr class='card-hr'/>", unsafe_allow_html=True)

                    # Footer Row: Date & Priority
                    c_bot1, c_bot2 = st.columns([1.6, 1.4])
                    with c_bot1:
                        st.markdown(
                            f"<div class='due-date-text'><span>📅</span> {due_text} <span class='days-badge'>{days_text}</span></div>",
                            unsafe_allow_html=True,
                        )
                    with c_bot2:
                        prio_col1, prio_col2 = st.columns([1, 1.2])
                        with prio_col1:
                            st.markdown("<div class='prio-label'>PRIORITY:</div>", unsafe_allow_html=True)
                        with prio_col2:
                            new_prio = st.selectbox(
                                "Priority",
                                PRIORITY_OPTIONS,
                                index=PRIORITY_OPTIONS.index(priority) if priority in PRIORITY_OPTIONS else 0,
                                key=f"prio_sel_{aid}",
                                label_visibility="collapsed",
                            )
                            if new_prio != priority:
                                row_dict["priority"] = new_prio
                                upsert_assignments([row_dict])
                                safe_rerun()
