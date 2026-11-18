# Bring your own storage

Any HTTPS endpoint that speaks the small JSON contract below can replace the Google backend. Set
`"storage": {"type": "google", "endpoint": "<your URL>", "token": "<your token>"}`. The type name
is historical: the client only cares about the contract.

## The contract

`POST <endpoint>` with `Content-Type: application/json`. Always answer HTTP 200 with JSON.

```jsonc
// request
{
  "token": "shared secret",
  "action": "log",                       // ping | log | check | list | answer
  "fy": "Tax26-27",                      // the client works out the tax year
  "receipt": {
    "date": "2026-11-14", "supplier": "...", "tax_id": "...", "what": "...", "purpose": "...",
    "line_items": [{"qty": 1, "description": "...", "amount": 179.0}],
    "category": "...", "subtotal": 162.73, "tax": 16.27, "total": 179.0, "currency": "AUD",
    "payment_method": "...", "receipt_number": "..."
  },
  "image_base64": "...", "mime": "image/jpeg", "filename": "IMG_2041.jpg",
  "force": false                          // true = log even if it looks like a duplicate
}
```

| action | must return |
|---|---|
| `ping` | `{"ok": true}` |
| `log` | `{"ok": true, "receipt_id", "financial_year", "file_link", "sheet_link", "warnings": []}`, or `{"ok": false, "reason": "possible duplicate", "duplicates": [{"id", "why"}]}` |
| `check` | `{"ok": true, "fy", "duplicates": [...]}` and writes nothing |
| `list` (`fy`) | `{"ok": true, "fy", "rows": [{"id", "date", "supplier", "total", "status"}]}` |
| `answer` (`receipt_id`, `work_use_pct`, `claimable`, `notes`) | `{"ok": true}` |
| any failure | `{"ok": false, "error": "human-readable reason"}` |

Spreadsheet columns, in order: see `COLUMNS` in
[`receipt_tax.py`](../skill/receipt-tax/scripts/receipt_tax.py). Keep the same headers so the
docs and the ChatGPT instructions still match.

## Ideas, by platform

| Platform | Easiest route | Notes |
|---|---|---|
| **OneDrive + Excel 365** | Power Automate flow *"When an HTTP request is received"* → *Create file* (photo to OneDrive) → *Add a row into a table* (Excel). Compare the token in a *Condition* | The HTTP trigger needs a Premium licence. Personal Microsoft accounts can't use it |
| **Notion** | Cloudflare Worker or Vercel function → Notion API: upload the image, create a database page | In the Claude app you can skip the backend and use Claude's Notion connector to create the page, then run `receipt_tax.py message` for the draft |
| **Airtable** | a Worker → Airtable REST (`/v0/<base>/<table>`), with the image as an attachment URL | An Airtable token goes in the Worker, never in the skill |
| **Dropbox / S3 / R2** | a Worker: put the image in the bucket, append to a CSV or database | Use the bucket's own lifecycle settings for 5-year retention |
| **Synced folder** | no backend: [local storage](storage-local.md) with `dir` inside the sync folder | Logging only works from your computer |
| **Self-hosted** | any small web server: Flask, FastAPI, Express | Put it behind HTTPS. The Claude app needs the domain allowed |

Whatever you build, the AI client must be allowed to reach your domain. In the Claude app,
add it to the network allow-list ([clients.md](clients.md#claude-app)).
