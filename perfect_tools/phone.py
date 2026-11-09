"""Indian phone numbers, one consistent shape: +91-XXXXXXXXXX.

Leads arrive as 9876543210, 098765 43210, +91 98765-43210, 919876543210 or even '+7400000123'
(a real quote). Matching duplicates and opening WhatsApp both need one canonical form.
"""
import re

import frappe

_NON_DIGIT = re.compile(r"\D")


def digits(number) -> str:
	return _NON_DIGIT.sub("", str(number or ""))


def normalize_in(number):
	"""Return +91-XXXXXXXXXX for anything that is clearly an Indian mobile; leave the rest as typed."""
	if not number:
		return number
	raw = str(number).strip()
	d = digits(raw)
	if len(d) == 10 and d[0] in "6789":
		return f"+91-{d}"
	if len(d) == 11 and d[0] == "0" and d[1] in "6789":
		return f"+91-{d[1:]}"
	if len(d) == 12 and d.startswith("91") and d[2] in "6789":
		return f"+91-{d[2:]}"
	if len(d) == 13 and d.startswith("091") and d[3] in "6789":
		return f"+91-{d[3:]}"
	return raw  # landline, foreign or incomplete: don't guess


def match_key(number) -> str:
	"""Last 10 digits: what two spellings of the same mobile have in common."""
	d = digits(number)
	return d[-10:] if len(d) >= 10 else ""


def whatsapp_digits(number) -> str:
	"""Digits for https://wa.me/<digits> (country code, no plus)."""
	key = match_key(number)
	if key and key[0] in "6789":
		return "91" + key
	return digits(number)


def normalize_contact(doc, method=None):
	for row in doc.get("phone_nos") or []:
		row.phone = normalize_in(row.phone)
	for field in ("mobile_no", "phone"):
		if doc.get(field):
			doc.set(field, normalize_in(doc.get(field)))


def find_leads_with_numbers(numbers, exclude=None):
	keys = sorted({k for k in (match_key(n) for n in numbers) if k})
	if not keys:
		return []
	expr = "right(regexp_replace(ifnull({0}, ''), '[^0-9]', ''), 10)"
	where = " or ".join(f"{expr.format(f)} in %(keys)s" for f in ("mobile_no", "whatsapp_no", "phone"))
	return frappe.db.sql(
		f"""select name, lead_name, company_name, status from `tabLead`
		where ({where}) and name != %(exclude)s order by creation""",
		{"keys": keys, "exclude": exclude or ""},
		as_dict=True,
	)


def find_customers_with_numbers(numbers):
	keys = sorted({k for k in (match_key(n) for n in numbers) if k})
	if not keys:
		return []
	return frappe.db.sql(
		"""select distinct dl.link_name as customer
		from `tabContact Phone` cp
		join `tabDynamic Link` dl on dl.parent = cp.parent and dl.parenttype = 'Contact' and dl.link_doctype = 'Customer'
		where right(regexp_replace(ifnull(cp.phone, ''), '[^0-9]', ''), 10) in %(keys)s""",
		{"keys": keys},
		as_dict=True,
	)
