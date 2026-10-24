import uuid
import pandas as pd
from sqlalchemy import create_engine
from supabase import create_client

# 1. Fill in your credentials
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_ANON_OR_SERVICE_KEY"
NEON_URL = "postgresql://neondb_owner:npg_BZ3Vrzyfe7xH@ep-late-lake-b4nv9ky5-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# Your target login email
USER_EMAIL = "30guptaa@simsburyschools.net"
NEW_USER_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_EMAIL.lower().strip()))

print(f"Target Neon User ID for {USER_EMAIL}: {NEW_USER_ID}")

# 2. Fetch rows from Supabase
sb = create_client(SUPABASE_URL, SUPABASE_KEY)
response = sb.table("assignments").select("*").execute()
data = response.data

if not data:
    print("❌ No data found in Supabase 'assignments' table.")
else:
    df = pd.DataFrame(data)
    print(f"Found {len(df)} rows in Supabase.")

    # 3. Update all user_id columns so they link to your new Neon login
    df["user_id"] = NEW_USER_ID

    # 4. Push directly into Neon PostgreSQL
    engine = create_engine(NEON_URL)
    df.to_sql("assignments", engine, if_exists="append", index=False, method="multi")
    print(f"✅ Successfully transferred {len(df)} rows to Neon!")
