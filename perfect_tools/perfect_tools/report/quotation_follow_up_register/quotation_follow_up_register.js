frappe.query_reports["Quotation Follow-up Register"] = {
	filters: [
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "User" },
		{ fieldname: "from_date", label: __("Quoted From"), fieldtype: "Date" },
		{ fieldname: "include_closed", label: __("Include won / lost / expired"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "stage" && data) {
			const colour = {
				"Follow-up overdue": "red",
				"Not sent yet": "orange",
				"Customer replied": "blue",
				"Waiting for reply": "grey",
				Won: "green",
				Lost: "darkgrey",
				Expired: "darkgrey",
			}[data.stage];
			if (colour) value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "days_left" && data && data.days_left !== null && data.days_left <= 2) {
			value = `<b style="color: var(--red-600)">${value}</b>`;
		}
		return value;
	},
};
