import frappe
from frappe import _
from .auth import get_current_user_from_token
import json
import secrets
import re


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def create_project(
    project_title: str,
    description: str = "",
    sector: str = "",
    country: str = "",
    organisation_name: str = "",
    organisation_type: str = "",
    team_size: str = "",
    current_data_method: str = "",
    funder_reporting: str = "",
):
    """
    Create a new IOS Project.
    POST /api/method/impact_os_ai.impact_os_ai.api.projects.create_project
    """
    user_email = get_current_user_from_token()
    _check_project_limit(user_email)

    slug = _make_slug(project_title)
    share_slug = secrets.token_urlsafe(8)

    doc = frappe.get_doc({
        "doctype": "IOS Project",
        "project_title": project_title,
        "slug": slug,
        "share_slug": share_slug,
        "description": description,
        "sector": sector,
        "country": country,
        "organisation_name": organisation_name,
        "organisation_type": organisation_type,
        "team_size": team_size,
        "current_data_method": current_data_method,
        "funder_reporting": funder_reporting,
        "generation_status": "draft",
        "generation_progress": 0,
        "owner": user_email,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return _serialize_project(doc)


@frappe.whitelist(allow_guest=True)
def get_project(project_name: str):
    """
    Get a single project by its Frappe name (doc.name).
    GET /api/method/impact_os_ai.impact_os_ai.api.projects.get_project?project_name=xxx
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Project", project_name):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Project", project_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to view this project"), frappe.PermissionError)

    return _serialize_project(doc)


@frappe.whitelist(allow_guest=True)
def list_projects():
    """
    List all projects for the current user.
    GET /api/method/impact_os_ai.impact_os_ai.api.projects.list_projects
    """
    user_email = get_current_user_from_token()

    projects = frappe.get_all(
        "IOS Project",
        filters={"owner": user_email},
        fields=[
            "name", "project_title", "slug", "sector", "country",
            "organisation_name", "generation_status",
            "creation", "modified",
        ],
        order_by="modified desc",
    )

    # Rename `name` → `project_name` for frontend consistency
    for p in projects:
        p["project_name"] = p.pop("name")

    return projects


@frappe.whitelist(allow_guest=True)
def update_project(project_name: str, **kwargs):
    """
    Update an existing project by name.
    POST /api/method/impact_os_ai.impact_os_ai.api.projects.update_project
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Project", project_name):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Project", project_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to modify this project"), frappe.PermissionError)

    allowed_fields = [
        "project_title", "description", "sector", "country",
        "organisation_name", "organisation_type", "team_size",
        "current_data_method", "funder_reporting",
        "generation_status", "generation_progress",
        "theory_of_change", "data_model", "module_specs",
        "dashboard_plan", "sprint_plan",
    ]

    data = kwargs
    if isinstance(kwargs.get("data"), str):
        try:
            data = json.loads(kwargs["data"])
        except Exception:
            data = kwargs

    for field in allowed_fields:
        if field in data:
            doc.set(field, data[field])

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return _serialize_project(doc)


@frappe.whitelist(allow_guest=True)
def delete_project(project_name: str):
    """
    Delete a project by name.
    POST /api/method/impact_os_ai.impact_os_ai.api.projects.delete_project
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Project", project_name):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Project", project_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to delete this project"), frappe.PermissionError)

    doc.delete(ignore_permissions=True)
    frappe.db.commit()

    return {"message": "Project deleted successfully"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_project(doc) -> dict:
    return {
        "project_name": doc.name,   # Frappe doc primary key → used as URL slug
        "name": doc.name,
        "project_title": doc.project_title,
        "slug": doc.slug,
        "share_slug": doc.share_slug,
        "description": doc.description or "",
        "sector": doc.sector or "",
        "country": doc.country or "",
        "organisation_name": doc.organisation_name or "",
        "organisation_type": doc.organisation_type or "",
        "team_size": doc.team_size or "",
        "current_data_method": doc.current_data_method or "",
        "funder_reporting": doc.funder_reporting or "",
        "generation_status": doc.generation_status or "draft",
        "generation_progress": doc.generation_progress or 0,
        "theory_of_change": doc.theory_of_change or "",
        "data_model": doc.data_model or "",
        "module_specs": doc.module_specs or "",
        "dashboard_plan": doc.dashboard_plan or "",
        "sprint_plan": doc.sprint_plan or "",
        "is_public": False,
        "creation": str(doc.creation),
        "modified": str(doc.modified),
    }


def _make_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    suffix = secrets.token_hex(3)
    return f"{slug}-{suffix}"


def _check_project_limit(user_email: str):
    tier = "free"
    if frappe.db.exists("IOS User Profile", {"user": user_email}):
        tier = frappe.db.get_value(
            "IOS User Profile", {"user": user_email}, "subscription_tier"
        ) or "free"

    limits = {"free": 3, "starter": 10, "pro": 50, "enterprise": 999}
    limit = limits.get(tier, 3)

    count = frappe.db.count("IOS Project", filters={"owner": user_email})
    if count >= limit:
        frappe.throw(
            _("Project limit reached for your {0} plan. Upgrade to create more projects.").format(tier),
            frappe.ValidationError,
        )


def _is_admin(user_email: str) -> bool:
    return "System Manager" in frappe.get_roles(user_email)
