frappe.query_reports["Lead Source Performance"] = {
	filters: [
		{ fieldname: "from_date", label: __("Leads From"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -6) },
		{ fieldname: "to_date", label: __("Leads To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
