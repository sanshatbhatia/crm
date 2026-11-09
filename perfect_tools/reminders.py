"""The daily 8 am sweep: nothing falls through the cracks.

Each check is independent and idempotent (it never creates a second open task for the same thing),
so a failed or repeated run is harmless. Failures land in Error Log and the System Managers get a
bell notification; 'Run reminders now' on Perfect Tools Settings re-runs everything by hand.
"""
import frappe
from frappe.utils import add_days, cint, date_diff, getdate, today

from perfect_tools.utils import close_todos, make_todo, money, notify, open_todos, settings

OPEN_QUOTE = ("Open", "Replied", "Partially Ordered")
LEAD_CLOSED = ("Converted", "Do Not Contact", "Lost Quotation")


def run_daily():
	results, errors = {}, []
	for job in (first_calls, unsent_quotes, quote_followups, expiring_quotes, inactive_leads, morning_digest):
		try:
			results[job.__name__] = job()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			errors.append(job.__name__)
			frappe.log_error(title=f"Perfect Tools reminder failed: {job.__name__}")
	if errors:
		managers = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
		notify(managers, f"Reminder jobs failed: {', '.join(errors)} - see Error Log, then 'Run reminders now'.")
		frappe.db.commit()
	frappe.db.set_single_value("Perfect Tools Settings", "last_reminder_run", frappe.utils.now_datetime())
	frappe.db.set_single_value("Perfect Tools Settings", "last_reminder_result", frappe.as_json({"created": results, "failed": errors}))
	frappe.db.commit()
	return {"created": results, "failed": errors}


@frappe.whitelist()
def run_now():
	frappe.only_for(("System Manager", "Sales Manager"))
	return run_daily()


# ------------------------------------------------------------------------------------ checks
def first_calls():
	"""Every live lead must have a next step. Lost-in-the-sheet leads get a call task."""
	s, made = settings(), 0
	for lead in frappe.get_all(
		"Lead",
		filters={"status": ["not in", LEAD_CLOSED]},
		fields=["name", "lead_name", "lead_owner", "status", "machine_interest"],
	):
		if open_todos("Lead", lead.name):
			continue
		if lead.status in ("Lead", "Open"):
			desc = f"[First call] Call {lead.lead_name} about {lead.machine_interest or 'their enquiry'}"
		else:
			continue  # quoted/replied leads are handled through their quotation
		make_todo("Lead", lead.name, desc, add_days(today(), cint(s.first_call_within_days)), lead.lead_owner, "High")
		made += 1
	return made


def unsent_quotes():
	made = 0
	for q in frappe.get_all(
		"Quotation",
		filters={"docstatus": 1, "status": ["in", OPEN_QUOTE], "pt_sent_on": ["is", "not set"], "pt_won_on": ["is", "not set"]},
		fields=["name", "owner", "customer_name", "party_name", "rounded_total", "grand_total"],
	):
		if open_todos("Quotation", q.name, "[Send]"):
			continue
		make_todo(
			"Quotation",
			q.name,
			f"[Send] {q.name} for {q.customer_name or q.party_name} ({money(q.rounded_total or q.grand_total)}) is ready but not marked as sent",
			today(),
			q.owner,
			"High",
		)
		made += 1
	return made


def quote_followups():
	"""Sent, no answer: follow up every N days, at most M times, then ask for a decision."""
	s, made = settings(), 0
	every = cint(s.repeat_followup_every_days) or 4
	limit = cint(s.max_auto_followups) or 3
	for q in frappe.get_all(
		"Quotation",
		filters={
			"docstatus": 1,
			"status": ["in", OPEN_QUOTE],
			"pt_sent_on": ["is", "set"],
			"pt_won_on": ["is", "not set"],
			"pt_next_followup_on": ["<=", today()],
		},
		fields=["name", "owner", "customer_name", "party_name", "rounded_total", "grand_total", "pt_followup_count", "pt_sent_on", "pt_viewed_on"],
	):
		if open_todos("Quotation", q.name, "[Follow-up"):
			continue
		n = cint(q.pt_followup_count) + 1
		who = q.customer_name or q.party_name
		days = date_diff(today(), getdate(q.pt_sent_on))
		seen = " (opened the PDF)" if q.pt_viewed_on else ""
		if n > limit:
			desc = f"[Follow-up: decide] {who} has not replied on {q.name} in {days} days after {limit} follow-ups{seen}. Call personally, or mark as Lost."
			nxt = None
			prio = "High"
		else:
			desc = f"[Follow-up {n}] Call {who} about {q.name} ({money(q.rounded_total or q.grand_total)}), sent {days} days ago{seen}"
			nxt = add_days(today(), every)
			prio = "Medium"
		make_todo("Quotation", q.name, desc, today(), q.owner, prio)
		frappe.db.set_value("Quotation", q.name, {"pt_followup_count": n, "pt_next_followup_on": nxt}, update_modified=False)
		made += 1
	return made


def expiring_quotes():
	s, made = settings(), 0
	horizon = add_days(today(), cint(s.expiry_alert_days) or 2)
	for q in frappe.get_all(
		"Quotation",
		filters={"docstatus": 1, "status": ["in", OPEN_QUOTE], "pt_won_on": ["is", "not set"], "valid_till": ["between", [today(), horizon]]},
		fields=["name", "owner", "customer_name", "party_name", "valid_till"],
	):
		if open_todos("Quotation", q.name, "[Expiring]"):
			continue
		make_todo(
			"Quotation",
			q.name,
			f"[Expiring] {q.name} for {q.customer_name or q.party_name} expires on {frappe.utils.formatdate(q.valid_till)} - call for a decision or extend it",
			today(),
			q.owner,
			"High",
		)
		made += 1
	return made


def inactive_leads():
	s, made = settings(), 0
	days = cint(s.inactive_lead_days) or 14
	cutoff = add_days(today(), -days)
	for lead in frappe.get_all(
		"Lead",
		filters={"status": ["not in", LEAD_CLOSED], "modified": ["<", cutoff]},
		fields=["name", "lead_name", "lead_owner", "pt_last_contacted_on", "modified"],
	):
		last = getdate(lead.pt_last_contacted_on or lead.modified)
		if last > getdate(cutoff) or open_todos("Lead", lead.name):
			continue
		make_todo(
			"Lead",
			lead.name,
			f"[Inactive] No contact with {lead.lead_name} for {date_diff(today(), last)} days - re-engage or close the lead",
			today(),
			lead.lead_owner,
		)
		made += 1
	return made


def morning_digest():
	"""One bell notification per person: what's on today."""
	rows = frappe.db.sql(
		"""select allocated_to, sum(date = %(t)s) as today, sum(date < %(t)s) as overdue
		from `tabToDo` where status = 'Open' and allocated_to is not null group by allocated_to""",
		{"t": today()},
		as_dict=True,
	)
	for r in rows:
		if not (r.today or r.overdue):
			continue
		bits = []
		if r.today:
			bits.append(f"{int(r.today)} follow-up(s) due today")
		if r.overdue:
			bits.append(f"{int(r.overdue)} overdue")
		notify([r.allocated_to], "Good morning: " + ", ".join(bits) + ". Open 'My follow-ups' on the Perfect Tools page.")
	return len(rows)
