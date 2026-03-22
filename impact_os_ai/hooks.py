app_name = "impact_os_ai"
app_title = "Impact OS AI"
app_publisher = "EdZola Technologies"
app_description = "ImpactOS AI — MIS Blueprint Platform powered by MAP Framework"
app_email = "hello@edzola.com"
app_license = "MIT"

# Runs after the app is installed on a site
# after_install = "impact_os_ai.impact_os_ai.setup.after_install"

# Called after a successful Frappe session login
on_session_creation = "impact_os_ai.impact_os_ai.api.auth.on_login_hook"
