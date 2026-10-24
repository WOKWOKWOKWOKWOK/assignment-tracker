import uuid
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from supabase import create_client

st.set_page_config(page_title="Data Migration Tool", page_icon="📦")

st.title("📦 Supabase ➔ Neon Migration Tool")
st.write("Transfer your existing assignments from Supabase into your new Neon database.")

default_neon_url = ""
if "postgres" in st.secrets and "url" in st.secrets["postgres"]:
    default_neon_url = st.secrets["postgres"]["url"]
elif "connections" in st.secrets and "neon" in st.secrets["connections"]:
    default_neon_url = st.secrets["connections"]["neon"]["url"]

with st.form("migration_form"):
    sb_url = st.text_input("Supabase URL", placeholder="https://xxx.supabase.co")
    sb_key = st.text_input("Supabase Anon / Service Key", type="password")
    neon_url = st.text_input("Neon PostgreSQL Connection URL", value=default_neon_url, type="password")
    email = st.text_input("Target Account Email", value="30guptaa@simsburyschools.net")
    
    submitted = st.form_submit_button("🚀 Start Data Migration")


def clean_priority_value(val):
    if pd.isna(val) or val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    val_str = str(val).strip()
    if val_str.isdigit():
        return int(val_str)
    mapping = {"High": 9, "Medium": 5, "Low": 2}
    return mapping.get(val_str, 5)


if submitted:
    if not sb_url or not sb_key or not neon_url or not email:
        st.error("Please fill in all database fields.")
    else:
        try:
            formatted_neon_url = neon_url
            if formatted_neon_url.startswith("postgresql://"):
                formatted_neon_url = formatted_neon_url.replace("postgresql://", "postgresql+psycopg2://", 1)

            new_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email.lower().strip()))
            st.info(f"Mapping all assignments to User ID: `{new_user_id}`")

            st.write("Connecting to Supabase...")
            sb = create_client(sb_url.strip(), sb_key.strip())
            res = sb.table("assignments").select("*").execute()
            data = res.data

            if not data:
                st.warning("⚠️ No rows were found in the Supabase `assignments` table.")
            else:
                df = pd.DataFrame(data)
                st.write(f"Found **{len(df)}** assignment records in Supabase.")

                st.write("Writing data into Neon PostgreSQL (UPSERT mode)...")
                engine = create_engine(formatted_neon_url)

                upsert_sql = text("""
                    INSERT INTO assignments (id, user_id, title, course, due_date, status, notes, created_at, priority, atype, eta)
                    VALUES (:id, :user_id, :title, :course, :due_date, :status, :notes, :created_at, :priority, :atype, :eta)
                    ON CONFLICT (id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        title = EXCLUDED.title,
                        course = EXCLUDED.course,
                        due_date = EXCLUDED.due_date,
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes,
                        created_at = EXCLUDED.created_at,
                        priority = EXCLUDED.priority,
                        atype = EXCLUDED.atype,
                        eta = EXCLUDED.eta;
                """)

                records = df.to_dict(orient="records")
                with engine.begin() as conn:
                    for r in records:
                        row_data = {
                            "id": str(r.get("id")),
                            "user_id": new_user_id,
                            "title": None if pd.isna(r.get("title")) else str(r.get("title")),
                            "course": None if pd.isna(r.get("course")) else str(r.get("course")),
                            "due_date": None if pd.isna(r.get("due_date")) else str(r.get("due_date")),
                            "status": None if pd.isna(r.get("status")) else str(r.get("status")),
                            "notes": None if pd.isna(r.get("notes")) else str(r.get("notes")),
                            "created_at": None if pd.isna(r.get("created_at")) else str(r.get("created_at")),
                            "priority": clean_priority_value(r.get("priority")),
                            "atype": None if pd.isna(r.get("atype")) else str(r.get("atype")),
                            "eta": None if pd.isna(r.get("eta")) else str(r.get("eta")),
                        }
                        conn.execute(upsert_sql, row_data)

                st.success(f"🎉 Successfully migrated/updated {len(df)} records in Neon for `{email}`!")
                st.balloons()

        except Exception as err:
            st.error(f"Migration Failed: {err}")
