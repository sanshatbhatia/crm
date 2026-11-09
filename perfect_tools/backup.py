"""Daily backup (database + uploaded files), kept for N days, optionally copied to a second folder.

On the local copy the second folder is the Windows side (C:\\Users\\user\\DadCRM\\backups), so a
broken Linux install never takes the data with it. On Frappe Cloud leave the copy path blank -
Cloud runs its own backups.
"""
import os
import shutil

import frappe
from frappe.utils import cint, now_datetime

from perfect_tools.utils import notify, settings


def run_daily_backup():
	s = settings()
	if not cint(s.backup_enabled):
		return None
	keep = cint(s.backup_keep_days) or 14
	try:
		from frappe.utils.backups import new_backup

		odb = new_backup(ignore_files=False, force=True)
		paths = [odb.backup_path_db, odb.backup_path_files, odb.backup_path_private_files, getattr(odb, "backup_path_conf", None)]
		# Frappe returns paths relative to the bench's sites/ folder (the process working directory).
		paths = [_resolve(p) for p in paths if p]
		missing = [p for p in paths if not os.path.exists(p)]
		if missing:
			raise FileNotFoundError(f"Backup files not found: {missing}")
		copied = _copy_out(paths, (s.backup_copy_path or "").strip(), keep)
		_prune_local(keep)
		frappe.db.set_single_value("Perfect Tools Settings", "last_backup_on", now_datetime())
		frappe.db.set_single_value("Perfect Tools Settings", "last_backup_result", f"OK - {len(paths)} file(s), {copied} copied")
		frappe.db.commit()
		return paths
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Perfect Tools: daily backup failed")
		managers = frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
		notify(managers, "Daily backup FAILED - see Error Log, then press 'Back up now' on Perfect Tools Settings.")
		frappe.db.set_single_value("Perfect Tools Settings", "last_backup_result", "FAILED - see Error Log")
		frappe.db.commit()
		return None


@frappe.whitelist()
def backup_now():
	frappe.only_for("System Manager")
	paths = run_daily_backup()
	if not paths:
		frappe.throw("Backup failed or is switched off - see Error Log.")
	return paths


def _resolve(p):
	if os.path.isabs(p):
		return p
	for base in (os.getcwd(), frappe.utils.get_bench_path() + "/sites"):
		candidate = os.path.normpath(os.path.join(base, p))
		if os.path.exists(candidate):
			return candidate
	return os.path.abspath(p)


def _copy_out(paths, target, keep):
	if not target:
		return 0
	if not os.path.isdir(target):
		os.makedirs(target, exist_ok=True)
	stamp = now_datetime().strftime("%Y-%m-%d_%H%M")
	day_dir = os.path.join(target, stamp)
	os.makedirs(day_dir, exist_ok=True)
	n = 0
	for p in paths:
		if p and os.path.exists(p):
			shutil.copy2(p, day_dir)
			n += 1
	dirs = sorted(d for d in os.listdir(target) if os.path.isdir(os.path.join(target, d)) and d[:4].isdigit())
	for old in dirs[:-keep]:
		shutil.rmtree(os.path.join(target, old), ignore_errors=True)
	return n


def _prune_local(keep):
	folder = frappe.get_site_path("private", "backups")
	if not os.path.isdir(folder):
		return
	files = sorted((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime)
	# Each backup is ~4 files; keep `keep` days' worth.
	for f in files[: max(0, len(files) - keep * 4)]:
		try:
			os.remove(f)
		except OSError:
			pass
