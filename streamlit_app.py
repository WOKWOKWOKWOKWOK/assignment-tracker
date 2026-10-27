"""
Assignment Tracker — Dedicated "Other" Tab Edition
Features:
- Dedicated "Other" Tab: Displays assignments where the type is 'Other' or the course is 'OTHER'.
- Clean Tab Routing: Separates general Homework/Projects, Tests & Quizzes, and Other tasks cleanly.
- Custom Badge Styling: Includes dedicated styling for the 'OTHER' course pill.
- Saved Settings Persistence: Remembers your 'Max Work / Day' and 'Priority System' preferences.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, date, timedelta, time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import create_engine, text


# Timezone helper for Simsbury/Eastern Time
def get_local_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.utcnow() - timedelta(hours=4)


# -----------------------
# Streamlit Page Config & Professional CSS Overrides
# -----------------------
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* Canvas & Global Typography */
    html, body, .stApp {
        background-color: #070a12 !important;
        color: #f1f5f9 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .main .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1420px;
    }

    /* Hide Chrome Elements */
    #MainMenu, header, footer {visibility: hidden;}
    div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}
    section[data-testid="stSidebar"], div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] {display: none !important;}

    /* Modern Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
        border-bottom: 1px solid #1e293b;
        margin-bottom: 20px;
    }

    .stTabs [data-baseweb="tab"] {
        height: 38px;
        border-radius: 6px;
        color: #94a3b8;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 6px 16px;
        background-color: #0f172a;
        border: 1px solid #1e293b;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1e1b4b !important;
        color: #a5b4fc !important;
        border-color: #6366f1 !important;
    }

    /* Card Containers */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 10px !important;
        padding: 16px 18px 22px 18px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
        transition: border-color 0.2s ease;
    }

    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #334155 !important;
    }

    /* Header & Banner Elements */
    .app-title {
        font-size: 1.6rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: -0.02em;
        margin: 0;
    }

    .app-subtitle {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 500;
        margin-top: 2px;
    }

    .date-banner {
        background-color: #0f172a;
        border: 1px solid #1e293
