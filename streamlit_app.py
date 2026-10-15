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
    /* Main Container Styling */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }
    
    /* Login / Signup Card Styling */
    .auth-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 30px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        max-width: 450px;
        margin: 0 auto;
    }

    /* Metric Header Card Styling */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    /* Task Card Item Styling */
    .task-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #3b82f6;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        transition: transform 0.1s ease-in-out;
    }
    .task-card.high { border-left-color: #ef4444; }
    .task-card.medium { border-left-color: #f59e0b; }
    .task-card.low { border-left-color: #3b82f6; }
    .task-card.completed { border-left-color: #10b981; background-color: #f8fafc; opacity: 0.85; }

    /* Badges */
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

    /* Custom Header Banner */
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
        # Mock initial user store (Username: password_hash)
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
    """Fetch assignments from Apps Script with fallback to session storage."""
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
    
    # Session state fallback
    df = st.session_state.assignments
    if not df.empty and "Username" in df.columns:
        return df[df["Username"] == username]
    return df

def save_remote_assignment(task_data, action="create"):
    """Send created/updated task payload to Apps Script endpoint."""
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
