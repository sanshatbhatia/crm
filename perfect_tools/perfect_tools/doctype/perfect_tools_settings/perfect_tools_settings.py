import frappe
from frappe.model.document import Document


class PerfectToolsSettings(Document):
	def validate(self):
		for field in ("rounding_unit", "quote_validity_days", "followup_after_sent_days", "repeat_followup_every_days",
					  "max_auto_followups", "backup_keep_days"):
			if self.get(field) is not None and self.get(field) < 0:
				frappe.throw(f"{self.meta.get_label(field)} cannot be negative.")
		if self.backup_copy_path:
			self.backup_copy_path = self.backup_copy_path.strip()
		for field in ("whatsapp_quote_message", "whatsapp_greeting_message"):
			text = self.get(field) or ""
			try:
				text.format(name="", customer="", pi_no="", amount="", valid_till="", link="", machine="", company="")
			except (KeyError, IndexError, ValueError) as e:
				frappe.throw(f"{self.meta.get_label(field)}: unknown placeholder {e}. Use only those listed above the box.")

	def on_update(self):
		frappe.clear_document_cache("Perfect Tools Settings", "Perfect Tools Settings")
