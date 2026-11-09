"""Idempotent setup, run on install and after every `bench migrate`.

Creates/updates: custom fields, property setters, lead sources, lost reasons, T&C variants,
settings defaults, dashboard cards/charts, the 'Perfect Tools' workspace, and points the letter
head / print format at images shipped inside this app (so they survive a move to Frappe Cloud).
"""
import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_days, getdate

MODULE = "Perfect Tools"
IMG = "/assets/perfect_tools/images"
LETTER_HEAD = "Perfect Tools - K-63 N"
PRINT_FORMAT = "Perfect Tools PI"

# ------------------------------------------------------------------------------- custom fields
def _f(**kw):
	kw.setdefault("module", MODULE)
	return kw


CUSTOM_FIELDS = {
	"Quotation": [
		_f(fieldname="pt_round_prices", label="Round discounted prices to nearest ₹1,000", fieldtype="Check",
		   default="1", insert_after="items",
		   description="Applied when you save: a discounted line like 6,37,500 becomes 6,38,000. Lines at list price are never changed."),
		_f(fieldname="pt_advance_received", label="Advance Received", fieldtype="Currency", options="currency",
		   insert_after="rounded_total", allow_on_submit=1, no_copy=1, print_hide=1),
		_f(fieldname="pt_balance_due", label="Balance Payable", fieldtype="Currency", options="currency",
		   insert_after="pt_advance_received", read_only=1, allow_on_submit=1, no_copy=1, print_hide=1),
		_f(fieldname="pt_followup_tab", label="Follow-up", fieldtype="Tab Break", insert_after="supplier_quotation"),
		_f(fieldname="pt_sent_on", label="Sent to Customer On", fieldtype="Datetime", insert_after="pt_followup_tab",
		   allow_on_submit=1, no_copy=1, in_standard_filter=1),
		_f(fieldname="pt_sent_via", label="Sent Via", fieldtype="Select", options="\nWhatsApp\nEmail\nBy hand\nCourier",
		   insert_after="pt_sent_on", allow_on_submit=1, no_copy=1),
		_f(fieldname="pt_viewed_on", label="Customer First Opened PDF", fieldtype="Datetime", insert_after="pt_sent_via",
		   read_only=1, allow_on_submit=1, no_copy=1,
		   description="Filled automatically when the customer opens the WhatsApp link (works once the system is online)."),
		_f(fieldname="pt_view_count", label="Times Opened", fieldtype="Int", insert_after="pt_viewed_on",
		   read_only=1, allow_on_submit=1, no_copy=1),
		_f(fieldname="pt_followup_col", fieldtype="Column Break", insert_after="pt_view_count"),
		_f(fieldname="pt_next_followup_on", label="Next Follow-up On", fieldtype="Date", insert_after="pt_followup_col",
		   allow_on_submit=1, no_copy=1, in_standard_filter=1),
		_f(fieldname="pt_followup_count", label="Follow-ups Done", fieldtype="Int", insert_after="pt_next_followup_on",
		   read_only=1, allow_on_submit=1, no_copy=1),
		_f(fieldname="pt_last_response_on", label="Last Response On", fieldtype="Date", insert_after="pt_followup_count",
		   read_only=1, allow_on_submit=1, no_copy=1),
		_f(fieldname="pt_last_response", label="Last Customer Response", fieldtype="Small Text",
		   insert_after="pt_last_response_on", allow_on_submit=1, no_copy=1),
		_f(fieldname="pt_won_on", label="Order Confirmed (Won) On", fieldtype="Date", insert_after="pt_last_response",
		   allow_on_submit=1, no_copy=1, in_standard_filter=1),
	],
	"Lead": [
		_f(fieldname="gstin", label="Company GSTIN", fieldtype="Data", insert_after="lead_name", length=15,
		   description="15-character GST number, e.g. 07BEHPS0506P1Z5. Goes onto the billing address, the quotation and the customer."),
		_f(fieldname="pt_company_address", label="Company Address", fieldtype="Small Text", insert_after="gstin",
		   description="Street / area / plot. With City and State below, this becomes the billing address on quotations "
					   "(and decides CGST+SGST vs IGST)."),
		_f(fieldname="pt_lead_source", label="Lead Source", fieldtype="Link", options="UTM Source",
		   insert_after="machine_interest", in_standard_filter=1,
		   description="Where this enquiry came from (IndiaMART, JustDial, phone call, reference ...)."),
		_f(fieldname="pt_next_followup_on", label="Next Follow-up", fieldtype="Date", insert_after="pt_lead_source",
		   read_only=1, in_list_view=1, no_copy=1),
		_f(fieldname="pt_last_contacted_on", label="Last Contacted", fieldtype="Date", insert_after="pt_next_followup_on",
		   read_only=1, no_copy=1),
		_f(fieldname="pt_whatsapp_opt_out", label="Do not message (customer opted out)", fieldtype="Check",
		   insert_after="whatsapp_no",
		   description="Tick when the customer asks not to be contacted on WhatsApp. The WhatsApp buttons then refuse to send."),
		_f(fieldname="pt_allow_duplicate", label="Different person, same number", fieldtype="Check",
		   insert_after="pt_whatsapp_opt_out", no_copy=1,
		   description="Only tick this if the duplicate-number warning is wrong (e.g. two brothers sharing a phone)."),
	],
	"Customer": [
		_f(fieldname="pt_whatsapp_opt_out", label="Do not message (customer opted out)", fieldtype="Check",
		   insert_after="customer_group"),
	],
}

