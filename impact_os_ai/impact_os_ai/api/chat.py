import frappe
from frappe import _
from .auth import get_current_user_from_token
import json
import openai


SYSTEM_PROMPT = (
    "You are ImpactOS AI, an expert assistant for impact measurement, monitoring & evaluation (M&E), "
    "and social impact strategy. You specialize in the MAP Framework (Mission-Aligned Planning), "
    "logframes, theories of change, SMART indicators, donor reporting, and MIS blueprints. "
    "You help NGOs, social enterprises, foundations, and development organizations design rigorous "
    "impact measurement systems. Always be professional, specific, and actionable. "
    "When referencing frameworks, cite them clearly (e.g., SDGs, IRIS+, GRI, OECD DAC criteria). "
    "If asked about a user's specific project, refer to the project context provided."
)


def _get_openai_client():
    api_key = frappe.conf.get("openai_api_key", "")
    if not api_key:
        frappe.throw(_("OpenAI API key is not configured"), frappe.ConfigurationError)
    return openai.OpenAI(api_key=api_key)


@frappe.whitelist(allow_guest=True)
def send_message(message: str, project_slug: str = "", session_id: str = ""):
    """
    Send a chat message and get an AI response.
    POST /api/method/impact_os_ai.impact_os_ai.api.chat.send_message
    """
    user_email = get_current_user_from_token()

    if not message or not message.strip():
        frappe.throw(_("Message cannot be empty"), frappe.ValidationError)

    # Build conversation context
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add project context if provided
    project_context = ""
    if project_slug:
        project_context = _get_project_context(project_slug, user_email)
        if project_context:
            messages.append({
                "role": "system",
                "content": f"Current project context:\n{project_context}",
            })

    # Load conversation history if session_id provided
    if session_id:
        history = _get_conversation_history(user_email, session_id, limit=10)
        messages.extend(history)

    # Add user message
    messages.append({"role": "user", "content": message})

    # Get AI response
    client = _get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )
        assistant_content = response.choices[0].message.content
    except openai.APIError as e:
        frappe.log_error(f"OpenAI Chat API error: {str(e)}", "ImpactOS Chat")
        frappe.throw(_("Chat service temporarily unavailable. Please try again."), frappe.ValidationError)

    # Persist messages
    _save_message(user_email, "user", message, project_slug, session_id)
    _save_message(user_email, "assistant", assistant_content, project_slug, session_id)

    return {
        "role": "assistant",
        "content": assistant_content,
        "session_id": session_id,
    }


@frappe.whitelist(allow_guest=True)
def get_history(project_slug: str = "", session_id: str = "", limit: int = 50):
    """
    Get chat history for the current user.
    GET /api/method/impact_os_ai.impact_os_ai.api.chat.get_history
    """
    user_email = get_current_user_from_token()

    filters = {"user": user_email}
    if project_slug:
        filters["project_slug"] = project_slug
    if session_id:
        filters["session_id"] = session_id

    messages = frappe.get_all(
        "IOS Chat Message",
        filters=filters,
        fields=["name", "role", "content", "project_slug", "session_id", "creation"],
        order_by="creation asc",
        limit_page_length=int(limit),
    )

    return {"messages": messages, "total": len(messages)}


@frappe.whitelist(allow_guest=True)
def clear_history(project_slug: str = "", session_id: str = ""):
    """
    Clear chat history.
    DELETE /api/method/impact_os_ai.impact_os_ai.api.chat.clear_history
    """
    user_email = get_current_user_from_token()

    filters = {"user": user_email}
    if project_slug:
        filters["project_slug"] = project_slug
    if session_id:
        filters["session_id"] = session_id

    messages = frappe.get_all("IOS Chat Message", filters=filters, fields=["name"])
    for msg in messages:
        frappe.delete_doc("IOS Chat Message", msg["name"], ignore_permissions=True)

    frappe.db.commit()
    return {"message": f"Cleared {len(messages)} messages"}


@frappe.whitelist(allow_guest=True)
def ask_about_section(slug: str, section: str, question: str):
    """
    Ask a specific question about a generated section.
    POST /api/method/impact_os_ai.impact_os_ai.api.chat.ask_about_section
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Project", {"slug": slug}):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    project_doc = frappe.get_doc("IOS Project", {"slug": slug})

    if project_doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized"), frappe.PermissionError)

    sections = {}
    if project_doc.generated_sections:
        try:
            sections = json.loads(project_doc.generated_sections)
        except Exception:
            sections = {}

    section_content = sections.get(section, {}).get("content", "")

    context = (
        f"Project: {project_doc.project_title} ({project_doc.organization})\n"
        f"Sector: {project_doc.sector}\n\n"
        f"Generated section '{section}':\n{section_content}\n\n"
        f"The user is asking: {question}"
    )

    client = _get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        answer = response.choices[0].message.content
    except openai.APIError as e:
        frappe.log_error(f"OpenAI Chat API error: {str(e)}", "ImpactOS Section Chat")
        frappe.throw(_("Chat service temporarily unavailable."), frappe.ValidationError)

    return {
        "section": section,
        "question": question,
        "answer": answer,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_context(slug: str, user_email: str) -> str:
    if not frappe.db.exists("IOS Project", {"slug": slug}):
        return ""
    doc = frappe.get_doc("IOS Project", {"slug": slug})
    if doc.owner != user_email and "System Manager" not in frappe.get_roles(user_email):
        return ""
    return (
        f"Title: {doc.project_title}\n"
        f"Organization: {doc.organization}\n"
        f"Sector: {doc.sector}\n"
        f"Country: {doc.country or 'N/A'}\n"
        f"Budget: USD {doc.budget_usd or 'N/A'}\n"
        f"Duration: {doc.duration_months or 12} months\n"
        f"Description: {doc.description or 'N/A'}\n"
    )


def _get_conversation_history(user_email: str, session_id: str, limit: int = 10) -> list:
    messages = frappe.get_all(
        "IOS Chat Message",
        filters={"user": user_email, "session_id": session_id},
        fields=["role", "content"],
        order_by="creation asc",
        limit_page_length=limit,
    )
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def _save_message(user_email: str, role: str, content: str, project_slug: str = "", session_id: str = ""):
    doc = frappe.get_doc({
        "doctype": "IOS Chat Message",
        "user": user_email,
        "role": role,
        "content": content,
        "project_slug": project_slug or "",
        "session_id": session_id or "",
    })
    doc.insert(ignore_permissions=True)


def _is_admin(user_email: str) -> bool:
    return "System Manager" in frappe.get_roles(user_email)
