def _wrap_result(res):
    """Normalize supabase client result to a dict-like with optional 'error' and 'data' keys."""
    if isinstance(res, dict):
        return res
    try:
        err = getattr(res, "error", None)
        data = getattr(res, "data", None)
        return {"error": err, "data": data}
    except Exception:
        return {"error": None, "data": None}
# TEMP DEBUG - remove after testing
try:
    st.sidebar.write("Streamlit started OK")
    # show only the secret keys names, not values
    st.sidebar.write("supabase secret keys present:", list(st.secrets.get("supabase", {}).keys()))
except Exception as e:
    st.sidebar.error("Secrets check error: " + str(e))

try:
    auth_obj = getattr(sb, "auth", None)
    auth_methods = [n for n in dir(auth_obj) if not n.startswith("_")] if auth_obj else []
    st.sidebar.write("sb.auth methods:", auth_methods)
except Exception as e:
    st.sidebar.write("Auth client inspection error: " + str(e))
# END TEMP DEBUG

def sign_in(email: str, password: str):
    """
    Robust sign-in that tries common auth client methods and call styles.
    Returns a dict-like result: either raw dict or {"error": ..., "data": ...}.
    """
    auth = sb.auth
    # Try the most common method names in order
    candidates = ["sign_in_with_password", "sign_in", "sign_in_with_email"]
    for name in candidates:
        fn = getattr(auth, name, None)
        if not fn:
            continue
        # Try dict-style payload first (most recent clients)
        try:
            res = fn({"email": email, "password": password})
            return _wrap_result(res)
        except TypeError:
            # Fallback to keyword args if supported
            try:
                res = fn(email=email, password=password)
                return _wrap_result(res)
            except TypeError:
                # method exists but signature different; try next candidate
                continue
            except Exception as e:
                return {"error": str(e), "data": None}
        except AttributeError:
            continue
        except Exception as e:
            return {"error": str(e), "data": None}

    # If we get here, no supported sign-in method was found
    return {"error": "No supported sign-in method on sb.auth (checked: " + ", ".join(candidates) + ")", "data": None}


def sign_up(email: str, password: str):
    """
    Robust sign-up that tries common auth client methods and call styles.
    Returns a dict-like result.
    """
    auth = sb.auth
    candidates = ["sign_up", "sign_up_with_email", "sign_up_with_password"]
    for name in candidates:
        fn = getattr(auth, name, None)
        if not fn:
            continue
        try:
            res = fn({"email": email, "password": password})
            return _wrap_result(res)
        except TypeError:
            try:
                res = fn(email=email, password=password)
                return _wrap_result(res)
            except TypeError:
                continue
            except Exception as e:
                return {"error": str(e), "data": None}
        except AttributeError:
            continue
        except Exception as e:
            return {"error": str(e), "data": None}

    return {"error": "No supported sign-up method on sb.auth (checked: " + ", ".join(candidates) + ")", "data": None}
