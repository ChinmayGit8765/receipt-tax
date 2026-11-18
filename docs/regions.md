# Tax years, currencies and tax names

The tax-year folder (`Tax26-27`), the currency and the words in the message ("GST", "ABN")
come from settings. Set them in **two places**: `region` in `config.json` (client) and
`FY_START` / `FY_LABEL` / `CURRENCY` in `Config.gs` (Google backend). The client sends the label
it works out, so the two only need to agree for `list` with no year given.

| Country | `fy_start` | `fy_label` (example) | currency | `tax_name` | `tax_id_name` | `date_format` |
|---|---|---|---|---|---|---|
| 🇦🇺 Australia | `07-01` | `Tax{yy}-{yy2}` → Tax26-27 | AUD `$` | GST | ABN | `%d/%m/%Y` |
| 🇳🇿 New Zealand | `04-01` | `Tax{yy}-{yy2}` → Tax26-27 | NZD `$` | GST | GST no. | `%d/%m/%Y` |
| 🇬🇧 United Kingdom | `04-06` | `{YYYY}-{yy2}` → 2026-27 | GBP `£` | VAT | VAT no. | `%d/%m/%Y` |
| 🇮🇳 India | `04-01` | `FY{YYYY}-{yy2}` → FY2026-27 | INR `₹` | GST | GSTIN | `%d/%m/%Y` |
| 🇺🇸 United States | `01-01` | `Tax{YYYY}` → Tax2026 | USD `$` | Sales tax | EIN | `%m/%d/%Y` |
| 🇨🇦 Canada | `01-01` | `Tax{YYYY}` → Tax2026 | CAD `$` | GST/HST | BN | `%Y-%m-%d` |

Tokens: `{YYYY}` start year, `{yy}` its last two digits, `{YYYY2}` end year, `{yy2}` its last
two digits. When `fy_start` is `01-01`, the start and end years are the same.

The tax year a receipt belongs to is worked out from **the date on the receipt**, not today's
date. A June receipt logged in July goes into the earlier year, and the reply says so.

UK example (`config.json`):

```json
"region": {
  "fy_start": "04-06", "fy_label": "{YYYY}-{yy2}", "currency": "GBP", "currency_symbol": "£",
  "tax_name": "VAT", "tax_id_name": "VAT no.", "date_format": "%d/%m/%Y"
}
```

Foreign-currency receipts keep their own currency in the row (`12.50 USD`). The assistant does
not convert. Your accountant will want the rate for the transaction date.

These are starting points, not tax advice: self-employed people, companies and some countries
use other year ends. Ask your accountant which year to use.
