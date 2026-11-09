"""Which lead sources are worth paying for? Leads -> quoted -> won, and the money, per source."""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	cols = [
		{"label": _("Lead Source"), "fieldname": "source", "fieldtype": "Data", "width": 170},
		{"label": _("Leads"), "fieldname": "leads", "fieldtype": "Int", "width": 80},
		{"label": _("Quoted"), "fieldname": "quoted", "fieldtype": "Int", "width": 80},
		{"label": _("Won"), "fieldname": "won", "fieldtype": "Int", "width": 70},
		{"label": _("Lead → Quote %"), "fieldname": "quote_rate", "fieldtype": "Percent", "width": 115},
		{"label": _("Quote → Won %"), "fieldname": "win_rate", "fieldtype": "Percent", "width": 115},
		{"label": _("Value Quoted"), "fieldname": "quoted_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Value Won"), "fieldname": "won_value", "fieldtype": "Currency", "width": 140},
	]
	lead_filters = {}
	if filters.get("from_date"):
		lead_filters["creation"] = [">=", filters.from_date]
	if filters.get("to_date"):
		lead_filters.setdefault("creation", [">=", "2000-01-01"])
		lead_filters["creation"] = ["between", [filters.get("from_date") or "2000-01-01", filters.to_date]]
	leads = frappe.get_all("Lead", filters=lead_filters, fields=["name", "utm_source"])
	by_lead = {l.name: (l.utm_source or "Not recorded") for l in leads}

	rows = {}
	for src in set(by_lead.values()):
		rows[src] = frappe._dict(source=src, leads=0, quoted=0, won=0, quoted_value=0, won_value=0)
	for src in by_lead.values():
		rows[src].leads += 1

	if by_lead:
		quotes = frappe.get_all(
			"Quotation",
			filters={"docstatus": 1, "quotation_to": "Lead", "party_name": ["in", list(by_lead)]},
			fields=["party_name", "rounded_total", "grand_total", "pt_won_on"],
		)
		seen_quoted, seen_won = set(), set()
		for q in quotes:
			r = rows[by_lead[q.party_name]]
			amount = flt(q.rounded_total or q.grand_total)
			r.quoted_value += amount
			if q.party_name not in seen_quoted:
				r.quoted += 1
				seen_quoted.add(q.party_name)
			if q.pt_won_on:
				r.won_value += amount
				if q.party_name not in seen_won:
					r.won += 1
					seen_won.add(q.party_name)
	for r in rows.values():
		r.quote_rate = flt(r.quoted * 100 / r.leads, 1) if r.leads else 0
		r.win_rate = flt(r.won * 100 / r.quoted, 1) if r.quoted else 0
	data = sorted(rows.values(), key=lambda r: (-r.leads, r.source))
	chart = {
		"data": {"labels": [r.source for r in data], "datasets": [
			{"name": "Leads", "values": [r.leads for r in data]},
			{"name": "Quoted", "values": [r.quoted for r in data]},
			{"name": "Won", "values": [r.won for r in data]},
		]},
		"type": "bar",
	} if data else None
	return cols, data, None, chart
