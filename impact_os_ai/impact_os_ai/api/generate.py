import frappe
from frappe import _
from .auth import get_current_user_from_token
import json
import openai


def _get_openai_client():
    api_key = frappe.conf.get("openai_api_key", "")
    if not api_key:
        frappe.throw(_("OpenAI API key is not configured in site_config.json"), frappe.ConfigurationError)
    return openai.OpenAI(api_key=api_key)


def _project_context(doc) -> str:
    return (
        f"Organisation: {doc.organisation_name or 'Unknown'}\n"
        f"Project Title: {doc.project_title}\n"
        f"Sector: {doc.sector}\n"
        f"Country: {doc.country or 'Not specified'}\n"
        f"Organisation Type: {doc.organisation_type or 'Not specified'}\n"
        f"Team Size: {doc.team_size or 'Not specified'}\n"
        f"Current Data Method: {doc.current_data_method or 'Not specified'}\n"
        f"Funder Reporting: {doc.funder_reporting or 'Not specified'}\n"
        f"Description: {doc.description or 'Not provided'}\n"
    )


# ---------------------------------------------------------------------------
# Main generation endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def start(project_name: str, scope: str = ""):
    """
    Kick off full blueprint generation for a project.
    POST /api/method/impact_os_ai.impact_os_ai.api.generate.start
    scope: JSON array e.g. '["toc","data_model","modules","dashboards","sprint_plan"]'
    """
    user_email = get_current_user_from_token()

    if not frappe.db.exists("IOS Project", project_name):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Project", project_name)

    if doc.owner != user_email and not _is_admin(user_email):
        frappe.throw(_("Not authorized"), frappe.PermissionError)

    # Mark as generating
    doc.generation_status = "generating"
    doc.generation_progress = 5
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Run the pipeline via background job
    frappe.enqueue(
        "impact_os_ai.impact_os_ai.api.generate.run_pipeline",
        queue="long",
        timeout=300,
        project_name=project_name,
        scope=scope,
    )

    return {
        "project_name": project_name,
        "status": "generating",
        "message": "Blueprint generation started",
    }


@frappe.whitelist(allow_guest=True)
def get_status(project_name: str):
    """
    Poll generation status.
    GET /api/method/impact_os_ai.impact_os_ai.api.generate.get_status?project_name=xxx
    """
    if not frappe.db.exists("IOS Project", project_name):
        frappe.throw(_("Project not found"), frappe.DoesNotExistError)

    doc = frappe.get_doc("IOS Project", project_name)

    return {
        "project_name": project_name,
        "generation_status": doc.generation_status,
        "generation_progress": doc.generation_progress or 0,
        "status": doc.generation_status,  # alias for frontend compat
    }


def run_pipeline(project_name: str, scope: str = ""):
    """
    Background job: generates all blueprint sections sequentially.
    """
    doc = frappe.get_doc("IOS Project", project_name)
    client = _get_openai_client()
    context = _project_context(doc)

    try:
        requested = json.loads(scope) if scope else ["toc", "data_model", "modules", "dashboards", "sprint_plan"]
    except Exception:
        requested = ["toc", "data_model", "modules", "dashboards", "sprint_plan"]

    steps = [
        ("toc", "theory_of_change", _prompt_toc, 20),
        ("data_model", "data_model", _prompt_data_model, 40),
        ("modules", "module_specs", _prompt_modules, 60),
        ("dashboards", "dashboard_plan", _prompt_dashboards, 80),
        ("sprint_plan", "sprint_plan", _prompt_sprint, 95),
    ]

    try:
        for key, field, prompt_fn, progress in steps:
            if key not in requested:
                continue

            prompt = prompt_fn(doc, context)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert nonprofit MIS consultant using the MAP Framework "
                            "(Model → Align → Power with AI). Always respond with valid JSON only. "
                            "No markdown, no code blocks, no commentary — pure JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2500,
            )
            content = response.choices[0].message.content.strip()

            # Validate JSON
            try:
                json.loads(content)
            except Exception:
                # Wrap raw text in a JSON structure if parsing fails
                content = json.dumps({"content": content})

            doc.set(field, content)
            doc.generation_progress = progress
            doc.save(ignore_permissions=True)
            frappe.db.commit()

        doc.generation_status = "completed"
        doc.generation_progress = 100
        doc.save(ignore_permissions=True)
        frappe.db.commit()

    except Exception as e:
        frappe.log_error(f"Blueprint generation failed for {project_name}: {str(e)}", "ImpactOS Generate")
        doc.generation_status = "failed"
        doc.generation_progress = 0
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        raise