PROPERTY_SETTERS = [
	("Quotation", "apply_discount_on", "default", "Net Total", "Data"),
	("Quotation", "valid_till", "reqd", "1", "Check"),
]

LEAD_SOURCES = ["IndiaMART", "JustDial", "TradeIndia", "Phone Call", "WhatsApp", "Walk In", "Reference",
				"Existing Customer", "GORSAN Referral", "Exhibition", "Website", "Social Media", "Cold Calling", "Advertisement"]
LOST_REASONS = ["Price too high", "Bought elsewhere", "Chose another brand", "Bought a used machine",
				"Postponed / no shed yet", "Budget / financing not arranged", "No response", "Delivery time too long"]
CONDITION_PRESETS = [
	"Transport charges to be paid by Perfect Tools.",
	"Transport charges extra, on actual basis.",
	"GI duct line free of cost.",
	"1 set of toolkit extra except pre-milling tools.",
	"Unloading and placement charges to be paid by the buyer on actual basis.",
	"Warranty: 18 months after installation of machines.",
	"Warranty: 24 months after installation of machines.",
	"Consumables and wear parts (tools, bits, buffing wheels, rubber wheels, belts, heaters) are not covered in warranty.",
	"Special price valid for 1 day only.",
	"Delivery: 20-30 days after order confirmation.",
	"Installation and one-time operator training free of charge.",
]


def after_install():
	after_migrate()


def after_migrate():
	steps = [
		ensure_custom_fields, ensure_lead_layout, ensure_property_setters, ensure_masters, ensure_settings, ensure_terms_variants,
		ensure_letterhead_and_print_format, ensure_dashboard, ensure_workspace, backfill_sent_quotes,
		backfill_lead_next_followup, backfill_lead_address,
	]
	for step in steps:
		try:
			step()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Perfect Tools setup step failed: {step.__name__}")
			print(f"Perfect Tools setup: {step.__name__} FAILED (see Error Log)")


