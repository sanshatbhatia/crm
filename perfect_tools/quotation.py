"""Quotation rules that encode how Perfect Tools actually quotes.

* A quote is valid for N days (15) unless the person changes it.
* Discounted line prices are rounded to the nearest Rs 1,000 (Excel's ROUND(x,-3)), on by default,
  switchable per quote.
* The special discount always comes off BEFORE GST (fixes the Santosh-quote error).
* Advance received -> balance payable is shown on the PI.
* Warn (never block) when a price falls below a set share of the list price.
* After submit: a 'send it' task; once sent, automatic follow-ups until the customer answers.
"""
from urllib.parse import quote as urlquote

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	flt,
	formatdate,
	get_url,
	getdate,
	now_datetime,
	today,
)

from perfect_tools.phone import whatsapp_digits
from perfect_tools.utils import (
	add_comment,
	close_todos,
	make_todo,
	money,
	notify,
	open_todos,
	round_half_up,
	settings,
)

PRINT_FORMAT = "Perfect Tools PI"


# ------------------------------------------------------------------------------------ doc events
def validate(doc, method=None):
	s = settings()
	if doc.transaction_date and not doc.valid_till:
		doc.valid_till = add_days(doc.transaction_date, cint(s.quote_validity_days) or 15)
	if not doc.get("kind_attention"):
		doc.kind_attention = default_attention(doc)
	recalc = False
	if (doc.discount_amount or doc.additional_discount_percentage) and doc.apply_discount_on != "Net Total":
		# Special discount reduces the taxable value; GST is charged on what the customer pays.
		doc.apply_discount_on = "Net Total"
		recalc = True
	if round_line_prices(doc, s):
		recalc = True
	if recalc:
		doc.calculate_taxes_and_totals()
	set_balance(doc)
	if not doc.flags.in_test and frappe.request:
		warn_below_floor(doc, s)


def before_update_after_submit(doc, method=None):
	set_balance(doc)


def on_submit(doc, method=None):
	if not doc.get("pt_sent_on") and not open_todos("Quotation", doc.name, "[Send]"):
		make_todo(
			"Quotation",
			doc.name,
			f"[Send] Send {doc.name} ({money(doc.rounded_total or doc.grand_total)}) to {doc.customer_name or doc.party_name}",
			today(),
			doc.owner,
			priority="High",
		)


def on_cancel(doc, method=None):
	close_todos("Quotation", doc.name)


# ------------------------------------------------------------------------------------ helpers
def default_attention(doc):
	if doc.get("contact_display"):
		return doc.contact_display
	if doc.quotation_to == "Lead" and doc.party_name:
		name = frappe.db.get_value("Lead", doc.party_name, "lead_name")
		return f"Mr./Ms. {name} Ji" if name else None
	return None


def round_line_prices(doc, s=None) -> bool:
	"""Round every DISCOUNTED line to the nearest unit (Rs 1,000). Lines at list price are untouched,
	so deliberate prices like 32,500 for an accessory stay as typed."""
	s = s or settings()
	if not cint(doc.get("pt_round_prices")):
		return False
	unit = cint(s.rounding_unit) or 1000
	changed = False
	for item in doc.items:
		plr, rate = flt(item.price_list_rate), flt(item.rate)
		if not plr or not rate or rate >= plr:
			continue
		rounded = round_half_up(rate, unit)
		if rounded <= 0 or rounded == rate:
			continue
		item.rate = rounded
		item.discount_percentage = 0
		item.discount_amount = flt(plr - rounded, item.precision("discount_amount"))
		changed = True
	return changed


def set_balance(doc):
	total = flt(doc.rounded_total) or flt(doc.grand_total)
	doc.pt_balance_due = flt(total - flt(doc.get("pt_advance_received")), doc.precision("grand_total"))


