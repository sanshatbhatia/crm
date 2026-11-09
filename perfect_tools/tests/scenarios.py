"""End-to-end checks of the Perfect Tools rules, run against the real site and ROLLED BACK.

    bench --site perfecttools.localhost execute perfect_tools.tests.scenarios.run

Nothing it creates survives: everything happens in one transaction that is rolled back at the end
(Frappe's own test runner is avoided on purpose - it would load ERPNext's test records into the
live database).
"""
import traceback

import frappe
from frappe.utils import add_days, flt, getdate, today

RESULTS = []


def check(name, cond, detail=""):
	RESULTS.append((bool(cond), name, detail))


def run():
	RESULTS.clear()
	frappe.set_user("Administrator")
	frappe.flags.in_test = True
	frappe.db.begin()
	try:
		for t in (t_phone, t_rounding_math, t_quote_rules, t_duplicate_lead, t_first_call, t_followup_cycle, t_won, t_reports,
				  t_lead_form):
			try:
				t()
			except Exception:
				RESULTS.append((False, t.__name__, traceback.format_exc(limit=3)))
	finally:
		frappe.db.rollback()
		frappe.flags.in_test = False
	ok = sum(1 for r in RESULTS if r[0])
	for passed, name, detail in RESULTS:
		print(("PASS " if passed else "FAIL ") + name + (f"  -- {detail}" if detail and not passed else ""))
	print(f"\n{ok}/{len(RESULTS)} checks passed (all changes rolled back)")
	return {"passed": ok, "total": len(RESULTS)}


# ------------------------------------------------------------------------------------ tests
def t_phone():
	from perfect_tools.phone import match_key, normalize_in, whatsapp_digits

	check("phone: 10 digits", normalize_in("9876543210") == "+91-9876543210")
	check("phone: spaces/0 prefix", normalize_in("098765 43210") == "+91-9876543210")
	check("phone: 91 prefix", normalize_in("+91 98765-43210") == "+91-9876543210")
	check("phone: malformed +74.. (missing country code, as seen on a real quote)", normalize_in("+7400000123") == "+91-7400000123")
	check("phone: landline untouched", normalize_in("011-2345678") == "011-2345678")
	check("phone: match key", match_key("+91-98765 43210") == "9876543210")
	check("phone: wa digits", whatsapp_digits("+91-9876543210") == "919876543210")


def t_rounding_math():
	from perfect_tools.utils import round_half_up

	check("round: 637,500 -> 638,000 (Alok quote)", round_half_up(637500) == 638000)
	check("round: 637,499 -> 637,000", round_half_up(637499) == 637000)
	check("round: 130,000 stays", round_half_up(130000) == 130000)


def _lead(mobile, name="PT TEST Lead", **kw):
	doc = frappe.get_doc({"doctype": "Lead", "lead_name": name, "first_name": name, "mobile_no": mobile, "status": "Lead", **kw})
	doc.insert(ignore_permissions=True)
	return doc


def _quote(party, items, discount_amount=0, quotation_to="Lead", **kw):
	q = frappe.get_doc({
		"doctype": "Quotation", "quotation_to": quotation_to, "party_name": party, "company": "Perfect Tools",
		"transaction_date": today(), "order_type": "Sales", "items": items, "discount_amount": discount_amount,
		"currency": "INR", "conversion_rate": 1, "selling_price_list": "Standard Selling", "price_list_currency": "INR",
		"plc_conversion_rate": 1, **kw,
	})
	q.run_method("set_missing_values")
	q.insert(ignore_permissions=True)
	return q


