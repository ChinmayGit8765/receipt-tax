# Google Drive + Sheets storage

A small **Apps Script web app** runs inside your own Google account. It receives a receipt
(fields + photo), files the photo in Drive, appends a row to a Google Sheet, and answers with
links. It's free, there's no server to host, and your data never leaves your Google account.

```
My Drive/
└── Taxes/                          ← PARENT_FOLDER
    ├── Tax26-27/                   ← one folder per tax year, created automatically
    │   ├── Tax26-27 receipts       ← Google Sheet: Receipts tab + Summary tab
    │   ├── 2026-11-14_Northside-Tech-Supplies_179.00_Tax26-27-0001.jpg
    │   └── ...
    └── Tax27-28/
```

## Option A: in the browser (about 10 minutes, nothing to install)

1. Go to https://script.google.com → **New project**. Rename it `receipt-tax`.
2. Replace the contents of `Code.gs` with [`backends/google-apps-script/Code.gs`](../backends/google-apps-script/Code.gs).
3. **+ → Script** and name it `Config`. Paste [`Config.example.gs`](../backends/google-apps-script/Config.example.gs).
   Fill in:
   - `TOKEN`: a long random string. Generate one with
     `python -c "import secrets;print(secrets.token_urlsafe(32))"`.
   - `FY_START` / `FY_LABEL` / `CURRENCY` for your country ([regions.md](regions.md)).
   - `ACCOUNTANT_EMAIL` (optional): they get view access to each year folder, so the receipt
     link in your message opens for them.
4. **Project Settings** (gear icon): set the time zone to yours.
5. Choose **`setup`** in the function dropdown → **Run** → **Review permissions**.
   - Google will say *"Google hasn't verified this app"*. That's normal for your own script.
     Click **Advanced → Go to receipt-tax (unsafe) → Allow**.
   - This creates `Taxes/<year>/` and the sheet.
6. **Deploy → New deployment** → gear icon → **Web app**.
   - *Execute as:* **Me**
   - *Who has access:* **Anyone**. Anyone can *reach* the URL, but nothing works without the
     token.
   - Click **Deploy** and copy the **Web app URL** (ends in `/exec`).
7. Put the URL and token into `skill/receipt-tax/config.json`:
   ```json
   "storage": { "type": "google", "endpoint": "https://script.google.com/macros/s/.../exec", "token": "..." }
   ```
8. Test from a terminal: `python skill/receipt-tax/scripts/receipt_tax.py ping`.

## Option B: from the command line with clasp

```bash
npm install -g @google/clasp
clasp login                                   # browser sign-in
# turn on "Google Apps Script API" at https://script.google.com/home/usersettings
cd backends/google-apps-script
cp Config.example.gs Config.gs                # fill in TOKEN etc.
clasp create --type standalone --title receipt-tax --rootDir .
clasp push -f                                 # if create overwrote appsscript.json, restore it first: git checkout appsscript.json
clasp create-deployment --description v1      # prints the deployment ID
```

You still have to run `setup` once in the editor (Option A step 5). Google only grants Drive
access through that click. Your URL is
`https://script.google.com/macros/s/<deployment ID>/exec`.

## Updating the code later

Don't click **New deployment** again: a new deployment gets a **new URL**. Instead:
- Browser: **Deploy → Manage deployments → ✏️ → Version: New version → Deploy**.
- clasp: `clasp push -f && clasp update-deployment <deployment ID>`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `HTTP 403` / `401` | `setup` never run, or access isn't *Anyone* | step 5, or redeploy with *Anyone* |
| `bad token` | token in config.json ≠ Config.gs | copy it again, no spaces |
| `Specified permissions are not sufficient` | code changed and needs a new scope | run `setup` again in the editor and allow |
| `did not return JSON` (HTML page) | wrong URL, or a Google sign-in page | use the `/exec` URL, not `/dev` or the editor URL |
| Claude app: "could not reach the backend" | sandbox network blocks Google | allow `script.google.com` and `script.googleusercontent.com` |
| Changes don't show up | deployment still on the old version | *Manage deployments → New version* |

## Want Excel instead of a Google Sheet?

- Every log returns an `excel_download` link (the Sheet exported as `.xlsx`).
- Or use **File → Download → Microsoft Excel** in the Sheet.
- Or open the Sheet in Excel through Google Drive for desktop.
- For a native, always-on Excel file, see OneDrive in [storage-custom.md](storage-custom.md).

## Limits

Apps Script has daily quotas (free Gmail accounts get about 20,000 URL fetches and 90 minutes of
runtime a day), far more than receipts need. A single request can be up to 50 MB, so phone
photos are fine.
