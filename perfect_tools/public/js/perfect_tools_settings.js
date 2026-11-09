frappe.ui.form.on("Perfect Tools Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Run reminders now"), () => {
			frappe.call({
				method: "perfect_tools.reminders.run_now",
				freeze: true,
				freeze_message: __("Checking leads and quotations..."),
				callback(r) {
					const res = (r.message && r.message.created) || {};
					const lines = Object.keys(res).map((k) => `${k.replace(/_/g, " ")}: ${res[k]}`);
					frappe.msgprint({ title: __("Reminders done"), message: lines.join("<br>"), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
		frm.add_custom_button(__("Back up now"), () => {
			frappe.call({
				method: "perfect_tools.backup.backup_now",
				freeze: true,
				freeze_message: __("Backing up..."),
				callback() {
					frappe.show_alert({ message: __("Backup done"), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
	},
});
