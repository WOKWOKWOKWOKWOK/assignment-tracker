from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# -----------------------
# App config
# -----------------------
DATA_FILE = Path("data.json")
COURSES_FILE = Path("courses.json")
DEFAULT_DOMAIN = "@simsburyschools.net"

STATUS_OPTIONS = ["Not Started", "In Progress", "Done"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
TYPE_OPTIONS = ["Essay", "Presentation", "Homework", "Test & Quizzes", "Other"]
SORT_OPTIONS = [
    "Spreadsheet Default Order",
    "Due Date (Soonest)",
    "Priority (High → Low)",
    "Created (Newest)",
]

hide_streamlit_elements = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    div[data-testid="stStatusWidget"] {visibility: hidden !important;}
    </style>
"""
st.markdown(hide_streamlit_elements, unsafe_allow_html=True)

try:
    from supabase import Client, create_client  # type: ignore
except Exception:
    Client = None
    create_client = None  # type: ignore

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

st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------
# Utility helpers
# -----------------------
def safe_rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


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
            data = mapped if isinstance(mapped, dict) else None
        raw = _to_dict(res) or None
        return {"error": err, "data": data, "raw": raw}
    except Exception:
        return {"error": None, "data": None, "raw": None}


# -----------------------
# Supabase auth
# -----------------------
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
    except Exception as exc:
        return {"error": str(exc), "data": None}


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
    except Exception as exc:
        return {"error": str(exc), "data": None}


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
            session = auth.get_user()
            user = extract_user_from_auth_response(session)
            if user:
                return user
    except Exception:
        pass
    if "user" in st.session_state:
        return st.session_state.user
    return None


# -----------------------
# Local persistence helpers
# -----------------------
def get_courses_config_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_courses_config_{user_id}"))


def invalidate_cache() -> None:
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
    courses_list: List[str] = []
    cfg_id = get_courses_config_id(user_id)

    if sb and user_id:
        try:
            res = sb.table("assignments").select("notes").eq("id", cfg_id).execute()
            if res and hasattr(res, "data") and res.data:
                raw_notes = res.data[0].get("notes")
                if raw_notes is not None:
                    parsed = json.loads(raw_notes)
                    if isinstance(parsed, list):
                        courses_list = [str(x).strip().upper() for x in parsed if str(x).strip()]
        except Exception:
            pass

    if not courses_list and sb and user_id:
        try:
            res = sb.table("assignments").select("course").eq("user_id", user_id).neq("title", "__SYSTEM_COURSES__").execute()
            if res and hasattr(res, "data") and res.data:
                c_set = set()
                for item in res.data:
                    c = item.get("course")
                    if isinstance(c, str) and c.strip() and c != "CONFIG":
                        c_set.add(c.strip().upper())
                courses_list = sorted(c_set)
        except Exception:
            pass

    if not courses_list and COURSES_FILE.exists() and user_id:
        try:
            with COURSES_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    courses_list = [str(x).strip().upper() for x in data.get(user_id, []) if str(x).strip()]
                elif isinstance(data, list):
                    courses_list = [str(x).strip().upper() for x in data if str(x).strip()]
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
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as exc:
            st.error(f"Supabase write error: {exc}")

    try:
        all_courses: Dict[str, List[str]] = {}
        if COURSES_FILE.exists():
            try:
                with COURSES_FILE.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if isinstance(existing, dict):
                        all_courses = existing
            except Exception:
                all_courses = {}
        all_courses[user_id] = [str(x).strip().upper() for x in courses if str(x).strip()]
        with COURSES_FILE.open("w", encoding="utf-8") as f:
            json.dump(all_courses, f, indent=2)
    except Exception:
        pass


def parse_date_iso_or_empty(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.strptime(value, fmt).date()
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
        df = df.copy()
        df["due_parsed"] = df["due_date"].apply(parse_date_iso_or_empty)
        return df.sort_values(by=["due_parsed"], na_position="last").drop(columns=["due_parsed"])
    if sort_by == "Priority (High → Low)":
        order = {"High": 0, "Medium": 1, "Low": 2, "": 3}
        df = df.copy()
        df["p_rank"] = df["priority"].map(lambda v: order.get(str(v), 3))
        return df.sort_values(by=["p_rank"]).drop(columns=["p_rank"])
    if sort_by == "Created (Newest)":
        df = df.copy()
        df["created_at_parsed"] = pd.to_datetime(df["created_at"], errors="coerce")
        return df.sort_values(by=["created_at_parsed"], ascending=False).drop(columns=["created_at_parsed"])
    return df


# -----------------------
# Assignment data layer
# -----------------------
def fetch_assignments(user_id: str) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    if sb and user_id:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id).neq("title", "__SYSTEM_COURSES__").execute()
            if res and hasattr(res, "data") and res.data:
                for row in res.data:
                    if str(row.get("id")) == get_courses_config_id(user_id):
                        continue
                    rows.append({
                        "id": str(row.get("id") or uuid.uuid4()),
                        "user_id": str(row.get("user_id") or user_id),
                        "title": str(row.get("title") or ""),
                        "course": str(row.get("course") or "GENERAL").strip().upper(),
                        "due_date": row.get("due_date") or "",
                        "status": row.get("status") or "Not Started",
                        "priority": row.get("priority") or "Medium",
                        "atype": row.get("atype") or "Homework",
                        "eta": row.get("eta") or "",
                        "notes": row.get("notes") or "",
                        "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
                        "prev_status": row.get("prev_status") or "Not Started",
                    })
        except Exception as exc:
            st.error(f"Supabase fetch error: {exc}")

    if not rows:
        local_rows = _read_data_file()
        for row in local_rows:
            if str(row.get("user_id")) == str(user_id) and row.get("title") != "__SYSTEM_COURSES__":
                rows.append({
                    "id": str(row.get("id") or uuid.uuid4()),
                    "user_id": str(row.get("user_id") or user_id),
                    "title": str(row.get("title") or ""),
                    "course": str(row.get("course") or "GENERAL").strip().upper(),
                    "due_date": row.get("due_date") or "",
                    "status": row.get("status") or "Not Started",
                    "priority": row.get("priority") or "Medium",
                    "atype": row.get("atype") or "Homework",
                    "eta": row.get("eta") or "",
                    "notes": row.get("notes") or "",
                    "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
                    "prev_status": row.get("prev_status") or "Not Started",
                })

    if not rows:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority",
            "atype", "eta", "notes", "created_at", "prev_status"
        ])

    df = pd.DataFrame(rows)
    for key in [
        "id", "user_id", "title", "course", "due_date", "status", "priority",
        "atype", "eta", "notes", "created_at", "prev_status"
    ]:
        if key not in df.columns:
            df[key] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    db_rows = []
    for row in rows_to_upsert:
        db_rows.append({
            "id": row.get("id"),
            "user_id": row.get("user_id"),
            "title": row.get("title", ""),
            "course": row.get("course", "GENERAL"),
            "due_date": row.get("due_date") or None,
            "status": row.get("status", "Not Started"),
            "priority": row.get("priority", "Medium"),
            "atype": row.get("atype", "Homework"),
            "eta": row.get("eta", ""),
            "notes": row.get("notes", ""),
            "prev_status": row.get("prev_status", "Not Started"),
            "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
        })

    if sb:
        try:
            sb.table("assignments").upsert(db_rows).execute()
        except Exception as exc:
            st.error(f"Supabase upsert error: {exc}")

    all_rows = _read_data_file()
    by_id = {str(r.get("id")): r for r in all_rows if isinstance(r, dict) and r.get("id") is not None}
    for row in rows_to_upsert:
        rid = str(row.get("id"))
        record = {
            "id": rid,
            "user_id": row.get("user_id"),
            "title": row.get("title", ""),
            "course": row.get("course", "GENERAL"),
            "due_date": row.get("due_date") or "",
            "status": row.get("status", "Not Started"),
            "priority": row.get("priority", "Medium"),
            "atype": row.get("atype", "Homework"),
            "eta": row.get("eta", ""),
            "notes": row.get("notes", ""),
            "prev_status": row.get("prev_status", "Not Started"),
            "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
        }
        if rid in by_id:
            by_id[rid].update(record)
        else:
            by_id[rid] = record
    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    if sb:
        try:
            sb.table("assignments").delete().eq("id", assignment_id).execute()
        except Exception as exc:
            st.error(f"Supabase delete error: {exc}")

    rows = _read_data_file()
    remaining = [r for r in rows if str(r.get("id")) != str(assignment_id)]
    _write_data_file(remaining)


# -----------------------
# Checkbox / status callbacks
# -----------------------
def on_checkbox_toggle(aid: str, row_dict: Dict[str, Any]):
    chk_val = st.session_state.get(f"chk_done_{aid}", False)
    if chk_val:
        current_status = row_dict.get("status", "Not Started")
        if current_status != "Done":
            row_dict["prev_status"] = current_status
            st.session_state[f"prev_st_{aid}"] = current_status
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
    new_priority = st.session_state.get(f"prio_sel_{aid}")
    if new_priority:
        row_dict["priority"] = new_priority
        upsert_assignments([row_dict])


# -----------------------
# Styling
# -----------------------
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0b0f19 !important;
        color: #e2e8f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    .main .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px;
    }

    section[data-testid="stSidebar"],
    div[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }

    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 12px !important;
    }

    div[data-testid="column"] {
        min-width: 330px !important;
        flex: 1 1 330px !important;
    }

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

    .domain-badge-active {
        background-color: #1e1b4b;
        border: 1px solid #4f46e5;
        color: #a5b4fc;
        padding: 9px 12px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 0.85rem;
        text-align: center;
        white-space: nowrap !important;
        margin-top: 28px;
    }

    .domain-badge-active.custom-domain {
        background-color: #064e3b;
        border: 1px solid #059669;
        color: #34d399;
    }

    .live-email-preview {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        color: #38bdf8;
        padding: 8px 14px;
        border-radius: 8px;
        font-size: 0.83rem;
        margin-bottom: 14px;
    }

    .live-email-preview.muted {
        color: #64748b;
    }

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

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
        padding: 14px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    }

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
        font-size: 0.81rem;
        margin-top: 8px;
        display: flex;
        align-items: flex-start;
        gap: 6px;
        white-space: pre-wrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------
# Dialogs
# -----------------------
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


@dialog_decorator("Sign In / Sign Up")
def show_auth_dialog():
    st.markdown("### 🔒 Account Authentication")
    mode = st.radio("Choose Action", ["Sign In", "Sign Up"], horizontal=True, key="auth_modal_mode")

    col_input, col_badge = st.columns([2.5, 1.5])
    with col_input:
        raw_email_input = st.text_input("Username or Full Email", key="auth_modal_email", placeholder="e.g. 30guptaa")

    typed_user = raw_email_input.strip()
    has_custom_domain = "@" in typed_user

    with col_badge:
        if has_custom_domain:
            st.markdown('<div class="domain-badge-active custom-domain">@custom</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="domain-badge-active">{DEFAULT_DOMAIN}</div>', unsafe_allow_html=True)

    if typed_user:
        resolved_email = typed_user if has_custom_domain else f"{typed_user}{DEFAULT_DOMAIN}"
        st.markdown(f'<div class="live-email-preview">📧 Full Account Email: <b>{resolved_email}</b></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="live-email-preview muted">📧 Full Account Email: <i>username{DEFAULT_DOMAIN}</i></div>', unsafe_allow_html=True)

    password = st.text_input("Password", type="password", key="auth_modal_pw")

    if st.button(mode, key="auth_modal_submit_btn"):
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
                st.session_state.user = {"id": str(uuid.uuid5(uuid.NAMESPACE_DNS, email_val)), "email": email_val}
                invalidate_cache()
                safe_rerun()
            else:
                st.session_state.user = user_obj
                u_id = str(user_obj.get("id") or user_obj.get("sub") or str(uuid.uuid4()))
                invalidate_cache()
                if not _read_courses_file(u_id):
                    st.session_state["_show_welcome_courses_modal"] = True
                safe_rerun()


@dialog_decorator("Welcome! Setup Your Classes")
def show_welcome_courses_dialog(user_id: str):
    st.session_state["_show_welcome_courses_modal"] = False
    st.markdown("### 🎓 Welcome to Assignment Tracker!")
    st.write("Please list the subjects or classes you are taking this term (comma separated or line by line):")
    courses_input = st.text_area(
        "Enter your classes:",
        value="MATH, SCIENCE, ENGLISH, HISTORY",
        help="Example: MATH, SCIENCE, SPANISH, AP PHYSICS",
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
        submitted = st.form_submit_button("Add Assignment")

        if submitted:
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
                "notes": notes.strip(),
                "created_at": datetime.utcnow().isoformat(),
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
    matching = df_current[df_current["id"] == aid].to_dict(orient="records") if not df_current.empty else []
    assignment_record = matching[0] if matching else None

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

        col_save, col_del = st.columns([1, 1])
        with col_save:
            updated_click = st.form_submit_button("Save Changes")
        with col_del:
            delete_click = st.form_submit_button("🗑️ Delete Assignment")

        if updated_click:
            course_val = (course_free.strip() or course_choice or "GENERAL").upper()
            updated = {
                "id": aid,
                "user_id": user_id,
                "title": title.strip() or "Untitled Assignment",
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
    to_remove: List[str] = []

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
        value = new_course.strip().upper()
        if value:
            if value not in courses:
                courses.append(value)
                _write_courses_file(user_id, courses)
                safe_rerun()
            else:
                st.warning("That class already exists.")


# -----------------------
# Auth session
# -----------------------
user = current_user()
if not user:
    show_auth_dialog()
    st.stop()

user_id = str(user.get("id") or user.get("sub") or user.get("user_id") or str(uuid.uuid4()))
email = user.get("email") or (user.get("user_metadata") or {}).get("email") or "Logged In"

if not _read_courses_file(user_id) and "_show_welcome_courses_modal" not in st.session_state:
    st.session_state["_show_welcome_courses_modal"] = True

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
# Header
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
                for assignment_id in done_ids:
                    delete_assignment(assignment_id)
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
        st.markdown(f'<div class="status-engine-pill"><span class="green-dot"></span> {email}</div>', unsafe_allow_html=True)

# -----------------------
# Date banner
# -----------------------
today_str = datetime.today().strftime("%A, %B %d, %Y")
st.markdown(f'<div class="calendar-banner-box">📅 Today\'s Date: {today_str}</div>', unsafe_allow_html=True)

# -----------------------
# Search / sort
# -----------------------
col_search, col_sort = st.columns([3, 1.5])
with col_search:
    search_q = st.text_input("Search tasks or subjects...", key="main_search", label_visibility="collapsed", placeholder="Search tasks or subjects...")
with col_sort:
    sort_by = st.selectbox("Sort By:", SORT_OPTIONS, index=0, key="main_sort")

# -----------------------
# Cards
# -----------------------
if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)

df = st.session_state.df_cached.copy()

if search_q:
    q = search_q.lower()
    df = df[df.apply(
        lambda r: q in str(r.get("title", "")).lower()
        or q in str(r.get("course", "")).lower()
        or q in str(r.get("atype", "")).lower(),
        axis=1,
    )]

df = sort_df(df, sort_by)

if df.empty:
    st.markdown("<div style='padding:60px 0; text-align:center; color:#64748b; font-size:1rem;'>🎉 No assignments found, enjoy.</div>", unsafe_allow_html=True)
else:
    cards_per_row = 3
    rows = [df.iloc[i:i + cards_per_row] for i in range(0, len(df), cards_per_row)]
    for row_group in rows:
        cols = st.columns(cards_per_row)
        for idx, (_, row) in enumerate(row_group.iterrows()):
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
                    eta = str(row.get("eta") or "").strip()
                    notes = str(row.get("notes") or "").strip()
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
                        st.checkbox(
                            "Done",
                            value=(status == "Done"),
                            key=f"chk_done_{aid}",
                            label_visibility="collapsed",
                            on_change=on_checkbox_toggle,
                            args=(aid, row_dict),
                        )
                    with c_top2:
                        st.markdown(f"<span class='course-badge'>{course}</span>", unsafe_allow_html=True)
                    with c_top3:
                        if st.button("✏️ Edit", key=f"edit_btn_{aid}"):
                            st.session_state["_edit_assignment_id"] = aid
                            safe_rerun()
                    with c_top4:
                        st.markdown(f"<div class='{status_class}'>", unsafe_allow_html=True)
                        st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                            key=f"status_sel_{aid}",
                            label_visibility="collapsed",
                            on_change=on_status_change,
                            args=(aid, row_dict),
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
                            st.selectbox(
                                "Priority",
                                PRIORITY_OPTIONS,
                                index=PRIORITY_OPTIONS.index(priority) if priority in PRIORITY_OPTIONS else 0,
                                key=f"prio_sel_{aid}",
                                label_visibility="collapsed",
                                on_change=on_priority_change,
                                args=(aid, row_dict),
                            )
                            st.markdown("</div>", unsafe_allow_html=True)

                    if eta:
                        st.markdown(f"<div class='meta-row'>⏱️ {eta}</div>", unsafe_allow_html=True)
                    if notes:
                        note_preview = notes if len(notes) <= 140 else notes[:137] + "..."
                        st.markdown(f"<div class='meta-row'>📝 {note_preview}</div>", unsafe_allow_html=True)


# End of file
"""}],