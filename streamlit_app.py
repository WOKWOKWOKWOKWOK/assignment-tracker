# -----------------------
# Supabase Cloud & Local Persistence Helpers
# -----------------------
def invalidate_cache():
    if "df_cached" in st.session_state:
        del st.session_state["df_cached"]


def _read_data_file() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_data_file(rows: List[Dict[str, Any]]) -> None:
    try:
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)
        invalidate_cache()
    except Exception:
        pass


def fetch_assignments(user_id: str) -> pd.DataFrame:
    """Fetches user assignments from Supabase Cloud and local fallback, preserving eta/notes."""
    cfg_id = get_courses_config_id(user_id)
    rows = []

    if sb and user_id:
        try:
            res = sb.table("assignments").select("*").eq("user_id", user_id).neq("title", "__SYSTEM_COURSES__").execute()
            if res and hasattr(res, "data") and res.data:
                for r in res.data:
                    if str(r.get("id")) == cfg_id:
                        continue

                    notes_raw = r.get("notes")
                    n_text, prev_st = _unpack_notes(notes_raw)
                    raw_course = r.get("course")

                    if isinstance(raw_course, list) and len(raw_course) > 0:
                        course_str = str(raw_course[0])
                    elif isinstance(raw_course, dict):
                        course_str = str(raw_course.get("name") or raw_course.get("title") or "GENERAL")
                    elif isinstance(raw_course, str):
                        course_str = raw_course
                    else:
                        course_str = str(raw_course) if raw_course else "GENERAL"

                    rows.append({
                        "id": str(r.get("id")),
                        "user_id": str(r.get("user_id")),
                        "title": r.get("title") or "",
                        "course": course_str.strip().upper(),
                        "due_date": r.get("due_date") or "",
                        "status": r.get("status") or "Not Started",
                        "priority": r.get("priority") or "Medium",
                        "atype": r.get("atype") or "Homework",
                        "eta": r.get("eta") or "",
                        "created_at": r.get("created_at") or "",
                        "notes": n_text,
                        "prev_status": prev_st
                    })
        except Exception as err:
            st.error(f"Supabase fetch error: {err}")

    if not rows:
        local_rows = _read_data_file()
        if isinstance(local_rows, list):
            for r in local_rows:
                if str(r.get("user_id")) == str(user_id) and r.get("title") != "__SYSTEM_COURSES__":
                    notes_raw = r.get("notes")
                    n_text, prev_st = _unpack_notes(notes_raw)
                    rows.append({
                        "id": str(r.get("id")),
                        "user_id": str(r.get("user_id")),
                        "title": r.get("title") or "",
                        "course": str(r.get("course") or "GENERAL").strip().upper(),
                        "due_date": r.get("due_date") or "",
                        "status": r.get("status") or "Not Started",
                        "priority": r.get("priority") or "Medium",
                        "atype": r.get("atype") or "Homework",
                        "eta": r.get("eta") or "",
                        "created_at": r.get("created_at") or "",
                        "notes": n_text,
                        "prev_status": prev_st
                    })

    if not rows:
        return pd.DataFrame(columns=[
            "id", "user_id", "title", "course", "due_date", "status", "priority", "atype",
            "eta", "created_at", "notes", "prev_status"
        ])

    df = pd.DataFrame(rows)
    for c in [
        "id", "user_id", "title", "course", "due_date", "status", "priority", "atype",
        "eta", "created_at", "notes", "prev_status"
    ]:
        if c not in df.columns:
            df[c] = ""
    return df


def upsert_assignments(rows_to_upsert: List[Dict[str, Any]]) -> None:
    """Upsert assignments while preserving eta/notes and not overwriting missing fields."""
    if not rows_to_upsert:
        return

    all_rows = _read_data_file()
    by_id = {r.get("id"): r for r in all_rows if isinstance(r, dict) and r.get("id") is not None}

    for row in rows_to_upsert:
        rid = row.get("id")
        clean = dict(row)

        # Normalize values
        clean["title"] = str(clean.get("title", "")).strip() or "Untitled Assignment"
        clean["course"] = str(clean.get("course", "GENERAL")).strip() or "GENERAL"
        clean["status"] = clean.get("status", "Not Started")
        clean["priority"] = clean.get("priority", "Medium")
        clean["atype"] = clean.get("atype", "Homework")
        clean["eta"] = str(clean.get("eta", "")).strip()
        clean["notes"] = str(clean.get("notes", "")).strip()
        clean["prev_status"] = clean.get("prev_status", "Not Started")
        clean["user_id"] = clean.get("user_id", "")
        clean["created_at"] = clean.get("created_at") or datetime.utcnow().isoformat()

        if rid in by_id:
            existing = by_id[rid]
            if isinstance(existing, dict):
                for key, value in clean.items():
                    if value is not None:
                        existing[key] = value
            by_id[rid] = existing
        else:
            by_id[rid] = clean

        # Pack notes into json payload for Supabase
        packed_notes = _pack_notes(clean.get("notes", ""), clean.get("prev_status", "Not Started"))
        db_row = {
            "id": rid,
            "user_id": clean.get("user_id"),
            "title": clean.get("title"),
            "course": clean.get("course"),
            "due_date": clean.get("due_date") or None,
            "status": clean.get("status"),
            "priority": clean.get("priority"),
            "atype": clean.get("atype"),
            "eta": clean.get("eta"),
            "notes": packed_notes,
            "created_at": clean.get("created_at"),
        }
        if sb:
            try:
                sb.table("assignments").upsert(db_row).execute()
            except Exception as err:
                st.error(f"Supabase upsert error: {err}")

    _write_data_file(list(by_id.values()))


def delete_assignment(assignment_id: str) -> None:
    if sb:
        try:
            sb.table("assignments").delete().eq("id", assignment_id).execute()
        except Exception as err:
            st.error(f"Supabase delete error: {err}")

    rows = _read_data_file()
    remaining = [r for r in rows if r.get("id") != assignment_id]
    _write_data_file(remaining)
