"""
Assignment Tracker — Streamlit app with Supabase auth + JSON persistence fallback

This version:
- removes debug output from the app UI
- keeps robust sign-in / sign-up support for different supabase-py versions
- handles multiple Supabase response shapes without failing on "could not extract user"
- uses JSON storage as a simple fallback for assignment data
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# -----------------------
# Configuration / secrets
# -----------------------
DATA_FILE = Path("data.json")

try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    st.error("Supabase credentials are not configured. Add them to Streamlit secrets as [supabase].")
    st.stop()

# Create Supabase client
try:
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"Failed to create Supabase client: {e}")
    st.stop()

STATUS_OPTIONS = ["Not Started", "In Progress", "Completed"]
st.set_page_config(page_title="Assignment Tracker (Multi-user)", layout="wide")
st.title("Assignment Tracker (Multi-user)")

# -----------------------
# Helpers
# -----------------------
def _to_dict(obj: Any) -> Optional[Dict[str, Any]]:
    """Convert common object-like values into a dict when possible."""
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
    """
    Normalize different Supabase response shapes into a dict with:
    - error
    - data
    - raw

    Important: preserve nested user/session data when Supabase returns it in
    a different structure so we can still extract the signed-in user.
    """
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


def extract_user_from_auth_response(response: Any) -> Optional[Dict[str, Any]]:
    """
    Try many shapes of Supabase auth responses and return a user dict or None.

    Handles:
    - {"data": {"user": {...}}}
    - {"user": {...}}
    - {"session": {"user": {...}}}
    - object with .data / .user / .session
    """
    if response is None:
        return None

    def first_user_from_mapping(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(obj, dict):
            return None

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

    # dict response
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

    # object response
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

    # full object -> dict
    mapped = _to_dict(response)
    if isinstance(mapped, dict):
        user = first_user_from_mapping(mapped)
        if user:
            return user

    return None


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
    auth = getattr(sb, "auth", None)
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
    auth = getattr(sb, "auth", None)
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
        auth = getattr(sb, "auth", None)
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


def current_user() -> Optional[Dict[str, Any]]:
    """Return the current signed-in user dict (or None)."""
    try:
        auth = getattr(sb, "auth", None)
        if auth is not None and hasattr(auth, "get_session"):
            session = auth.get_session()
            user = extract_user_from_auth_response(session)
            if user:
                return user
    except Exception:
        pass

    try:
        auth = getattr(sb, "auth", None)
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
# Simple JSON persistence fallback
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


def fetch_assignments(user_id: str) -> pd.DataFrame:
    rows = _read_data_file()
    user_rows = [r for r in rows if r.get("user_id") == user_id]
    if not user_rows:
        df = pd.DataFrame(columns=["id", "user_id", "title", "course", "due_date", "status", "notes", "created_at"])
    else:
        df = pd.DataFrame(user_rows)

    for c in ["id", "user_id", "title", "course", "due_date", "status", "notes", "created_at"]:
        if c not in df.columns:
            df[c] = ""

    return df


def upsert_assignments(rows: List[Dict[str, Any]]) -> None:
    all_rows = _read_data_file()
    by_id = {r.get("id"): r for r in all_rows}
    for row in rows:
        rid = row.get("id")
        if rid in by_id:
            by_id[rid].update(row)
        else:
            by_id[rid] = row
    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    all_rows = _read_data_file()
    remaining = [r for r in all_rows if r.get("id") != assignment_id]
    _write_data_file(remaining)


# -----------------------
# UI: Authentication
# -----------------------
user = current_user()
if user:
    email = user.get("email") or (user.get("user_metadata") or {}).get("email")
    st.sidebar.write(f"Signed in as: {email or user.get('id') or 'unknown'}")
    if st.sidebar.button("Sign out"):
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

                # Try the raw fallback too:
                if not user_obj and isinstance(r, dict):
                    raw = r.get("raw")
                    if isinstance(raw, dict):
                        user_obj = extract_user_from_auth_response(raw)

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
# App main UI (requires authentication)
# -----------------------
user = current_user()
if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from Supabase user. Inspect auth response.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.header("Add assignment")

with st.sidebar.form("add_form", clear_on_submit=True):
    title = st.text_input("Title", "")
    course = st.text_input("Course", "")
    due_date = st.date_input("Due date", value=None)
    status = st.selectbox("Status", STATUS_OPTIONS, index=0)
    notes = st.text_area("Notes", "")
    submitted = st.form_submit_button("Add assignment")

    if submitted:
        new_row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title.strip(),
            "course": course.strip(),
            "due_date": due_date.isoformat() if isinstance(due_date, date) else "",
            "status": status,
            "notes": notes.strip(),
            "created_at": datetime.utcnow().isoformat(),
        }
        upsert_assignments([new_row])
        st.success("Added assignment")
        st.session_state.df_cached = fetch_assignments(user_id)

st.markdown("---")

if "df_cached" not in st.session_state:
    st.session_state.df_cached = fetch_assignments(user_id)
df = st.session_state.df_cached.copy()

# Summary stats
if "status" in df.columns:
    total = len(df)
    in_progress = int(df["status"].eq("In Progress").sum())
    completed = int(df["status"].eq("Completed").sum())
else:
    total = in_progress = completed = 0

c1, c2, c3 = st.columns(3)
c1.metric("Total assignments", total)
c2.metric("In progress", in_progress)
c3.metric("Completed", completed)

st.subheader("Your assignments")

if df.empty:
    st.info("No assignments yet. Add one from the sidebar.")
else:
    df_display = df[["id", "title", "course", "due_date", "status", "notes", "created_at"]].copy()
    df_display = df_display.sort_values("created_at", ascending=False)
    st.dataframe(df_display.reset_index(drop=True), use_container_width=True)

    for _, row in df_display.iterrows():
        with st.expander(f"{row['title']} — {row['course']}"):
            st.write("Due:", row["due_date"])
            st.write("Status:", row["status"])
            st.write("Notes:", row["notes"])
            col_a, col_b = st.columns([1, 1])

            if col_a.button("Delete", key=f"del_{row['id']}"):
                delete_assignment(row["id"])
                st.session_state.df_cached = fetch_assignments(user_id)
                st.success("Deleted assignment")
                st.rerun()

            if col_b.button("Mark Completed", key=f"complete_{row['id']}"):
                updated = dict(row)
                updated["status"] = "Completed"
                upsert_assignments([updated])
                st.session_state.df_cached = fetch_assignments(user_id)
                st.success("Marked completed")
                st.rerun()