def t_quote_rules():
	lead = _lead("9000077701", "PT TEST Quote Lead", city="Delhi", state="Delhi")
	# 15% off a 7,50,000 machine = 6,37,500 -> rounds to 6,38,000 (exactly the Alok-quote case)
	q = _quote(lead.name, [{"item_code": "GE-1303-LI-PRIME", "qty": 1, "price_list_rate": 750000, "discount_percentage": 15}])
	item = q.items[0]
	check("quote: name in PI/nnn/FY form", q.name.startswith("PI/") and q.name.count("/") == 2, q.name)
	check("quote: valid till = date + 15", getdate(q.valid_till) == getdate(add_days(today(), 15)), str(q.valid_till))
	check("quote: discounted line rounded to 6,38,000", flt(item.rate) == 638000, str(item.rate))
	check("quote: discount back-solved to 1,12,000", flt(item.discount_amount) == 112000, str(item.discount_amount))
	check("quote: GST added (18%)", flt(q.total_taxes_and_charges) == flt(638000 * 0.18), str(q.total_taxes_and_charges))
	check("quote: kind attention filled", bool(q.kind_attention), q.kind_attention)

	# rounding switched off on a quote -> exact figure kept
	q2 = _quote(lead.name, [{"item_code": "GE-1303-LI-PRIME", "qty": 1, "price_list_rate": 750000, "discount_percentage": 15}], pt_round_prices=0)
	check("quote: rounding can be switched off", flt(q2.items[0].rate) == 637500, str(q2.items[0].rate))

	# list-price lines are never touched (e.g. 32,500 accessory)
	q3 = _quote(lead.name, [{"item_code": "DC-4HP", "qty": 1, "rate": 32500}])
	check("quote: list-price accessory untouched", flt(q3.items[0].rate) == 32500, str(q3.items[0].rate))

	# Santosh case: special discount must reduce the taxable value
	q4 = _quote(lead.name, [{"item_code": "GE-1611J-SMART", "qty": 1, "rate": 1760000}], discount_amount=182000)
	check("quote: discount applied on Net Total", q4.apply_discount_on == "Net Total", q4.apply_discount_on)
	check("quote: GST on discounted value (Santosh fix)", flt(q4.total_taxes_and_charges) == flt((1760000 - 182000) * 0.18), str(q4.total_taxes_and_charges))

	# advance -> balance
	q4.pt_advance_received = 100000
	q4.save(ignore_permissions=True)
	check("quote: balance = total - advance", flt(q4.pt_balance_due) == flt((q4.rounded_total or q4.grand_total) - 100000), str(q4.pt_balance_due))

	# submit -> a 'send it' task appears
	q.submit()
	todos = frappe.get_all("ToDo", filters={"reference_type": "Quotation", "reference_name": q.name, "status": "Open"}, pluck="description")
	check("quote: submit creates [Send] task", any("[Send]" in t for t in todos), str(todos))

	# print format renders (HTML, not the full PDF)
	html = frappe.get_print("Quotation", q.name, "Perfect Tools PI")
	check("print: PI renders with PI number and Valid Till", q.name in html and "Valid Till" in html)
	check("print: stamp and signature inlined from private files", html.count("data:image/jpeg;base64,") >= 2 and "/images/stamp" not in html, "")


def t_duplicate_lead():
	_lead("9000077702", "PT TEST Original")
	try:
		_lead("+91 90000 77702", "PT TEST Same Number")
		check("lead: duplicate number blocked", False, "second lead was saved")
	except frappe.ValidationError as e:
		check("lead: duplicate number blocked", "already saved" in str(e), str(e)[:120])
	twin = frappe.get_doc({"doctype": "Lead", "lead_name": "PT TEST Twin", "first_name": "PT TEST Twin", "mobile_no": "9000077702", "pt_allow_duplicate": 1})
	twin.insert(ignore_permissions=True)
	check("lead: override tick allows it", bool(twin.name))
	check("lead: phone normalised on save", twin.mobile_no == "+91-9000077702", twin.mobile_no)


