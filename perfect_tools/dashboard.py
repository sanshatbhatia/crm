"""Numbers for the Perfect Tools page that a plain count/sum card can't give."""
import frappe
from frappe.utils import add_months, flt, get_first_day, today


@frappe.whitelist()
def conversion_rate(filters=None):
	"""Share of submitted quotations (last 6 months) that were won."""
	since = add_months(get_first_day(today()), -5)
	total = frappe.db.count("Quotation", {"docstatus": 1, "transaction_date": [">=", since]})
	won = frappe.db.count("Quotation", {"docstatus": 1, "transaction_date": [">=", since], "pt_won_on": ["is", "set"]})
	return {"value": flt(won * 100 / total, 1) if total else 0, "fieldtype": "Percent"}


@frappe.whitelist()
def followups_today(filters=None):
	return {
		"value": frappe.db.count("ToDo", {"status": "Open", "date": ["<=", today()], "allocated_to": frappe.session.user}),
		"fieldtype": "Int",
		"route": ["List", "ToDo", {"status": "Open", "allocated_to": frappe.session.user}],
	}
