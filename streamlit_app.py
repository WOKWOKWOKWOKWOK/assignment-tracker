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

from datetime import datetime, date
import uuid
import pandas as pd
import streamlit as st
from supabase import create_client, Client

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
# Helpers
# -----------------------
def _wrap_result(res):
    if isinstance(res, dict):
        return res
    try:
        return {"error": getattr(res, "error", None), "data": getattr(res, "data", None)}
    except Exception:
        return {"error": None, "data": None}


def extract_user_from_auth_response(response):
    """
    Try many shapes of Supabase auth responses and return a user dict or None.
    """
    if response is None:
        return None

    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            user = data.get("user")
            if isinstance(user, dict):
                return user
            session = data.get("session")
            if isinstance(session, dict):
                user = session.get("user")
                if isinstance(user, dict):
                    return user

        user = response.get("user")
        if isinstance(user, dict):
            return user

        session = response.get("session")
        if isinstance(session, dict):
            user = session.get("user")
            if isinstance(user, dict):
                return user

    # object based response
    for attr in ["user", "session"]:
        try:
            obj = getattr(response, attr, None)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            return obj
        if obj is not None and hasattr(obj, "user"):
            nested = getattr(obj, "user", None)
            if isinstance(nested, dict):
                return nested

    try:
        data_obj = getattr(response, "data", None)
        if isinstance(data_obj, dict):
            user = data_obj.get("user")
            if isinstance(user, dict):
                return user
            session = data_obj.get("session")
            if isinstance(session, dict):
                user = session.get("user")
                if isinstance(user, dict):
                    return user
    except Exception:
        pass

    return None


# -----------------------
# Auth helpers
# -----------------------
def current_user():
    """
    Return the current signed-in user dict (or None).
    """
    try:
        session = sb.auth.get_session()
        user = extract_user_from_auth_response(session)
        if user:
            return user
    except Exception:
        pass

    try:
        resp = sb.auth.get_user()
        user = extract_user_from_auth_response(resp)
        if user:
            return user
    except Exception:
        pass

    return None


def sign_up(email: str, password: str):
    try:
        res = sb.auth.sign_up({"email": email, "password": password})
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_in(email: str, password: str):
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_out():
    try:
        sb.auth.sign_out()
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


def upsert_assignments(records: list):
    if not records:
        return
    try:
        return sb.table("assignments").upsert(records).execute()
    except Exception as e:
        st.error(f"Failed to write to database: {e}")
        return None


def delete_assignment_by_id(assign_id: str, user_id: str):
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
    st.sidebar.write(f"Signed in as: {user.get('email') or user.get('user_metadata', {}).get('email')}")
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
            if auth_mode == "Sign up":
                r = sign_up(email.strip(), password)
                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                if err:
                    st.sidebar.error(f"Sign up failed: {err}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required; then sign in.")
            else:
                r = sign_in(email.strip(), password)
                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)

                # Try to extract user in all common shapes
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
    t = st.text_input("Title", "")
    c = st.text_input("Course", "")
    d = st.date_input("Due date", value=None)
    s = st.selectbox("Status", STATUS_OPTIONS, index=0)
    n = st.text_area("Notes", "")
    submitted = st.form_submit_button("Add assignment")

    if submitted:
        new_row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": t.strip(),
            "course": c.strip(),
            "due_date": d.isoformat() if isinstance(d, date) else "",
            "status": s,
            "notes": n.strip(),
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
total = len(df)
in_progress = df["status"].eq("In Progress").sum() if "status" in df else 0
completed = df["status"].eq("Completed").sum() if "status" in df else 0

st.metric("Total", total)
col1, col2 = st.columns(2)
col1.metric("In Progress", in_progress)
col2.metric("Completed", completed)

st.markdown("---")

# Filters
filter_status = st.multiselect("Status", options=STATUS_OPTIONS, default=STATUS_OPTIONS)
filter_course = st.text_input("Course contains", value="")
filtered = df
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
    display_df["due_date"] = display_df["due_date"].replace("", pd.NA)

    try:
        edited = st.experimental_data_editor(display_df.drop(columns=["user_id"]), num_rows="dynamic")
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
        st.dataframe(display_df.drop(columns=["user_id"]))
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
