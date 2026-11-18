# Privacy and safety

**Where the data goes**

| Data | Goes to |
|---|---|
| Receipt photo + your purpose | the AI provider you chat with (Anthropic / OpenAI), as with any chat |
| Photo + spreadsheet row | your storage: your Google Drive, or a folder on your computer |
| Message | your accountant, only when you press send (or confirm a webhook post) |

Nothing goes to the author of this repo or any other third-party server.

**The token**
- The Apps Script web app is reachable by anyone who knows its URL. The token is the only lock.
- Use a long random token (32+ characters). Never put it in a public repo, screenshot or shared GPT.
- `config.json`, `Config.gs`, `.clasp.json` and `dist/` are in `.gitignore` for that reason.
- If it leaks, change `TOKEN` in `Config.gs` and redeploy (*Manage deployments → New version*).
  Rebuild and re-upload the skill zip, and update the ChatGPT Action.
- With the token, someone could add or annotate rows and photos. They **can't** read the rest of
  your Drive, and they can't delete anything: the backend has no delete action.

**Google permissions.** The backend asks for Drive and Sheets access because it creates folders
and files. It runs as you and only touches what the code tells it to. Read `Code.gs`; it's
about 300 lines.

**Keeping records.** Many tax offices want receipts kept for years (Australia: 5 years from
lodging). Printed till receipts fade, so the photo copy matters. Don't delete the year folders
after you lodge.

**What the assistant won't do**
- guess unreadable values
- add reasons, opinions or claims to your purpose
- tell you whether something is deductible
- send anything without your confirmation
