"""
Assignment Tracker — Polished UI pass

This file is an improved replacement for streamlit_app.py that focuses on
visual polish, clearer card boundaries, reliable button layout, and readable
text. It preserves the existing functionality:
- Supabase auth wrappers (optional, via Streamlit secrets)
- JSON fallback persistence for assignments and classes
- Add / Edit modals, Manage Classes modal
- Search, sort, clear completed, add/edit/delete/mark-done actions

What's improved in this version:
- Cards are compact (fixed max width), clearly separated with stronger
  borders, multi-layer shadows, and subtle gradients.
- Buttons are larger with consistent spacing and don't overlap.
- Priority is displayed as a clearly visible badge (never left blank).
- Title and other text wrap properly; no truncated text.
- Action buttons inside each card are spaced and readable.
- The top toolbar buttons are larger and spaced out.
- The calendar banner uses the current date (auto-rotates daily).

Notes:
- Streamlit CSS is used to style built-in Streamlit buttons and inputs.
- We keep usage of Streamlit primitives (st.button, st.columns, st.modal).
- If you want pixel-perfect matching to a mockup, we can fine-tune colors/spacing further.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# -----------------------
# Config / Files
# -----------------------
DATA_FILE = Path("data.json")
COURSES_FILE = Path("courses.json")

# Supabase credentials (optional)
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = None
    SUPABASE_KEY = None

sb: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        sb = None

# Options
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
# Small helpers
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
                v = method()
                if isinstance(v, dict):
                    return v
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
            "error": res.get("error", None) if isinstance(res, dict) else None,
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
# Auth helpers (robust)
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
    for k in ["user", "df_cached"]:
        if k in st.session_state:
            del st.session_state[k]
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
        raw = response.get("raw") if isinstance(response, dict) else None
        if isinstance(raw, dict):
            user = first_user_from_mapping(raw)
            if user:
                return user
        data = response.get("data") if isinstance(response, dict) else None
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
# Persistence (JSON fallback)
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
    rows = _read_data_file()
    if not isinstance(rows, list):
        rows = []
    user_rows = [r for r in rows if r.get("user_id") == user_id]
    if not user_rows:
        df = pd.DataFrame(columns=["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"])
    else:
        df = pd.DataFrame(user_rows)
    for c in ["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    all_rows = _read_data_file()
    if not isinstance(all_rows, list):
        all_rows = []
    by_id = {r.get("id"): r for r in all_rows}
    for row in rows_to_upsert:
        rid = row.get("id")
        if rid in by_id:
            by_id[rid].update(row)
        else:
            by_id[rid] = row
    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    all_rows = _read_data_file()
    if not isinstance(all_rows, list):
        all_rows = []
    remaining = [r for r in all_rows if r.get("id") != assignment_id]
    _write_data_file(remaining)


# -----------------------
# Date helpers & formatting
# -----------------------
def parse_date_iso_or_empty(s: Any) -> Optional[date]:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        if isinstance(s, str):
            s = s.strip()
            if not s:
                return None
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
                try:
                    return datetime.strptime(s, fmt).date()
                except Exception:
                    pass
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
# Polished styling (stronger outlines, shadows, spacing)
# -----------------------
st.markdown(
    """
    <style>
    /* Page background & base font */
    .stApp {
        background: linear-gradient(180deg,#071019,#0b1420);
        color: #e6eef9;
        font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }

    /* Header */
    .app-header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .app-title { font-size:34px; font-weight:800; color:#f8fafc; margin:0; }

    /* Toolbar buttons — larger and spaced */
    .toolbar-btn { margin-left:8px; margin-right:8px; }
    .stButton>button {
        padding:10px 16px !important;
        font-size:14px !important;
        border-radius:10px !important;
        min-width:130px !important;
    }
    /* make toolbar group align right */
    .toolbar-right { display:flex; gap:12px; align-items:center; justify-content:flex-end; }

    /* Search input bigger */
    .stTextInput>div>div>input {
        padding:14px !important;
        border-radius:10px !important;
        background: rgba(255,255,255,0.02) !important;
        color: #e6eef9 !important;
    }

    /* Cards container: centered with wrap */
    .cards-wrap { display:flex; flex-wrap:wrap; gap:18px; align-items:flex-start; justify-content:flex-start; padding-top:12px; }

    /* Card - compact fixed width, multi-layer shadows, clear outline */
    .card {
        width: 330px;
        min-height: 120px;
        padding: 16px;
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(20,25,30,0.9), rgba(12,16,20,0.85));
        border: 1px solid rgba(255,255,255,0.04);
        box-shadow:
            0 10px 30px rgba(2,6,23,0.55),
            0 2px 8px rgba(2,6,23,0.35),
            inset 0 1px 0 rgba(255,255,255,0.02);
        transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .card:hover { transform: translateY(-6px); box-shadow: 0 18px 40px rgba(2,6,23,0.65), 0 6px 12px rgba(2,6,23,0.45); }

    .course-badge {
        display:inline-block;
        padding:7px 12px;
        border-radius:10px;
        background: linear-gradient(90deg, rgba(99,102,241,0.18), rgba(79,70,229,0.08));
        color:#e6eef9; font-weight:800; font-size:12px;
        border: 1px solid rgba(99,102,241,0.08);
    }

    .title { font-weight:800; font-size:18px; margin-top:6px; margin-bottom:8px; color:#e6eef9; word-wrap:break-word; white-space:normal; }

    .atype { color:#fda4af; margin-bottom:10px; font-weight:600; font-size:13px; }

    .card .stButton>button { min-width:110px !important; padding:8px 12px !important; font-size:13px !important; margin-right:8px; border-radius:10px !important; }

    .card-actions { display:flex; gap:12px; align-items:center; margin-top:8px; margin-bottom:8px; }

    .pill {
        display:inline-block;
        padding:6px 10px;
        border-radius:999px;
        font-weight:700;
        font-size:12px;
    }
    .pill-not-started { background: rgba(239,68,68,0.06); color:#fccaca; border: 1px solid rgba(239,68,68,0.06); }
    .pill-in-progress { background: rgba(250,204,21,0.06); color:#fef08a; border: 1px solid rgba(250,204,21,0.06); }
    .pill-done { background: rgba(34,197,94,0.06); color:#bbf7d0; border: 1px solid rgba(34,197,94,0.06); }

    .priority-badge {
        display:inline-block;
        padding:6px 10px;
        border-radius:10px;
        font-weight:700;
        font-size:13px;
        background: linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
        border: 1px solid rgba(255,255,255,0.03);
        color:#d1fae5;
    }

    .small-muted { color:#9ca3af; font-size:13px; }

    /* Footer spacing */
    .card-footer { display:flex; justify-content:space-between; align-items:center; margin-top:12px; gap:12px; }

    /* Improve visual separation on the page */
    .section-divider { height:1px; background: linear-gradient(90deg, rgba(255,255,255,0.01), rgba(255,255,255,0.02)); margin-top:12px; margin-bottom:12px; border-radius:2px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Top header + toolbar
# -----------------------
if "_action_clear_completed" not in st.session_state:
    st.session_state["_action_clear_completed"] = False
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""

def render_top_toolbar():
    left_col, right_col = st.columns([3, 1])
    with left_col:
        st.markdown("<div class='app-header'><div><h1 class='app-title'>📋 Assignment Tracker</h1><div class='small-muted'>Live application syncing — keep your classes up to date</div></div></div>", unsafe_allow_html=True)
    with right_col:
        # toolbar group
        with st.container():
            st.markdown("<div class='toolbar-right'>", unsafe_allow_html=True)
            if st.button("🧹 Clear Completed", key="clear_completed_button"):
                st.session_state["_action_clear_completed"] = True
            if st.button("➕ Add Assignment", key="add_assignment_button"):
                st.session_state["_open_add_modal"] = True
            if st.button("📚 Manage Classes", key="manage_classes_button"):
                st.session_state["_open_manage_courses"] = True
            st.markdown("</div>", unsafe_allow_html=True)

render_top_toolbar()

# handle clear completed action outside render
if st.session_state.get("_action_clear_completed", False):
    user = current_user()
    if user:
        all_rows = _read_data_file()
        uid = user.get("id") or user.get("sub") or user.get("user_id")
        remaining = [r for r in all_rows if not (r.get("user_id") == uid and r.get("status") == "Done")]
        _write_data_file(remaining)
    st.session_state["_action_clear_completed"] = False
    st.experimental_rerun()

# date banner (auto-updates daily)
today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f"<div style='margin-top:10px; margin-bottom:12px; padding:10px; border-radius:8px; background: linear-gradient(90deg, rgba(79,70,229,0.06), rgba(6,182,212,0.02)); color:#c7d2fe; text-align:center;'>📅 Today's Matrix Operations Calendar: {today_str}</div>", unsafe_allow_html=True)

# -----------------------
# Sidebar auth
# -----------------------
user = current_user()
if user:
    email = user.get("email") or (user.get("user_metadata") or {}).get("email")
    st.sidebar.write(f"Signed in as: {email or user.get('id') or 'unknown'}")
    if st.sidebar.button("Sign out", key="signout_button"):
        sign_out()
else:
    st.sidebar.header("Sign in / Sign up")
    auth_mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"])
    with st.sidebar.form("auth_form"):
        s_email = st.text_input("Email", key="auth_email")
        s_password = st.text_input("Password", type="password", key="auth_pw")
        submitted = st.form_submit_button(auth_mode)
        if submitted:
            e = s_email.strip()
            p = s_password.strip()
            if auth_mode == "Sign up":
                res = sign_up(e, p)
                if res.get("error"):
                    st.sidebar.error(f"Sign up failed: {res.get('error')}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if needed.")
            else:
                res = sign_in(e, p)
                err = res.get("error")
                data = res.get("data") if isinstance(res, dict) else getattr(res, "data", None)
                user_obj = extract_user_from_auth_response(res)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or (data.get("session") or {}).get("user")
                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not user_obj:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or config.")
                else:
                    st.session_state.user = user_obj
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass

# require sign-in
user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from Supabase user.")
    st.stop()

# -----------------------
# Manage classes modal
# -----------------------
if st.session_state.get("_open_manage_courses", False):
    with st.modal("Manage Classes"):
        st.subheader("Your Classes")
        courses = _read_courses_file()
        to_remove = []
        for i, c in enumerate(courses):
            a, b = st.columns([10,1])
            with a:
                st.write(f"• {c}")
            with b:
                if st.button("Remove", key=f"remove_course_{i}"):
                    to_remove.append(c)
        if to_remove:
            courses = [c for c in courses if c not in to_remove]
            _write_courses_file(courses)
            st.success("Updated classes.")
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()
        st.markdown("---")
        new_course = st.text_input("Add a new course (e.g., Math 101)", key="new_course_field")
        if st.button("Add Course", key="add_course_btn"):
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
                    st.warning("That course is already in the list.")
        if st.button("Close", key="close_manage_courses"):
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()

# -----------------------
# Search + Sort row
# -----------------------
search_col, sort_col = st.columns([3,1])
with search_col:
    search_q = st.text_input("Search tasks or subjects...", key="search_q")
with sort_col:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0, key="sort_by")

# -----------------------
# Add modal
# -----------------------
if st.session_state.get("_open_add_modal", False):
    st.session_state["_open_add_modal"] = False
    with st.modal("Create New Assignment"):
        courses = _read_courses_file()
        with st.form("add_assignment_form"):
            title = st.text_input("Assignment Name", key="add_title")
            course_select = st.selectbox("Subject / Course (choose)", options=[""] + courses, key="add_course_select")
            course_free = st.text_input("Or type a course name", value="", key="add_course_free")
            status = st.selectbox("Status", STATUS_OPTIONS, index=0, key="add_status")
            due = st.date_input("Due Date (MM/DD/YYYY)", value=date.today(), key="add_due")
            priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=0, key="add_priority")
            atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=0, key="add_atype")
            eta = st.text_input("Estimated Duration (e.g., 30 mins)", key="add_eta")
            notes = st.text_area("Notes", value="", key="add_notes")
            submitted_add = st.form_submit_button("Add to Layout")
            if submitted_add:
                course_val = course_free.strip() or course_select or ""
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

# -----------------------
# Edit modal
# -----------------------
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""
if st.session_state.get("_edit_assignment_id"):
    aid = st.session_state["_edit_assignment_id"]
    rows = _read_data_file()
    assignment = next((r for r in rows if r.get("id") == aid), None)
    if assignment:
        with st.modal("Edit Assignment Details"):
            with st.form("edit_assignment_form"):
                title = st.text_input("Assignment Name", value=assignment.get("title", ""), key=f"edit_title_{aid}")
                courses = _read_courses_file()
                course_select = st.selectbox("Subject / Course (choose)", options=[""] + courses, index=0, key=f"edit_course_select_{aid}")
                course_free = st.text_input("Or type a course name", value=assignment.get("course", ""), key=f"edit_course_free_{aid}")
                status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(assignment.get("status")) if assignment.get("status") in STATUS_OPTIONS else 0, key=f"edit_status_{aid}")
                due_parsed = parse_date_iso_or_empty(assignment.get("due_date")) or date.today()
                due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed, key=f"edit_due_{aid}")
                priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(assignment.get("priority")) if assignment.get("priority") in PRIORITY_OPTIONS else 0, key=f"edit_priority_{aid}")
                atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=TYPE_OPTIONS.index(assignment.get("atype")) if assignment.get("atype") in TYPE_OPTIONS else 0, key=f"edit_atype_{aid}")
                eta = st.text_input("Estimated Duration (e.g., 30 mins)", value=assignment.get("eta", ""), key=f"edit_eta_{aid}")
                notes = st.text_area("Notes", value=assignment.get("notes", ""), key=f"edit_notes_{aid}")
                submitted_edit = st.form_submit_button("Save Changes")
                if submitted_edit:
                    course_val = course_free.strip() or course_select or ""
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

# -----------------------
# Load assignments and render compact cards
# -----------------------
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)
else:
    st.session_state.df_cached = fetch_assignments(user_id)
