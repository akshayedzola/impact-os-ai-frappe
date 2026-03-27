app_name = "impact_os_ai"
app_title = "Impact OS AI"
app_publisher = "EdZola Technologies"
app_description = "ImpactOS AI — MIS Blueprint Platform powered by MAP Framework"
app_email = "hello@edzola.com"
app_license = "MIT"

required_apps = ["frappe"]

# Fixtures — exports/imports Workspace so ImpactOS AI appears in the Frappe desk
fixtures = [
    {"doctype": "Workspace", "filters": [["module", "=", "Impact OS AI"]]}
]

# Called after a successful Frappe session login
on_session_creation = "impact_os_ai.impact_os_ai.api.auth.on_login_hook"
