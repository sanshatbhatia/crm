"""Lead rules: clean phone numbers, block duplicate enquiries, never leave a new lead without a first call."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from perfect_tools.phone import find_customers_with_numbers, find_leads_with_numbers, normalize_in
from perfect_tools.utils import add_comment, close_todos, make_todo, open_todos, settings

PHONE_FIELDS = ("mobile_no", "whatsapp_no", "phone")
CLOSED_STATUSES = ("Converted", "Do Not Contact", "Lost Quotation")


def before_validate(doc, method=None):
	for field in PHONE_FIELDS:
		if doc.get(field):
			doc.set(field, normalize_in(doc.get(field)))
	if doc.get("mobile_no") and not doc.get("whatsapp_no"):
		doc.whatsapp_no = doc.mobile_no

	# One visible "Lead Source" field; ERPNext's own utm_source (used by its reports and copied
	# onto quotations) is kept in step with it.
	if doc.get("pt_lead_source"):
		doc.utm_source = doc.pt_lead_source
	elif doc.get("utm_source"):
		doc.pt_lead_source = doc.utm_source

	if doc.meta.has_field("enquiry_date") and not doc.get("enquiry_date"):
		doc.enquiry_date = today()

	if doc.get("gstin"):
		doc.gstin = doc.gstin.strip().upper().replace(" ", "")
		try:
			from india_compliance.gst_india.utils import validate_gstin
		except ImportError:
			validate_gstin = None
		if validate_gstin:
			doc.gstin = validate_gstin(doc.gstin, _("Company GSTIN")) or doc.gstin
		# First two digits of a GSTIN are the state code - fill State if it's empty.
		if not doc.get("state"):
			state = _state_from_gstin(doc.gstin)
			if state:
				doc.state = state


def _state_from_gstin(gstin):
	try:
		from india_compliance.gst_india.constants import STATE_NUMBERS

		by_code = {v: k for k, v in STATE_NUMBERS.items()}
		return by_code.get(gstin[:2])
	except Exception:
		return None


def sync_address(doc, method=None):
	"""Company Address + City + State (+ GSTIN) on the lead = its billing address. Quotations take the
	address from here, and the address decides CGST+SGST (Delhi) vs IGST (other states)."""
	if not (doc.get("pt_company_address") or doc.get("gstin")):
		return
	if not (doc.get("city") and doc.get("state")):
		frappe.msgprint(
			_("Add City and State too - the billing address for quotations is made from them."),
			indicator="orange", alert=True,
		)
		return
	values = {
		"address_line1": (doc.get("pt_company_address") or doc.city).strip()[:240],
		"city": doc.city,
		"state": doc.state,
		"country": doc.get("country") or "India",
		"gstin": doc.get("gstin") or "",
		"gst_category": "Registered Regular" if doc.get("gstin") else "Unregistered",
	}
	name = frappe.db.sql(
		"""select a.name from `tabAddress` a join `tabDynamic Link` dl on dl.parent = a.name
		and dl.parenttype = 'Address' and dl.link_doctype = 'Lead' and dl.link_name = %s
		order by a.is_primary_address desc, a.creation limit 1""",
		doc.name,
	)
	try:
		if name:
			addr = frappe.get_doc("Address", name[0][0])
			if all((addr.get(k) or "") == (v or "") for k, v in values.items()):
				return
			addr.update(values)
			addr.flags.ignore_permissions = True
			addr.save()
		else:
			addr = frappe.get_doc({
				"doctype": "Address", "address_title": doc.company_name or doc.lead_name, "address_type": "Billing",
				"is_primary_address": 1, "links": [{"link_doctype": "Lead", "link_name": doc.name}], **values,
			})
			addr.flags.ignore_permissions = True
			addr.insert()
	except Exception as e:
		frappe.log_error(title=f"Perfect Tools: address sync failed for {doc.name}")
		frappe.msgprint(_("The lead is saved, but its billing address could not be updated: {0}").format(e),
						indicator="orange", title=_("Address not updated"))


def validate(doc, method=None):
	if doc.flags.ignore_duplicate_check or doc.get("pt_allow_duplicate"):
		return
	numbers = [doc.get(f) for f in PHONE_FIELDS if doc.get(f)]
	if not numbers:
		return
	if not (doc.is_new() or any(doc.has_value_changed(f) for f in PHONE_FIELDS)):
		return

	dupes = find_leads_with_numbers(numbers, exclude=doc.name)
	if dupes:
		d = dupes[0]
		who = " - ".join(x for x in (d.lead_name, d.company_name) if x)
		frappe.throw(
			_(
				"This number is already saved on lead {0} ({1}, status {2}).<br><br>"
				"Open that lead and add this enquiry to it, so the whole history stays in one place. "
				"If this really is a different person, tick <b>Different person, same number</b> and save again."
			).format(f'<a href="/app/lead/{d.name}">{d.name}</a>', frappe.bold(who), d.status),
			title=_("Duplicate enquiry"),
		)

	customers = find_customers_with_numbers(numbers)
	if customers:
		frappe.msgprint(
			_("This number belongs to existing customer {0}. Treat this as a repeat enquiry.").format(
				", ".join(f'<a href="/app/customer/{c.customer}">{c.customer}</a>' for c in customers)
			),
			title=_("Existing customer"),
			indicator="blue",
		)


def after_insert(doc, method=None):
	if doc.status in CLOSED_STATUSES or open_todos("Lead", doc.name):
		return
	s = settings()
	due = add_days(today(), cint(s.first_call_within_days))
	what = doc.get("machine_interest") or _("their enquiry")
	make_todo(
		"Lead",
		doc.name,
		f"[First call] Call {doc.lead_name} about {what}",
		due,
		doc.lead_owner or frappe.session.user,
		priority="High",
	)
	frappe.db.set_value("Lead", doc.name, "pt_next_followup_on", due, update_modified=False)


def todo_on_update(doc, method=None):
	"""When a follow-up on a lead is ticked off, the lead was contacted today."""
	if doc.reference_type != "Lead" or not doc.reference_name:
		return
	if not frappe.db.exists("Lead", doc.reference_name):
		return
	if doc.has_value_changed("status") and doc.status == "Closed":
		frappe.db.set_value("Lead", doc.reference_name, "pt_last_contacted_on", today(), update_modified=False)
	if doc.has_value_changed("status") or doc.has_value_changed("date"):
		from perfect_tools.utils import refresh_lead_next_followup

		refresh_lead_next_followup(doc.reference_name)


# ---------------------------------------------------------------------------------------------
@frappe.whitelist()
def log_call(lead, outcome, notes=None, next_followup_on=None, new_status=None):
	"""One click after every call: what happened, what's next."""
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	text = f"<b>{frappe.utils.escape_html(outcome)}</b>"
	if notes:
		text += f"<br>{frappe.utils.escape_html(notes)}"
	if next_followup_on:
		text += f"<br>Next follow-up: {frappe.utils.formatdate(next_followup_on)}"
	add_comment("Lead", lead, text)

	close_todos("Lead", lead)
	updates = {"pt_last_contacted_on": today(), "pt_next_followup_on": next_followup_on or None}
	if doc.meta.has_field("first_reached_out_on") and not doc.get("first_reached_out_on"):
		updates["first_reached_out_on"] = today()
	if outcome in ("Spoke to customer", "Meeting fixed", "Interested - send quote") and doc.meta.has_field(
		"first_connected_on"
	) and not doc.get("first_connected_on"):
		updates["first_connected_on"] = today()
	if outcome == "Customer replied" and doc.meta.has_field("last_response_on"):
		updates["last_response_on"] = today()
		if notes and doc.meta.has_field("last_response"):
			updates["last_response"] = notes
	frappe.db.set_value("Lead", lead, updates)

	if next_followup_on:
		make_todo("Lead", lead, f"[Follow-up] {doc.lead_name}: {notes or outcome}", next_followup_on, doc.lead_owner)

	if new_status and new_status != doc.status:
		doc.reload()
		doc.status = new_status
		doc.flags.ignore_duplicate_check = True
		doc.save()
	return {"ok": True}


@frappe.whitelist()
def whatsapp_greeting(lead):
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("read")
	from perfect_tools.phone import whatsapp_digits

	if doc.get("pt_whatsapp_opt_out") or doc.status == "Do Not Contact":
		return {"blocked": _("{0} asked not to be messaged.").format(doc.lead_name)}
	number = doc.whatsapp_no or doc.mobile_no
	if not number:
		return {"blocked": _("No mobile number on this lead.")}
	s = settings()
	text = (s.whatsapp_greeting_message or "").format(
		name=doc.lead_name or "",
		machine=doc.get("machine_interest") or "machines",
		company="Perfect Tools",
	)
	return {"phone": whatsapp_digits(number), "text": text}