# ------------------------------------------------------------------------------- steps
def ensure_custom_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	# Fields added earlier from the UI belong to this app too, so they travel with it.
	for dt, names in {
		"Quotation": ["kind_attention", "special_conditions"],
		"Lead": ["enquiry_date", "machine_interest", "journey_tab", "journey_intro", "number_received_on",
				 "first_reached_out_on", "first_reached_out_via", "journey_col1", "first_connected_on",
				 "first_meeting_on", "first_meeting_place", "journey_col2", "quotation_sent_on",
				 "last_response_on", "last_response"],
	}.items():
		for fn in names:
			cf = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fn}, "name")
			if cf:
				frappe.db.set_value("Custom Field", cf, "module", MODULE, update_modified=False)


LEAD_HIDE = ["job_title", "gender", "type", "request_type", "phone_ext", "fax", "market_segment"]
# (field, put it right after) - builds the Details tab the way Perfect Tools works
LEAD_MOVES = [
	("company_name", "lead_name"),
	("gstin", "company_name"),
	("pt_company_address", "gstin"),
	("city", "pt_company_address"),
	("state", "city"),
	("pt_lead_source", "status"),
]
LEAD_LIST_VIEW = {"company_name": 1, "pt_lead_source": 1, "job_title": 0}
LEAD_LABELS = {"company_name": "Company Name"}


def ensure_lead_layout():
	"""Same as doing it by hand in Customize Form: hide unused fields, move the important ones to Details."""
	cf = frappe.get_doc("Customize Form")
	cf.doc_type = "Lead"
	cf.fetch_to_customize()
	rows = {r.fieldname: r for r in cf.fields}
	for fn in LEAD_HIDE:
		if fn in rows:
			rows[fn].hidden = 1
			rows[fn].in_list_view = 0
			rows[fn].in_standard_filter = 0
	for fn, flag in LEAD_LIST_VIEW.items():
		if fn in rows:
			rows[fn].in_list_view = flag
	for fn, label in LEAD_LABELS.items():
		if fn in rows:
			rows[fn].label = label
	order = [r.fieldname for r in cf.fields]
	for fn, after in LEAD_MOVES:
		if fn in order and after in order:
			order.remove(fn)
			order.insert(order.index(after) + 1, fn)
	cf.set("fields", [rows[fn] for fn in order])
	for i, r in enumerate(cf.fields, start=1):
		r.idx = i
	cf.save_customization()


def ensure_property_setters():
	for dt, field, prop, value, ptype in PROPERTY_SETTERS:
		frappe.make_property_setter(
			{"doctype": dt, "fieldname": field, "property": prop, "value": value, "property_type": ptype},
			validate_fields_for_doctype=False,
		)
	# Everything the earlier setup changed on these forms is part of this app.
	for ps in frappe.get_all("Property Setter", filters={"doc_type": ["in", ["Lead", "Quotation"]], "module": ["is", "not set"]}, pluck="name"):
		frappe.db.set_value("Property Setter", ps, "module", MODULE, update_modified=False)
	for ps in frappe.get_all("Property Setter", filters={"doc_type": ["in", ["Lead", "Quotation"]], "field_name": ["like", "pt_%"]}, pluck="name"):
		frappe.db.set_value("Property Setter", ps, "module", MODULE, update_modified=False)
	for dt, field, prop, value, ptype in PROPERTY_SETTERS:
		name = frappe.db.get_value("Property Setter", {"doc_type": dt, "field_name": field, "property": prop})
		if name:
			frappe.db.set_value("Property Setter", name, "module", MODULE, update_modified=False)


def ensure_masters():
	for s in LEAD_SOURCES:
		if not frappe.db.exists("UTM Source", s):
			frappe.get_doc({"doctype": "UTM Source", "name": s, "__newname": s}).insert(ignore_permissions=True, set_name=s)
	for r in LOST_REASONS:
		if not frappe.db.exists("Quotation Lost Reason", r):
			frappe.get_doc({"doctype": "Quotation Lost Reason", "order_lost_reason": r}).insert(ignore_permissions=True)


