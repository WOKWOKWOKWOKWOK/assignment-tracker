import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date

# ---------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Your Google Apps Script Web App Executable URL
GAS_URL = "https://script.google.com/a/macros/simsburyschools.net/s/AKfycbzF4gggoAuw3EN6IJU6z-K9ay6cWCdicMXVfMD2VeI-6ShPaT5laDJGmCZkTCeMombx/exec"

# ---------------------------------------------------------
# API HELPER FUNCTIONS (GOOGLE APPS SCRIPT INTEGRATION)
# ---------------------------------------------------------
def fetch_assignments():
    """Fetch assignments from Google Apps Script Web App (doGet)."""
    try:
        response = requests.get(GAS_URL, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return pd.DataFrame(data)
            elif isinstance(data, dict) and "data" in data:
                return pd.DataFrame(data["data"])
        st.warning(f"Unable to load data (Status code: {response.status_code}). Using local session buffer.")
    except Exception as e:
        st.info("Operating in local offline mode (or Google Apps Script URL requires auth).")
    
    # Fallback default empty dataframe with expected schema
    if "local_assignments" not in st.session_state:
        st.session_state.local_assignments = pd.DataFrame(columns=[
            "ID", "Title", "Subject", "Due Date", "Priority", "Status", "Notes"
        ])
    return st.session_state.local_assignments

def save_assignment_to_gas(assignment_data, action="create"):
    """Send payload to Google Apps Script Web App (doPost)."""
    payload = {
        "action": action,
        "data": assignment_data
    }
    try:
        response = requests.post(GAS_URL, json=payload, timeout=10, allow_redirects=True)
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error communicating with Google Script: {e}")
        return False

# ---------------------------------------------------------
# MAIN APP INTERFACE
# ---------------------------------------------------------
st.title("📚 School Assignment Tracker")
st.markdown("Stay organized, track deadlines, and sync your coursework in real-time.")

# Fetch Data
df = fetch_assignments()

# Ensure required columns exist
expected_cols = ["ID", "Title", "Subject", "Due Date", "Priority", "Status", "Notes"]
for col in expected_cols:
    if col not in df.columns:
        df[col] = None

# Format Due Date column
if not df.empty and "Due Date" in df.columns:
    df["Due Date Raw"] = pd.to_datetime(df["Due Date"], errors="coerce")
else:
    df["Due Date Raw"] = pd.NaT

# ---------------------------------------------------------
# DASHBOARD METRICS
# ---------------------------------------------------------
st.subheader("📊 Summary Dashboard")
col1, col2, col3, col4 = st.columns(4)

total_tasks = len(df)
completed_tasks = len(df[df["Status"] == "Completed"]) if not df.empty else 0
pending_tasks = len(df[df["Status"].isin(["Pending", "In Progress"])]) if not df.empty else 0

today = pd.to_datetime(date.today())
overdue_tasks = len(df[(df["Due Date Raw"] < today) & (df["Status"] != "Completed")]) if not df.empty else 0

col1.metric("Total Assignments", total_tasks)
col2.metric("Pending Tasks", pending_tasks)
col3.metric("Completed Tasks", completed_tasks)
col4.metric("Overdue Tasks", overdue_tasks, delta_color="inverse")

st.markdown("---")

# ---------------------------------------------------------
# SIDEBAR: FILTERS & ADD NEW ASSIGNMENT
# ---------------------------------------------------------
st.sidebar.header("➕ Add New Assignment")
with st.sidebar.form("add_assignment_form", clear_on_submit=True):
    title = st.text_input("Assignment Name*", placeholder="e.g. History Essay")
    subject = st.text_input("Subject / Class*", placeholder="e.g. AP US History")
    due_date = st.date_input("Due Date", value=date.today())
    priority = st.selectbox("Priority Level", ["High", "Medium", "Low"], index=1)
    status = st.selectbox("Current Status", ["Pending", "In Progress", "Completed"])
    notes = st.text_area("Notes / Description", placeholder="Additional details or guidelines...")
    
    submit_btn = st.form_submit_button("Submit Assignment")

    if submit_btn:
        if not title or not subject:
            st.error("Please enter both Assignment Name and Subject.")
        else:
            new_id = f"TASK-{int(datetime.now().timestamp())}"
            new_record = {
                "ID": new_id,
                "Title": title,
                "Subject": subject,
                "Due Date": due_date.strftime("%Y-%m-%d"),
                "Priority": priority,
                "Status": status,
                "Notes": notes
            }
            
            # Save via API
            success = save_assignment_to_gas(new_record, action="create")
            
            # Local state update
            new_df = pd.DataFrame([new_record])
            if "local_assignments" in st.session_state:
                st.session_state.local_assignments = pd.concat(
                    [st.session_state.local_assignments, new_df], ignore_index=True
                )
            
            st.success(f"Assignment '{title}' added successfully!")
            st.rerun()

# ---------------------------------------------------------
# FILTER CONTROLS
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.header("🔍 Filter Assignments")

subjects_list = ["All"] + list(df["Subject"].dropna().unique()) if not df.empty else ["All"]
selected_subject = st.sidebar.selectbox("Filter by Subject", subjects_list)

status_filter = st.sidebar.multiselect(
    "Filter by Status", 
    options=["Pending", "In Progress", "Completed"], 
    default=["Pending", "In Progress", "Completed"]
)

# Apply Filters
filtered_df = df.copy()

if selected_subject != "All":
    filtered_df = filtered_df[filtered_df["Subject"] == selected_subject]

if status_filter:
    filtered_df = filtered_df[filtered_df["Status"].isin(status_filter)]

# ---------------------------------------------------------
# MAIN CONTENT: ASSIGNMENT LIST & ACTIONS
# ---------------------------------------------------------
st.subheader("📋 Assignment List")

if filtered_df.empty:
    st.info("No assignments found matching your filter criteria.")
else:
    # Sort by Due Date
    filtered_df = filtered_df.sort_values(by="Due Date Raw", ascending=True)

    for idx, row in filtered_df.iterrows():
        status_color = "🟢" if row["Status"] == "Completed" else ("🟡" if row["Status"] == "In Progress" else "🔴")
        
        with st.expander(f"{status_color} **{row['Title']}** ({row['Subject']}) — Due: {row['Due Date']}"):
            c1, c2, c3 = st.columns([2, 2, 1])
            
            with c1:
                st.write(f"**Priority:** {row['Priority']}")
                st.write(f"**Status:** {row['Status']}")
            with c2:
                st.write(f"**Due Date:** {row['Due Date']}")
                st.write(f"**Notes:** {row['Notes'] if row['Notes'] else 'N/A'}")
            
            with c3:
                # Toggle Status Button
                new_status = "Completed" if row["Status"] != "Completed" else "Pending"
                btn_label = "Mark Complete" if row["Status"] != "Completed" else "Mark Pending"
                
                if st.button(btn_label, key=f"status_{row['ID']}_{idx}"):
                    update_data = {"ID": row["ID"], "Status": new_status}
                    save_assignment_to_gas(update_data, action="update")
                    
                    # Local update
                    if "local_assignments" in st.session_state:
                        st.session_state.local_assignments.loc[
                            st.session_state.local_assignments["ID"] == row["ID"], "Status"
                        ] = new_status
                    st.rerun()
                
                # Delete Button
                if st.button("Delete Task", key=f"del_{row['ID']}_{idx}", type="secondary"):
                    save_assignment_to_gas({"ID": row["ID"]}, action="delete")
                    
                    # Local update
                    if "local_assignments" in st.session_state:
                        st.session_state.local_assignments = st.session_state.local_assignments[
                            st.session_state.local_assignments["ID"] != row["ID"]
                        ]
                    st.success("Deleted!")
                    st.rerun()

# Data Table View
with st.expander("📄 View Full Raw Data Table"):
    st.dataframe(df[expected_cols], use_container_width=True)
