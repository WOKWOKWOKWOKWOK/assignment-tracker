"""
Assignment Tracker — Streamlit app with Supabase auth + Postgres persistence

Requirements:
- Create a Supabase project and run the SQL in init_db.sql (not included here).
- Add the Supabase URL & ANON KEY to Streamlit secrets.
- Install requirements in requirements.txt.

Example Streamlit secrets:
[supabase]
url = "https://YOURPROJECT.supabase.co"
key = "YOUR_ANON_KEY"
"""

from __future__ import annotations

from datetime import datetime, date
import uuid
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# -----------------------
# Configuration / secrets
# -----------------------
try:
    SUPABASE_URL = st.secrets["supabase"]["url"]
    SUPABASE_KEY = st.secrets["supabase"]["key"]
except Exception:
    st.error("Supabase credentials are not configured. Add them to Streamlit secrets as [supabase].")
    st.stop()

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

STATUS_OPTIONS = ["Not Started", "In Progress", "Completed"]
st.set_page_config(page_title="Assignment Tracker (Multi-user)", layout="wide")
st.title("Assignment Tracker (Multi-user)")


# -----------------------
# Utilities
# -----------------------
def _wrap_result(res: Any) -> dict:
    if isinstance(res, dict):
        return res
    try:
        return {"error": getattr(res, "error", None), "data": getattr(res, "data", None)}
    except Exception:
        return {"error": None, "data": None}


def _to_dict(obj: Any) -> dict | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    # Common supabase objects may expose .dict() or .model_dump()
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
        return dict(obj.__dict__)
    return None


def extract_user_from_auth_response(response: Any) -> dict | None:
    """
    Accept many Supabase auth response shapes and return a user dict or None.
    """
    candidates: list[Any] = []

    if response is None:
        return None

    candidates.append(response)

    if isinstance(response, dict):
        candidates.append(response.get("data"))
        candidates.append(response.get("user"))
        candidates.append(response.get("session"))
    else:
        candidates.append(getattr(response, "data", None))
        candidates.append(getattr(response, "user", None))
        candidates.append(getattr(response, "session", None))

    seen = set()
    for item in candidates:
        if item is None:
            continue
        key = id(item)
        if key in seen:
            continue
        seen.add(key)

        item_dict = _to_dict(item)
        if item_dict is not None:
            # Search for nested user/session dictionaries anywhere in this object
            # e.g. {"data": {"user": {...}}} or {"user": {...}}
            for key_name in ("user", "session", "data"):
                value = item_dict.get(key_name)
                if isinstance(value, dict):
                    user = value.get("user")
                    if isinstance(user, dict):
                        return user
                    if isinstance(value, dict):
                        session_user = value.get("session", {}).get("user") if isinstance(value.get("session"), dict) else None
                        if isinstance(session_user, dict):
                            return session_user
                if isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, dict):
                            nested_user = entry.get("user")
                            if isinstance(nested_user, dict):
                                return nested_user

            # plain user dict at top level
            if isinstance(item_dict.get("user"), dict):
                return item_dict["user"]
            session = item_dict.get("session")
            if isinstance(session, dict):
                user = session.get("user")
                if isinstance(user, dict):
                    return user

        # object-attribute fallback
        for attr_name in ("user", "session", "data"):
            try:
                value = getattr(item, attr_name, None)
            except Exception:
                value = None
            if isinstance(value, dict):
                user = value.get("user")
                if isinstance(user, dict):
                    return user
                session = value.get("session")
                if isinstance(session, dict):
                    nested_user = session.get("user")
                    if isinstance(nested_user, dict):
                        return nested_user
            if value is not None and hasattr(value, "user"):
                nested = getattr(value, "user", None)
                if isinstance(nested, dict):
                    return nested
                nested_obj = _to_dict(nested)
                if isinstance(nested_obj, dict):
                    return nested_obj

    return None


