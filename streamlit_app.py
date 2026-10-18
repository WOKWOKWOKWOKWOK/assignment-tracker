"""
Assignment Tracker — compact, polished UI version with Supabase Persistence
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

st.set_page_config(page_title="Assignment Tracker", layout="wide")

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
    try:
        st.experimental_rerun()
    except Exception:
        pass


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
# Persistence (Supabase + Local Fallback)
# -----------------------
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
    except Exception:
        pass


def _read_courses_file() -> List[str]:
    if not COURSES_FILE.exists():
        return []
    try:
        with COURSES_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_courses_file(courses: List[str]) -> None:
    try:
        with COURSES_FILE.open("w", encoding="utf-8") as f:
            json.dump(courses, f, indent=2)
    except Exception:
        pass


def fetch_assignments(user_id: str) -> pd.DataFrame:
    rows = []
    if sb:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id).execute()
            rows = res.data if hasattr(res, "data") else (res.get("data") if isinstance(res, dict) else [])
        except Exception:
            rows = []
    
    if not rows:
        local_rows = _read_data_file()
        rows = [r for r in local_rows if r.get("user_id") == user_id]

    if not rows:
        return pd.DataFrame(columns=["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"])
    
    df = pd.DataFrame(rows)
    for c in ["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    if sb:
        try:
            sb.table("assignments").upsert(rows_to_upsert).execute()
        except Exception as e:
            print("Supabase upsert error:", e)

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
    if sb:
        try:
            sb.table("assignments").delete().eq("id", assignment_id).execute()
        except Exception as e:
            print("Supabase delete error:", e)

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
        return ""
    return d.strftime("%m/%d/%Y")


def days_left(d: Optional[date]) -> Tuple[str, int]:
    if not d:
        return ("No date", 0)
    today = date.today()
    delta = (d - today).days
    if delta < 0:
        return ("Overdue", delta)
    if delta == 0:
        return ("Due Today", 0)
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
# CSS Styling
# -----------------------
st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at top right, #f4f6fc, #e9edf6);
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1250px;
    }

    .stSidebar > div:first-child {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
        box-shadow: 2px 0 10px rgba(0,0,0,0.02);
    }

    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
    }

    .assignment-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #3b82f6;
        border-radius: 12px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
        padding: 16px;
        margin-bottom: 16px;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    .assignment-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
    }

    .assignment-card .title {
        font-size: 17px;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }

    .course-badge {
        display: inline-block;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #1d4ed8;
        background: #eff6ff;
        border: 1px solid #dbeafe;
        border-radius: 6px;
        padding: 4px 8px;
        margin-right: 8px;
    }

    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }

    .title-wrap {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
        min-width: 0;
    }

    .assignment-type {
        font-size: 12px;
        font-weight: 600;
        color: #64748b;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    .type-pin {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #f43f5e;
    }

    .footer-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-top: 10px;
        border-top: 1px solid #f1f5f9;
        margin-top: 8px;
    }

    .due-text {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #475569;
        font-weight: 600;
        font-size: 12px;
    }

    .days-badge {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 3px 6px;
        font-weight: 600;
        font-size: 11px;
        color: #334155;
    }

    .status-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
    }

    .status-not-started {
        background: #fef2f2;
        color: #dc2626;
        border: 1px solid #fee2e2;
    }

    .status-in-progress {
        background: #fefce8;
        color: #ca8a04;
        border: 1px solid #fef9c3;
    }

    .status-done {
        background: #f0fdf4;
        color: #16a34a;
        border: 1px solid #dcfce7;
    }

    .top-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }

    .app-title {
        font-size: 28px;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.03em;
        margin: 0;
    }

    .app-subtitle {
        font-size: 13px;
        color: #64748b;
        margin: 0;
    }

    .banner {
        padding: 10px 16px;
        border-radius: 10px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.02);
        color: #334155;
        text-align: center;
        font-weight: 600;
        margin: 12px 0 20px 0;
    }

    .toolbar-row {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Layout / Execution
# -----------------------
if "_clear_completed_flag" not in st.session_state:
    st.session_state["_clear_completed_flag"] = False
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""

def render_header():
    left, right = st.columns([2.5, 1.5])
    with left:
        st.markdown(
            """
            <div class="top-header">
                <div class="title-stack">
                    <div class="app-title">🚀 Assignment Tracker</div>
                    <div class="app-subtitle">Stay on top of your classes with synced workspace management</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="toolbar-row">', unsafe_allow_html=True)
        col_c, col_a, col_m = st.columns(3)
        with col_c:
            if st.button("🧹 Clear", key="toolbar_clear", help="Clear completed tasks"):
                st.session_state["_clear_completed_flag"] = True
        with col_a:
            if st.button("➕ Add", key="toolbar_add", help="Add new assignment"):
                st.session_state["_open_add_modal"] = True
        with col_m:
            if st.button("📚 Classes", key="toolbar_classes", help="Manage courses"):
                st.session_state["_open_manage_courses"] = True
        st.markdown("</div>", unsafe_allow_html=True)

