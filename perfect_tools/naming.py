"""Quotation numbering in Perfect Tools' existing style: PI/164/2026-27.

- The counter restarts every financial year (April-March): it is keyed "PI/<FY>".
- Amendments keep ERPNext's standard suffix: PI/164/2026-27-1, -2, ...
  (Frappe names amended docs before this hook runs, so they never reach it.)
"""
import frappe
from frappe.model.naming import getseries
from frappe.utils import getdate, today

from erpnext.accounts.utils import get_fiscal_year

PREFIX = "PI"
DIGITS = 3  # PI/164/..., PI/001/... at the start of a year


def short_fiscal_year(date, company=None) -> str:
    """'2026-27' for the fiscal year that contains `date`."""
    _, start, end = get_fiscal_year(date=date, company=company)[:3]
    return f"{getdate(start).year}-{str(getdate(end).year)[-2:]}"


def quotation_autoname(doc, method=None):
    if doc.name:  # amended document already named by Frappe
        return
    fy = short_fiscal_year(doc.transaction_date or today(), doc.company)
    number = getseries(f"{PREFIX}/{fy}", DIGITS)
    doc.name = f"{PREFIX}/{number}/{fy}"