def current_user() -> dict | None:
    """Return the current signed-in user dict (or None)."""
    # Prefer get_user() because it works for the active session and is common in supabase-py.
    for method_name in ["get_user", "get_session"]:
        try:
            method = getattr(sb.auth, method_name, None)
            if method is None:
                continue
            response = method()
            user = extract_user_from_auth_response(response)
            if user:
                return user
        except Exception:
            pass

    return None


def sign_up(email: str, password: str) -> dict:
    try:
        # supabase-py versions differ here; support both.
        if hasattr(sb.auth, "sign_up"):
            res = sb.auth.sign_up({"email": email, "password": password})
        else:
            res = sb.auth.sign_up_with_password({"email": email, "password": password})
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_in(email: str, password: str) -> dict:
    try:
        if hasattr(sb.auth, "sign_in_with_password"):
            res = sb.auth.sign_in_with_password({"email": email, "password": password})
        elif hasattr(sb.auth, "sign_in"):
            res = sb.auth.sign_in({"email": email, "password": password})
        else:
            raise AttributeError("No supported Supabase sign-in method found.")
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_out() -> None:
    try:
        sb.auth.sign_out()
    except Exception:
        pass

    for key in ["user", "df_cached"]:
        if key in st.session_state:
            del st.session_state[key]

    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


# -----------------------
# DB helpers
# -----------------------
def fetch_assignments(user_id: str) -> pd.DataFrame:
    if not user_id:
        return pd.DataFrame(columns=["id", "title", "course", "due_date", "status", "notes", "created_at", "user_id"])

    try:
        res = sb.table("assignments").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    except Exception:
        return pd.DataFrame(columns=["id", "title", "course", "due_date", "status", "notes", "created_at", "user_id"])

    if isinstance(res, dict):
        data = res.get("data")
    else:
        data = getattr(res, "data", None)

    if data is None:
        return pd.DataFrame(columns=["id", "title", "course", "due_date", "status", "notes", "created_at", "user_id"])

    df = pd.DataFrame(data)
    if "due_date" in df.columns:
        df["due_date"] = df["due_date"].fillna("").astype(str)
    for col in ["notes", "title", "course", "status", "created_at", "id"]:
        if col not in df.columns:
            df[col] = ""
    if "user_id" not in df.columns:
        df["user_id"] = user_id

    return df[["id", "title", "course", "due_date", "status", "notes", "created_at", "user_id"]]


def upsert_assignments(records: list[dict]) -> Any:
    if not records:
        return None
    try:
        return sb.table("assignments").upsert(records).execute()
    except Exception as e:
        st.error(f"Failed to write to database: {e}")
        return None


def delete_assignment_by_id(assign_id: str, user_id: str) -> Any:
    try:
        return sb.table("assignments").delete().eq("id", assign_id).eq("user_id", user_id).execute()
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return None


# -----------------------
# UI: Authentication
# -----------------------
user = current_user()
if user:
    st.sidebar.write(f"Signed in as: {user.get('email') or user.get('user_metadata', {}).get('email') or 'Unknown user'}")
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
                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                if err:
                    st.sidebar.error(f"Sign up failed: {err}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required; then sign in.")
            else:
                r = sign_in(email, password)
                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)

                user_obj = extract_user_from_auth_response(r)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or data.get("session", {}).get("user")

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

if "user" in st.session_state:
    user = st.session_state.user

if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")
if not user_id:
    st.error("Could not determine user id from Supabase user. Inspect auth response.")
    st.stop()

# -----------------------
# Main app UI (authenticated)
# -----------------------
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
    in_progress = df["status"].eq("In Progress").sum()
    completed = df["status"].eq("Completed").sum()
else:
    total = 0
    in_progress = 0
    completed = 0

st.metric("Total", total)
col1, col2 = st.columns(2)
col1.metric("In Progress", in_progress)
col2.metric("Completed", completed)

st.markdown("---")