render_header()

if st.session_state.get("_clear_completed_flag", False):
    user = current_user()
    if user:
        uid = user.get("id") or user.get("sub") or user.get("user_id")
        rows = _read_data_file()
        remaining = [r for r in rows if not (r.get("user_id") == uid and r.get("status") == "Done")]
        _write_data_file(remaining)
    st.session_state["_clear_completed_flag"] = False
    st.experimental_rerun()

today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f"<div class='banner'>📅 Today: {today_str}</div>", unsafe_allow_html=True)

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
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass

user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user ID from the signed-in user.")
    st.stop()

if st.session_state.get("_open_manage_courses", False):
    with st.modal("Manage Classes"):
        st.subheader("Your Classes")
        courses = _read_courses_file()
        to_remove: List[str] = []
        for i, c in enumerate(courses):
            col_a, col_b = st.columns([7, 1])
            with col_a:
                st.write(f"• {c}")
            with col_b:
                if st.button("Remove", key=f"remove_course_{i}"):
                    to_remove.append(c)
        if to_remove:
            courses = [c for c in courses if c not in to_remove]
            _write_courses_file(courses)
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()

        st.markdown("---")
        new_course = st.text_input("Add a new course", key="new_course_field")
        if st.button("Add Course", key="add_course_button"):
            v = new_course.strip()
            if v:
                courses = _read_courses_file()
                if v not in courses:
                    courses.append(v)
                    _write_courses_file(courses)
                    st.success("Added class")
                    st.session_state["_open_manage_courses"] = False
                    st.experimental_rerun()
                else:
                    st.warning("That class already exists.")
        if st.button("Close", key="close_manage_classes"):
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()

search_col, sort_col = st.columns([2.2, 1])
with search_col:
    search_q = st.text_input("Search tasks or subjects...", key="main_search", label_visibility="collapsed", placeholder="🔍 Search tasks or subjects...")
with sort_col:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0, key="main_sort", label_visibility="collapsed")

if st.session_state.get("_open_add_modal", False):
    st.session_state["_open_add_modal"] = False
    with st.modal("Create New Assignment"):
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
                course_val = course_free.strip() or course_choice or ""
                new_row = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "title": title.strip(),
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
                    courses = _read_courses_file()
                    if course_free.strip() not in courses:
                        courses.append(course_free.strip())
                        _write_courses_file(courses)
                st.success("Added assignment")
                st.experimental_rerun()

if st.session_state.get("_edit_assignment_id"):
    aid = st.session_state["_edit_assignment_id"]
    df_current = fetch_assignments(user_id)
    assignment = df_current[df_current["id"] == aid].to_dict(orient="records")
    assignment = assignment[0] if assignment else None
    if assignment:
        with st.modal("Edit Assignment Details"):
            with st.form("edit_assignment_form"):
                title = st.text_input("Assignment Name", value=assignment.get("title", ""), key=f"edit_title_{aid}")
                courses = _read_courses_file()
                course_choice = st.selectbox("Subject / Course", options=[""] + courses, index=0, key=f"edit_course_choice_{aid}")
                course_free = st.text_input("Or type a course name", value=assignment.get("course", ""), key=f"edit_course_free_{aid}")
                status = st.selectbox("Status", STATUS_OPTIONS, index=(STATUS_OPTIONS.index(assignment.get("status")) if assignment.get("status") in STATUS_OPTIONS else 0), key=f"edit_status_{aid}")
                due_parsed = parse_date_iso_or_empty(assignment.get("due_date")) or date.today()
                due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed, key=f"edit_due_{aid}")
                priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=(PRIORITY_OPTIONS.index(assignment.get("priority")) if assignment.get("priority") in PRIORITY_OPTIONS else 1), key=f"edit_priority_{aid}")
                atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=(TYPE_OPTIONS.index(assignment.get("atype")) if assignment.get("atype") in TYPE_OPTIONS else 0), key=f"edit_atype_{aid}")
                eta = st.text_input("Estimated Duration (e.g., 30 mins)", value=assignment.get("eta", ""), key=f"edit_eta_{aid}")
                notes = st.text_area("Notes", value=assignment.get("notes", ""), key=f"edit_notes_{aid}")
                updated_click = st.form_submit_button("Save Changes")
                if updated_click:
                    course_val = course_free.strip() or course_choice or ""
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
                    if course_free.strip():
                        courses = _read_courses_file()
                        if course_free.strip() not in courses:
                            courses.append(course_free.strip())
                            _write_courses_file(courses)
                    st.success("Saved")
                    st.session_state["_edit_assignment_id"] = ""
                    st.experimental_rerun()
            if st.button("Cancel", key=f"cancel_edit_{aid}"):
                st.session_state["_edit_assignment_id"] = ""
                st.experimental_rerun()
    else:
        st.session_state["_edit_assignment_id"] = ""

