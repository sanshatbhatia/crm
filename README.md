# Perfect Tools CRM (`perfect_tools`)

CRM and quotation system for **Perfect Tools**, Nangloi, Delhi — authorised GORSAN woodworking-machine dealer.
A [Frappe](https://frappe.io) app on top of **ERPNext v16** + **India Compliance**. Nothing in ERPNext's core is
modified; everything lives in this app.

## What it adds

**Quotations (Proforma Invoice)**
- PI numbering in the existing style: `PI/164/2026-27`, restarting every April; revisions become `…-1`, `…-2`.
- "Perfect Tools PI" print format matching the Excel PIs (K-63 N letterhead, GORSAN logo, stamp & signature).
- Discounted line prices rounded to the nearest ₹1,000 (Excel `ROUND(x,-3)`), switchable per quote.
- Special discount always applied **before GST**; validity 15 days by default; advance received → balance payable.
- Warning (never a block) when a price falls below a set % of list price.
- Customer menu: **Send on WhatsApp** (public PDF link with "opened" tracking), **Mark as sent**,
  **Customer replied**, **Order confirmed (Won)** — the last one turns the lead into a Customer.
- One-click special-condition presets; T&C templates for 12 / 18 / 24-month warranty.

**Leads**
- Company name, GSTIN (validated, fills state), company address → real billing address (decides CGST+SGST vs IGST).
- Indian mobile numbers normalised to `+91-XXXXXXXXXX`; duplicate numbers blocked with a link to the existing lead.
- Lead Source, WhatsApp opt-out, **Log call / outcome** dialog, first-call task on every new lead.
- Unused standard fields hidden (job title, gender, lead/request type, phone ext., fax, market segment).

**Never miss a follow-up** — daily 08:00 sweep (Asia/Kolkata)
- first calls, quotes not yet sent, follow-ups every N days up to M times, quotes about to expire,
  leads with no contact for N days, and a morning summary in the bell icon.
- Idempotent and logged; failures go to Error Log + a notification; "Run reminders now" re-runs it.

**Seeing the business**
- "Perfect Tools" workspace: 8 number cards, 5 charts, latest leads / open quotations / follow-ups lists.
- Reports: *Quotation Follow-up Register*, *Lead Source Performance*.

**Operations**
- Daily 01:30 backup, optional copy to a second folder.
- **Perfect Tools Settings** holds every rule (validity, rounding, timings, WhatsApp texts, presets, backups).
- All UI configuration (custom fields, property setters, print format, letter head, T&C, dashboard,
  workspace, lead sources, lost reasons) ships as **fixtures**, so a fresh site gets the same setup on `bench migrate`.

## Install

```bash
bench get-app https://github.com/sanshatbhatia/crm --branch main
bench --site <site> install-app perfect_tools
bench --site <site> migrate
```

Requires `erpnext` (version-16) and `india_compliance` (version-16). Python ≥ 3.14, Node ≥ 24.

Go-live checklist: set the PI counter (`tabSeries` key `PI/<FY>`, e.g. `PI/2026-27`) to the last real PI number;
leave *Backups → Also copy to folder* blank on Frappe Cloud; upload the **company stamp** and **authorised signature**
in *Perfect Tools Settings → Quotations* (kept as private files and inlined into each PDF — they are deliberately
not in this repository).

## Tests

End-to-end scenarios against a real site, rolled back afterwards (58 checks):

```bash
bench --site <site> execute perfect_tools.tests.scenarios.run
```

## Layout

| Path | What |
|---|---|
| `perfect_tools/hooks.py` | doc events, scheduler, fixtures |
| `perfect_tools/quotation.py` | quote rules, WhatsApp / sent / replied / won, public PDF link |
| `perfect_tools/lead.py` | phone + GSTIN cleanup, duplicate block, address sync, log call |
| `perfect_tools/reminders.py` | daily follow-up sweep |
| `perfect_tools/backup.py` | daily backup |
| `perfect_tools/setup.py` | idempotent setup run after every migrate |
| `perfect_tools/perfect_tools/` | Settings doctype, reports |
| `perfect_tools/fixtures/` | exported UI configuration |
| `perfect_tools/public/` | form scripts, letterhead / stamp / signature images |
