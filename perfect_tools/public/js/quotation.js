// Perfect Tools: send on WhatsApp, track sent / replied / won, quick special conditions.
frappe.ui.form.on("Quotation", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.amended_from) {
			frappe.db.get_single_value("Perfect Tools Settings", "round_line_prices").then((v) => {
				if (v !== undefined && v !== null) frm.set_value("pt_round_prices", v ? 1 : 0);
			});
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Add special condition"), () => pt_pick_conditions(frm));
		}
		if (frm.doc.docstatus !== 1) return;

		const g = __("Customer");
		frm.add_custom_button(__("Send on WhatsApp"), () => pt_send_whatsapp(frm), g);
		frm.add_custom_button(__("Mark as sent"), () => pt_mark_sent(frm), g);
		frm.add_custom_button(__("Customer replied"), () => pt_log_response(frm), g);
		if (!frm.doc.pt_won_on && !["Lost", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Order confirmed (Won)"), () => pt_mark_won(frm), g);
		}
		pt_headline(frm);
	},
});

function pt_headline(frm) {
	const d = frm.doc;
	let html;
	if (d.pt_won_on) {
		html = `<span class="indicator-pill green">${__("Won on {0}", [frappe.datetime.str_to_user(d.pt_won_on)])}</span>`;
	} else if (!d.pt_sent_on) {
		html = `<span class="indicator-pill orange">${__("Not sent to the customer yet")}</span>`;
	} else {
		const bits = [__("Sent {0} via {1}", [frappe.datetime.str_to_user(d.pt_sent_on), d.pt_sent_via || "?"])];
		bits.push(d.pt_viewed_on ? __("opened by customer {0}", [frappe.datetime.str_to_user(d.pt_viewed_on)]) : __("not opened yet"));
		if (d.pt_next_followup_on) bits.push(__("next follow-up {0}", [frappe.datetime.str_to_user(d.pt_next_followup_on)]));
		html = `<span class="text-muted">${bits.join(" · ")}</span>`;
	}
	frm.dashboard.set_headline_alert(html);
}

function pt_send_whatsapp(frm) {
	frappe.call({
		method: "perfect_tools.quotation.get_whatsapp_message",
		args: { name: frm.doc.name },
		callback(r) {
			const m = r.message || {};
			if (m.blocked) {
				frappe.msgprint({ title: __("Can't send"), message: m.blocked, indicator: "red" });
				return;
			}
			const open = () => {
				window.open(`https://wa.me/${m.phone}?text=${encodeURIComponent(m.text)}`, "_blank");
				frappe.confirm(__("Did you press send in WhatsApp?"), () => pt_do_mark_sent(frm, "WhatsApp"));
			};
			if (m.local_only) {
				frappe.confirm(
					__(
						"This copy runs only on this laptop, so the PDF link in the message won't open for the customer. " +
							"Download the PDF (Print → PDF) and attach it in WhatsApp yourself. Open WhatsApp now?"
					),
					open
				);
			} else {
				open();
			}
		},
	});
}

function pt_mark_sent(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Mark as sent"),
		fields: [
			{ fieldname: "via", label: __("Sent via"), fieldtype: "Select", options: "WhatsApp\nEmail\nBy hand\nCourier", default: "WhatsApp", reqd: 1 },
			{ fieldname: "sent_on", label: __("Sent on"), fieldtype: "Datetime", default: frappe.datetime.now_datetime(), reqd: 1 },
		],
		primary_action_label: __("Save"),
		primary_action(v) {
			d.hide();
			pt_do_mark_sent(frm, v.via, v.sent_on);
		},
	});
	d.show();
}

function pt_do_mark_sent(frm, via, sent_on) {
	frappe.call({
		method: "perfect_tools.quotation.mark_sent",
		args: { name: frm.doc.name, via, sent_on },
		freeze: true,
		callback(r) {
			const next = r.message && r.message.next_followup_on;
			frappe.show_alert({
				message: __("Marked as sent. First follow-up: {0}", [next ? frappe.datetime.str_to_user(next) : "-"]),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}

function pt_log_response(frm) {
	const d = new frappe.ui.Dialog({
		title: __("What did the customer say?"),
		fields: [
			{ fieldname: "response", label: __("Response"), fieldtype: "Small Text", reqd: 1 },
			{
				fieldname: "next_followup_on",
				label: __("Next follow-up on"),
				fieldtype: "Date",
				default: frappe.datetime.add_days(frappe.datetime.get_today(), 3),
			},
		],
		primary_action_label: __("Save"),
		primary_action(v) {
			frappe.call({
				method: "perfect_tools.quotation.log_response",
				args: Object.assign({ name: frm.doc.name }, v),
				freeze: true,
				callback() {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function pt_mark_won(frm) {
	const is_lead = frm.doc.quotation_to === "Lead";
	const d = new frappe.ui.Dialog({
		title: __("Order confirmed"),
		fields: [
			{ fieldname: "won_on", label: __("Confirmed on"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
			{
				fieldname: "make_customer",
				label: __("Create the customer record from this lead"),
				fieldtype: "Check",
				default: 1,
				hidden: !is_lead,
			},
		],
		primary_action_label: __("Mark as Won"),
		primary_action(v) {
			frappe.call({
				method: "perfect_tools.quotation.mark_won",
				args: { name: frm.doc.name, won_on: v.won_on, make_customer: v.make_customer ? 1 : 0 },
				freeze: true,
				callback(r) {
					d.hide();
					const c = r.message && r.message.customer;
					frappe.show_alert({ message: c ? __("Won! Customer {0} created.", [c]) : __("Won!"), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function pt_pick_conditions(frm) {
	frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Perfect Tools Settings", name: "Perfect Tools Settings" },
		callback(r) {
			const presets = ((r.message && r.message.condition_presets) || []).map((p) => p.condition);
			if (!presets.length) {
				frappe.msgprint(__("No presets yet - add them in Perfect Tools Settings."));
				return;
			}
			const current = (frm.doc.special_conditions || "").split("\n").map((s) => s.trim());
			const d = new frappe.ui.Dialog({
				title: __("Add special conditions"),
				fields: [
					{
						fieldname: "picked",
						fieldtype: "MultiCheck",
						columns: 1,
						options: presets.map((p) => ({ label: p, value: p, checked: current.includes(p) })),
					},
				],
				primary_action_label: __("Add"),
				primary_action(v) {
					const lines = (frm.doc.special_conditions || "").split("\n").filter((s) => s.trim());
					(v.picked || []).forEach((p) => {
						if (!lines.includes(p)) lines.push(p);
					});
					frm.set_value("special_conditions", lines.join("\n"));
					d.hide();
				},
			});
			d.show();
		},
	});
}
