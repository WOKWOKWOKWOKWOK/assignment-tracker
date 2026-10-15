import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
from datetime import datetime, date

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & CUSTOM STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Google Apps Script Executable URL
GAS_URL = "https://script.google.com/a/macros/simsburyschools.net/s/AKfycbzF4gggoAuw3EN6IJU6z-K9ay6cWCdicMXVfMD2VeI-6ShPaT5laDJGmCZkTCeMombx/exec"

# Touch-up CSS Styling
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }
    .task-card {
        background-color: #ffffff;
        border-left: 6px solid #3B82F6;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.06);
    }
    .task-card.completed {
        border-left-color: #10B981;
        background-color: #F0FDF4;
    }
    .task-card.high {
        border-left-color: #EF4444;
    }
    .badge-priority {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 700;
        color: white;
    }
    .badge-high { background-color: #EF4444; }
    .badge-medium { background-color: #F59E0B; }
    .badge-low { background-color: #3B82F6; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS & DATA SYNC
# -----------------------------------------------------------------------------
@st.cache_data(ttl=30)
def fetch_assignments(url):
    """Fetch assignment data with redirect and session error handling."""
    try:
        session = requests.Session()
        res = session.get(url, timeout=10, allow_redirects=True)
        if res.status_code == 200:
            payload = res.json()
            if isinstance(payload, list):
                return pd.DataFrame(payload)
            elif isinstance(payload, dict) and "data" in payload:
                return pd.DataFrame(payload["data"])
    except Exception:
        pass

    # Default fallback dataset stored in session state if backend requires Google Login
    if "assignments_db" not in st.session_state:
        st.session_state.assignments_db = pd.DataFrame([
            {
                "ID": "TASK-101",
                "Title": "AP US History Essay Outline",
                "Subject": "History",
                "Due Date": str(date.today()),
                "Priority": "High",
                "Status": "In Progress",
                "Notes": "Chapter 14 thesis draft and arguments."
            },
            {
                "ID": "TASK-102",
                "Title": "Math Worksheet #5",
                "Subject": "Math",
                "Due Date": str(date.today()),
                "Priority": "Medium",
                "Status": "Pending",
                "Notes": "Complete odd numbers 1-29."
            }
        ])
    return st.session_state.assignments_db

def send_task_to_gas(url, task_payload):
    """POST payload to Google Apps Script Web App."""
    try:
        session = requests.Session()
        res = session.post(url, json=task_payload, timeout=10, allow_redirects=True)
        return res.status_code == 200
    except Exception:
        return False

# -----------------------------------------------------------------------------
# 3. INTERFACE LAYOUT & NAVIGATION TABS
# -----------------------------------------------------------------------------
st.title("📚 School Assignment Tracker")

tab1, tab2, tab3 = st.tabs(["🖥️ Apps Script Web App", "📊 Dashboard & Filter View", "➕ Add Assignment"])

# TAB 1: EMBEDDED WEB APP VIEW
with tab1:
    st.markdown("### Google Apps Script Live Portal")
    st.caption("Note: Ensure you are logged into your `@simsburyschools.net` Google Workspace account in this browser.")
    
    # Render embedded iframe using Streamlit Components
    components.iframe(
        src=GAS_URL,
        height=720,
        scrolling=True
    )

# TAB 2: PYTHON DASHBOARD & FILTERABLE LIST
with tab2:
    df = fetch_assignments(GAS_URL)
    
    # Ensure expected columns exist
    cols = ["ID", "Title", "Subject", "Due Date", "Priority", "Status", "Notes"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""

    # Top Search & Filters
    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
    with col_s1:
        search_query = st.text_input("🔍 Search assignments...", "")
    with col_s2:
        subjects = ["All"] + list(df["Subject"].unique())
        selected_subject = st.selectbox("Filter Subject", subjects)
    with col_s3:
        status_options = st.multiselect("Status", ["Pending", "In Progress", "Completed"], default=["Pending", "In Progress", "Completed"])

    # Filter Logic
    filtered_df = df.copy()
    if search_query:
        filtered_df = filtered_df[filtered_df["Title"].astype(str).str.contains(search_query, case=False, na=False)]
    if selected_subject != "All":
        filtered_df = filtered_df[filtered_df["Subject"] == selected_subject]
    if status_options:
        filtered_df = filtered_df[filtered_df["Status"].isin(status_options)]

    # Metrics Summary
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Tasks", len(df))
    m2.metric("Pending", len(df[df["Status"] == "Pending"]))
    m3.metric("In Progress", len(df[df["Status"] == "In Progress"]))
    m4.metric("Completed", len(df[df["Status"] == "Completed"]))

    st.divider()

    # Display Task Cards
    if filtered_df.empty:
        st.info("No assignments match your filter criteria.")
    else:
        for idx, row in filtered_df.iterrows():
            priority_val = str(row.get("Priority", "Medium")).lower()
            status_val = str(row.get("Status", "Pending"))
            card_class = "completed" if status_val == "Completed" else priority_val
            
            st.markdown(
                f"""
                <div class="task-card {card_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin:0; font-size: 1.1rem; color: #1E293B;">{row.get('Title', 'Untitled')}</h4>
                        <span class="badge-priority badge-{priority_val}">{row.get('Priority', 'Medium')}</span>
                    </div>
                    <p style="margin: 6px 0; color: #64748B; font-size: 0.9rem;">
                        <b>Subject:</b> {row.get('Subject', 'N/A')} &nbsp;|&nbsp; 
                        <b>Due Date:</b> {row.get('Due Date', 'N/A')} &nbsp;|&nbsp; 
                        <b>Status:</b> {status_val}
                    </p>
                    <p style="margin:0; color: #334155; font-size: 0.88rem;">{row.get('Notes', '')}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

# TAB 3: ADD NEW ASSIGNMENT FORM
with tab3:
    st.subheader("Add New Assignment")
    with st.form("add_task_form", clear_on_submit=True):
        title = st.text_input("Assignment Title*")
        subject = st.selectbox("Subject*", ["Math", "English", "History", "Science", "Foreign Language", "Elective", "Other"])
        due_date = st.date_input("Due Date", value=date.today())
        priority = st.select_slider("Priority Level", options=["Low", "Medium", "High"], value="Medium")
        status = st.selectbox("Status", ["Pending", "In Progress", "Completed"])
        notes = st.text_area("Notes / Instructions")
        
        submitted = st.form_submit_button("Submit Assignment")
        if submitted:
            if not title:
                st.error("Please enter a title for the assignment.")
            else:
                new_payload = {
                    "action": "create",
                    "data": {
                        "ID": f"TASK-{int(datetime.now().timestamp())}",
                        "Title": title,
                        "Subject": subject,
                        "Due Date": str(due_date),
                        "Priority": priority,
                        "Status": status,
                        "Notes": notes
                    }
                }
                
                # Send to Google Apps Script
                send_task_to_gas(GAS_URL, new_payload)
                
                # Local state update
                if "assignments_db" in st.session_state:
                    st.session_state.assignments_db = pd.concat([
                        st.session_state.assignments_db,
                        pd.DataFrame([new_payload["data"]])
                    ], ignore_index=True)
                
                st.success(f"Assignment '{title}' saved successfully!")
                st.rerun()