def ensure_settings():
	s = frappe.get_single("Perfect Tools Settings")
	changed = False
	defaults = {
		"round_line_prices": 1, "rounding_unit": 1000, "quote_validity_days": 15, "warn_below_list_pct": 70,
		"first_call_within_days": 1, "followup_after_sent_days": 3, "repeat_followup_every_days": 4,
		"max_auto_followups": 3, "expiry_alert_days": 2, "inactive_lead_days": 14,
		"backup_enabled": 1, "backup_keep_days": 14,
		"whatsapp_quote_message": (
			"Namaste {name},\n\nThank you for your interest in GORSAN machines. Please find our quotation "
			"*{pi_no}* for *{amount}* (incl. GST), valid till {valid_till}:\n{link}\n\n"
			"For any query please call us. - {company}, Nangloi, Delhi"
		),
		"whatsapp_greeting_message": (
			"Namaste {name} ji, this is {company}, Nangloi (authorised GORSAN dealer). "
			"Thank you for your enquiry about {machine}. When is a good time to talk?"
		),
	}
	first_run = not s.get("setup_done")
	for k, v in defaults.items():
		if not s.meta.has_field(k):
			continue
		# Text fields: fill when empty. Numbers/checks: only on the very first run, so a value
		# someone deliberately set to 0 later is respected.
		if s.get(k) in (None, "") or (first_run and not s.get(k)):
			s.set(k, v)
			changed = True
	if first_run:
		s.setup_done = 1
		changed = True
	if not s.get("condition_presets"):
		for c in CONDITION_PRESETS:
			s.append("condition_presets", {"condition": c})
		changed = True
	if not s.backup_copy_path and _on_local_wsl():
		s.backup_copy_path = "/mnt/c/Users/user/DadCRM/backups"
		changed = True
	if changed:
		s.flags.ignore_permissions = True
		s.save()


def _on_local_wsl():
	import os

	return os.path.isdir("/mnt/c/Users/user/DadCRM")


def ensure_terms_variants():
	base = frappe.db.get_value("Terms and Conditions", "Perfect Tools Standard", "terms")
	if not base:
		return
	for months in (18, 24):
		title = f"Perfect Tools - Warranty {months} months"
		if frappe.db.exists("Terms and Conditions", title):
			continue
		tc = frappe.get_doc({"doctype": "Terms and Conditions", "title": title,
							 "terms": base.replace("12 months", f"{months} months")})
		if tc.meta.has_field("selling"):
			tc.selling = 1
		tc.insert(ignore_permissions=True)
	# The standard one is the default on every new quotation.
	if frappe.db.exists("Company", "Perfect Tools") and frappe.get_meta("Company").has_field("default_selling_terms"):
		if not frappe.db.get_value("Company", "Perfect Tools", "default_selling_terms"):
			frappe.db.set_value("Company", "Perfect Tools", "default_selling_terms", "Perfect Tools Standard")


SIGN_SOURCES = {  # only used on this laptop, to move the existing images into private files once
	"pi_stamp": "/mnt/c/Users/user/DadCRM/erpnext-import/assets/stamp.jpeg",
	"pi_signature": "/mnt/c/Users/user/DadCRM/erpnext-import/assets/signature.jpeg",
}


def ensure_private_sign_images():
	"""Stamp and signature live as PRIVATE files on Perfect Tools Settings, never in the app's public folder."""
	import os

	from frappe.utils.file_manager import save_file

	for field, path in SIGN_SOURCES.items():
		if frappe.db.get_single_value("Perfect Tools Settings", field) or not os.path.exists(path):
			continue
		with open(path, "rb") as fh:
			f = save_file(os.path.basename(path), fh.read(), "Perfect Tools Settings", "Perfect Tools Settings",
						  is_private=1, df=field)
		frappe.db.set_single_value("Perfect Tools Settings", field, f.file_url)


