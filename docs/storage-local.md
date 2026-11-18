# Local Excel / CSV storage

Use this when the assistant runs **on your own computer** (Claude Code, Codex). It doesn't work
in the Claude app or ChatGPT, because their sandboxes are wiped after each chat.

```json
"storage": { "type": "local", "dir": "~/Receipts", "format": "xlsx", "parent_folder": "Taxes" }
```

```
~/Receipts/
└── Taxes/
    └── Tax26-27/
        ├── Tax26-27 receipts.xlsx      ← Receipts sheet + Summary sheet (live formulas)
        └── 2026-11-14_Northside-Tech-Supplies_179.00_Tax26-27-0001.jpg
```

| `format` | Needs | Notes |
|---|---|---|
| `xlsx` | `pip install openpyxl` | Real Excel file. Falls back to CSV with a warning if openpyxl is missing |
| `csv` | nothing | Opens in Excel, Numbers and Sheets. No Summary sheet |

**Cloud backup without a backend.** Point `dir` at a folder your sync client already watches.
For example `~/OneDrive/Receipts`, `~/Dropbox/Receipts`, `G:/My Drive/Receipts` (Google Drive
for desktop) or `~/Library/Mobile Documents/com~apple~CloudDocs/Receipts` (iCloud). The files
sync like any other, and you can open the spreadsheet on your phone. You just can't *log* from
your phone.

**Editing by hand:** fine, but close the file before the next log. The script rewrites the
whole workbook on each log or answer, so formatting you add by hand isn't kept. Use the Google
backend if you want to decorate the sheet.
