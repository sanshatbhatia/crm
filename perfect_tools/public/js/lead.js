// Perfect Tools: one-click Call / WhatsApp / Log call on every lead.
frappe.ui.form.on("Lead", {
	refresh(frm) {
		if (frm.is_new()) return;
		const number = frm.doc.mobile_no || frm.doc.whatsapp_no || frm.doc.phone;
		const group = __("Contact");

		if (number) {
			frm.add_custom_button(__("Call"), () => {
				window.location.href = "tel:" + number.replace(/[^\d+]/g, "");
			}, group);
		}
		frm.add_custom_button(__("WhatsApp"), () => perfect_tools_open_whatsapp(frm), group);
		frm.add_custom_button(__("Log call / outcome"), () => perfect_tools_log_call(frm), group);

		if (frm.doc.pt_whatsapp_opt_out) {
			frm.dashboard.set_headline_alert(
				`<div class="text-danger">${__("Customer opted out of messages - do not WhatsApp.")}</div>`
			);
		} else if (frm.doc.pt_next_followup_on) {
			const overdue = frm.doc.pt_next_followup_on < frappe.datetime.get_today();
			frm.dashboard.set_headline_alert(
				`<div class="${overdue ? "text-danger" : "text-muted"}">${__("Next follow-up")}: ${frappe.datetime.str_to_user(frm.doc.pt_next_followup_on)}${overdue ? " - " + __("overdue") : ""}</div>`
			);
		}
	},
});

function perfect_tools_open_whatsapp(frm) {
	frappe.call({
		method: "perfect_tools.lead.whatsapp_greeting",
		args: { lead: frm.doc.name },
		callback(r) {
			const m = r.message || {};
			if (m.blocked) {
				frappe.msgprint({ title: __("Can't message"), message: m.blocked, indicator: "red" });
				return;
			}
			window.open(`https://wa.me/${m.phone}?text=${encodeURIComponent(m.text)}`, "_blank");
			setTimeout(() => perfect_tools_log_call(frm, "WhatsApp message sent"), 800);
		},
	});
}

function perfect_tools_log_call(frm, preset) {
	const d = new frappe.ui.Dialog({
		title: __("What happened?"),
		fields: [
			{
				fieldname: "outcome",
				label: __("Outcome"),
				fieldtype: "Select",
				reqd: 1,
				default: preset || "Spoke to customer",
				options: [
					"Spoke to customer",
					"No answer",
					"Busy - call back",
					"Switched off / not reachable",
					"WhatsApp message sent",
					"Customer replied",
					"Interested - send quote",
					"Meeting fixed",
					"Not interested",
					"Wrong number",
				].join("\n"),
			},
			{ fieldname: "notes", label: __("Notes"), fieldtype: "Small Text" },
			{
				fieldname: "next_followup_on",
				label: __("Next follow-up on"),
				fieldtype: "Date",
				default: frappe.datetime.add_days(frappe.datetime.get_today(), 2),
				description: __("Leave empty if no further follow-up is needed."),
			},
			{
				fieldname: "new_status",
				label: __("Change lead status to"),
				fieldtype: "Select",
				options: ["", "Open", "Replied", "Interested", "Opportunity", "Do Not Contact"].join("\n"),
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			if (values.outcome === "Wrong number") {
				values.new_status = values.new_status || "Do Not Contact";
			}
			frappe.call({
				method: "perfect_tools.lead.log_call",
				args: Object.assign({ lead: frm.doc.name }, values),
				freeze: true,
				callback() {
					d.hide();
					frappe.show_alert({ message: __("Saved to the lead's history"), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.fields_dict.outcome.$input.on("change", () => {
		const v = d.get_value("outcome");
		if (v === "Not interested") {
			// Not now isn't never: check back in 2 months unless cleared.
			d.set_value("next_followup_on", frappe.datetime.add_months(frappe.datetime.get_today(), 2));
		}
		if (v === "Wrong number") {
			d.set_value("next_followup_on", "");
			d.set_value("new_status", "Do Not Contact");
		}
		if (v === "Interested - send quote") d.set_value("new_status", "Interested");
		if (v === "No answer" || v === "Busy - call back" || v === "Switched off / not reachable") {
			d.set_value("next_followup_on", frappe.datetime.add_days(frappe.datetime.get_today(), 1));
		}
	});
	d.show();
}