def ensure_letterhead_and_print_format():
	"""Letter head from the app's images; stamp/signature from private files (see pt_image)."""
	ensure_private_sign_images()
	if frappe.db.exists("Letter Head", LETTER_HEAD):
		frappe.db.set_value("Letter Head", LETTER_HEAD, {
			"image": f"{IMG}/letterhead_K-63N_with_Gorsan.jpeg",
			"footer_image": f"{IMG}/footer_machines_strip.png",
		})
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		return
	pf = frappe.get_doc("Print Format", PRINT_FORMAT)
	html = pf.html
	import re

	# Stamp & signature: private files from Perfect Tools Settings, inlined at print time (pt_image).
	html = re.sub(r'<img src="[^"]*stamp[^"]*" class="s-stamp">',
				  '{% set _st = pt_image("pi_stamp") %}{% if _st %}<img src="{{ _st }}" class="s-stamp">{% endif %}', html)
	html = re.sub(r'<img src="[^"]*signature[^"]*" class="s-sign">',
				  '{% set _sg = pt_image("pi_signature") %}{% if _sg %}<img src="{{ _sg }}" class="s-sign">{% endif %}', html)
	if "Valid Till" not in html:
		html = html.replace(
			'<td class="pt-k"></td><td class="pt-v"></td>',
			'<td class="pt-k">Valid Till</td><td class="pt-v">{{ frappe.utils.formatdate(doc.valid_till, "dd-MMM-yyyy") if doc.valid_till else "" }}</td>',
		)
	# Address like the Excel PIs ("Ludhiana, Punjab"): street (if not just the city), city, state - pin.
	# The default address_display repeats the city and adds "State Code: 06, India".
	old_addr = '{{ (doc.address_display or "") | replace("<br>", ", ") | striptags | trim(", ") }}'
	new_addr = (
		'{%- set _a = frappe.get_doc("Address", doc.customer_address) if doc.customer_address else None -%}'
		'{%- if _a -%}'
		'{{ [(_a.address_line1 if (_a.address_line1 or "") | trim | lower != (_a.city or "") | lower else ""), _a.address_line2, _a.city, '
		'((_a.state or "") ~ (" - " ~ _a.pincode if _a.pincode else ""))] | select | join(", ") }}'
		'{%- if _a.gstin %}<br>GSTIN: {{ _a.gstin }}{% endif -%}'
		'{%- else -%}{{ (doc.address_display or "") | replace("<br>", ", ") | striptags | trim(", ") }}{%- endif -%}'
	)
	if old_addr in html:
		html = html.replace(old_addr, new_addr)
	if "pt_advance_received" not in html:
		html = html.replace(
			'<tr><td colspan="2" class="t-words">',
			'{% if doc.pt_advance_received %}\n'
			'    <tr><td class="t-l">Less: Advance Received</td><td class="t-v">({{ money(doc.pt_advance_received) }})</td></tr>\n'
			'    <tr class="t-grand"><td class="t-l">Balance Payable</td><td class="t-v">{{ money(doc.pt_balance_due) }}</td></tr>\n'
			'    {% endif %}\n    <tr><td colspan="2" class="t-words">',
		)
	if html != pf.html:
		pf.html = html
		pf.flags.ignore_permissions = True
		pf.save()