def t_first_call():
	lead = _lead("9000077703", "PT TEST First Call", machine_interest="Panel Saw", pt_lead_source="IndiaMART")
	todos = frappe.get_all("ToDo", filters={"reference_type": "Lead", "reference_name": lead.name, "status": "Open"}, fields=["description", "date"])
	check("lead: first-call task created", any("[First call]" in t.description for t in todos), str(todos))
	check("lead: source mirrored to utm_source", frappe.db.get_value("Lead", lead.name, "utm_source") == "IndiaMART")
	from perfect_tools.lead import log_call

	log_call(lead.name, "No answer", "rang twice", add_days(today(), 1))
	lead.reload()
	open_now = frappe.get_all("ToDo", filters={"reference_type": "Lead", "reference_name": lead.name, "status": "Open"}, pluck="description")
	check("log call: old task closed, new follow-up created", len(open_now) == 1 and "[Follow-up]" in open_now[0], str(open_now))
	check("log call: last contacted = today", str(lead.pt_last_contacted_on) == today(), str(lead.pt_last_contacted_on))


def t_followup_cycle():
	from perfect_tools import reminders
	from perfect_tools.quotation import get_whatsapp_message, log_response, mark_sent

	lead = _lead("9000077704", "PT TEST Followup", city="Delhi", state="Delhi")
	q = _quote(lead.name, [{"item_code": "CP-50T", "qty": 1, "rate": 390000}])
	q.submit()
	msg = get_whatsapp_message(q.name)
	check("whatsapp: message has PI no and link", q.name in msg["text"] and "open_pdf" in msg["link"], msg.get("text", "")[:80])
	check("whatsapp: number in wa.me form", msg["phone"] == "919000077704", msg["phone"])

	mark_sent(q.name, "WhatsApp", f"{add_days(today(), -5)} 10:00:00")
	q.reload()
	check("sent: send task closed", not frappe.get_all("ToDo", filters={"reference_name": q.name, "status": "Open", "description": ["like", "%[Send]%"]}))
	check("sent: first follow-up 3 days after sending", getdate(q.pt_next_followup_on) == getdate(add_days(today(), -2)), str(q.pt_next_followup_on))

	made = reminders.quote_followups()
	q.reload()
	fu = frappe.get_all("ToDo", filters={"reference_name": q.name, "status": "Open", "description": ["like", "%[Follow-up 1]%"]})
	check("reminders: follow-up 1 created for overdue quote", made >= 1 and fu, f"made={made}")
	check("reminders: next follow-up rescheduled", getdate(q.pt_next_followup_on) == getdate(add_days(today(), 4)), str(q.pt_next_followup_on))
	again = reminders.quote_followups()
	check("reminders: idempotent (no duplicate task)", len(frappe.get_all("ToDo", filters={"reference_name": q.name, "status": "Open", "description": ["like", "%[Follow-up%"]})) == 1, f"second run made {again}")

	log_response(q.name, "Will decide after Diwali", add_days(today(), 7))
	q.reload()
	check("response: saved and follow-up moved", q.pt_last_response == "Will decide after Diwali" and getdate(q.pt_next_followup_on) == getdate(add_days(today(), 7)))

	# expiring soon
	frappe.db.set_value("Quotation", q.name, "valid_till", add_days(today(), 1))
	reminders.expiring_quotes()
	check("reminders: expiring quote flagged", frappe.get_all("ToDo", filters={"reference_name": q.name, "status": "Open", "description": ["like", "%[Expiring]%"]}))

	# opt-out blocks WhatsApp
	frappe.db.set_value("Lead", lead.name, "pt_whatsapp_opt_out", 1)
	check("whatsapp: opt-out respected", "blocked" in get_whatsapp_message(q.name))

	# public link: key validated, view recorded
	from perfect_tools.quotation import open_pdf
	import re
	k = re.search(r"k=([^&]+)", msg["link"]).group(1)
	frappe.db.commit = lambda *a, **kw: None  # keep everything inside the rolled-back transaction
	open_pdf(q.name, k)
	check("link: view recorded", bool(frappe.db.get_value("Quotation", q.name, "pt_viewed_on")))
	try:
		open_pdf(q.name, "wrong-key")
		check("link: bad key refused", False)
	except frappe.PermissionError:
		check("link: bad key refused", True)


