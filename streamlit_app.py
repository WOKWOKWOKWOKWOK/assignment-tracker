"""
Assignment Tracker — Polished visual update (final UI pass)

This Streamlit app file implements:
- Supabase-auth helpers (compatible with several supabase-py versions) + JSON fallback
- Manage Classes modal (keeps courses in courses.json)
- Centered Add / Edit modals (complete forms)
- Compact, highly-stylized assignment cards that match the requested visuals:
  - left thumbnail/preview box
  - course badge, radio selector, edit control and status dropdown
  - large title, type icon/label
  - footer with due date (MM/DD/YYYY), days-left badge, Priority select and status pill
  - precise spacing, outlines, multi-layer shadows and gradients
- Search, sort and top toolbar (Clear Completed / Add Assignment / Manage Classes)
- Inline priority and status editing (selectboxes in each card with immediate persist)
- Robust keying and session-state driven modal/action flow to avoid crashes

Drop this file into your app directory (replace your existing streamlit_app.py),
install requirements (streamlit, pandas, supabase) and run:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# Optional supabase support
try:
    from supabase import Client, create_client  # type: ignore
except Exception:
    Client = None
    create_client = None  # type: ignore

# -----------------------
# Files & config
# -----------------------
DATA_FILE = Path("data.json")
COURSES_FILE = Path("courses.json")

# Read Supabase creds from Streamlit secrets (optional)
SUPABASE_URL = None
SUPABASE_KEY = None
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

# Option lists (user-specified in conversation)
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
        m = getattr(obj, method_name, None)
        if callable(m):
            try:
                v = m()
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
# Auth wrappers (robust)
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
        u = first_user_from_mapping(response)
        if u:
            return u
        raw = response.get("raw")
        if isinstance(raw, dict):
            u = first_user_from_mapping(raw)
            if u:
                return u
        data = response.get("data")
        if isinstance(data, dict):
            u = first_user_from_mapping(data)
            if u:
                return u

    for attr in ("user", "session", "data", "raw"):
        try:
            obj = getattr(response, attr, None)
        except Exception:
            obj = None
        if obj is not None:
            if isinstance(obj, dict):
                u = first_user_from_mapping(obj)
                if u:
                    return u
            else:
                mapped = _to_dict(obj)
                if isinstance(mapped, dict):
                    u = first_user_from_mapping(mapped)
                    if u:
                        return u

    mapped = _to_dict(response)
    if isinstance(mapped, dict):
        u = first_user_from_mapping(mapped)
        if u:
            return u
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
# Persistence (JSON)
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
# Date formatting & helpers
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
# Visual CSS: carefully tuned to match provided mockups
# -----------------------
st.markdown(
    """
    <style>
    /* Page base */
    .stApp { background: linear-gradient(180deg,#081018 0%, #0b1219 100%); color:#e6eef9; font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; }

    /* Header area */
    .header-area { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:6px; }
    .app-title { font-size:34px; font-weight:900; color:#f8fafc; margin:0; display:flex; align-items:center; gap:12px; }
    .app-sub { color:#9aa6ba; font-size:14px; margin-top:6px; }

    /* Top toolbar buttons (pill with subtle borders and shadows) */
    .toolbar { display:flex; gap:12px; align-items:center; justify-content:flex-end; }
    .stButton>button {
        padding:10px 16px !important;
        font-size:14px !important;
        border-radius:12px !important;
        min-width:140px;
    }
    /* Small green primary */
    .btn-clear { background: linear-gradient(90deg,#0f7a4b,#0d8d5a) !important; color:white !important; border: none !important; box-shadow: 0 8px 18px rgba(7, 102, 66, 0.18); }
    .btn-add { background: linear-gradient(90deg,#6d5ef8,#7b6dfb) !important; color:white !important; border: none !important; box-shadow: 0 8px 18px rgba(81, 60, 230, 0.18); }

    /* Date banner */
    .date-banner { padding:12px; border-radius:10px; background: linear-gradient(90deg, rgba(99,102,241,0.06), rgba(59,130,246,0.02)); color:#bcd2ff; text-align:center; margin:12px 0; border:1px solid rgba(99,102,241,0.04); }

    /* Search + sort container */
    .search-row { display:flex; gap:18px; align-items:center; justify-content:space-between; margin-bottom:18px; }
    .search-box input { padding:14px !important; border-radius:10px !important; background: rgba(255,255,255,0.02) !important; color:#e6eef9 !important; }

    /* Cards container */
    .cards-wrap { display:flex; flex-wrap:wrap; gap:22px; align-items:flex-start; }

    /* Card: compact box like mockup */
    .card {
        width: 420px;
        background: linear-gradient(180deg, rgba(12,16,20,0.95), rgba(10,12,16,0.92));
        border-radius: 12px;
        padding: 14px;
        border: 1px solid rgba(255,255,255,0.03);
        box-shadow: 0 18px 40px rgba(2,6,23,0.6), inset 0 1px 0 rgba(255,255,255,0.012);
        transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .card:hover { transform: translateY(-6px); box-shadow: 0 28px 56px rgba(2,6,23,0.7); }

    .card-row { display:flex; gap:12px; align-items:flex-start; }
    .thumbnail {
        width:160px;
        height:84px;
        border-radius:10px;
        background: linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.003));
        border:1px solid rgba(255,255,255,0.02);
        box-shadow: inset 0 2px 6px rgba(255,255,255,0.01);
    }

    .card-content { flex:1; display:flex; flex-direction:column; gap:6px; }
    .meta-row { display:flex; gap:8px; align-items:center; justify-content:space-between; }
    .left-meta { display:flex; gap:8px; align-items:center; }
    .course-badge {
        display:inline-block; padding:6px 10px; border-radius:8px; font-weight:800; font-size:12px;
        color:#c7d2fe; background: linear-gradient(90deg, rgba(99,102,241,0.14), rgba(79,70,229,0.06)); border:1px solid rgba(99,102,241,0.06);
    }
    .title { font-weight:800; font-size:20px; color:#f8fafc; margin:0; }
    .atype { color:#fda4af; font-weight:600; font-size:13px; margin-top:4px; }

    .actions-row { display:flex; gap:12px; margin-top:8px; }
    .card .stButton>button { min-width:110px !important; padding:8px 12px !important; font-size:13px !important; border-radius:10px !important; }

    .footer { display:flex; justify-content:space-between; align-items:center; margin-top:12px; gap:12px; }
    .small-muted { color:#98a6b8; font-size:13px; }

    .days-badge {
        padding:6px 10px; border-radius:8px; background: rgba(255,255,255,0.02); color:#cbd5e1; border:1px solid rgba(255,255,255,0.02); font-weight:700;
    }

    .priority-select select {
        padding:6px 10px; border-radius:8px; background: rgba(255,255,255,0.02); color:#e6eef9;
    }

    /* status pill */
    .status-pill { display:inline-block; padding:7px 12px; border-radius:12px; font-weight:800; font-size:13px; }
    .st-not-started { background: linear-gradient(90deg, rgba(220,38,38,0.06), rgba(220,38,38,0.02)); color:#ffc4c4; border:1px solid rgba(220,38,38,0.05); }
    .st-in-progress { background: linear-gradient(90deg, rgba(234,179,8,0.06), rgba(234,179,8,0.02)); color:#fff1a8; border:1px solid rgba(234,179,8,0.05); }
    .st-done { background: linear-gradient(90deg, rgba(16,185,129,0.06), rgba(16,185,129,0.02)); color:#baf7d6; border:1px solid rgba(16,185,129,0.05); }

    /* make select boxes fit */
    select { background: rgba(255,255,255,0.015) !important; color:#e6eef9 !important; padding:6px 10px !important; border-radius:8px !important; }

    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------
# Top header and toolbar behavior (safe flags)
# -----------------------
if "_clear_completed_flag" not in st.session_state:
    st.session_state["_clear_completed_flag"] = False
if "_open_add_modal" not in st.session_state:
    st.session_state["_open_add_modal"] = False
if "_open_manage_courses" not in st.session_state:
    st.session_state["_open_manage_courses"] = False
if "_edit_assignment_id" not in st.session_state:
    st.session_state["_edit_assignment_id"] = ""

def render_header_and_toolbar():
    left, right = st.columns([3, 1])
    with left:
        st.markdown("<div class='header-area'><div><div class='app-title'>📋 Assignment Tracker</div><div class='app-sub'>Live application syncing — keep your classes up to date</div></div></div>", unsafe_allow_html=True)
    with right:
        st.markdown("<div class='toolbar'>", unsafe_allow_html=True)
        if st.button("🧹 Clear Completed", key="clear_completed"):
            st.session_state["_clear_completed_flag"] = True
        # styled add button using css class - we apply style by calling st.button then color by CSS is limited,
        # to keep color we will set style via classes that target generic buttons — we can't pass class directly,
        # but we highlight by using separate keys and rely on CSS gradients above.
        if st.button("➕ Add Assignment", key="add_assignment"):
            st.session_state["_open_add_modal"] = True
        if st.button("📚 Manage Classes", key="manage_classes"):
            st.session_state["_open_manage_courses"] = True
        st.markdown("</div>", unsafe_allow_html=True)

render_header_and_toolbar()

# Perform actions after render so we don't call rerun inside render function
if st.session_state.get("_clear_completed_flag"):
    user = current_user()
    if user:
        uid = user.get("id") or user.get("sub") or user.get("user_id")
        rows = _read_data_file()
        remaining = [r for r in rows if not (r.get("user_id") == uid and r.get("status") == "Done")]
        _write_data_file(remaining)
    st.session_state["_clear_completed_flag"] = False
    st.experimental_rerun()

# Date banner (auto-updates)
today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f"<div class='date-banner'>📅 Today's Matrix Operations Calendar: {today_str}</div>", unsafe_allow_html=True)

# -----------------------
# Sidebar auth form
# -----------------------
user = current_user()
if user:
    email = user.get("email") or (user.get("user_metadata") or {}).get("email")
    st.sidebar.markdown(f"**Signed in as:**  \n[{email}](#)")
    if st.sidebar.button("Sign out", key="sidebar_signout"):
        sign_out()
else:
    st.sidebar.header("Sign in / Sign up")
    mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"])
    with st.sidebar.form("auth_form"):
        sin_email = st.text_input("Email", key="sin_email")
        sin_pw = st.text_input("Password", type="password", key="sin_pw")
        submitted = st.form_submit_button(mode)
        if submitted:
            e = sin_email.strip()
            p = sin_pw.strip()
            if mode == "Sign up":
                r = sign_up(e, p)
                if r.get("error"):
                    st.sidebar.error(f"Sign up failed: {r.get('error')}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if needed.")
            else:
                r = sign_in(e, p)
                err = r.get("error")
                data = r.get("data")
                u = extract_user_from_auth_response(r)
                if not u and isinstance(data, dict):
                    u = data.get("user") or (data.get("session") or {}).get("user")
                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not u:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or config.")
                else:
                    st.session_state.user = u
                    try:
                        st.experimental_rerun()
                    except Exception:
                        pass

# Require sign in to proceed
user = current_user()
if not user:
    st.info("Please sign in or sign up to manage your assignments.")
    st.stop()
user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from auth response.")
    st.stop()

# -----------------------
# Manage Classes modal
# -----------------------
if st.session_state.get("_open_manage_courses", False):
    with st.modal("Manage Classes"):
        st.subheader("Manage Classes")
        courses = _read_courses_file()
        to_remove: List[str] = []
        for i, c in enumerate(courses):
            a, b = st.columns([8, 1])
            with a:
                st.write(f"• {c}")
            with b:
                if st.button("Remove", key=f"rm_course_{i}"):
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
        if st.button("Close", key="close_courses_btn"):
            st.session_state["_open_manage_courses"] = False
            st.experimental_rerun()

# -----------------------
# Search + Sort row
# -----------------------
search_col, sort_col = st.columns([3, 1])
with search_col:
    search_q = st.text_input("Search tasks or subjects...", key="main_search")
with sort_col:
    sort_by = st.selectbox("Sort Matrix By:", SORT_OPTIONS, index=0, key="main_sort")

# -----------------------
# Add Assignment modal (centered)
# -----------------------
if st.session_state.get("_open_add_modal", False):
    st.session_state["_open_add_modal"] = False
    with st.modal("Create New Assignment"):
        courses = _read_courses_file()
        with st.form("add_form"):
            title = st.text_input("Assignment Name", key="add_title")
            course_choice = st.selectbox("Subject / Course (choose)", options=[""] + courses, index=0, key="add_course_choice")
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

# -----------------------
# Edit modal (triggered by setting _edit_assignment_id)
# -----------------------
if st.session_state.get("_edit_assignment_id"):
    aid = st.session_state["_edit_assignment_id"]
    rows = _read_data_file()
    assignment = next((r for r in rows if r.get("id") == aid), None)
    if assignment:
        with st.modal("Edit Assignment"):
            with st.form("edit_form"):
                title = st.text_input("Assignment Name", value=assignment.get("title", ""), key=f"edit_title_{aid}")
                courses = _read_courses_file()
                course_choice = st.selectbox("Subject / Course (choose)", options=[""] + courses, index=0, key=f"edit_course_choice_{aid}")
                course_free = st.text_input("Or type a course name", value=assignment.get("course", ""), key=f"edit_course_free_{aid}")
                status = st.selectbox("Status", STATUS_OPTIONS, index=(STATUS_OPTIONS.index(assignment.get("status")) if assignment.get("status") in STATUS_OPTIONS else 0), key=f"edit_status_{aid}")
                due_parsed = parse_date_iso_or_empty(assignment.get("due_date")) or date.today()
                due = st.date_input("Due Date (MM/DD/YYYY)", value=due_parsed, key=f"edit_due_{aid}")
                priority = st.selectbox("Priority Level", PRIORITY_OPTIONS, index=(PRIORITY_OPTIONS.index(assignment.get("priority")) if assignment.get("priority") in PRIORITY_OPTIONS else 1), key=f"edit_priority_{aid}")
                atype = st.selectbox("Assignment Type", TYPE_OPTIONS, index=(TYPE_OPTIONS.index(assignment.get("atype")) if assignment.get("atype") in TYPE_OPTIONS else 0), key=f"edit_atype_{aid}")
                eta = st.text_input("Estimated Duration (e.g., 30 mins)", value=assignment.get("eta", ""), key=f"edit_eta_{aid}")
                notes = st.text_area("Notes", value=assignment.get("notes", ""), key=f"edit_notes_{aid}")
                submitted_edit = st.form_submit_button("Save Changes")
                if submitted_edit:
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

# -----------------------
# Load assignments
# -----------------------
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)
else:
    # refresh each run to pick up external edits
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

# Apply search
if search_q:
    q = search_q.lower()
    df = df[df.apply(lambda r: q in str(r.get("title", "")).lower() or q in str(r.get("course", "")).lower() or q in str(r.get("atype", "")).lower(), axis=1)]

# Sort
df = sort_df(df, sort_by)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# Helper: open edit modal
def open_edit(aid: str):
    st.session_state["_edit_assignment_id"] = aid
    st.experimental_rerun()

# -----------------------
# Render assignment cards (careful layout)
# -----------------------
st.markdown("<div class='cards-wrap'>", unsafe_allow_html=True)
if df.empty:
    st.markdown("<div style='padding:60px; text-align:center; color:#9ca3af'>🎉 All done — no assignments found.</div>", unsafe_allow_html=True)
else:
    items = df.to_dict(orient="records")
    for item in items:
        aid = item.get("id")
        title = item.get("title") or "(No title)"
        course = item.get("course") or "Unspecified"
        atype = item.get("atype") or ""
        due_parsed = parse_date_iso_or_empty(item.get("due_date"))
        due_text = format_mdy(due_parsed)
        days_text, _ = days_left(due_parsed)
        priority = item.get("priority") or "Medium"
        status = item.get("status") or "Not Started"

        st.markdown("<div class='card'>", unsafe_allow_html=True)
        # Top row: thumbnail + content
        st.markdown("<div class='card-row'>", unsafe_allow_html=True)
        # thumbnail placeholder
        st.markdown(f"<div class='thumbnail' aria-hidden='true'></div>", unsafe_allow_html=True)
        # content column
        # meta row: left meta (radio + course badge + title) and actions (edit + status select)
        st.markdown("<div class='card-content'>", unsafe_allow_html=True)
        # meta: radio and course badge + title
        st.markdown("<div class='meta-row'>", unsafe_allow_html=True)
        # left meta
        left, right = st.columns([7,3], gap="small")
        with left:
            c1, c2 = st.columns([1,15], gap="small")
            with c1:
                # simple radio-like circle (visual only)
                st.markdown("<div style='width:18px; height:18px; border-radius:50%; border:2px solid rgba(255,255,255,0.06);'></div>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<div style='display:flex; gap:10px; align-items:center'><div class='course-badge'>{course}</div><div class='title'>{title}</div></div>", unsafe_allow_html=True)
        # right actions: edit and status select
        with right:
            # Edit button
            if st.button("✏️ Edit", key=f"edit_btn_{aid}"):
                open_edit(aid)
            # status select inline (small)
            sel_status_key = f"status_sel_{aid}"
            # ensure session_state default for select so UI remains stable
            st.session_state.setdefault(sel_status_key, status)
            selected_status = st.selectbox("", STATUS_OPTIONS, index=STATUS_OPTIONS.index(st.session_state.get(sel_status_key, status)) if st.session_state.get(sel_status_key, status) in STATUS_OPTIONS else 0, key=sel_status_key, label_visibility="collapsed")
            # if user changed, persist
            if selected_status != status:
                updated = dict(item)
                updated["status"] = selected_status
                upsert_assignments([updated])
                st.experimental_rerun()

        st.markdown("</div>", unsafe_allow_html=True)  # meta-row

        # type row
        if atype:
            st.markdown(f"<div class='atype'>📌 {atype}</div>", unsafe_allow_html=True)

        # actions row (spaced)
        a1, a2, a3 = st.columns([1,1,1], gap="small")
        with a1:
            if st.button("✅ Mark Done", key=f"done_btn_{aid}"):
                updated = dict(item)
                updated["status"] = "Done"
                upsert_assignments([updated])
                st.experimental_rerun()
        with a2:
            if st.button("🔁 Duplicate", key=f"dup_btn_{aid}"):
                dup = dict(item)
                dup["id"] = str(uuid.uuid4())
                dup["created_at"] = datetime.utcnow().isoformat()
                upsert_assignments([dup])
                st.experimental_rerun()
        with a3:
            if st.button("🗑️ Delete", key=f"del_btn_{aid}"):
                delete_assignment(aid)
                st.experimental_rerun()

        # footer row
        st.markdown("<div class='footer'>", unsafe_allow_html=True)
        # left footer
        left_f, right_f = st.columns([3,2], gap="small")
        with left_f:
            st.markdown(f"<div class='small-muted'>📅 {due_text} &nbsp; • &nbsp; <span class='days-badge'>{days_text}</span></div>", unsafe_allow_html=True)
        with right_f:
            # Inline priority select
            prio_key = f"prio_sel_{aid}"
            st.session_state.setdefault(prio_key, priority)
            selected_prio = st.selectbox("", PRIORITY_OPTIONS, index=PRIORITY_OPTIONS.index(st.session_state.get(prio_key, priority)) if st.session_state.get(prio_key, priority) in PRIORITY_OPTIONS else 1, key=prio_key, label_visibility="collapsed")
            if selected_prio != priority:
                updated = dict(item)
                updated["priority"] = selected_prio
                upsert_assignments([updated])
                st.experimental_rerun()
            # show status pill visually as well
            pill_cls = "st-not-started"
            if status == "In Progress":
                pill_cls = "st-in-progress"
            elif status == "Done":
                pill_cls = "st-done"
            st.markdown(f"<div style='display:flex; gap:8px; align-items:center; justify-content:flex-end'><div class='small-muted' style='margin-right:6px'>PRIORITY:</div><div class='priority-badge' style='padding:6px 10px; border-radius:8px; background: rgba(255,255,255,0.01); color:#d1fae5; border:1px solid rgba(255,255,255,0.03);'>{selected_prio}</div><div class='status-pill {pill_cls}' style='margin-left:8px'>{status}</div></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)  # footer
        st.markdown("</div>", unsafe_allow_html=True)  # card-content
        st.markdown("</div>", unsafe_allow_html=True)  # card-row
        st.markdown("</div>", unsafe_allow_html=True)  # card outer

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)
