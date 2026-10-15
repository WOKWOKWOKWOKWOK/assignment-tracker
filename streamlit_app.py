"""
Assignment Tracker — Streamlit app with Supabase auth + JSON persistence fallback

Features in this version:
- Robust Supabase auth wrappers (supports multiple supabase-py versions)
- Centered modal for Create and Edit assignment (with date picker)
- Responsive card grid for assignments with course badge, status pill,
  title, type icon, due date (MM/DD/YYYY) and days-left indicator
- Top toolbar with Add Assignment, Clear Completed, Manage Classes
- Manage Classes modal allows adding/removing courses which update the
  Subject/Course dropdown in the assignment form
- Search & sort for assignments
- JSON fallback persistence (data.json) and separate courses.json for class list
- No debug UI shown to general users
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

# Supabase credentials MUST be stored in Streamlit secrets under [supabase]
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    SUPABASE_URL = None
    SUPABASE_KEY = None

# Create Supabase client if credentials present
sb: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        sb = None

# App constants
STATUS_OPTIONS = ["Not Started", "In Progress", "Done"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
TYPE_OPTIONS = ["Essay", "Presentation", "Homework", "Test & Quizzes", "Other"]
SORT_OPTIONS = [
    "Spreadsheet Default Order",
    "Due Date (Soonest)",
    "Priority (High → Low)",
    "Created (Newest)",
]

st.set_page_config(page_title="Assignment Tracker (Multi-user)", layout="wide")
st.title("Assignment Tracker")

# -----------------------
# Utilities
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
    """Normalize Supabase client responses into dict {error, data, raw}."""
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
        try:
            raw = _to_dict(res) or None
            return {"error": None, "data": raw, "raw": raw}
        except Exception:
            return {"error": None, "data": None, "raw": None}


def _available_auth_methods() -> List[str]:
    try:
        auth = getattr(sb, "auth", None)
        if auth is None:
            return []
        return [m for m in dir(auth) if not m.startswith("_")]
    except Exception:
        return []


# -----------------------
# Auth helpers
# -----------------------
def sign_up(email: str, password: str) -> Dict[str, Any]:
    auth = getattr(sb, "auth", None) if sb else None
    if auth is None:
        return {"error": "sb.auth is not available", "data": None, "raw": None}
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
            return {"error": "No supported sign-up method found", "data": None, "raw": None}
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None, "raw": None}


def sign_in(email: str, password: str) -> Dict[str, Any]:
    auth = getattr(sb, "auth", None) if sb else None
    if auth is None:
        return {"error": "sb.auth is not available", "data": None, "raw": None}
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
            return {"error": "No supported sign-in method found", "data": None, "raw": None}
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None, "raw": None}


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
        st.rerun()
    except Exception:
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
        # defensive fallback
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
# Helpers: date, days-left, sorting, filtering
# -----------------------
def parse_date_iso_or_empty(s: Any) -> Optional[date]:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    try:
        # Accept ISO or YYYY-MM-DD or MM/DD/YYYY
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
    # spreadsheet default -> assume insertion order (as stored)
    return df


# -----------------------
# Styling (inject CSS)
# -----------------------
st.markdown(
    """
    <style>
    /* page background */
    .stApp {
        background-color: #0f1720;
        color: #dbeafe;
    }
    .header-row {
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
    }
    .toolbar-right {
        display:flex;
        gap:10px;
        align-items:center;
    }
    .btn-primary {
        background: linear-gradient(90deg,#6d5ef8,#7b6dfb);
        color:white;
        padding:8px 14px;
        border-radius:8px;
        border: none;
    }
    .btn-ghost {
        background:transparent;
        color:#cbd5e1;
        padding:8px 12px;
        border-radius:8px;
        border:1px solid rgba(255,255,255,0.04);
    }
    .card {
        background: linear-gradient(180deg, rgba(20,25,30,0.6), rgba(12,16,20,0.6));
        border:1px solid rgba(255,255,255,0.03);
        padding:16px;
        border-radius:14px;
        box-shadow: 0 6px 20px rgba(3,5,10,0.6);
    }
    .course-badge {
        background: rgba(99,102,241,0.16);
        color:#a5b4fc;
        padding:6px 10px;
        border-radius:8px;
        font-weight:700;
        font-size:12px;
    }
    .pill {
        padding:6px 10px;
        border-radius:999px;
        font-weight:600;
        font-size:12px;
    }
    .pill-not-started { background: rgba(239,68,68,0.08); color:#fca5a5; border:1px solid rgba(239,68,68,0.06); }
    .pill-in-progress { background: rgba(250,204,21,0.06); color:#fef08a; border:1px solid rgba(250,204,21,0.06); }
    .pill-done { background: rgba(34,197,94,0.06); color:#bbf7d0; border:1px solid rgba(34,197,94,0.06); }
    .small-muted { color:#9ca3af; font-size:13px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Top header + actions
# -----------------------
def render_top_toolbar():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("<div class='header-row'><div><h2 style='margin:0; color:#e6eef9'>📋 Assignment Tracker</h2><div class='small-muted'>Live application syncing — keep your classes up to date</div></div></div>", unsafe_allow_html=True)
    with col2:
        with st.container():
            st.write("")  # spacer
            # toolbar buttons
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("🧹 Clear Completed", key="clear_completed"):
                    # remove assignments where status == Done for current user
                    user = current_user()
                    if user:
                        all_rows = _read_data_file()
                        user_id = user.get("id") or user.get("sub") or user.get("user_id")
                        remaining = [r for r in all_rows if not (r.get("user_id") == user_id and r.get("status") == "Done")]
                        _write_data_file(remaining)
                        st.experimental_rerun()
            with c2:
                if st.button("➕ Add Assignment", key="top_add"):
                    st.session_state["_open_add_modal"] = True
            with c3:
                if st.button("📚 Manage Classes", key="manage_classes"):
                    st.session_state["_open_manage_courses"] = True


render_top_toolbar()

# Banner with today's date (rotates automatically)
today_str = datetime.today().strftime("%A, %B %-d, %Y") if hasattr(datetime, "strftime") else datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f"<div style='margin-top:8px; padding:10px; border-radius:8px; background:rgba(255,255,255,0.02); color:#c7d2fe; text-align:center;'>📅 Today's Matrix Operations Calendar: {today_str}</div>", unsafe_allow_html=True)

# -----------------------
# Auth UI (sidebar)
# -----------------------
user = current_user()
if user:
    email = user.get("email") or (user.get("user_metadata") or {}).get("email")
    st.sidebar.write(f"Signed in as: {email or user.get('id') or 'unknown'}")
    if st.sidebar.button("Sign out", key="signout"):
        sign_out()
else:
    st.sidebar.header("Sign in / Sign up")
    auth_mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"])
    with st.sidebar.form("auth_form"):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_pw")
        submitted = st.form_submit_button(auth_mode)
        if submitted:
            email = email.strip()
            password = password.strip()
            if auth_mode == "Sign up":
                r = sign_up(email, password)
                err = r.get("error")
                if err:
                    st.sidebar.error(f"Sign up failed: {err}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required; then sign in.")
            else:
                r = sign_in(email, password)
                err = r.get("error")
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)
                user_obj = extract_user_from_auth_response(r)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or (data.get("session") or {}).get("user")
                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not user_obj:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or your Supabase config.")
                else:
                    st.session_state.user = user_obj
                    try:
                        st.rerun()
                    except Exception:
                        try:
                            st.experimental_rerun()
                        except Exception:
                            pass

# -----------------------
# If not signed in, stop
# -----------------------
user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from Supabase user. Inspect auth response.")
    st.stop()

# -----------------------
# Manage Classes Modal
# -----------------------
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if st.session_state["_open_manage_courses"]:
    with st.modal("Manage Classes"):
        st.subheader("Your Classes")
        courses = _read_courses_file()
        # show existing courses with remove buttons
        to_remove = []
        for i, c in enumerate(courses):
            col_a, col_b = st.columns([8, 1])
            with col_a:
                st.write(f"- {c}")
            with col_b:
                if st.button("Remove", key=f"remove_course_{i}"):
                    to_remove.append(c)
                    st.experimental_rerun()
        # remove marked
        if to_remove:
            courses = [c for c in courses if c not in to_remove]
            _write_courses_file(courses)
            st.success("Updated classes.")
            st.experimental_rerun()

        st.markdown("---")
        new_course = st.text_input("Add a new course (e.g., Math 101)")
        if st.button("Add Course"):
            v = new_course.strip()
            if v:
                courses = _read_courses_file()
                if v not in courses:
                    courses.append(v)
                    _write_courses_file(courses)
                    st.success("Added class")
                    st.experimental_rerun()
                else:
                    st.warning("That course is already in the list.")
        if st.button("Close"):
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()

# -----------------------
# Search and Sort Row
# -----------------------
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
search_col, sort_col = st.columns([3, 1])
with search_col:
    search_q = st.text_input("Search tasks or subjects...", key="search_q")
with sort_col:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0)

# -----------------------
# Add / Edit modal state
# -----------------------
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""

# Open add modal if button clicked
if st.session_state.get("_open_add_modal", False):
    # Keep it open only for this run; we'll set to False when closed
    st.session_state["_open_add_modal"] = False
    with st.modal("Create New Assignment"):
        # Build form fields
        courses = _read_courses_file()
        with st.form("add_assignment_form"):
            title = st.text_input("Assignment Name", "")
            # allow selecting existing course or typing a new one
            course_select = st.selectbox("Subject / Course (choose or type below)", options=[""] + courses, index=0)
            course_free = st.text_input("Or type a course name", value="")
            status = st.selectbox("Status", STATUS_OPTIONS, index=0)
            due = st.date_input("Due Date (MM/DD/YYYY)", value=date.today())
            priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=0)
            atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=0)
            eta = st.text_input("Estimated Duration (e.g., 30 mins)")
            notes = st.text_area("Notes", value="")
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
                # if user typed a new course, add to courses list
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
def open_edit_modal(assign_id: str):
    st.session_state["_edit_assignment_id"] = assign_id
    # We'll rerun and the modal will present since var is set
    st.experimental_rerun()