# ------------------------------------------------------------------------------- dashboard
CARDS = [
	dict(label="Leads This Month", type="Document Type", document_type="Lead", function="Count",
		 filters_json=[["Lead", "creation", "Timespan", "this month", False]], color="#2563EB"),
	dict(label="New Leads Not Yet Called", type="Document Type", document_type="Lead", function="Count",
		 filters_json=[["Lead", "status", "in", ["Lead", "Open"], False]], color="#F59E0B"),
	dict(label="My Follow-ups Due", type="Custom", document_type="ToDo", method="perfect_tools.dashboard.followups_today", color="#DC2626"),
	dict(label="Open Quotations (₹)", type="Document Type", document_type="Quotation", function="Sum",
		 aggregate_function_based_on="rounded_total",
		 filters_json=[["Quotation", "docstatus", "=", 1, False], ["Quotation", "status", "in", ["Open", "Replied"], False],
					   ["Quotation", "pt_won_on", "is", "not set", False]], color="#7C3AED"),
	dict(label="Quotes Sent This Month", type="Document Type", document_type="Quotation", function="Count",
		 filters_json=[["Quotation", "pt_sent_on", "Timespan", "this month", False]], color="#0891B2"),
	dict(label="Won This Month (₹)", type="Document Type", document_type="Quotation", function="Sum",
		 aggregate_function_based_on="rounded_total",
		 filters_json=[["Quotation", "pt_won_on", "Timespan", "this month", False]], color="#16A34A"),
	dict(label="Win Rate (6 months)", type="Custom", document_type="Quotation", method="perfect_tools.dashboard.conversion_rate", color="#16A34A"),
	dict(label="Quotes Expired / Lost This Month", type="Document Type", document_type="Quotation", function="Count",
		 filters_json=[["Quotation", "status", "in", ["Expired", "Lost"], False], ["Quotation", "modified", "Timespan", "this month", False]],
		 color="#6B7280"),
]
CHARTS = [
	dict(chart_name="Leads per Week", chart_type="Count", document_type="Lead", based_on="creation",
		 timeseries=1, timespan="Last Quarter", time_interval="Weekly", type="Bar", filters_json=[], color="#2563EB"),
	dict(chart_name="Leads by Source", chart_type="Group By", document_type="Lead", group_by_based_on="utm_source",
		 group_by_type="Count", type="Donut", filters_json=[], number_of_groups=8),
	dict(chart_name="Leads by Machine", chart_type="Group By", document_type="Lead", group_by_based_on="machine_interest",
		 group_by_type="Count", type="Bar", filters_json=[], number_of_groups=10, color="#F59E0B"),
	dict(chart_name="Quotations by Status", chart_type="Group By", document_type="Quotation", group_by_based_on="status",
		 group_by_type="Count", type="Pie", filters_json=[["Quotation", "docstatus", "=", 1, False]]),
	dict(chart_name="Quoted Value per Month", chart_type="Sum", document_type="Quotation", based_on="transaction_date",
		 value_based_on="rounded_total", timeseries=1, timespan="Last Year", time_interval="Monthly", type="Bar",
		 filters_json=[["Quotation", "docstatus", "=", 1, False]], color="#7C3AED"),
]


def ensure_dashboard():
	for c in CARDS:
		c = dict(c)
		c["filters_json"] = json.dumps(c.get("filters_json", []))
		c.update({"doctype": "Number Card", "module": MODULE, "is_public": 1, "is_standard": 0,
				  "show_percentage_stats": 0})
		name = frappe.db.get_value("Number Card", {"label": c["label"]}, "name")
		doc = frappe.get_doc("Number Card", name) if name else frappe.get_doc(c)
		if name:
			doc.update(c)
			doc.save(ignore_permissions=True)
		else:
			doc.name = c["label"]
			doc.insert(ignore_permissions=True, set_name=c["label"])
		# Only money cards get a currency; otherwise counts/percentages render as "₹ 3.00".
		frappe.db.set_value("Number Card", doc.name, "currency", "INR" if c.get("function") == "Sum" else None,
							update_modified=False)
	for ch in CHARTS:
		ch = dict(ch)
		color = ch.pop("color", None)
		ch["filters_json"] = json.dumps(ch.get("filters_json", []))
		ch.update({"doctype": "Dashboard Chart", "module": MODULE, "is_public": 1, "is_standard": 0, "source": ""})
		if color:
			ch["color"] = color
		if frappe.db.exists("Dashboard Chart", ch["chart_name"]):
			doc = frappe.get_doc("Dashboard Chart", ch["chart_name"])
			doc.update(ch)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(ch).insert(ignore_permissions=True)
		frappe.db.set_value("Dashboard Chart", ch["chart_name"], "currency", "INR" if ch["chart_type"] == "Sum" else None,
							update_modified=False)


