"""
Assignment Tracker — Streamlit app

Run locally:
pip install -r requirements.txt
streamlit run streamlit_app.py
"""
from datetime import datetime
import json
import os
import uuid

import pandas as pd
import streamlit as st

DATA_FILE = "data.json"
STATUS_OPTIONS = ["Not Started", "In Progress", "Completed"]


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                rows = json.load(f)
            return pd.DataFrame(rows)
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            return pd.DataFrame(columns=cols())
    else:
        return pd.DataFrame(columns=cols())


def save_data(df: pd.DataFrame):
    try:
        records = df.to_dict(orient="records")
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Failed to save data: {e}")


def cols():
    return ["id", "title", "course", "due_date", "status", "notes", "created_at"]


def make_empty_row():
    return {
        "id": str(uuid.uuid4()),
        "title": "",
        "course": "",
        "due_date": "",
        "status": "Not Started",
        "notes": "",
        "created_at": datetime.utcnow().isoformat(),
    }


st.set_page_config(page_title="Assignment Tracker", layout="wide")
st.title("Assignment Tracker (Streamlit)")

# Top-level layout: left sidebar for adding / filters, main area for table & details
with st.sidebar:
    st.header("Add assignment")
    with st.form("add_form", clear_on_submit=True):
        t = st.text_input("Title", "")
        c = st.text_input("Course", "")
        d = st.date_input("Due date", value=None)
        s = st.selectbox("Status", STATUS_OPTIONS, index=0)
        n = st.text_area("Notes", "")
        submitted = st.form_submit_button("Add assignment")
        if submitted:
            df = st.session_state.get("df", load_data())
            row = make_empty_row()
            row.update({
                "title": t.strip(),
                "course": c.strip(),
                "due_date": d.isoformat() if d else "",
                "status": s,
                "notes": n.strip(),
            })
            df = pd.concat([pd.DataFrame([row]), df], ignore_index=True)
            save_data(df)
            st.session_state.df = df
            st.success("Added assignment")

    st.markdown("---")
    st.header("Filters")
    filter_status = st.multiselect("Status", options=STATUS_OPTIONS, default=STATUS_OPTIONS)
    filter_course = st.text_input("Course contains", value="")
    st.button("Refresh", on_click=lambda: st.session_state.update({"reload": True}))

# Load data (into session state so edits persist while app instance runs)
if "df" not in st.session_state or st.session_state.get("reload"):
    st.session_state.df = load_data()
    st.session_state.reload = False

df = st.session_state.df.copy()

# Summary stats
total = len(df)
in_progress = df["status"].eq("In Progress").sum() if "status" in df else 0
completed = df["status"].eq("Completed").sum() if "status" in df else 0

st.metric("Total", total, delta=None)
col1, col2 = st.columns(2)
col1.metric("In Progress", in_progress)
col2.metric("Completed", completed)

st.markdown("---")

# Apply filters
if filter_course:
    df = df[df["course"].str.contains(filter_course, case=False, na=False)]
if filter_status:
    df = df[df["status"].isin(filter_status)]

# Show table and allow edit
st.subheader("Assignments")
if df.empty:
    st.info("No assignments yet. Add one from the sidebar.")
else:
    # Show a human-friendly due_date column
    display_df = df.copy()
    display_df["due_date"] = display_df["due_date"].replace("", pd.NA)
    display_df = display_df[["id", "title", "course", "due_date", "status", "notes", "created_at"]]

    # Use experimental_data_editor if available for inline edits; otherwise show a table and an edit flow
    try:
        edited = st.experimental_data_editor(display_df, num_rows="dynamic")
        if st.button("Save edits"):
            # edited is a DataFrame-like object
            new_df = edited.copy()
            # Keep created_at if missing
            new_df["created_at"] = new_df["created_at"].fillna("")
            # Replace df in session and save
            st.session_state.df = new_df
            save_data(new_df)
            st.success("Saved changes")
    except Exception:
        st.dataframe(display_df)
        st.info("Use the controls in the sidebar to add items. Use the actions below to modify data.")

# Actions: delete, clear completed, export
st.markdown("---")
st.subheader("Actions")
cols = st.columns([1, 1, 1, 2])
with cols[0]:
    delete_id = st.text_input("Delete by id", "")
    if st.button("Delete assignment"):
        if not delete_id:
            st.warning("Provide an assignment id to delete (copy id from table).")
        else:
            df_all = st.session_state.get("df", load_data())
            before = len(df_all)
            df_all = df_all[df_all["id"] != delete_id]
            if len(df_all) < before:
                st.session_state.df = df_all
                save_data(df_all)
                st.success("Assignment deleted")
            else:
                st.warning("No assignment found with that id.")
with cols[1]:
    if st.button("Clear completed"):
        df_all = st.session_state.get("df", load_data())
        df_all = df_all[df_all["status"] != "Completed"]
        st.session_state.df = df_all
        save_data(df_all)
        st.success("Cleared completed assignments")
with cols[2]:
    if st.button("Export CSV"):
        df_all = st.session_state.get("df", load_data())
        csv = df_all.to_csv(index=False)
        st.download_button("Download CSV", data=csv, file_name="assignments.csv", mime="text/csv")
with cols[3]:
    if st.button("Reset demo data"):
        demo = [
            {
                "id": str(uuid.uuid4()),
                "title": "Essay draft",
                "course": "English 101",
                "due_date": (datetime.utcnow().date().isoformat()),
                "status": "In Progress",
                "notes": "First draft due next week",
                "created_at": datetime.utcnow().isoformat(),
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Problem set 6",
                "course": "CS 101",
                "due_date": (datetime.utcnow().date().isoformat()),
                "status": "Not Started",
                "notes": "",
                "created_at": datetime.utcnow().isoformat(),
            },
        ]
        df_demo = pd.DataFrame(demo)
        st.session_state.df = df_demo
        save_data(df_demo)
        st.success("Demo data loaded")

st.markdown("### Notes on persistence")
st.info(
    "This app saves assignments to a local file data.json in the app folder. On Streamlit Community Cloud this file will persist while the instance is running but can be lost on redeploys or when the instance is recycled. "
    "For production persistence, connect to an external database (Postgres, Supabase, Google Sheets, etc.) or use a cloud-backed storage solution."
)