if st.session_state.get("_edit_assignment_id"):
    aid = st.session_state["_edit_assignment_id"]
    # find assignment data
    rows = _read_data_file()
    assignment = next((r for r in rows if r.get("id") == aid), None)
    if assignment:
        with st.modal("Edit Assignment Details"):
            with st.form("edit_assignment_form"):
                title = st.text_input("Assignment Name", value=assignment.get("title", ""))
                courses = _read_courses_file()
                course_select = st.selectbox("Subject / Course (choose or type below)", options=[""] + courses, index=0)
                course_free = st.text_input("Or type a course name", value=assignment.get("course", ""))
                status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(assignment.get("status")) if assignment.get("status") in STATUS_OPTIONS else 0)
                due_parsed = parse_date_iso_or_empty(assignment.get("due_date")) or date.today()
                due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed)
                priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(assignment.get("priority")) if assignment.get("priority") in PRIORITY_OPTIONS else 0)
                atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=TYPE_OPTIONS.index(assignment.get("atype")) if assignment.get("atype") in TYPE_OPTIONS else 0)
                eta = st.text_input("Estimated Duration (e.g., 30 mins)", value=assignment.get("eta", ""))
                notes = st.text_area("Notes", value=assignment.get("notes", ""))
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
                    # add course to courses list if typed
                    if course_free.strip():
                        courses = _read_courses_file()
                        if course_free.strip() not in courses:
                            courses.append(course_free.strip())
                            _write_courses_file(courses)
                    st.success("Saved")
                    st.session_state["_edit_assignment_id"] = ""
                    st.experimental_rerun()
            if st.button("Cancel"):
                st.session_state["_edit_assignment_id"] = ""
                st.experimental_rerun()
    else:
        st.session_state["_edit_assignment_id"] = ""

