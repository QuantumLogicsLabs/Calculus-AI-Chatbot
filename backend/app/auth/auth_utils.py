from starlette.requests import Request

def require_user(request: Request):
    """
    Extract user_id from request.
    Checks Authorization header for Bearer token.
    Returns user_id (int) if authenticated, None if guest.
    
    For now: returns a hardcoded user_id for testing.
    Replace with real JWT decode when auth system is ready.
    """
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token:
            # TODO: Replace with real JWT decode
            # For testing, any Bearer token = user_id 1
            return 1
    
    return None  # Guest user