def warn_below_floor(doc, s):
	pct = flt(s.warn_below_list_pct)
	if not pct:
		return
	low = [
		f"{i.item_name}: {money(i.rate)} is {flt(i.rate * 100 / i.price_list_rate, 1)}% of list {money(i.price_list_rate)}"
		for i in doc.items
		if flt(i.price_list_rate) and flt(i.rate) < flt(i.price_list_rate) * pct / 100
	]
	if low:
		frappe.msgprint(
			"<br>".join(low)
			+ "<br><br>"
			+ _("These prices are below {0}% of list. Saved anyway - just make sure this is intended.").format(pct),
			title=_("Below the usual price"),
			indicator="orange",
		)


def party_mobile(doc):
	if doc.get("contact_mobile"):
		return doc.contact_mobile
	if doc.quotation_to == "Lead":
		return frappe.db.get_value("Lead", doc.party_name, "whatsapp_no") or frappe.db.get_value(
			"Lead", doc.party_name, "mobile_no"
		)
	if doc.quotation_to == "Customer":
		return frappe.db.get_value("Customer", doc.party_name, "mobile_no")
	return None


def opted_out(doc):
	if doc.quotation_to == "Lead":
		lead = frappe.db.get_value("Lead", doc.party_name, ["pt_whatsapp_opt_out", "status"], as_dict=True)
		return bool(lead and (lead.pt_whatsapp_opt_out or lead.status == "Do Not Contact"))
	if doc.quotation_to == "Customer":
		return bool(frappe.db.get_value("Customer", doc.party_name, "pt_whatsapp_opt_out"))
	return False


def share_link(doc):
	"""A link the customer can open without logging in. It goes through our tracker so we know
	when (and if) they opened it, then serves the PDF."""
	expires = add_days(doc.valid_till or today(), 60)
	key = doc.get_document_share_key(expires_on=expires)
	return get_url(f"/api/method/perfect_tools.quotation.open_pdf?q={urlquote(doc.name)}&k={key}")


# ------------------------------------------------------------------------------------ actions
@frappe.whitelist()
def get_whatsapp_message(name):
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Submit the quotation first - only final quotations go to customers."))
	if opted_out(doc):
		return {"blocked": _("This customer asked not to be messaged (opt-out is ticked).")}
	number = party_mobile(doc)
	if not number:
		return {"blocked": _("No mobile number for this customer. Add one to the lead/contact first.")}

	link = share_link(doc)
	s = settings()
	text = (s.whatsapp_quote_message or "").format(
		name=doc.kind_attention or doc.customer_name or "",
		customer=doc.customer_name or doc.party_name,
		pi_no=doc.name,
		amount=money(doc.rounded_total or doc.grand_total),
		valid_till=formatdate(doc.valid_till, "dd-MMM-yyyy") if doc.valid_till else "",
		link=link,
		company="Perfect Tools",
	)
	host = frappe.utils.get_host_name()
	return {
		"phone": whatsapp_digits(number),
		"text": text,
		"link": link,
		"local_only": host.startswith(("localhost", "127.")) or host.endswith(".localhost"),
	}


@frappe.whitelist()
def mark_sent(name, via="WhatsApp", sent_on=None):
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("write")
	s = settings()
	first_time = not doc.get("pt_sent_on")
	sent_at = sent_on or now_datetime()
	doc.db_set(
		{
			"pt_sent_on": sent_at,
			"pt_sent_via": via,
			"pt_next_followup_on": add_days(getdate(sent_at), cint(s.followup_after_sent_days) or 3),
			"pt_followup_count": 0 if first_time else cint(doc.get("pt_followup_count")),
		}
	)
	close_todos("Quotation", name, "[Send]")
	add_comment("Quotation", name, f"Quotation {'sent' if first_time else 're-sent'} via {via}.")
	if doc.quotation_to == "Lead" and frappe.db.has_column("Lead", "quotation_sent_on"):
		if not frappe.db.get_value("Lead", doc.party_name, "quotation_sent_on"):
			frappe.db.set_value("Lead", doc.party_name, "quotation_sent_on", getdate(sent_at), update_modified=False)
	return {"next_followup_on": doc.pt_next_followup_on}


