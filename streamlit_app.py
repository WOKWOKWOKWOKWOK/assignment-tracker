"""
📚 Assignment Tracker — Part 1: Core Engine & Callbacks
Fix: Restored tasks are automatically unchecked in session state so they return 
to active views clean and ready.
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


def get_local_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return datetime.utcnow() - timedelta(hours=4)


# Streamlit Page Config
st.set_page_config(
    page_title="Assignment Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom Styling
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, .stApp {
        background-color: #070a12 !important;
        background-image: 
            radial-gradient(at 15% 15%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
            radial-gradient(at 85% 85%, rgba(14, 165, 233, 0.06) 0px, transparent 50%);
        color: #f1f5f9 !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .main .block-container {
        padding-top: 1rem !important;
        padding-bottom: 3rem !important;
        max-width: 1420px;
    }

    #MainMenu, header, footer {visibility: hidden;}
    div[data-testid="stToolbar"], div[data-testid="stDecoration"], div[data-testid="stStatusWidget"] {display: none !important;}
    section[data-testid="stSidebar"], div[data-testid="collapsedControl"], button[data-testid="stSidebarCollapseButton"] {display: none !important;}

    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: rgba(15, 23, 42, 0.6);
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 4px;
        margin-bottom: 22px;
        backdrop-filter: blur(8px);
        overflow-x: auto;
        white-space: nowrap;
    }

    .stTabs [data-baseweb="tab"] {
        height: 40px;
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 600;
        font-size: 0.85rem;
        padding: 6px 16px;
        background-color: transparent;
        border: none;
        transition: all 0.2s ease-in-out;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(15, 23, 42, 0.75) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        padding: 16px 18px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(12px);
    }

    .app-title {
        font-size: 1.7rem;
        font-weight: 800;
        background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
        margin: 0;
    }

    .app-subtitle {
        font-size: 0.82rem;
        color: #64748b;
        font-weight: 500;
        margin-top: 2px;
    }

    .date-banner {
        background: linear-gradient(90deg, rgba(30, 27, 75, 0.5) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 10px;
        padding: 10px 18px;
        font-size: 0.85rem;
        font-weight: 700;
        color: #818cf8;
        text-align: center;
        margin-bottom: 20px;
    }

    .prio-high {
        background: rgba(244, 63, 94, 0.15);
        color: #fb7185;
        border: 1px solid rgba(244, 63, 94, 0.35);
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .prio-medium {
        background: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .prio-low {
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .recovery-card {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


if hasattr(st, "dialog"):
    dialog_decorator = st.dialog
elif hasattr(st, "experimental_dialog"):
    dialog_decorator = st.experimental_dialog
else:
    def dialog_decorator(title: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                st.subheader(title)
                return func(*args, **kwargs)
            return wrapper
        return decorator


DEFAULT_DOMAIN = "@simsburyschools.net"
STATUS_OPTIONS = ["Not Started", "In Progress", "Done"]
TYPE_OPTIONS = ["Homework", "Essay", "Presentation", "Test & Quizzes", "Other"]
PRIORITY_OPTIONS = ["Low", "Medium", "High"]
PRIORITY_SYSTEM_MODES = ["Low / Medium / High", "1 to 10 Scale (Slider)", "Both Systems"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_connection_url() -> str:
    url = ""
    if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        url = st.secrets["postgres"]["url"]
    elif "connections" in st.secrets and "neon" in st.secrets["connections"]:
        url = st.secrets["connections"]["neon"]["url"]
    else:
        raise ValueError("Missing PostgreSQL database URL in secrets configuration.")

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


@st.cache_resource
def get_db_engine():
    db_url = get_connection_url()
    return create_engine(db_url, pool_pre_ping=True)


engine = get_db_engine()


def init_db():
    sql_users = text("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    sql_assignments = text("""
        CREATE TABLE IF NOT EXISTS assignments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            course TEXT,
            due_date TEXT,
            status TEXT,
            priority INTEGER,
            atype TEXT,
            eta TEXT,
            notes TEXT,
            created_at TEXT
        );
    """)
    with engine.begin() as conn:
        conn.execute(sql_users)
        conn.execute(sql_assignments)


try:
    init_db()
except Exception as e:
    st.error(f"Database Connection Error: {e}")


def invalidate_cache():
    if "df_cached" in st.session_state:
        del st.session_state["df_cached"]


def fetch_assignments(user_id: str) -> pd.DataFrame:
    today_iso = get_local_now().date().isoformat()

    sql_purge_expired = text("""
        DELETE FROM assignments
        WHERE user_id = :uid
          AND status = 'Done'
          AND due_date IS NOT NULL
          AND due_date != ''
          AND due_date < :today_iso;
    """)

    sql_fetch = text("""
        SELECT * FROM assignments 
        WHERE user_id = :uid 
          AND title NOT IN (
            '__SYSTEM_COURSES__', 
            '__SYSTEM_SCHEDULE__', 
            '__SYSTEM_PRIO_CONFIG__', 
            '__SYSTEM_MAX_WORK_CONFIG__', 
            '__SYSTEM_COMPLETED_SLOTS__'
          )
    """)

    with engine.begin() as conn:
        conn.execute(sql_purge_expired, {"uid": user_id, "today_iso": today_iso})
        df = pd.read_sql(sql_fetch, conn, params={"uid": user_id})

    if df.empty:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority",
            "atype", "eta", "created_at", "notes", "prev_status"
        ])

    rows = []
    for _, r in df.iterrows():
        n_text, prev_st = _unpack_notes(r.get("notes"))
        rows.append({
            "id": str(r.get("id")),
            "user_id": str(r.get("user_id")),
            "title": str(r.get("title") or ""),
            "course": str(r.get("course") or "GENERAL").strip().upper(),
            "due_date": str(r.get("due_date") or ""),
            "status": str(r.get("status") or "Not Started"),
            "priority": priority_to_int(r.get("priority")),
            "atype": str(r.get("atype") or "Homework"),
            "eta": str(r.get("eta") or ""),
            "created_at": str(r.get("created_at") or ""),
            "notes": n_text,
            "prev_status": prev_st
        })

    return pd.DataFrame(rows)


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    if not rows_to_upsert:
        return

    sql = text("""
        INSERT INTO assignments (id, user_id, title, course, due_date, status, priority, atype, eta, notes, created_at)
        VALUES (:id, :user_id, :title, :course, :due_date, :status, :priority, :atype, :eta, :notes, :created_at)
        ON CONFLICT (id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            title = EXCLUDED.title,
            course = EXCLUDED.course,
            due_date = EXCLUDED.due_date,
            status = EXCLUDED.status,
            priority = EXCLUDED.priority,
            atype = EXCLUDED.atype,
            eta = EXCLUDED.eta,
            notes = EXCLUDED.notes,
            created_at = EXCLUDED.created_at;
    """)

    with engine.begin() as conn:
        for row in rows_to_upsert:
            n_text = str(row.get("notes", "")).strip()
            prev_st = str(row.get("prev_status", "Not Started"))
            packed = _pack_notes(n_text, prev_st)

            conn.execute(sql, {
                "id": str(row.get("id")),
                "user_id": str(row.get("user_id")),
                "title": str(row.get("title", "")).strip() or "Untitled Assignment",
                "course": str(row.get("course", "GENERAL")).strip().upper(),
                "due_date": str(row.get("due_date") or ""),
                "status": str(row.get("status", "Not Started")),
                "priority": priority_to_int(row.get("priority")),
                "atype": str(row.get("atype", "Homework")),
                "eta": str(row.get("eta", "")).strip(),
                "notes": packed,
                "created_at": str(row.get("created_at") or get_local_now().isoformat())
            })

    invalidate_cache()


def restore_single_assignment(row_dict: Dict[str, Any]):
    """Restores assignment, unchecks checkbox, and reverts to previous status."""
    aid = row_dict.get("id")
    prev_st = row_dict.get("prev_status") or "In Progress"
    if prev_st == "Done":
        prev_st = "In Progress"
    
    row_dict["status"] = prev_st
    upsert_assignments([row_dict])

    # Uncheck checkboxes and reset dropdowns across all tab views
    if aid:
        for prefix in ["reg_", "tests_", "other_"]:
            st.session_state[f"{prefix}chk_done_{aid}"] = False
            st.session_state[f"{prefix}status_sel_{aid}"] = prev_st
        st.session_state.pop(f"prev_st_{aid}", None)

    safe_rerun()"""
📚 Assignment Tracker — Part 2: Interface & Rendering
"""

def render_assignment_grid(df_grid: pd.DataFrame, user_prio_mode: str, key_prefix: str = "reg_"):
    if df_grid.empty:
        st.markdown("<div style='padding:50px 0; text-align:center; color:#475569; font-size:0.9rem;'>No active assignments in this view.</div>", unsafe_allow_html=True)
        return

    df_sorted = df_grid.copy()
    df_sorted["due_parsed"] = df_sorted["due_date"].apply(parse_date_iso_or_empty)
    df_sorted = df_sorted.sort_values(by=["due_parsed", "priority"], ascending=[True, False]).drop(columns=["due_parsed"])

    cards_per_row = 3
    chunked_rows = [df_sorted.iloc[i:i + cards_per_row] for i in range(0, len(df_sorted), cards_per_row)]

    for row_df in chunked_rows:
        cols = st.columns(cards_per_row)
        for idx, (_, row) in enumerate(row_df.iterrows()):
            with cols[idx]:
                with st.container(border=True):
                    aid = row.get("id")
                    title = row.get("title") or "Untitled"
                    course = (row.get("course") or "MATH").upper()
                    atype = row.get("atype") or "Homework"
                    due_d = parse_date_iso_or_empty(row.get("due_date"))
                    due_text = format_mdy(due_d)
                    days_text, _ = days_left(due_d)

                    chk_key = f"{key_prefix}chk_done_{aid}"
                    sel_key = f"{key_prefix}status_sel_{aid}"

                    status = st.session_state.get(sel_key) or row.get("status") or "Not Started"
                    prio_num = priority_to_int(row.get("priority"))
                    prio_label = priority_to_label(prio_num)
                    prio_cls = f"prio-{prio_label.lower()}"
                    prio_display_str = format_priority_display(prio_num, user_prio_mode)
                    row_dict = row.to_dict()

                    # Header controls
                    c_top1, c_top2, c_top3, c_top4 = st.columns([0.4, 1.8, 1.1, 2.3])

                    with c_top1:
                        st.checkbox(
                            "Done",
                            value=(status == "Done"),
                            key=chk_key,
                            label_visibility="collapsed",
                            on_change=on_checkbox_toggle,
                            args=(aid, row_dict, chk_key, sel_key)
                        )

                    with c_top2:
                        st.markdown(get_course_badge_html(course), unsafe_allow_html=True)

                    with c_top3:
                        if st.button("Edit", key=f"{key_prefix}edit_btn_{aid}"):
                            st.session_state["_edit_assignment_id"] = aid
                            safe_rerun()

                    with c_top4:
                        st.selectbox(
                            "Status",
                            STATUS_OPTIONS,
                            index=STATUS_OPTIONS.index(status) if status in STATUS_OPTIONS else 0,
                            key=sel_key,
                            label_visibility="collapsed",
                            on_change=on_status_change,
                            args=(aid, row_dict, sel_key, chk_key)
                        )

                    st.markdown(f"<div style='font-size:1.15rem; font-weight:700; color:#f8fafc; margin-top:10px;'>{title}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='color:#64748b; font-size:0.8rem; margin-top:2px; margin-bottom:12px;'>{atype}</div>", unsafe_allow_html=True)

                    eta = str(row.get("eta") or "").strip()
                    notes = str(row.get("notes") or "").strip()
                    eta_snippet = f" &bull; Est: {eta}" if eta else ""

                    st.markdown(
                        f"<div style='display:flex; align-items:center; justify-content:space-between; margin-top:10px; margin-bottom:12px; padding-top:10px; border-top:1px solid rgba(255, 255, 255, 0.08);'>"
                        f"<div style='font-size:0.78rem; color:#94a3b8;'>Due {due_text} <span style='color:#64748b;'>({days_text})</span>{eta_snippet}</div>"
                        f"<div class='{prio_cls}'>Priority: {prio_display_str}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                    if notes:
                        note_preview = notes if len(notes) <= 90 else notes[:87] + "..."
                        st.markdown(f"<div style='font-size:0.75rem; color:#64748b; margin-top:4px; margin-bottom:8px;'>Note: {note_preview}</div>", unsafe_allow_html=True)


# Main App Navigation & Active Tab Filtering
tab_assignments, tab_tests, tab_other, tab_schedule, tab_completed = st.tabs([
    "Assignments", 
    "Tests & Quizzes", 
    "Other",
    "Weekly Schedule & AI Planner",
    "Completed & Recovery"
])

# Active tabs exclude tasks with status == "Done"
with tab_assignments:
    df_regular = df_all[(df_all["status"] != "Done") & (df_all["atype"] != "Test & Quizzes") & (df_all["atype"] != "Other") & (df_all["course"] != "OTHER")]
    render_assignment_grid(df_regular, user_prio_mode, key_prefix="reg_")

with tab_tests:
    df_tests = df_all[(df_all["status"] != "Done") & (df_all["atype"] == "Test & Quizzes")]
    render_assignment_grid(df_tests, user_prio_mode, key_prefix="tests_")

with tab_other:
    df_other = df_all[(df_all["status"] != "Done") & ((df_all["atype"] == "Other") | (df_all["course"] == "OTHER"))]
    render_assignment_grid(df_other, user_prio_mode, key_prefix="other_")

# Recovery Tab displays completed items with one-click restore
with tab_completed:
    st.markdown("<div style='font-weight:800; font-size:1.2rem; color:#f8fafc; margin-bottom:4px;'>Completed Tasks & Recovery Center</div>", unsafe_allow_html=True)
    df_done_db = df_all[df_all["status"] == "Done"].copy()

    if not df_done_db.empty:
        for _, r_done in df_done_db.iterrows():
            r_aid = r_done.get("id")
            c_info_db, c_act_db = st.columns([4, 1.4])
            with c_info_db:
                st.markdown(
                    f"<div class='recovery-card'>"
                    f"<div><b style='color:#f8fafc;'>{r_done.get('title')}</b> {get_course_badge_html(r_done.get('course'))}"
                    f"<div style='font-size:0.76rem; color:#94a3b8; margin-top:2px;'>Type: {r_done.get('atype')} &bull; Due: {r_done.get('due_date')}</div></div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c_act_db:
                if st.button("Restore Item", key=f"rec_db_{r_aid}", use_container_width=True):
                    restore_single_assignment(r_done.to_dict())
    else:
        st.info("No main database assignments currently marked as 'Done'.")
