# -----------------------
# Helpers
# -----------------------
def _wrap_result(res):
    if isinstance(res, dict):
        return res
    try:
        return {"error": getattr(res, "error", None), "data": getattr(res, "data", None)}
    except Exception:
        return {"error": None, "data": None}


def _to_dict(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    for method_name in ("dict", "model_dump"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return None


def debug_print_response(label, value):
    try:
        st.sidebar.markdown(f"**DEBUG: {label}**")
        st.sidebar.write("type:", type(value))
        if isinstance(value, dict):
            st.sidebar.json(value)
        elif isinstance(value, (list, tuple)):
            st.sidebar.json(value)
        else:
            # object-like response
            data = _to_dict(value)
            if isinstance(data, dict):
                st.sidebar.json(data)
            else:
                try:
                    st.sidebar.write(str(value))
                except Exception:
                    st.sidebar.write("Could not stringify response")
    except Exception as e:
        st.sidebar.write(f"DEBUG render failed for {label}: {e}")


def extract_user_from_auth_response(response):
    """
    Try many shapes of Supabase auth responses and return a user dict or None.
    """
    if response is None:
        return None

    def first_user_from_mapping(obj):
        if not isinstance(obj, dict):
            return None
        # Common Supabase responses
        for path in [
            ("data", "user"),
            ("data", "session", "user"),
            ("user",),
            ("session", "user"),
        ]:
            cur = obj
            ok = True
            for key in path:
                if not isinstance(cur, dict):
                    ok = False
                    break
                cur = cur.get(key)
                if cur is None:
                    ok = False
                    break
            if ok and isinstance(cur, dict):
                return cur
        return None

    # dict response
    if isinstance(response, dict):
        user = first_user_from_mapping(response)
        if user:
            return user

    # object response
    for attr_name in ["user", "session", "data"]:
        try:
            obj = getattr(response, attr_name, None)
        except Exception:
            obj = None
        if obj is not None:
            if isinstance(obj, dict):
                user = first_user_from_mapping(obj)
                if user:
                    return user
            else:
                mapped = _to_dict(obj)
                if isinstance(mapped, dict):
                    user = first_user_from_mapping(mapped)
                    if user:
                        return user

    # full object -> dict
    mapped = _to_dict(response)
    if isinstance(mapped, dict):
        user = first_user_from_mapping(mapped)
        if user:
            return user

    return None


# -----------------------
# Auth helpers
# -----------------------
def current_user():
    """
    Return the current signed-in user dict (or None).
    """
    try:
        session = sb.auth.get_session()
        user = extract_user_from_auth_response(session)
        if user:
            return user
    except Exception:
        pass

    try:
        resp = sb.auth.get_user()
        user = extract_user_from_auth_response(resp)
        if user:
            return user
    except Exception:
        pass

    return None


def sign_up(email: str, password: str):
    try:
        # Support different supabase-py versions
        if hasattr(sb.auth, "sign_up"):
            res = sb.auth.sign_up({"email": email, "password": password})
        else:
            res = sb.auth.sign_up_with_password({"email": email, "password": password})
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_in(email: str, password: str):
    try:
        # Support different supabase-py versions
        if hasattr(sb.auth, "sign_in_with_password"):
            res = sb.auth.sign_in_with_password({"email": email, "password": password})
        elif hasattr(sb.auth, "sign_in"):
            res = sb.auth.sign_in({"email": email, "password": password})
        else:
            raise AttributeError("No supported sign-in method found")
        return _wrap_result(res)
    except Exception as e:
        return {"error": str(e), "data": None}


def sign_out():
    try:
        sb.auth.sign_out()
    except Exception:
        pass

    for k in ["user", "df_cached"]:
        if k in st.session_state:
            del st.session_state[k]

    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


# -----------------------
# UI: Authentication
# -----------------------
user = current_user()
if user:
    st.sidebar.write(f"Signed in as: {user.get('email') or user.get('user_metadata', {}).get('email')}")
    if st.sidebar.button("Sign out"):
        sign_out()
else:
    st.sidebar.header("Sign in / Sign up")
    auth_mode = st.sidebar.radio("Mode", ["Sign in", "Sign up"])
    with st.sidebar.form("auth_form"):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Password", type="password", key="auth_pw")
        submitted = st.form_submit_button(auth_mode)

        if submitted:
            if auth_mode == "Sign up":
                r = sign_up(email.strip(), password)
                debug_print_response("sign_up result", r)

                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                if err:
                    st.sidebar.error(f"Sign up failed: {err}")
                else:
                    st.sidebar.success("Sign up successful. Check your email if confirmation is required; then sign in.")
            else:
                r = sign_in(email.strip(), password)
                debug_print_response("sign_in result", r)

                err = r.get("error") if isinstance(r, dict) else getattr(r, "error", None)
                data = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)

                user_obj = extract_user_from_auth_response(r)
                if not user_obj and isinstance(data, dict):
                    user_obj = data.get("user") or data.get("session", {}).get("user")

                if err:
                    st.sidebar.error(f"Sign in failed: {err}")
                elif not user_obj:
                    st.sidebar.error("Sign in failed: could not extract user. Check credentials or your Supabase config.")
                else:
                    st.session_state.user = user_obj
                    try:
                        st.rerun()
                    except Exception:
                        try:
                            st.experimental_rerun()
                        except Exception:
                            pass