SHORTCUTS = [
	dict(label="New Lead", type="DocType", link_to="Lead", doc_view="New", color="Blue"),
	dict(label="New Quotation", type="DocType", link_to="Quotation", doc_view="New", color="Blue"),
	dict(label="My Follow-ups", type="DocType", link_to="ToDo", doc_view="List", color="Red",
		 stats_filter=json.dumps({"status": "Open"}), format="{} open"),
	dict(label="Leads", type="DocType", link_to="Lead", doc_view="List", color="Orange",
		 stats_filter=json.dumps({"status": ["in", ["Lead", "Open"]]}), format="{} not called"),
	dict(label="Quotations", type="DocType", link_to="Quotation", doc_view="List", color="Purple",
		 stats_filter=json.dumps({"docstatus": 1, "status": "Open"}), format="{} open"),
	dict(label="Follow-up Register", type="Report", link_to="Quotation Follow-up Register", report_ref_doctype="Quotation", color="Grey"),
	dict(label="Lead Source Performance", type="Report", link_to="Lead Source Performance", report_ref_doctype="Lead", color="Grey"),
	dict(label="Lead Journey", type="Report", link_to="Lead Journey", report_ref_doctype="Lead", color="Grey"),
	dict(label="Machines & Prices", type="DocType", link_to="Item Price", doc_view="List", color="Grey"),
	dict(label="Customers", type="DocType", link_to="Customer", doc_view="List", color="Grey"),
	dict(label="Follow-up Calendar", type="DocType", link_to="ToDo", doc_view="Calendar", color="Grey"),
	dict(label="Settings", type="DocType", link_to="Perfect Tools Settings", doc_view="", color="Grey"),
]


# Filters MUST be 4-part [doctype, field, op, value]: Frappe's quick-list widget (cleanup_filters) drops
# the LAST filter whenever the first one has 5 parts, so a single 5-part filter silently disappears.
QUICK_LISTS = [
	dict(label="Latest Leads", document_type="Lead", filters=[]),
	dict(label="Open Quotations", document_type="Quotation",
		 filters=[["Quotation", "docstatus", "=", 1], ["Quotation", "status", "in", ["Open", "Replied"]],
				  ["Quotation", "pt_won_on", "is", "not set"]]),
	dict(label="Follow-ups Due", document_type="ToDo", filters=[["ToDo", "status", "=", "Open"]]),
]


