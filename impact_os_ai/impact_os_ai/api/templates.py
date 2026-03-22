import frappe
from frappe import _
from .auth import get_current_user_from_token
import json


@frappe.whitelist(allow_guest=True)
def list_templates(sector: str = "", is_public: int = 1):
    """
    List available project templates.
    GET /api/method/impact_os_ai.impact_os_ai.api.templates.list_templates
    """
    user_email = get_current_user_from_token()

    filters = {}
    if sector:
        filters["sector"] = sector
    if int(is_public):
        filters["is_public"] = 1
    else:
        # Return public + user's own private templates
        filters = [
            ["IOS Template", "is_public", "=", 1],
            ["IOS Template", "owner", "=", user_email],
        ]

    templates = frappe.get_all(
        "IOS Template",
        filters=filters if isinstance(filters, dict) else None,
        or_filters=filters if isinstance(filters, list) else None,
        fields=[
            "name", "template_title", "sector", "description",
            "is_public", "owner", "creation", "modified",
        ],
        order_by="template_title asc",
    )

    return {"templates": templates, "total": len(templates)}


@frappe.whitelist(allow_guest=True)
def get_template(template_name: str):
    """
    Get a template by name/ID.
    GET /api/method/impact_os_ai.impact_os_ai.api.templates.get_template?template_name=xxx
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Template", template_name):
        frappe.throw(_("Template not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Template", template_name)

    if not doc.is_public and doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to view this template"), frappe.PermissionError)

    return _serialize_template(doc)


@frappe.whitelist(allow_guest=True)
def create_template(
    template_title: str,
    sector: str,
    description: str = "",
    is_public: int = 0,
    template_data: str = "",
):
    """
    Create a new project template.
    POST /api/method/impact_os_ai.impact_os_ai.api.templates.create_template
    """
    user_email = get_current_user_from_token()

    # Validate template_data JSON if provided
    if template_data:
        try:
            json.loads(template_data)
        except ValueError:
            frappe.throw(_("template_data must be valid JSON"), frappe.ValidationError)

    doc = frappe.get_doc({
        "doctype": "IOS Template",
        "template_title": template_title,
        "sector": sector,
        "description": description,
        "is_public": int(is_public),
        "template_data": template_data,
        "owner": user_email,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return _serialize_template(doc)


@frappe.whitelist(allow_guest=True)
def update_template(template_name: str, **kwargs):
    """
    Update an existing template.
    PUT /api/method/impact_os_ai.impact_os_ai.api.templates.update_template
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Template", template_name):
        frappe.throw(_("Template not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Template", template_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to modify this template"), frappe.PermissionError)

    allowed_fields = ["template_title", "sector", "description", "is_public", "template_data"]
    for field in allowed_fields:
        if field in kwargs:
            doc.set(field, kwargs[field])

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return _serialize_template(doc)


@frappe.whitelist(allow_guest=True)
def delete_template(template_name: str):
    """
    Delete a template.
    DELETE /api/method/impact_os_ai.impact_os_ai.api.templates.delete_template
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Template", template_name):
        frappe.throw(_("Template not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Template", template_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to delete this template"), frappe.PermissionError)

    doc.delete(ignore_permissions=True)
    frappe.db.commit()

    return {"message": "Template deleted successfully"}


@frappe.whitelist(allow_guest=True)
def apply_template(template_name: str, project_slug: str):
    """
    Apply a template's default data to an existing project.
    POST /api/method/impact_os_ai.impact_os_ai.api.templates.apply_template
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Template", template_name):
        frappe.throw(_("Template not found"), frappe.DoesNotExistError)

    template_doc = frappe.get_doc("IOS Template", template_name)

    if not template_doc.is_public and template_doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to use this template"), frappe.PermissionError)

    if not frappe.db.exists("IOS Project", {"slug": project_slug}):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    project_doc = frappe.get_doc("IOS Project", {"slug": project_slug})

    if project_doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized to modify this project"), frappe.PermissionError)

    # Apply template data to project
    if template_doc.template_data:
        try:
            template_data = json.loads(template_doc.template_data)
            # Merge template sections into project sections
            existing_sections = {}
            if project_doc.generated_sections:
                try:
                    existing_sections = json.loads(project_doc.generated_sections)
                except Exception:
                    existing_sections = {}

            if "sections" in template_data:
                for key, value in template_data["sections"].items():
                    if key not in existing_sections:
                        existing_sections[key] = value

            project_doc.generated_sections = json.dumps(existing_sections)
            project_doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Template apply error: {str(e)}", "ImpactOS Apply Template")
            frappe.throw(_("Failed to apply template data"), frappe.ValidationError)

    return {
        "message": "Template applied successfully",
        "project_slug": project_slug,
        "template_name": template_name,
    }


@frappe.whitelist(allow_guest=True)
def list_sectors():
    """
    List all unique sectors from templates.
    GET /api/method/impact_os_ai.impact_os_ai.api.templates.list_sectors
    """
    get_current_user_from_token()  # Auth check only

    sectors = frappe.db.sql(
        "SELECT DISTINCT sector FROM `tabIOS Template` WHERE sector IS NOT NULL AND sector != '' ORDER BY sector",
        as_list=True,
    )
    sector_list = [row[0] for row in sectors if row[0]]

    # Add default sectors if DB is empty
    defaults = [
        "Education", "Health", "Livelihoods", "WASH", "Food Security",
        "Environment", "Gender & Inclusion", "Governance", "Economic Development",
        "Humanitarian Response", "Youth Development", "Disability Inclusion",
    ]
    all_sectors = sorted(set(sector_list + defaults))

    return {"sectors": all_sectors}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_template(doc) -> dict:
    template_data = {}
    if doc.template_data:
        try:
            template_data = json.loads(doc.template_data)
        except Exception:
            template_data = {}
    return {
        "name": doc.name,
        "template_title": doc.template_title,
        "sector": doc.sector,
        "description": doc.description,
        "is_public": bool(doc.is_public),
        "owner": doc.owner,
        "template_data": template_data,
        "created_at": str(doc.creation),
        "updated_at": str(doc.modified),
    }


def _is_admin(user_email: str) -> bool:
    return "System Manager" in frappe.get_roles(user_email)
