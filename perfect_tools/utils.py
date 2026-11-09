from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe.utils import cint, getdate, today


def settings():
	return frappe.get_cached_doc("Perfect Tools Settings")


def pt_image(which):
	"""Jinja helper for the PI: the stamp / signature from Perfect Tools Settings as an inline data URI.
	The files stay private (no public URL); the image travels inside the printed page / PDF only."""
	import base64

	if which not in ("pi_stamp", "pi_signature"):
		return ""
	url = frappe.db.get_single_value("Perfect Tools Settings", which)
	if not url:
		return ""
	try:
		f = frappe.get_doc("File", {"file_url": url})
		content = f.get_content()
		if isinstance(content, str):
			content = content.encode()
		ext = (f.file_name or url).rsplit(".", 1)[-1].lower()
		mime = {"png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
		return f"data:{mime};base64," + base64.b64encode(content).decode()
	except Exception:
		frappe.log_error(title=f"Perfect Tools: could not load {which} for printing")
		return ""


def round_half_up(value, unit=1000):
	"""Excel's ROUND(x, -3): 637,500 -> 638,000; 637,499 -> 637,000."""
	unit = cint(unit) or 1000
	q = (Decimal(str(value)) / Decimal(unit)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
	return float(q * unit)


def open_todos(reference_type, reference_name, marker=None):
	filters = {"reference_type": reference_type, "reference_name": reference_name, "status": "Open"}
	if marker:
		filters["description"] = ["like", f"%{marker}%"]
	return frappe.get_all("ToDo", filters=filters, pluck="name")


def make_todo(reference_type, reference_name, description, date=None, user=None, priority="Medium"):
	"""Create an open ToDo (a follow-up on someone's list). Returns its name."""
	user = user or frappe.session.user
	if user in ("Guest", None) or not frappe.db.exists("User", user):
		user = "Administrator"
	todo = frappe.get_doc(
		{
			"doctype": "ToDo",
			"status": "Open",
			"priority": priority,
			"date": getdate(date or today()),
			"allocated_to": user,
			"assigned_by": "Administrator",
			"description": description,
			"reference_type": reference_type,
			"reference_name": reference_name,
		}
	)
	todo.flags.ignore_permissions = True
	todo.insert()
	if reference_type == "Lead":
		refresh_lead_next_followup(reference_name)
	elif reference_type == "Quotation":
		refresh_for_quote(reference_name)
	return todo.name


def close_todos(reference_type, reference_name, marker=None):
	for name in open_todos(reference_type, reference_name, marker):
		frappe.db.set_value("ToDo", name, "status", "Closed", update_modified=True)
	if reference_type == "Lead":
		refresh_lead_next_followup(reference_name)
	elif reference_type == "Quotation":
		refresh_for_quote(reference_name)


def refresh_lead_next_followup(lead):
	"""A lead's 'Next follow-up' = the earliest of: its open tasks, and the follow-ups planned on its live
	quotations (blank when nothing is planned)."""
	if not lead or not frappe.db.exists("Lead", lead):
		return
	dates = frappe.get_all("ToDo", filters={"reference_type": "Lead", "reference_name": lead, "status": "Open"}, pluck="date")
	quotes = frappe.get_all(
		"Quotation",
		filters={"quotation_to": "Lead", "party_name": lead, "docstatus": 1, "status": ["in", ["Open", "Replied"]],
				 "pt_won_on": ["is", "not set"]},
		fields=["name", "pt_next_followup_on"],
	)
	for q in quotes:
		if q.pt_next_followup_on:
			dates.append(q.pt_next_followup_on)
		dates += frappe.get_all("ToDo", filters={"reference_type": "Quotation", "reference_name": q.name, "status": "Open"}, pluck="date")
	dates = [getdate(d) for d in dates if d]
	frappe.db.set_value("Lead", lead, "pt_next_followup_on", min(dates) if dates else None, update_modified=False)


def refresh_for_quote(quotation):
	party = frappe.db.get_value("Quotation", quotation, ["quotation_to", "party_name"], as_dict=True)
	if party and party.quotation_to == "Lead":
		refresh_lead_next_followup(party.party_name)


def add_comment(doctype, name, text, comment_type="Comment"):
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": comment_type,
			"reference_doctype": doctype,
			"reference_name": name,
			"content": text,
			"comment_email": frappe.session.user,
		}
	).insert(ignore_permissions=True)


def notify(users, subject, doctype=None, name=None, body=None):
	"""Bell-icon notification in the app (no email/WhatsApp needed)."""
	from frappe.desk.doctype.notification_log.notification_log import make_notification_logs

	users = [u for u in set(users or []) if u and u != "Guest"]
	if not users:
		return
	make_notification_logs(
		frappe._dict(
			subject=subject,
			email_content=body or subject,
			type="Alert",
			document_type=doctype,
			document_name=name,
			from_user="Administrator",
		),
		users,
	)


def money(value):
	return frappe.utils.fmt_money(value or 0, 0, "INR")