def ensure_workspace():
	name = "Perfect Tools"
	ws = frappe.get_doc("Workspace", name) if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace")
	ws.update({"label": name, "title": name, "module": MODULE, "public": 1, "icon": "crm", "sequence_id": 0.5,
			   "is_hidden": 0})
	ws.set("shortcuts", [])
	for s in SHORTCUTS:
		ws.append("shortcuts", s)
	ws.set("number_cards", [])
	for c in CARDS:
		ws.append("number_cards", {"number_card_name": frappe.db.get_value("Number Card", {"label": c["label"]}, "name"), "label": c["label"]})
	ws.set("charts", [])
	for ch in CHARTS:
		ws.append("charts", {"chart_name": ch["chart_name"], "label": ch["chart_name"]})
	ws.set("quick_lists", [])
	for ql in QUICK_LISTS:
		ws.append("quick_lists", {"document_type": ql["document_type"], "label": ql["label"],
								  "quick_list_filter": json.dumps(ql["filters"])})
	ws.set("roles", [])
	for r in ("Sales User", "Sales Manager", "System Manager"):
		ws.append("roles", {"role": r})

	blocks = []

	def add(btype, data):
		blocks.append({"id": frappe.generate_hash(length=10), "type": btype, "data": data})

	add("header", {"text": '<span class="h4"><b>Today</b></span>', "col": 12})
	for c in CARDS[:4]:
		add("number_card", {"number_card_name": frappe.db.get_value("Number Card", {"label": c["label"]}, "name"), "col": 3})
	add("header", {"text": '<span class="h4"><b>Latest</b></span>', "col": 12})
	for ql in QUICK_LISTS:
		add("quick_list", {"quick_list_name": ql["label"], "col": 4})
	add("header", {"text": '<span class="h4"><b>Quick actions</b></span>', "col": 12})
	for s in SHORTCUTS:
		add("shortcut", {"shortcut_name": s["label"], "col": 3})
	add("header", {"text": '<span class="h4"><b>This month</b></span>', "col": 12})
	for c in CARDS[4:]:
		add("number_card", {"number_card_name": frappe.db.get_value("Number Card", {"label": c["label"]}, "name"), "col": 3})
	add("header", {"text": '<span class="h4"><b>Trends</b></span>', "col": 12})
	for i, ch in enumerate(CHARTS):
		add("chart", {"chart_name": ch["chart_name"], "col": 12 if i in (0, 4) else 6})
	ws.content = json.dumps(blocks)
	ws.flags.ignore_permissions = True
	ws.flags.ignore_links = True
	if ws.is_new():
		ws.insert()
	else:
		ws.save()
	for user in frappe.get_all("User", filters={"user_type": "System User", "enabled": 1}, pluck="name"):
		if frappe.get_meta("User").has_field("default_workspace") and not frappe.db.get_value("User", user, "default_workspace"):
			frappe.db.set_value("User", user, "default_workspace", name, update_modified=False)


def backfill_lead_address():
	"""Leads that already have a billing address: show it in the new Company Address / GSTIN fields."""
	rows = frappe.db.sql(
		"""select dl.link_name as lead, a.address_line1, a.gstin from `tabAddress` a
		join `tabDynamic Link` dl on dl.parent = a.name and dl.parenttype = 'Address' and dl.link_doctype = 'Lead'
		order by a.is_primary_address desc, a.creation""",
		as_dict=True,
	)
	seen = set()
	for r in rows:
		if r.lead in seen or not frappe.db.exists("Lead", r.lead):
			continue
		seen.add(r.lead)
		cur = frappe.db.get_value("Lead", r.lead, ["pt_company_address", "gstin"], as_dict=True)
		vals = {}
		if not cur.pt_company_address and r.address_line1:
			vals["pt_company_address"] = r.address_line1
		if not cur.gstin and r.gstin:
			vals["gstin"] = r.gstin
		if vals:
			frappe.db.set_value("Lead", r.lead, vals, update_modified=False)


def backfill_lead_next_followup():
	"""Every lead's 'Next follow-up' = its earliest open task (fixes any stale date)."""
	from perfect_tools.utils import refresh_lead_next_followup

	for lead in frappe.get_all("Lead", pluck="name"):
		refresh_lead_next_followup(lead)


def backfill_sent_quotes():
	"""Quotes made before this app tracked 'sent' carry the date on their lead; copy it over once."""
	if not frappe.db.has_column("Lead", "quotation_sent_on"):
		return
	for q in frappe.get_all(
		"Quotation",
		filters={"docstatus": 1, "quotation_to": "Lead", "pt_sent_on": ["is", "not set"], "status": ["in", ["Open", "Replied", "Lost", "Expired"]]},
		fields=["name", "party_name", "status"],
	):
		sent = frappe.db.get_value("Lead", q.party_name, "quotation_sent_on")
		if not sent:
			continue
		values = {"pt_sent_on": f"{getdate(sent)} 11:00:00", "pt_sent_via": "WhatsApp"}
		if q.status in ("Open", "Replied"):
			values["pt_next_followup_on"] = add_days(sent, 3)
		frappe.db.set_value("Quotation", q.name, values, update_modified=False)