def t_won():
	from perfect_tools.quotation import mark_won

	lead = _lead("9000077705", "PT TEST Winner", company_name="PT TEST Winner Furniture", city="Delhi", state="Delhi")
	q = _quote(lead.name, [{"item_code": "GP-400", "qty": 1, "rate": 303000}])
	q.submit()
	res = mark_won(q.name)
	check("won: customer created from lead", bool(res.get("customer")), str(res))
	check("won: lead converted", frappe.db.get_value("Lead", lead.name, "status") == "Converted")
	check("won: follow-ups closed", not frappe.get_all("ToDo", filters={"reference_name": q.name, "status": "Open"}))
	from perfect_tools.dashboard import conversion_rate

	check("dashboard: win rate computes", conversion_rate()["value"] > 0)


def t_reports():
	from perfect_tools.perfect_tools.report.lead_source_performance.lead_source_performance import execute as lsp
	from perfect_tools.perfect_tools.report.quotation_follow_up_register.quotation_follow_up_register import execute as qfr

	cols, data, *_ = qfr({})
	check("report: follow-up register runs", isinstance(data, list) and cols, f"{len(data)} rows")
	cols, data, *_ = lsp({})
	check("report: lead source performance runs", isinstance(data, list) and cols, f"{len(data)} rows")
	from perfect_tools.reminders import run_daily  # noqa: F401  (import check)
	check("settings: single exists", bool(frappe.get_single("Perfect Tools Settings").quote_validity_days))


def t_lead_form():
	meta = frappe.get_meta("Lead")
	hidden = {f.fieldname: f.hidden for f in meta.fields}
	HIDDEN = ("job_title", "gender", "type", "request_type", "phone_ext", "fax", "market_segment")
	check("form: job title, gender, lead/request type, phone ext, fax, market segment hidden",
		  all(hidden.get(f) for f in HIDDEN), str({f: hidden.get(f) for f in HIDDEN}))
	order = [f.fieldname for f in meta.fields]
	check("form: company name, GSTIN, address, city, state in Details right after the name",
		  order.index("company_name") < order.index("gstin") < order.index("pt_company_address") < order.index("city") < order.index("state") < order.index("contact_info_tab"),
		  str([f for f in order[:30]]))
	check("form: lead source right after status", order.index("pt_lead_source") == order.index("status") + 1)

	# address typed on the lead becomes a real billing address (drives the GST type on quotes)
	lead = _lead("9000077706", "PT TEST Address", company_name="PT TEST Hisar Works", city="Hisar", state="Haryana",
				 pt_company_address="Plot 7, Industrial Area")
	addr = frappe.db.sql("""select a.name, a.address_line1, a.state from `tabAddress` a join `tabDynamic Link` dl on dl.parent=a.name
		and dl.link_doctype='Lead' and dl.link_name=%s""", lead.name, as_dict=True)
	check("address: billing address created from the lead", addr and addr[0].address_line1 == "Plot 7, Industrial Area" and addr[0].state == "Haryana", str(addr))
	lead.reload()
	lead.pt_company_address = "Plot 9, Industrial Area"
	lead.save(ignore_permissions=True)
	check("address: editing the lead updates the same address",
		  frappe.db.get_value("Address", addr[0].name, "address_line1") == "Plot 9, Industrial Area")

	# GSTIN: cleaned, validated, fills state
	g = frappe.get_doc({"doctype": "Lead", "lead_name": "PT TEST Gst", "first_name": "PT TEST Gst", "mobile_no": "9000077707",
						"gstin": " 07behps0506p1z5 ", "city": "Delhi"})
	g.insert(ignore_permissions=True)
	check("gstin: cleaned to upper case", g.gstin == "07BEHPS0506P1Z5", g.gstin)
	check("gstin: state filled from its first two digits", g.state == "Delhi", str(g.state))
	try:
		frappe.get_doc({"doctype": "Lead", "lead_name": "PT TEST BadGst", "first_name": "PT TEST BadGst", "mobile_no": "9000077708",
						"gstin": "07ABCDE1234F1Z9"}).insert(ignore_permissions=True)
		check("gstin: wrong check digit rejected", False, "saved")
	except frappe.ValidationError:
		check("gstin: wrong check digit rejected", True)
