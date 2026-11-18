---
name: receipt-tax
description: Log a receipt photo for tax — read the receipt, ask what the purchase was for, clean up the wording without adding anything, store the photo and a spreadsheet row for the right tax year (Google Drive + Sheets, or a local Excel/CSV), and draft a message to the accountant (WhatsApp, Telegram, SMS, email, Discord, Slack or copy-paste) asking how much can be claimed. Use when the user shares a receipt or invoice photo, says "log this receipt", "tax receipt", "ask my accountant about this", or reports what their accountant said about a receipt.
---

# Receipt → storage + spreadsheet + accountant draft

`scripts/receipt_tax.py` (in this skill's folder) does every exact step: tax-year folder,
duplicate check, storing the photo, the spreadsheet row, and the message drafts. Its settings are
in `config.json` next to this file. Your job is the three judgement steps: **read**,
**ask and clean**, **confirm**. Never send anything without the user's confirmation.

## 1. Read the receipt

Look at the photo. Extract this JSON. Copy values exactly as printed. If a field is not on the
receipt or you cannot read it, use `null`. Never guess.

```json
{
  "date": "YYYY-MM-DD",
  "supplier": "business name as printed",
  "tax_id": "supplier's business/tax number as printed (ABN, VAT no., GSTIN, EIN...) or null",
  "what": "short plain name, e.g. 'Logitech MX Keys keyboard'",
  "purpose": "(step 2)",
  "line_items": [{"qty": 1, "description": "...", "amount": 0.00}],
  "category": "Equipment | Software | Phone & internet | Stationery | Books & courses | Travel | Clothing (work) | Other",
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "currency": "ISO code, e.g. AUD",
  "payment_method": "e.g. Visa ••1234, cash, or null",
  "receipt_number": "or null"
}
```

`tax` is the GST/VAT/sales tax **printed on the receipt**. If none is printed, use `null`. Do not
calculate it.

Tell the user briefly if the line items don't add up to the total, or if the photo is blurry or
cut off. In that case ask for a better photo rather than guessing. For Australian tax invoices
over $82.50, mention if there's no ABN.

## 2. Ask for the purpose, then clean it up

Ask exactly one question: **"Roughly, what's this for?"** (skip it if they already said).

Clean the answer using **only** these changes: spelling, grammar, punctuation, capitalisation,
and joining fragments into sentences. Keep the first person.

Never:
- add facts, reasons, percentages or details they did not say
- add opinions ("great buy", "essential", "clearly work-related")
- add tax conclusions ("deductible", "claim 100%")
- make it more persuasive, formal or longer
- drop anything they said, including private use

Example. "for uni mostly and my tutoring gig, sometimes gaming tbh" →
"I use it mostly for university and my tutoring work, and sometimes for gaming."

## 3. Confirm once

Show the extracted fields, then the cleaned purpose under the user's original words. Ask
**"Log it?"** Apply any corrections, then go on. This is the only confirmation. If
`config.json` has a `discord` or `slack` channel, say that confirming will also post the
message there.

## 4. Store it

Write the JSON to a file, find the photo as a file, then run:

```bash
python <skill-dir>/scripts/receipt_tax.py log --json receipt.json --image <photo> [--post]
```

- Add `--post` only if a Discord/Slack channel is configured and the user confirmed in step 3.
- **Finding the photo.** In the Claude app, uploads are under `/mnt/user-data/uploads/`. Use
  `ls` and pick the newest image. If there is no file, ask the user to attach the photo again
  as a file.
- **Exit 2 = possible duplicate.** Say which receipt it matches. Re-run with `--force` only if
  the user says it is a different purchase.
- **Network error.** Show the script's message (it says which domains to allow). Run
  `receipt_tax.py message --json receipt.json` so the user still gets the draft, and say the
  receipt is **not stored yet**.
- **Several different receipts.** Do steps 1–4 for each one in turn.

## 5. Report

1. "Logged **<receipt_id>**: <supplier>, <total>, filed in <financial_year>", plus `file_link`
   and `sheet_link`. Mention `excel_download` if it is present.
2. For each entry in `drafts`:
   - `link`: show it as a markdown link ("Open WhatsApp draft", "Open email draft"...)
   - `text`: show `message_text` in a quote block to copy
   - `posted` / `error`: say what happened

   Repeat the `note`. Say link drafts are not sent until the user sends them.
3. Every warning.

Do not comment on whether anything is claimable.

## Accountant replies and lookups

- "Accountant said 60%, $107.40 for the keyboard": `receipt_tax.py list` to find the ID, then
  `receipt_tax.py answer --id <ID> --pct 60 --claimable 107.40 --notes "<their words>"`.
- "What have I logged?": `receipt_tax.py list [--fy <label>]`.