@frappe.whitelist()
def log_response(name, response, next_followup_on=None):
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("write")
	add_comment("Quotation", name, f"<b>Customer response:</b> {frappe.utils.escape_html(response)}")
	updates = {"pt_last_response": response, "pt_last_response_on": today()}
	updates["pt_next_followup_on"] = next_followup_on or None
	doc.db_set(updates)
	close_todos("Quotation", name, "[Follow-up")
	if next_followup_on:
		make_todo(
			"Quotation",
			name,
			f"[Follow-up] {doc.customer_name or doc.party_name} on {name}: {response}",
			next_followup_on,
			doc.owner,
		)
	if doc.quotation_to == "Lead":
		lead_updates = {}
		if frappe.db.has_column("Lead", "last_response_on"):
			lead_updates["last_response_on"] = today()
		if frappe.db.has_column("Lead", "last_response"):
			lead_updates["last_response"] = response
		if lead_updates:
			frappe.db.set_value("Lead", doc.party_name, lead_updates, update_modified=False)
	return {"ok": True}


@frappe.whitelist()
def mark_won(name, won_on=None, make_customer=1):
	"""Order confirmed. Records the win, stops follow-ups and (for a lead) creates the Customer."""
	doc = frappe.get_doc("Quotation", name)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted quotation can be marked as won."))
	doc.db_set({"pt_won_on": won_on or today(), "pt_next_followup_on": None})
	close_todos("Quotation", name)
	add_comment("Quotation", name, f"Order confirmed - quotation won ({money(doc.rounded_total or doc.grand_total)}).")

	customer = None
	if doc.quotation_to == "Lead" and cint(make_customer):
		customer = frappe.db.get_value("Customer", {"lead_name": doc.party_name}, "name")
		if not customer:
			from erpnext.crm.doctype.lead.lead import _make_customer

			cust = _make_customer(doc.party_name, ignore_permissions=True)
			cust.flags.ignore_permissions = True
			cust.insert()
			customer = cust.name
		frappe.db.set_value("Lead", doc.party_name, "status", "Converted")
		close_todos("Lead", doc.party_name)
	notify(
		[doc.owner] + [u for u in frappe.get_all("Has Role", filters={"role": "Sales Manager", "parenttype": "User"}, pluck="parent")],
		f"Won: {doc.customer_name or doc.party_name} - {money(doc.rounded_total or doc.grand_total)} ({name})",
		"Quotation",
		name,
	)
	return {"customer": customer}


@frappe.whitelist(allow_guest=True)
def open_pdf(q=None, k=None):
	"""Public link sent on WhatsApp: records 'viewed', tells the owner, then serves the PDF."""
	if not q or not k:
		raise frappe.PermissionError
	valid = frappe.db.get_value(
		"Document Share Key",
		{"reference_doctype": "Quotation", "reference_docname": q, "key": k},
		["name", "expires_on"],
		as_dict=True,
	)
	if not valid or (valid.expires_on and getdate(valid.expires_on) < getdate(today())):
		frappe.throw(_("This quotation link has expired. Please ask Perfect Tools for a fresh copy."), frappe.PermissionError)

	doc = frappe.get_doc("Quotation", q)
	try:
		frappe.flags.ignore_permissions = True
		first = not doc.get("pt_viewed_on")
		doc.db_set({"pt_viewed_on": doc.get("pt_viewed_on") or now_datetime(), "pt_view_count": cint(doc.get("pt_view_count")) + 1}, update_modified=False)
		if first:
			add_comment("Quotation", q, "Customer opened the quotation link for the first time.", "Info")
			notify([doc.owner], f"{doc.customer_name or doc.party_name} opened {q}", "Quotation", q)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Perfect Tools: could not record quotation view")
	finally:
		frappe.flags.ignore_permissions = False

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = (
		f"/api/method/frappe.utils.print_format.download_pdf?doctype=Quotation&name={urlquote(q)}"
		f"&format={urlquote(PRINT_FORMAT)}&key={k}"
	)
