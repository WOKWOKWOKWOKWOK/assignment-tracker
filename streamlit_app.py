def fetch_assignments(user_id: str) -> pd.DataFrame:
    rows = []
    if sb:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id).execute()
            rows = res.data if hasattr(res, "data") else (res.get("data") if isinstance(res, dict) else [])
        except Exception:
            rows = []
    
    # Fallback to local file if Supabase fails or isn't connected
    if not rows:
        local_rows = _read_data_file()
        rows = [r for r in local_rows if r.get("user_id") == user_id]

    if not rows:
        return pd.DataFrame(columns=["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"])
    
    df = pd.DataFrame(rows)
    for c in ["id", "user_id", "title", "course", "due_date", "status", "priority", "atype", "eta", "created_at", "notes"]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    # Save to Supabase table
    if sb:
        try:
            sb.table("assignments").upsert(rows_to_upsert).execute()
        except Exception as e:
            print("Supabase upsert error:", e)

    # Also update local file fallback
    all_rows = _read_data_file()
    by_id = {r.get("id"): r for r in all_rows if isinstance(r, dict)}
    for row in rows_to_upsert:
        rid = row.get("id")
        if rid in by_id:
            by_id[rid].update(row)
        else:
            by_id[rid] = row
    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    # Delete from Supabase table
    if sb:
        try:
            sb.table("assignments").delete().eq("id", assignment_id).execute()
        except Exception as e:
            print("Supabase delete error:", e)

    # Also remove from local file fallback
    rows = _read_data_file()
    remaining = [r for r in rows if r.get("id") != assignment_id]
    _write_data_file(remaining)
