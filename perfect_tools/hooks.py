app_name = "perfect_tools"
app_title = "Perfect Tools"
app_publisher = "Perfect Tools"
app_description = "CRM and quotation customisations for Perfect Tools (GORSAN dealer, Nangloi)"
app_email = "satish.perfect@yahoo.com"
app_license = "mit"
required_apps = ["erpnext", "india_compliance"]

# ---------------------------------------------------------------------------------------------
# Form scripts (served directly, no build step needed)
doctype_js = {
	"Lead": "public/js/lead.js",
	"Quotation": "public/js/quotation.js",
	"Perfect Tools Settings": "public/js/perfect_tools_settings.js",
}
doctype_list_js = {"Quotation": "public/js/quotation_list.js"}

# ---------------------------------------------------------------------------------------------
doc_events = {
	"Quotation": {
		"autoname": "perfect_tools.naming.quotation_autoname",
		"validate": "perfect_tools.quotation.validate",
		"on_submit": "perfect_tools.quotation.on_submit",
		"before_update_after_submit": "perfect_tools.quotation.before_update_after_submit",
		"on_cancel": "perfect_tools.quotation.on_cancel",
	},
	"Lead": {
		"before_validate": "perfect_tools.lead.before_validate",
		"validate": "perfect_tools.lead.validate",
		"after_insert": "perfect_tools.lead.after_insert",
		"on_update": "perfect_tools.lead.sync_address",
	},
	"Contact": {"before_validate": "perfect_tools.phone.normalize_contact"},
	"ToDo": {"on_update": "perfect_tools.lead.todo_on_update"},
}

# Times are the site's time zone (Asia/Kolkata).
scheduler_events = {
	"cron": {
		"0 8 * * *": ["perfect_tools.reminders.run_daily"],
		"30 1 * * *": ["perfect_tools.backup.run_daily_backup"],
	},
}

# pt_image("pi_stamp") / pt_image("pi_signature") in print formats: private images inlined at print time.
jinja = {"methods": ["perfect_tools.utils.pt_image"]}

after_install = "perfect_tools.setup.after_install"
after_migrate = "perfect_tools.setup.after_migrate"

# ---------------------------------------------------------------------------------------------
# Everything configured through the UI that this business depends on travels with the app,
# so a fresh site (e.g. Frappe Cloud) gets the same setup on `bench migrate`.
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "Perfect Tools"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "Perfect Tools"]]},
	{"dt": "Print Format", "filters": [["name", "in", ["Perfect Tools PI"]]]},
	{"dt": "Letter Head", "filters": [["name", "in", ["Perfect Tools - K-63 N"]]]},
	{"dt": "Terms and Conditions", "filters": [["name", "like", "Perfect Tools%"]]},
	{"dt": "Quotation Lost Reason"},
	{"dt": "UTM Source"},
	{"dt": "Number Card", "filters": [["module", "=", "Perfect Tools"]]},
	{"dt": "Dashboard Chart", "filters": [["module", "=", "Perfect Tools"]]},
	{"dt": "Workspace", "filters": [["name", "in", ["Perfect Tools"]]]},
	{"dt": "Report", "filters": [["name", "in", ["Lead Journey"]]]},
]
