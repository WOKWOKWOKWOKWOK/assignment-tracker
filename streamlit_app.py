import streamlit as st
import pandas as pd
import requests
import hashlib
from datetime import datetime, date

# =============================================================================
# 1. PAGE CONFIGURATION & APPS SCRIPT STYLE INJECTION
# =============================================================================
st.set_page_config(
    page_title="Simsbury Schools | Assignment Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Google Apps Script Web App Endpoint
GAS_URL = "https://script.google.com/a/macros/simsburyschools.net/s/AKfycbzF4gggoAuw3EN6IJU6z-K9ay6cWCdicMXVfMD2VeI-6ShPaT5laDJGmCZkTCeMombx/exec"

# Styling matching the Google Apps Script Web App theme
st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }
    
    .auth-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 30px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        max-width: 450px;
        margin: 0 auto;
    }

    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    .task-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #3b82f6;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .task-card.high { border-left-color: #ef4444; }
    .task-card.medium { border-left-color: #f59e0b; }
    .task-card.low { border-left-color: #3b82f6; }
    .task-card.completed { border-left-color: #10b981; background-color: #f8fafc; opacity: 0.85; }

    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        color: white;
    }
    .badge-high { background-color: #ef4444; }
    .badge-medium { background-color: #f59e0b; }
    .badge-low { background-color: #3b82f6; }
    .badge-completed { background-color: #10b981; }
    .badge-pending { background-color: #64748b; }
    .badge-in-progress { background-color: #8b5cf6; }

    .app-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        padding: 20px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
    }
    .app-header h1 { color: white !important; margin: 0; font-size: 1.8rem; }
    .app-header p { margin: 4px 0 0 0; opacity: 0.9; font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. SESSION STATE & UTILITY FUNCTIONS
# =============================================================================
def init_session():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "current_user" not in st.session_state:
        st.session_state.current_user = None
    if "users_db" not in st.session_state:
        st.session_state.users_db = {
            "student@simsburyschools.net": hashlib.sha256("password123".encode()).hexdigest()
        }
    if "assignments" not in st.session_state:
        st.session_state.assignments = pd.DataFrame(columns=[
            "ID", "Username", "Title", "Subject", "Due Date", "Priority", "Status", "Notes"
        ])

init_session()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# =============================================================================
# 3. BACKEND API INTEGRATION (GOOGLE APPS SCRIPT SYNC)
# =============================================================================
def fetch_remote_assignments(username):
    try:
        session = requests.Session()
        res = session.get(GAS_URL, params={"username": username}, timeout=8, allow_redirects=True)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data)
                return df[df["Username"] == username] if "Username" in df.columns else df
    except Exception:
        pass
    
    df = st.session_state.assignments
    if not df.empty and "Username" in df.columns:
        return df[df["Username"] == username]
    return df

def save_remote_assignment(task_data, action="create"):
    payload = {
        "action": action,
        "data": task_data
    }
    try:
        session = requests.Session()
        res = session.post(GAS_URL, json=payload, timeout=8, allow_redirects=True)
        return res.status_code == 200
    except Exception:
        return False

# =============================================================================
# 4. AUTHENTICATION MODULE (SIGN IN & SIGN UP)
# =============================================================================
if not st.session_state.authenticated:
    st.markdown("""
    <div style="text-align: center; margin-top: 30px; margin-bottom: 20px;">
        <h1 style="color: #1e3a8a; font-weight: 800;">📚 Simsbury Schools</h1>
        <p style="color: #64748b;">Assignment Tracker Portal</p>
    </div>
    """, unsafe_allow_html=True)

    auth_tab1, auth_tab2 = st.tabs(["🔒 Sign In", "📝 Sign Up"])

    with auth_tab1:
        st.subheader("Sign In to Your Account")
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("School Email", placeholder="user@simsburyschools.net")
            password = st.text_input("Password", type="password")
            login_btn = st.form_submit_button("Sign In", use_container_width=True)

            if login_btn:
                hashed = hash_password(password)
                if email in st.session_state.users_db and st.session_state.users_db[email] == hashed:
                    st.session_state.authenticated = True
                    st.session_state.current_user = email
                    st.success("Successfully logged in!")
                    st.rerun()
                else:
                    st.error("Invalid email or password. Please try again.")

    with auth_tab2:
        st.subheader("Create New Account")
        with st.form("signup_form", clear_on_submit=True):
            new_email = st.text_input("School Email*", placeholder="user@simsburyschools.net")
            new_pass = st.text_input("New Password*", type="password")
            confirm_pass = st.text_input("Confirm Password*", type="password")
            signup_btn = st.form_submit_button("Sign Up", use_container_width=True)

            if signup_btn:
                if not new_email or not new_pass:
                    st.error("Please fill out all required fields.")
                elif "@" not in new_email:
                    st.error("Please provide a valid school email address.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                elif new_email in st.session_state.users_db:
                    st.warning("An account with this email already exists. Please Sign In.")
                else:
                    st.session_state.users_db[new_email] = hash_password(new_pass)
                    st.success("Account created successfully! You can now Sign In.")

    st.stop()

# =============================================================================
# 5. MAIN DASHBOARD APPLICATION
# =============================================================================

header_html = f"""
<div class="app-header">
    <h1>📚 Assignment Tracker</h1>
    <p>Logged in as: <b>{st.session_state.current_user}</b> | Simsbury Public Schools Sync Engine</p>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

# Sidebar User Management & Actions
st.sidebar.markdown("### 👤 User Profile")
st.sidebar.info(f"**Account:**\n{st.session_state.current_user}")

if st.sidebar.button("🚪 Sign Out", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.rerun()

st.sidebar.divider()

# Sidebar Task Creation
st.sidebar.markdown("### ➕ Add Assignment")
with st.sidebar.form("new_assignment_sidebar", clear_on_submit=True):
    task_title = st.text_input("Title*", placeholder="e.g. History Chapter 4")
    task_subject = st.selectbox("Subject*", ["Math", "English", "History", "Science", "World Language", "Computer Science", "Elective"])
    task_due = st.date_input("Due Date", value=date.today())
    task_priority = st.selectbox("Priority", ["High", "Medium", "Low"], index=1)
    task_status = st.selectbox("Status", ["Pending", "In Progress", "Completed"])
    task_notes = st.text_area("Notes / Details", placeholder="Optional instructions or links...")
    
    add_submitted = st.form_submit_button("Save Assignment", use_container_width=True)

    if add_submitted:
        if not task_title:
            st.sidebar.error("Title is required.")
        else:
            new_id = f"TASK-{int(datetime.now().timestamp())}"
            new_task = {
                "ID": new_id,
                "Username": st.session_state.current_user,
                "Title": task_title,
                "Subject": task_subject,
                "Due Date": str(task_due),
                "Priority": task_priority,
                "Status": task_status,
                "Notes": task_notes
            }

            new_row = pd.DataFrame([new_task])
            st.session_state.assignments = pd.concat([st.session_state.assignments, new_row], ignore_index=True)

            save_remote_assignment(new_task, action="create")

            st.sidebar.success("Assignment added!")
            st.rerun()

# Load User Specific Data
df = fetch_remote_assignments(st.session_state.current_user)

required_cols = ["ID", "Username", "Title", "Subject", "Due Date", "Priority", "Status", "Notes"]
for col in required_cols:
    if col not in df.columns:
        df[col] = ""

# Metric Overview Cards
m1, m2, m3, m4 = st.columns(4)

total_count = len(df)
pending_count = len(df[df["Status"] == "Pending"])
in_prog_count = len(df[df["Status"] == "In Progress"])
completed_count = len(df[df["Status"] == "Completed"])

m1.metric("Total Assignments", total_count)
m2.metric("Pending", pending_count)
m3.metric("In Progress", in_prog_count)
m4.metric("Completed", completed_count)

st.divider()

# Search and Filter Toolbar
f_col1, f_col2, f_col3 = st.columns([2, 1, 1])

with f_col1:
    search_term = st.text_input("🔍 Search assignments by name...", "")
with f_col2:
    subject_filter = st.selectbox("Filter Subject", ["All"] + list(df["Subject"].unique()) if not df.empty else ["All"])
with f_col3:
    status_filter = st.multiselect("Status", ["Pending", "In Progress", "Completed"], default=["Pending", "In Progress", "Completed"])

filtered_df = df.copy()

if search_term:
    filtered_df = filtered_df[filtered_df["Title"].astype(str).str.contains(search_term, case=False, na=False)]
if subject_filter != "All":
    filtered_df = filtered_df[filtered_df["Subject"] == subject_filter]
if status_filter:
    filtered_df = filtered_df[filtered_df["Status"].isin(status_filter)]

# Assignment Card List View
st.markdown("### 📋 Your Assignments")

if filtered_df.empty:
    st.info("No assignments found matching your search or filter settings.")
else:
    for idx, row in filtered_df.iterrows():
        p_val = str(row["Priority"])
        p_badge_class = p_val.lower()
        s_val = str(row["Status"])
        s_badge_class = s_val.lower().replace(" ", "-")
        card_state = "completed" if s_val == "Completed" else p_badge_class
        notes_text = str(row["Notes"]) if row["Notes"] else "<i>No additional notes provided.</i>"

        card_html = f"""
        <div class="task-card {card_state}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; color: #1e293b; font-weight: 700;">{row['Title']}</h4>
                <div>
                    <span class="badge badge-{p_badge_class}">{p_val}</span>
                    <span class="badge badge-{s_badge_class}">{s_val}</span>
                </div>
            </div>
            <p style="margin: 8px 0; color: #64748b; font-size: 0.9rem;">
                <b>Subject:</b> {row['Subject']} &nbsp; | &nbsp; <b>Due Date:</b> {row['Due Date']}
            </p>
            <p style="margin: 0; color: #334155; font-size: 0.88rem;">{notes_text}</p>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        b_col1, b_col2, b_col3, _ = st.columns([1.5, 1.5, 1, 4])
        
        with b_col1:
            if s_val != "Completed":
                if st.button("✅ Mark Done", key=f"done_{row['ID']}_{idx}"):
                    st.session_state.assignments.loc[st.session_state.assignments["ID"] == row["ID"], "Status"] = "Completed"
                    save_remote_assignment({"ID": row["ID"], "Status": "Completed"}, action="update")
                    st.rerun()
            else:
                if st.button("↩️ Reopen", key=f"reopen_{row['ID']}_{idx}"):
                    st.session_state.assignments.loc[st.session_state.assignments["ID"] == row["ID"], "Status"] = "Pending"
                    save_remote_assignment({"ID": row["ID"], "Status": "Pending"}, action="update")
                    st.rerun()

        with b_col2:
            if s_val != "In Progress" and s_val != "Completed":
                if st.button("⏳ In Progress", key=f"prog_{row['ID']}_{idx}"):
                    st.session_state.assignments.loc[st.session_state.assignments["ID"] == row["ID"], "Status"] = "In Progress"
                    save_remote_assignment({"ID": row["ID"], "Status": "In Progress"}, action="update")
                    st.rerun()

        with b_col3:
            if st.button("🗑️ Delete", key=f"del_{row['ID']}_{idx}"):
                st.session_state.assignments = st.session_state.assignments[st.session_state.assignments["ID"] != row["ID"]]
                save_remote_assignment({"ID": row["ID"]}, action="delete")
                st.rerun()

with st.expander("📊 View Raw Assignment Table"):
    st.dataframe(df[required_cols], use_container_width=True)