df = st.session_state.df_cached.copy()

# Search filter
search_q = st.session_state.get("search_q", "") if "search_q" in st.session_state else ""
if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda r: q in str(r.get("title", "")).lower() or q in str(r.get("course", "")).lower() or q in str(r.get("atype", "")).lower(), axis=1)]

# Sort
sort_by = st.session_state.get("sort_by", SORT_OPTIONS[0]) if "sort_by" in st.session_state else SORT_OPTIONS[0]
df = sort_df(df, sort_by)

# Helper to open edit modal
def open_edit_modal(assign_id: str):
    st.session_state["_edit_assignment_id"] = assign_id
    st.experimental_rerun()

# Card rendering: each card is placed using a simple loop; CSS keeps them compact
st.markdown("<div class='cards-wrap'>", unsafe_allow_html=True)
if df.empty:
    st.markdown("<div style='padding:60px; text-align:center; color:#9ca3af'>🎉 GOOOOOOOODDD BOOOOYYYYY, YOU FINISHED ALL YOUR HOMEWORK, YOU GET THE A+++++++++</div>", unsafe_allow_html=True)
else:
    items = df.to_dict(orient="records")
    for item in items:
        aid = item.get("id")
        course = item.get("course") or "Unspecified"
        title = item.get("title") or "(no title)"
        atype = item.get("atype") or ""
        due_parsed = parse_date_iso_or_empty(item.get("due_date"))
        due_text = format_mdy(due_parsed)
        days_text, _ = days_left(due_parsed)
        priority = item.get("priority") or "Medium"
        status = item.get("status") or "Not Started"

        # map status to pill class
        status_cls = "pill-not-started"
        if status == "In Progress":
            status_cls = "pill-in-progress"
        elif status == "Done":
            status_cls = "pill-done"

        # Render card markup (use native buttons for actions)
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"<div style='display:flex; align-items:center; gap:12px;'><div class='course-badge'>{course}</div><div style='flex:1;'><div class='title'>{title}</div></div></div>", unsafe_allow_html=True)
        if atype:
            st.markdown(f"<div class='atype'>📌 {atype}</div>", unsafe_allow_html=True)
        # Action buttons row
        btn_col1, btn_col2, btn_col3 = st.columns([1,1,1])
        with btn_col1:
            if st.button("✏️ Edit", key=f"edit_{aid}"):
                open_edit_modal(aid)
        with btn_col2:
            if st.button("✅ Mark Done", key=f"done_{aid}"):
                updated = dict(item)
                updated["status"] = "Done"
                upsert_assignments([updated])
                st.experimental_rerun()
        with btn_col3:
            if st.button("🗑️ Delete", key=f"delete_{aid}"):
                delete_assignment(aid)
                st.experimental_rerun()
        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
        # Footer: due & days left on left, priority & status on right
        footer_html = f"""
            <div class='card-footer'>
                <div class='small-muted'>📅 {due_text} &nbsp; • &nbsp; <span style='background:rgba(255,255,255,0.02); padding:6px 8px; border-radius:8px'>{days_text}</span></div>
                <div style='display:flex; gap:10px; align-items:center;'>
                    <div class='small-muted' style='margin-right:6px'>PRIORITY:</div>
                    <div class='priority-badge'>{priority}</div>
                    <div class='pill {status_cls}' style='margin-left:10px'>{status}</div>
                </div>
            </div>
        """
        st.markdown(footer_html, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