# Filters
filter_status = st.multiselect("Status", options=STATUS_OPTIONS, default=STATUS_OPTIONS)
filter_course = st.text_input("Course contains", value="")
filtered = df.copy()
if not filtered.empty and "course" in filtered.columns:
    if filter_course:
        filtered = filtered[filtered["course"].str.contains(filter_course, case=False, na=False)]
    if filter_status:
        filtered = filtered[filtered["status"].isin(filter_status)]

# Display / edit
st.subheader("Assignments (your data)")
if filtered.empty:
    st.info("No assignments yet. Add one from the sidebar.")
else:
    display_df = filtered.copy()
    if "due_date" in display_df.columns:
        display_df["due_date"] = display_df["due_date"].replace("", pd.NA)

    try:
        # Newer Streamlit uses st.data_editor; older versions use st.experimental_data_editor
        if hasattr(st, "data_editor"):
            edited = st.data_editor(display_df.drop(columns=["user_id"], errors="ignore"), num_rows="dynamic")
        else:
            edited = st.experimental_data_editor(display_df.drop(columns=["user_id"], errors="ignore"), num_rows="dynamic")

        if st.button("Save edits"):
            new_df = edited.fillna("").copy()
            records = []
            for _, row in new_df.iterrows():
                rid = row.get("id") or str(uuid.uuid4())
                rec = {
                    "id": rid,
                    "user_id": user_id,
                    "title": row.get("title", ""),
                    "course": row.get("course", ""),
                    "due_date": (row.get("due_date") or "") if not pd.isna(row.get("due_date")) else "",
                    "status": row.get("status", "Not Started"),
                    "notes": row.get("notes", ""),
                    "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
                }
                records.append(rec)
            upsert_assignments(records)
            st.success("Saved changes")
            st.session_state.df_cached = fetch_assignments(user_id)
            try:
                st.rerun()
            except Exception:
                try:
                    st.experimental_rerun()
                except Exception:
                    pass
    except Exception:
        st.dataframe(display_df.drop(columns=["user_id"], errors="ignore"))
        st.info("Inline editor not available in this Streamlit version; use actions below to modify data.")

st.markdown("---")
st.subheader("Actions")
cols = st.columns([1, 1, 1, 2])

with cols[0]:
    delete_id = st.text_input("Delete by id", "")
    if st.button("Delete assignment"):
        if not delete_id:
            st.warning("Provide an assignment id to delete (copy id from table).")
        else:
            delete_assignment_by_id(delete_id, user_id)
            st.session_state.df_cached = fetch_assignments(user_id)
            st.success("Deleted (if it existed)")

with cols[1]:
    if st.button("Clear completed"):
        to_delete = st.session_state.df_cached[st.session_state.df_cached["status"] == "Completed"]["id"].tolist()
        for aid in to_delete:
            delete_assignment_by_id(aid, user_id)
        st.session_state.df_cached = fetch_assignments(user_id)
        st.success("Cleared completed assignments")

with cols[2]:
    if st.button("Export CSV"):
        csv = st.session_state.df_cached.to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="assignments.csv", mime="text/csv")

with cols[3]:
    if st.button("Reset demo data"):
        demo = [
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": "Essay draft",
                "course": "English 101",
                "due_date": date.today().isoformat(),
                "status": "In Progress",
                "notes": "First draft due next week",
                "created_at": datetime.utcnow().isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "title": "Problem set 6",
                "course": "CS 101",
                "due_date": date.today().isoformat(),
                "status": "Not Started",
                "notes": "",
                "created_at": datetime.utcnow().isoformat(),
            },
        ]
        upsert_assignments(demo)
        st.session_state.df_cached = fetch_assignments(user_id)
        st.success("Demo data loaded")

st.markdown("### Notes on persistence")
st.info("This app stores assignments in Supabase Postgres under the 'assignments' table. Each user only sees their own rows (enforced by Row Level Security).")
