import streamlit as st
import pandas as pd
from datetime import date

# =============================================================================
# 1. PAGE CONFIG & CONTRAST STYLING
# =============================================================================
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS to fix sidebar label visibility and dark theme contrast
st.markdown("""
<style>
    /* Fix sidebar contrast */
    [data-testid="stSidebar"] {
        background-color: #111827 !important;
    }
    [data-testid="stSidebar"] *, 
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] span, 
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #f3f4f6 !important;
    }
    
    /* Date banner styling */
    .date-banner {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        font-weight: 500;
        color: #111827;
        margin-top: 10px;
        margin-bottom: 20px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    
    .stAlert {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. SESSION STATE MANAGEMENT (PURE LOCAL STORAGE)
# =============================================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "users_db" not in st.session_state:
    st.session_state.users_db = {}
if "show_add" not in st.session_state:
    st.session_state.show_add = False
if "show_classes" not in st.session_state:
    st.session_state.show_classes = False
if "classes_list" not in st.session_state:
    st.session_state.classes_list = ["Math", "Science", "English", "History", "Elective"]
if "assignments" not in st.session_state:
    st.session_state.assignments = []

# =============================================================================
# 3. SIDEBAR AUTHENTICATION (SIGN IN / SIGN UP)
# =============================================================================
st.sidebar.markdown("### Sign in / Sign up")

if not st.session_state.authenticated:
    mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"], key="auth_mode")
    email = st.sidebar.text_input("Email", key="sidebar_email")
    password = st.sidebar.text_input("Password", type="password", key="sidebar_pass")

    if mode == "Sign in":
        if st.sidebar.button("Sign in", use_container_width=True):
            if not email or not password:
                st.sidebar.error("Please enter email and password.")
            elif email in st.session_state.users_db and st.session_state.users_db[email] == password:
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.rerun()
            else:
                # Fallback local sign in creation
                st.session_state.users_db[email] = password
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.rerun()
    else:
        if st.sidebar.button("Sign up", use_container_width=True):
            if not email or not password:
                st.sidebar.error("Please enter email and password.")
            else:
                st.session_state.users_db[email] = password
                st.session_state.authenticated = True
                st.session_state.user_email = email
                st.rerun()
else:
    st.sidebar.markdown(f"**Logged in as:**  \n`{st.session_state.user_email}`")
    if st.sidebar.button("Sign out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_email = ""
        st.session_state.show_add = False
        st.session_state.show_classes = False
        st.rerun()

# =============================================================================
# 4. MAIN HEADER & TOP ACTION BUTTONS
# =============================================================================
col_header, col_actions = st.columns([2.5, 1.5])

with col_header:
    st.markdown("## 🚀 Assignment Tracker")
    st.caption("Stay on top of your classes with synced workspace management")

with col_actions:
    st.write("")
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    
    with btn_col1:
        if st.button("🧹 Clear", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.assignments = [
                    a for a in st.session_state.assignments 
                    if not (a.get("user") == st.session_state.user_email and a.get("status") == "Completed")
                ]
                st.toast("Cleared completed assignments!")
                st.rerun()
            else:
                st.warning("Please sign in first.")
                
    with btn_col2:
        if st.button("➕ Add", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.show_add = not st.session_state.show_add
            else:
                st.warning("Please sign in first.")
                
    with btn_col3:
        if st.button("🎨 Classes", use_container_width=True):
            if st.session_state.authenticated:
                st.session_state.show_classes = not st.session_state.show_classes
            else:
                st.warning("Please sign in first.")

# =============================================================================
# 5. DATE BANNER & STATE ALERTS
# =============================================================================
today_formatted = date.today().strftime("%A, %B %d, %Y")
st.markdown(f'<div class="date-banner">📅 Today: {today_formatted}</div>', unsafe_allow_html=True)

if not st.session_state.authenticated:
    st.info("Please sign in or sign up in the sidebar to manage your assignments.")

# =============================================================================
# 6. DASHBOARD & INTERACTIVE WORKSPACE
# =============================================================================
else:
    # Panel: Class Manager
    if st.session_state.show_classes:
        with st.expander("🎨 Manage Classes", expanded=True):
            st.write("**Current Classes:** " + ", ".join(st.session_state.classes_list))
            new_cls = st.text_input("New Class Name")
            if st.button("Add Class"):
                if new_cls and new_cls not in st.session_state.classes_list:
                    st.session_state.classes_list.append(new_cls)
                    st.success(f"Added '{new_cls}'!")
                    st.rerun()

    # Panel: Add New Assignment
    if st.session_state.show_add:
        with st.expander("➕ New Assignment", expanded=True):
            with st.form("add_assignment_form", clear_on_submit=True):
                title = st.text_input("Assignment Title*")
                selected_class = st.selectbox("Class", st.session_state.classes_list)
                due_date = st.date_input("Due Date", value=date.today())
                notes = st.text_area("Notes / Description")
                
                if st.form_submit_button("Save Assignment"):
                    if not title:
                        st.error("Title is required.")
                    else:
                        new_task = {
                            "id": len(st.session_state.assignments) + 1,
                            "user": st.session_state.user_email,
                            "title": title,
                            "class": selected_class,
                            "due": str(due_date),
                            "notes": notes,
                            "status": "Pending"
                        }
                        st.session_state.assignments.append(new_task)
                        st.session_state.show_add = False
                        st.success(f"Assignment '{title}' saved!")
                        st.rerun()

    # Display User Assignments List
    st.subheader("Your Assignments")
    user_tasks = [t for t in st.session_state.assignments if t.get("user") == st.session_state.user_email]
    
    if not user_tasks:
        st.caption("No assignments added yet. Click **➕ Add** at the top right to create one.")
    else:
        for idx, task in enumerate(user_tasks):
            col_t1, col_t2, col_t3 = st.columns([4, 2, 1])
            with col_t1:
                st.markdown(f"**{task['title']}** (`{task['class']}`)")
                if task.get("notes"):
                    st.caption(task["notes"])
            with col_t2:
                st.write(f"Due: {task['due']}")
            with col_t3:
                if task.get("status") != "Completed":
                    if st.button("Complete", key=f"comp_{idx}"):
                        task["status"] = "Completed"
                        st.rerun()
                else:
                    st.write("✅ Done")
