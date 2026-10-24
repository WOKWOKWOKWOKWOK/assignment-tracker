import uuid
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
from supabase import create_client

st.set_page_config(page_title="Data Migration Tool", page_icon="📦")

st.title("📦 Supabase ➔ Neon Migration Tool")
st.write("Transfer your existing assignments from Supabase into your new Neon database.")

# Pull Neon URL automatically from secrets if available
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
            # 1. Format driver for SQLAlchemy
            formatted_neon_url = neon_url
            if formatted_neon_url.startswith("postgresql://"):
                formatted_neon_url = formatted_neon_url.replace("postgresql://", "postgresql+psycopg2://", 1)

            # 2. Derive new Neon user ID namespace
            new_user_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, email.lower().strip()))
            st.info(f"Mapping all assignments to User ID: `{new_user_id}`")

            # 3. Read rows from Supabase
            st.write("Connecting to Supabase...")
            sb = create_client(sb_url.strip(), sb_key.strip())
            res = sb.table("assignments").select("*").execute()
            data = res.data

            if not data:
                st.warning("⚠️ No rows were found in the Supabase `assignments` table.")
            else:
                df = pd.DataFrame(data)
                st.write(f"Found **{len(df)}** assignment records in Supabase.")

                # Remap user_id
                df["user_id"] = new_user_id

                # Clean priority column so it matches Neon INTEGER type
                if "priority" in df.columns:
                    df["priority"] = df["priority"].apply(clean_priority_value)

                # 4. Write to Neon
                st.write("Writing data into Neon PostgreSQL...")
                engine = create_engine(formatted_neon_url)
                df.to_sql("assignments", engine, if_exists="append", index=False, method="multi")
                
                st.success(f"🎉 Successfully migrated {len(df)} records into Neon!")
                st.balloons()

        except Exception as err:
            st.error(f"Migration Failed: {err}")
