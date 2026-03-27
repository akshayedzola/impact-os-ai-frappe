import frappe
from frappe import _
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
import json


def get_jwt_secret():
    return frappe.conf.get("jwt_secret", "CHANGE-THIS-IN-PRODUCTION")


def generate_jwt_token(user_email: str, expires_hours: int = 24) -> str:
    """Generate a JWT token for the given user."""
    secret = get_jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_email,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
        "iss": "impact_os_ai",
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def verify_jwt_token(token: str) -> dict:
    """Verify a JWT token and return the payload."""
    secret = get_jwt_secret()
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except pyjwt.PyJWTError as e:
        frappe.throw(_("Invalid or expired token: {0}").format(str(e)), frappe.AuthenticationError)


def get_current_user_from_token():
    """
    Resolve the current user via:
      1. Custom X-IOS-Token header (preferred for frontend clients — avoids
         Frappe intercepting the standard Authorization header)
      2. Authorization: Bearer <jwt>  (fallback, may be intercepted by Frappe)
      3. Active Frappe session (desk / browser users)
    """
    # 1. Custom header (used by Next.js frontend)
    ios_token = frappe.get_request_header("X-IOS-Token", "")
    if ios_token:
        payload = verify_jwt_token(ios_token)
        return payload.get("sub")

    # 2. Standard Bearer header
    auth_header = frappe.get_request_header("Authorization", "")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_jwt_token(token)
        return payload.get("sub")

    # 3. Active Frappe session (desk users / API key auth already handled by Frappe)
    session_user = frappe.session.user if frappe.session else None
    if session_user and session_user != "Guest":
        return session_user

    frappe.throw(_("Authentication required: provide X-IOS-Token header or log in"), frappe.AuthenticationError)


@frappe.whitelist(allow_guest=True)
def login(email: str, password: str):
    """
    Authenticate user with email/password and return JWT token.
    POST /api/method/impact_os_ai.impact_os_ai.api.auth.login
    """
    if not email or not password:
        frappe.throw(_("Email and password are required"), frappe.ValidationError)

    # Use Frappe's built-in login manager
    from frappe.auth import LoginManager
    login_manager = LoginManager()
    login_manager.authenticate(user=email, pwd=password)
    login_manager.post_login()

    user_doc = frappe.get_doc("User", email)

    # Ensure user profile exists
    _ensure_user_profile(email, user_doc)

    token = generate_jwt_token(email)

    return {
        "token": token,
        "user": {
            "email": email,
            "full_name": user_doc.full_name,
            "role": _get_user_role(email),
        },
    }


@frappe.whitelist(allow_guest=True)
def register(email: str, password: str, full_name: str, organization: str = ""):
    """
    Register a new user.
    POST /api/method/impact_os_ai.impact_os_ai.api.auth.register
    """
    if not email or not password or not full_name:
        frappe.throw(_("Email, password, and full name are required"), frappe.ValidationError)

    if frappe.db.exists("User", email):
        frappe.throw(_("A user with this email already exists"), frappe.DuplicateEntryError)

    # Create Frappe user
    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name.split(" ")[0],
        "last_name": " ".join(full_name.split(" ")[1:]) if len(full_name.split(" ")) > 1 else "",
        "new_password": password,
        "send_welcome_email": 0,
        "roles": [{"role": "Impact OS User"}],
    })
    user.insert(ignore_permissions=True)
    frappe.db.commit()

    # Create user profile
    _ensure_user_profile(email, user, organization=organization)

    token = generate_jwt_token(email)

    return {
        "token": token,
        "user": {
            "email": email,
            "full_name": full_name,
            "role": "Impact OS User",
        },
    }


@frappe.whitelist(allow_guest=True)
def refresh_token():
    """
    Refresh JWT token.
    POST /api/method/impact_os_ai.impact_os_ai.api.auth.refresh_token
    """
    user_email = get_current_user_from_token()
    if not frappe.db.exists("User", user_email):
        frappe.throw(_("User not found"), frappe.DoesNotExistError)

    new_token = generate_jwt_token(user_email)
    return {"token": new_token}


@frappe.whitelist(allow_guest=True)
def me():
    """
    Get current user profile.
    GET /api/method/impact_os_ai.impact_os_ai.api.auth.me
    """
    user_email = get_current_user_from_token()
    user_doc = frappe.get_doc("User", user_email)

    profile = None
    if frappe.db.exists("IOS User Profile", {"user": user_email}):
        profile_doc = frappe.get_doc("IOS User Profile", {"user": user_email})
        profile = {
            "organization": profile_doc.organization,
            "tier": profile_doc.subscription_tier,
            "credits_used": profile_doc.credits_used,
            "credits_limit": profile_doc.credits_limit,
        }

    return {
        "email": user_email,
        "full_name": user_doc.full_name,
        "role": _get_user_role(user_email),
        "profile": profile,
    }


def on_login_hook(login_manager):
    """Hook called after successful login — ensure profile exists."""
    _ensure_user_profile(login_manager.user)


def _ensure_user_profile(email: str, user_doc=None, organization: str = ""):
    """Create IOS User Profile if it doesn't exist."""
    if frappe.db.exists("IOS User Profile", {"user": email}):
        return
    if user_doc is None:
        user_doc = frappe.get_doc("User", email)
    profile = frappe.get_doc({
        "doctype": "IOS User Profile",
        "user": email,
        "full_name": user_doc.full_name,
        "organization": organization,
        "subscription_tier": "free",
        "credits_used": 0,
        "credits_limit": 10,
    })
    profile.insert(ignore_permissions=True)
    frappe.db.commit()


def _get_user_role(email: str) -> str:
    roles = frappe.get_roles(email)
    if "System Manager" in roles:
        return "admin"
    if "Impact OS Pro" in roles:
        return "pro"
    return "free"
