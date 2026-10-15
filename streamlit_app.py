"""
Assignment Tracker — updated UI, fixed toolbar and card layout, larger buttons, modal edit/add

Notes on fixes:
- Removed duplicate title and unified header rendering.
- Avoid calling st.rerun / st.experimental_rerun directly from inside helper render functions;
  instead button clicks set session_state flags and actions occur immediately after render.
- Enlarged and restyled buttons with CSS so labels fit.
- Narrowed assignment cards (max-width) and added gradients, shadows, badges to match screenshots.
- Ensured unique keys for buttons and stable behavior on clicks.
- Keeps Supabase auth + JSON fallback and Manage Classes feature.
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

sb: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        sb = None

# App constants / options
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
# Helpers for responses / mapping
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
# Auth helpers (safe wrappers)
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
    # simple rerun
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
# Date & formatting helpers
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
    return df  # default: spreadsheet order


# -----------------------
# Styling — carefully tuned
# -----------------------
st.markdown(
    """
    <style>
    /* Page background & defaults */
    .stApp {
        background-color: #0b1220;
        color: #e6eef9;
        font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }

    /* Make Streamlit native buttons larger and more pill-like */
    .stButton>button {
        padding: 10px 16px !important;
        font-size: 14px !important;
        border-radius: 10px !important;
        min-width: 120px;
    }

    /* toolbar group spacing */
    .toolbar-row { display:flex; gap:12px; align-items:center; justify-content:flex-end; }

    /* card styling: narrower, rounded, gradient, shadow */
    .card {
        display:inline-block;
        vertical-align: top;
        width: 320px;
        margin: 12px;
        padding: 16px;
        border-radius: 12px;
        background: linear-gradient(180deg, rgba(22,27,34,0.75), rgba(10,14,20,0.75));
        border: 1px solid rgba(255,255,255,0.03);
        box-shadow: 0 8px 24px rgba(2,6,10,0.6), inset 0 1px 0 rgba(255,255,255,0.02);
        color: #e6eef9;
    }

    .card .title { font-weight:800; font-size:18px; margin-top:6px; margin-bottom:6px; }
    .course-badge {
        display:inline-block;
        padding:6px 10px;
        border-radius:10px;
        background: linear-gradient(90deg, rgba(99,102,241,0.16), rgba(79,70,229,0.08));
        color:#c7d2fe;
        font-weight:700;
        font-size:12px;
    }
    .atype { color:#fda4af; margin-top:6px; font-weight:600; font-size:13px; }

    .pill {
        display:inline-block;
        padding:6px 10px;
        border-radius:999px;
        font-weight:700;
        font-size:12px;
    }
    .pill-not-started { background: rgba(239,68,68,0.08); color:#fca5a5; border: 1px solid rgba(239,68,68,0.06); }
    .pill-in-progress { background: rgba(250,204,21,0.06); color:#fef08a; border: 1px solid rgba(250,204,21,0.06); }
    .pill-done { background: rgba(34,197,94,0.06); color:#bbf7d0; border: 1px solid rgba(34,197,94,0.06); }

    .small-muted { color:#9ca3af; font-size:13px; }

    /* center the cards container */
    .cards-wrap { display:flex; gap:12px; flex-wrap:wrap; justify-content:flex-start; align-items:flex-start; }

    /* top banner */
    .banner {
        padding:10px;
        border-radius:8px;
        background: linear-gradient(90deg, rgba(79,70,229,0.08), rgba(56,189,248,0.03));
        color:#c7d2fe;
        text-align:center;
        margin-top:10px;
        margin-bottom:10px;
    }

    /* larger search box */
    .searchbox .stTextInput>div>label { color:#cbd5e1; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Top header + improved toolbar behavior
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
    # Single header with subtitle (no duplicate st.title)
    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown("<div style='display:flex; flex-direction:column; gap:4px;'><div style='display:flex; align-items:center; gap:12px'><div style='font-size:34px; font-weight:800'>📋 Assignment Tracker</div></div><div class='small-muted'>Live application syncing — keep your classes up to date</div></div>", unsafe_allow_html=True)
    with cols[1]:
        # toolbar buttons - use st.button so actions are wired to session_state flags
        c1, c2, c3 = st.columns([1,1,1])
        with c1:
            if st.button("🧹 Clear Completed", key="clear_completed_button"):
                st.session_state["_action_clear_completed"] = True
        with c2:
            if st.button("➕ Add Assignment", key="add_assignment_button"):
                st.session_state["_open_add_modal"] = True
        with c3:
            if st.button("📚 Manage Classes", key="manage_classes_button"):
                st.session_state["_open_manage_courses"] = True

render_top_toolbar()

# After top render, handle flags (so we do side-effects outside render function)
if st.session_state.get("_action_clear_completed", False):
    # perform clearing then rerun once
    user = current_user()
    if user:
        all_rows = _read_data_file()
        uid = user.get("id") or user.get("sub") or user.get("user_id")
        remaining = [r for r in all_rows if not (r.get("user_id") == uid and r.get("status") == "Done")]
        _write_data_file(remaining)
    st.session_state["_action_clear_completed"] = False
    st.experimental_rerun()

# Banner with today's date (auto-updates daily)
today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f"<div class='banner'>📅 Today's Matrix Operations Calendar: {today_str}</div>", unsafe_allow_html=True)

# -----------------------
# Sidebar auth UI (unchanged behavior)
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

# -----------------------
# Require signed-in user
# -----------------------
user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()
user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from Supabase user.")
    st.stop()

# -----------------------
# Manage classes modal (unchanged flow but stable)
# -----------------------
if st.session_state.get("_open_manage_courses", False):
    with st.modal("Manage Classes"):
        st.subheader("Your Classes")
        courses = _read_courses_file()
        to_remove = []
        for i, c in enumerate(courses):
            a, b = st.columns([8,1])
            with a:
                st.write(f"- {c}")
            with b:
                if st.button("Remove", key=f"remove_course_{i}"):
                    to_remove.append(c)
                    # mark removal and refresh after modal ends
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
# Search and sort row
# -----------------------
search_col, sort_col = st.columns([3,1])
with search_col:
    search_q = st.text_input("Search tasks or subjects...", key="search_q")
with sort_col:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0, key="sort_by")

# -----------------------
# Add assignment modal (state-driven)
# -----------------------
if st.session_state.get("_open_add_modal", False):
    st.session_state["_open_add_modal"] = False  # consume flag (modal will show once)
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
# Edit modal: open when session_state._edit_assignment_id is set
# -----------------------
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
# Load assignments and render cards grid (improved layout)
# -----------------------
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)
else:
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

# Apply search
if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda r: q in str(r.get("title", "")).lower() or q in str(r.get("course", "")).lower() or q in str(r.get("atype", "")).lower(), axis=1)]

# Sort
df = sort_df(df, sort_by)

# Helper to open edit modal by setting session_state id
def open_edit_modal(assign_id: str):
    st.session_state["_edit_assignment_id"] = assign_id
    # modal will open on rerun
    st.experimental_rerun()

# Render small cards container
def render_assignment_card(item: Dict[str, Any]):
    aid = item.get("id")
    course = item.get("course") or ""
    title = item.get("title") or ""
    atype = item.get("atype") or ""
    due_parsed = parse_date_iso_or_empty(item.get("due_date"))
    due_text = format_mdy(due_parsed)
    days_text, _ = days_left(due_parsed)
    priority = item.get("priority") or ""
    status = item.get("status") or ""

    status_cls = "pill-not-started"
    if status == "In Progress":
        status_cls = "pill-in-progress"
    elif status == "Done":
        status_cls = "pill-done"

    # unique action keys per card
    edit_key = f"card_edit_{aid}"
    del_key = f"card_delete_{aid}"
    done_key = f"card_done_{aid}"

    # card markup
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    # top row: badge and title
    st.markdown(f"<div style='display:flex; align-items:center; gap:10px;'><div class='course-badge'>{course}</div><div class='title'>{title}</div></div>", unsafe_allow_html=True)
    # type / notes
    st.markdown(f"<div class='atype'>📌 {atype}</div>", unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # actions row
    a1, a2, a3 = st.columns([1,1,1])
    with a1:
        if st.button("✏️ Edit", key=edit_key):
            open_edit_modal(aid)
    with a2:
        if st.button("✅ Mark Done", key=done_key):
            updated = dict(item)
            updated["status"] = "Done"
            upsert_assignments([updated])
            st.experimental_rerun()
    with a3:
        if st.button("🗑️ Delete", key=del_key):
            delete_assignment(aid)
            st.experimental_rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.04)'/>", unsafe_allow_html=True)
    # footer info row
    f1, f2 = st.columns([2,1])
    with f1:
        st.markdown(f"<div class='small-muted'>📅 {due_text} • <span style='background:rgba(255,255,255,0.02); padding:4px 8px; border-radius:6px'>{days_text}</span></div>", unsafe_allow_html=True)
    with f2:
        st.markdown(f"<div style='text-align:right'>PRIORITY: <span style='background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:8px; color:#9ae6b4'>{priority}</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Render all cards inside a wrap
st.markdown("<div class='cards-wrap'>", unsafe_allow_html=True)
if df.empty:
    st.markdown("<div style='padding:60px; text-align:center; color:#9ca3af'>🎉 GOOOOOOOODDD BOOOOYYYYY, YOU FINISHED ALL YOUR HOMEWORK, YOU GET THE A+++++++++</div>", unsafe_allow_html=True)
else:
    items = df.to_dict(orient="records")
    for item in items:
        render_assignment_card(item)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
