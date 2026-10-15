"""
Assignment Tracker — Streamlit app with Supabase auth + Postgres persistence

Requirements:
- Create a Supabase project and run the SQL in init_db.sql (provided).
- Add the SUPABASE URL & ANON KEY to Streamlit secrets (see instructions).
- Install requirements in requirements.txt.

This file implements:
- Sign up / sign in / sign out
- Per-user assignment CRUD (list, add, edit, delete)
- CSV export for the signed-in user's assignments
"""
from datetime import datetime, date
import uuid
import pandas as pd
import streamlit as st
from supabase import create_client, Client  # pip install supabase

# -----------------------
# Configuration / secrets
# -----------------------
# Put these into Streamlit secrets (see instructions): st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
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
# Auth helpers
# -----------------------
def current_user():
    """Return current user dict from Supabase client (or None)."""
    session = sb.auth.get_session()
    # supabase-py returns a dict with "data" key or object depending on version.
    try:
        data = session.get("data", session)
        user = data.get("session", {}).get("user") if isinstance(data, dict) else None
    except Exception:
        # Fallback: older/newer signatures
        try:
            user = session.user
        except Exception:
            user = None
    return user

def sign_in(email: str, password: str):
    # supabase-py changed method names between releases; try common ones
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        try:
            res = sb.auth.sign_in(email=email, password=password)
        except Exception as e:
            return {"error": str(e), "data": None}
    return res

def sign_up(email: str, password: str):
    try:
        res = sb.auth.sign_up({"email": email, "password": password})
    except Exception:
        try:
            res = sb.auth.sign_up(email=email, password=password)
        except Exception as e:
            return {"error": str(e), "data": None}
    return res

def sign_out():
    try:
        sb.auth.sign_out()
    except Exception:
        # Some versions return None; reset local session_state
        pass
    # clear front-end session state
    for k in ["user", "df_cached"]:
        if k in st.session_state:
            del st.session_state[k]

# -----------------------
# DB helpers
# -----------------------
def fetch_assignments(user_id: str) -> pd.DataFrame:
    if not user_id:
        return pd.DataFrame(columns=["id","title","course","due_date","status","notes","created_at","user_id"])
    res = sb.table("assignments").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    data = res.get("data") if isinstance(res, dict) else getattr(res, "data", None)
    if data is None:
        return pd.DataFrame(columns=["id","title","course","due_date","status","notes","created_at","user_id"])
    df = pd.DataFrame(data)
    # Normalize columns, ensure strings and dates
    if "due_date" in df.columns:
        df["due_date"] = df["due_date"].fillna("").astype(str)
    for col in ["notes", "title", "course", "status", "created_at", "id"]:
        if col not in df.columns:
            df[col] = ""
    return df[["id","title","course","due_date","status","notes","created_at","user_id"]]

def upsert_assignments(records: list):
    # records: list of dicts. Each must include 'user_id' set to current user's id.
    if not records:
        return
    res = sb.table("assignments").upsert(records).execute()
    return res

def delete_assignment_by_id(assign_id: str, user_id: str):
    # delete row by id where user_id matches (RLS will protect)
    res = sb.table("assignments").delete().eq("id", assign_id).eq("user_id", user_id).execute()
    return res

# -----------------------
# UI: Authentication
# -----------------------
user = current_user()
if user:
    st.sidebar.write(f"Signed in as: {user.get('email') or user.get('user_metadata', {}).get('email')}")
    if st.sidebar.button("Sign out"):
        sign_out()
        st.experimental_rerun()
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
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)
                if err:
                    st.sidebar.error(f"Sign up failed: {err}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required; then sign in.")
            else:
                r = sign_in(email.strip(), password)
                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)
                # Extract user from data/session keys
                user_obj = None
                try:
                    if isinstance(data, dict):
                        user_obj = data.get("user") or data.get("session", {}).get("user")
                except Exception:
                    pass
                if not user_obj:
                    try:
                        user_obj = r.get("user") if isinstance(r, dict) else getattr(r, "user", None)
                    except Exception:
                        user_obj = None
                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not user_obj:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or your Supabase config.")
                else:
                    # successful sign in: store user and reload
                    st.session_state.user = user_obj
                    st.experimental_rerun()

# refresh user info from session_state (if sign in stored it)
if "user" in st.session_state:
    user = st.session_state.user

if not user:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")
    st.stop()

user_id = user.get("id") or user.get("sub") or user.get("user_id")  # try common id keys
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
        # refresh
        st.session_state.df_cached = fetch_assignments(user_id)

st.markdown("---")
# Load assignments for the current user (cached in session_state to reduce calls)
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
    # show editor when available
    try:
        edited = st.experimental_data_editor(display_df.drop(columns=["user_id"]), num_rows="dynamic")
        if st.button("Save edits"):
            # Map edited rows back to include user_id
            new_df = edited.fillna("").copy()
            # ensure id exists for each row; new rows might not have id
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
            st.experimental_rerun()
    except Exception:
        st.dataframe(display_df.drop(columns=["user_id"]))
        st.info("Inline editor not available in this Streamlit version; use actions below to modify data.")

st.markdown("---")
st.subheader("Actions")
cols = st.columns([1,1,1,2])
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
        # fetch current, delete all completed for this user
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