# -----------------------
# Load and display assignments grid
# -----------------------
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)
else:
    # refresh from disk each run to reflect external changes like classes
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

# Apply search filter
if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda row: q in str(row.get("title", "")).lower() or q in str(row.get("course", "")).lower() or q in str(row.get("atype", "")).lower(), axis=1)]

# Apply sort
df = sort_df(df, sort_by)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# Render cards in responsive grid
def render_assignment_card(row: pd.Series):
    aid = row["id"]
    course = row.get("course") or ""
    title = row.get("title") or ""
    atype = row.get("atype") or ""
    due_parsed = parse_date_iso_or_empty(row.get("due_date"))
    due_text = format_mdy(due_parsed)
    days_text, _ = days_left(due_parsed)
    priority = row.get("priority") or ""
    status = row.get("status") or ""

    # status pill class
    status_cls = "pill-not-started"
    if status == "In Progress":
        status_cls = "pill-in-progress"
    elif status == "Done":
        status_cls = "pill-done"

    # build UI
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    col1, col2 = st.columns([8, 1])
    with col1:
        st.markdown(f"<div style='display:flex; gap:10px; align-items:center;'><div class='course-badge'>{course}</div><div style='font-weight:700; font-size:18px'>{title}</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:6px; color:#cbd5e1'>📌 {atype}</div>", unsafe_allow_html=True)
    with col2:
        # small action buttons
        if st.button("✏️ Edit", key=f"edit_{aid}"):
            open_edit_modal(aid)
        if st.button("🗑️", key=f"del_{aid}"):
            delete_assignment(aid)
            st.experimental_rerun()
    st.markdown("<hr style='border-color: rgba(255,255,255,0.03)'/>", unsafe_allow_html=True)
    col3, col4, col5 = st.columns([3, 2, 2])
    with col3:
        st.markdown(f"<div style='display:flex; gap:8px; align-items:center;'><span style='font-size:13px;'>📅 {due_text}</span><span style='background:rgba(255,255,255,0.02); padding:4px 8px; border-radius:6px; font-weight:600; color:#cbd5e1'>{days_text}</span></div>", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<div style='text-align:right'>PRIORITY: <span style='background:rgba(255,255,255,0.02); padding:4px 8px; border-radius:6px; color:#9ae6b4'>{priority}</span></div>", unsafe_allow_html=True)
    with col5:
        # status pill
        st.markdown(f"<div style='text-align:right'><span class='pill {status_cls}'>{status}</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


if df.empty:
    st.markdown("<div style='padding:60px; text-align:center; color:#9ca3af'>🎉 GOOOOOOOODDD BOOOOYYYYY, YOU FINISHED ALL YOUR HOMEWORK, YOU GET THE A+++++++++</div>", unsafe_allow_html=True)
else:
    # render grid - use columns to simulate responsive layout
    cols_per_row = 3
    # responsive heuristic: narrow screens -> fewer cols. We can't read actual width, so simple heuristic: if many items, use 3.
    items = df.to_dict(orient="records")
    rows = [items[i:i+cols_per_row] for i in range(0, len(items), cols_per_row)]
    for row_items in rows:
        cols = st.columns(len(row_items))
        for c, item in zip(cols, row_items):
            with c:
                render_assignment_card(pd.Series(item))

# -----------------------
# Footer / end
# -----------------------
st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