df = fetch_assignments(user_id)

if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda row: q in str(row.get("title", "")).lower() or q in str(row.get("course", "")).lower() or q in str(row.get("atype", "")).lower(), axis=1)]

df = sort_df(df, sort_by)

def open_edit_modal(aid: str):
    st.session_state["_edit_assignment_id"] = aid
    st.experimental_rerun()

st.markdown("<div class='cards-wrap'>", unsafe_allow_html=True)
if df.empty:
    st.markdown("<div style='padding:50px 0; text-align:center; color:#64748b;'>🎉 No assignments yet — your workspace is clear.</div>", unsafe_allow_html=True)
else:
    for _, row in df.iterrows():
        aid = row.get("id")
        title = row.get("title") or "(No title)"
        course = row.get("course") or "Unspecified"
        atype = row.get("atype") or "Other"
        due_d = parse_date_iso_or_empty(row.get("due_date"))
        due_text = format_mdy(due_d)
        days_text, _ = days_left(due_d)
        status = row.get("status") or "Not Started"
        priority = row.get("priority") or "Medium"

        status_cls = "status-not-started"
        if status == "In Progress":
            status_cls = "status-in-progress"
        elif status == "Done":
            status_cls = "status-done"

        st.markdown("<div class='assignment-card'>", unsafe_allow_html=True)

        st.markdown("<div class='card-top'>", unsafe_allow_html=True)
        col_left, col_right = st.columns([4, 1.1])
        with col_left:
            st.markdown(
                f"""
                <div class='title-wrap'>
                    <span class='course-badge'>{course}</span>
                    <div class='title'>{title}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_right:
            if st.button("✏️ Edit", key=f"edit_{aid}"):
                open_edit_modal(aid)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown(
            f"<div class='assignment-type'><span class='type-pin'></span>{atype}</div>",
            unsafe_allow_html=True,
        )

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("✅ Mark Done", key=f"done_{aid}"):
                updated = row.to_dict()
                updated["status"] = "Done"
                upsert_assignments([updated])
                st.experimental_rerun()
        with c2:
            if st.button("🔁 Copy", key=f"copy_{aid}"):
                dup = row.to_dict()
                dup["id"] = str(uuid.uuid4())
                dup["created_at"] = datetime.utcnow().isoformat()
                upsert_assignments([dup])
                st.experimental_rerun()
        with c3:
            if st.button("🗑️ Delete", key=f"delete_{aid}"):
                delete_assignment(aid)
                st.experimental_rerun()

        st.markdown("<div class='footer-row'>", unsafe_allow_html=True)
        leftf, rightf = st.columns([3, 2.2])
        with leftf:
            st.markdown(f"<div class='due-text'><span>📅</span> {due_text} <span class='days-badge'>{days_text}</span></div>", unsafe_allow_html=True)
        with rightf:
            prio_key = f"prio_sel_{aid}"
            st.session_state.setdefault(prio_key, priority)
            selected_prio = st.selectbox("Priority", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(st.session_state.get(prio_key, priority)) if st.session_state.get(prio_key, priority) in PRIORITY_OPTIONS else 1, key=prio_key, label_visibility="collapsed")
            if selected_prio != priority:
                updated = row.to_dict()
                updated["priority"] = selected_prio
                upsert_assignments([updated])
                st.experimental_rerun()
            st.markdown(f"<div style='margin-top:6px; text-align:right;'><span class='status-pill {status_cls}'>{status}</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
