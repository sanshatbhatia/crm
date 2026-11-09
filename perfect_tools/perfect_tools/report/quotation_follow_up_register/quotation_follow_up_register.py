"""Every live quotation on one screen: who, how much, sent when, opened?, next call, expires when."""
import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters), None, chart(filters)


def columns():
	return [
		{"label": _("Quotation"), "fieldname": "name", "fieldtype": "Link", "options": "Quotation", "width": 150},
		{"label": _("Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
		{"label": _("Customer / Lead"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Mobile"), "fieldname": "mobile", "fieldtype": "Data", "width": 125},
		{"label": _("Amount (incl. GST)"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 135},
		{"label": _("Sent On"), "fieldname": "sent_on", "fieldtype": "Date", "width": 95},
		{"label": _("Via"), "fieldname": "pt_sent_via", "fieldtype": "Data", "width": 80},
		{"label": _("Opened PDF"), "fieldname": "opened", "fieldtype": "Data", "width": 95},
		{"label": _("Follow-ups"), "fieldname": "pt_followup_count", "fieldtype": "Int", "width": 85},
		{"label": _("Next Follow-up"), "fieldname": "pt_next_followup_on", "fieldtype": "Date", "width": 110},
		{"label": _("Valid Till"), "fieldname": "valid_till", "fieldtype": "Date", "width": 95},
		{"label": _("Days to Expiry"), "fieldname": "days_left", "fieldtype": "Int", "width": 95},
		{"label": _("Last Response"), "fieldname": "pt_last_response", "fieldtype": "Data", "width": 220},
		{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 130},
	]


def _rows(filters):
	conds = {"docstatus": 1}
	if not filters.get("include_closed"):
		conds["status"] = ["in", ["Open", "Replied", "Partially Ordered"]]
		conds["pt_won_on"] = ["is", "not set"]
	if filters.get("owner"):
		conds["owner"] = filters.owner
	if filters.get("from_date"):
		conds["transaction_date"] = [">=", filters.from_date]
	return frappe.get_all(
		"Quotation",
		filters=conds,
		fields=["name", "transaction_date", "customer_name", "party_name", "quotation_to", "contact_mobile", "rounded_total",
				"grand_total", "status", "pt_sent_on", "pt_sent_via", "pt_viewed_on", "pt_view_count", "pt_followup_count",
				"pt_next_followup_on", "valid_till", "pt_last_response", "pt_won_on", "owner"],
		order_by="transaction_date desc",
	)


def stage(r):
	if r.pt_won_on:
		return "Won"
	if r.status in ("Lost", "Expired", "Cancelled"):
		return r.status
	if not r.pt_sent_on:
		return "Not sent yet"
	if r.pt_last_response:
		return "Customer replied"
	if r.pt_next_followup_on and getdate(r.pt_next_followup_on) < getdate(today()):
		return "Follow-up overdue"
	return "Waiting for reply"


def data(filters):
	out = []
	for r in _rows(filters):
		mobile = r.contact_mobile
		if not mobile and r.quotation_to == "Lead":
			mobile = frappe.db.get_value("Lead", r.party_name, "mobile_no")
		out.append(
			{
				**r,
				"customer_name": r.customer_name or r.party_name,
				"mobile": mobile,
				"amount": r.rounded_total or r.grand_total,
				"stage": stage(r),
				"sent_on": getdate(r.pt_sent_on) if r.pt_sent_on else None,
				"opened": (f"Yes ({r.pt_view_count}x)" if r.pt_viewed_on else ("No" if r.pt_sent_on else "")),
				"days_left": date_diff(r.valid_till, today()) if r.valid_till else None,
			}
		)
	# Most urgent first: earliest follow-up date, quotes with no date at the end.
	out.sort(key=lambda r: (r["pt_next_followup_on"] is None, str(r["pt_next_followup_on"] or ""), str(r["transaction_date"])))
	return out


def chart(filters):
	counts = {}
	for r in data(filters):
		counts[r["stage"]] = counts.get(r["stage"], 0) + 1
	if not counts:
		return None
	return {"data": {"labels": list(counts), "datasets": [{"name": "Quotations", "values": list(counts.values())}]}, "type": "bar"}