# ---------------------------------------------------------------------------
# Section-level prompts
# ---------------------------------------------------------------------------

def _prompt_toc(doc, context: str) -> str:
    return f"""Generate a Theory of Change for this nonprofit programme.

{context}

Return JSON with this exact structure:
{{
  "problem_statement": "...",
  "target_population": "...",
  "activities": ["activity 1", "activity 2", "activity 3", "activity 4"],
  "outputs": ["output 1", "output 2", "output 3"],
  "outcomes": ["short-term outcome 1", "short-term outcome 2", "medium-term outcome 1"],
  "impact": "...",
  "assumptions": ["assumption 1", "assumption 2"],
  "indicators": ["indicator 1", "indicator 2", "indicator 3"]
}}"""


def _prompt_data_model(doc, context: str) -> str:
    return f"""Design a Frappe/database data model for this nonprofit MIS system.

{context}

Return JSON with this exact structure:
{{
  "entities": [
    {{
      "name": "EntityName",
      "label": "Human Label",
      "description": "...",
      "fields": [
        {{"name": "field_name", "label": "Field Label", "type": "Data|Select|Int|Date|Link|Text", "required": true}}
      ]
    }}
  ]
}}

Include 5-8 entities relevant to {doc.sector} sector tracking (e.g. Beneficiary, Intervention, Indicator, Report, Staff)."""


def _prompt_modules(doc, context: str) -> str:
    return f"""Design module specifications for a Frappe-based MIS for this programme.

{context}

Return JSON with this exact structure:
{{
  "modules": [
    {{
      "name": "ModuleName",
      "label": "Module Label",
      "description": "...",
      "user_stories": ["As a [role], I want to [action] so that [benefit]"],
      "key_fields": ["field1", "field2"],
      "permissions": {{"field_officer": "read/write", "manager": "read/write/delete"}}
    }}
  ]
}}

Design 4-6 modules appropriate for {doc.sector} sector. Include: Beneficiary Management, Data Collection, Reporting, and sector-specific modules."""


def _prompt_dashboards(doc, context: str) -> str:
    return f"""Design dashboard specifications for this nonprofit MIS.

{context}

Return JSON with this exact structure:
{{
  "dashboards": [
    {{
      "name": "DashboardName",
      "label": "Dashboard Label",
      "target_user": "Programme Manager / Field Officer / Donor",
      "kpis": [
        {{"metric": "KPI Name", "description": "...", "visualization": "number/bar/line/pie"}}
      ],
      "charts": [
        {{"title": "Chart Title", "type": "bar|line|pie|table", "data_source": "..."}}
      ],
      "filters": ["filter1", "filter2"]
    }}
  ]
}}

Design 3-4 dashboards for different user roles in {doc.sector} programmes."""


def _prompt_sprint(doc, context: str) -> str:
    return f"""Create an implementation sprint plan to build this MIS in Frappe.

{context}

Return JSON with this exact structure:
{{
  "total_weeks": 12,
  "sprints": [
    {{
      "sprint_number": 1,
      "weeks": "1-2",
      "theme": "Sprint Theme",
      "goals": ["goal 1", "goal 2"],
      "deliverables": ["deliverable 1", "deliverable 2"],
      "tasks": [
        {{"task": "Task description", "owner": "developer/consultant", "days": 2}}
      ]
    }}
  ]
}}

Plan 6 sprints of 2 weeks each. Start with data model setup, then modules, then dashboards, then testing."""


def _is_admin(user_email: str) -> bool:
    return "System Manager" in frappe.get_roles(user_email)
