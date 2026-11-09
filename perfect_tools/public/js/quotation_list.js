// Perfect Tools: the quotation list says where each quote really stands.
frappe.listview_settings["Quotation"] = Object.assign(frappe.listview_settings["Quotation"] || {}, {
	add_fields: ["pt_sent_on", "pt_won_on", "pt_viewed_on", "pt_next_followup_on", "status", "docstatus", "valid_till"],
	get_indicator(doc) {
		if (doc.docstatus === 0) return [__("Draft"), "red", "docstatus,=,0"];
		if (doc.docstatus === 2) return [__("Cancelled"), "darkgrey", "docstatus,=,2"];
		if (doc.pt_won_on) return [__("Won"), "green", "pt_won_on,is,set"];
		if (doc.status === "Lost") return [__("Lost"), "darkgrey", "status,=,Lost"];
		if (doc.status === "Expired") return [__("Expired"), "grey", "status,=,Expired"];
		if (doc.status === "Ordered") return [__("Ordered"), "green", "status,=,Ordered"];
		if (!doc.pt_sent_on) return [__("Not sent"), "orange", "pt_sent_on,is,not set|docstatus,=,1"];
		if (doc.pt_next_followup_on && doc.pt_next_followup_on < frappe.datetime.get_today())
			return [__("Follow-up due"), "red", "pt_next_followup_on,<," + frappe.datetime.get_today()];
		if (doc.pt_viewed_on) return [__("Opened by customer"), "blue", "pt_viewed_on,is,set"];
		return [__("Sent"), "cyan", "pt_sent_on,is,set"];
	},
});
