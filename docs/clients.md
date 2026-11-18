# Where you use it: connecting each assistant

The skill itself (`skill/receipt-tax/`) is a standard `SKILL.md` folder. Claude and Codex both
read that format. ChatGPT has no skills, so it gets a Custom GPT version.

| | Claude app | Claude Code | Codex | ChatGPT |
|---|---|---|---|---|
| Phone camera → receipt | ✅ | ❌ (desktop) | ❌ (desktop) | ✅ |
| Google storage | ✅ | ✅ | ✅ | ✅ (Action) |
| Local Excel/CSV | ❌ sandbox is temporary | ✅ | ✅ | ❌ |
| Opens WhatsApp etc. | tap the link | click the link | click the link | tap the link |
| Install | upload a zip | copy a folder | copy a folder | paste instructions + schema |

---

## Claude app

Covers claude.ai on the web, the iOS and Android apps, and Claude Desktop. The skill runs in
Claude's code sandbox, which is temporary and can only reach domains it's allowed to. So use
**Google storage** (or your own backend), not local.

1. **Fill in `skill/receipt-tax/config.json`.** Copy it from `config.example.json`. Set
   `"storage": {"type": "google", ...}` and your channels.
2. **Build the zip:** `python scripts/build_skill_zip.py`. This makes `dist/receipt-tax-skill.zip`.
   Use the script rather than Windows' "Send to → Compressed folder", which writes backslashes
   in paths that the upload can reject.
3. **Check capabilities.** In Settings → Capabilities:
   - **Code execution and file creation** must be on. It's on by default for Free, Pro and Max.
   - **Network access / egress** must allow the backend. If you see an allow-list, add
     `script.google.com` and `script.googleusercontent.com`. For Discord or Slack channels, also
     add `discord.com` or `hooks.slack.com`.
   - On Team and Enterprise plans an admin may control these settings.
4. **Upload the skill.** Go to Settings → Skills (under *Customize* or *Capabilities*, depending
   on app version) → **Upload skill** → choose the zip.
5. **Test.** In a new chat: *"use receipt-tax to ping the backend"*. It should come back with
   `ok: true` and your Taxes folder link.

**Using it:** attach the receipt with the paperclip or camera button, so it arrives as a file,
and say *"log this receipt"*.

**Changing settings later:** edit `config.json`, rebuild the zip and upload it again. Backend
settings such as the parent folder or tax-year format live in `Config.gs` instead, so for those
you redeploy the backend and leave the zip alone.

## Claude Code

```bash
# macOS / Linux
cp -r skill/receipt-tax ~/.claude/skills/receipt-tax
# Windows (PowerShell)
Copy-Item -Recurse skill\receipt-tax $HOME\.claude\skills\receipt-tax
```

Put `config.json` in that copied folder. Then: *"log this receipt ~/Downloads/IMG_2041.jpg"*,
or run `/receipt-tax`. Local storage works here (`pip install openpyxl` for .xlsx).

## Codex

Codex (the OpenAI coding agent, CLI or IDE) reads skills from `~/.agents/skills/` (personal)
or `.agents/skills/` (per repo):

```bash
cp -r skill/receipt-tax ~/.agents/skills/receipt-tax
```

Same `config.json`, same commands. Codex runs the same Python script, so it writes to the same
spreadsheet as Claude.

## ChatGPT

ChatGPT can't run the script, so it calls the Google backend directly through a **Custom GPT
Action**, and writes the message itself.

1. Deploy the Google backend first ([storage-google.md](storage-google.md)).
2. In ChatGPT, go to **GPTs → Create → Configure**. Paste [`chatgpt/instructions.md`](../chatgpt/instructions.md)
   into Instructions, after filling in your accountant line.
3. **Actions → Create new action.** Paste [`chatgpt/action-schema.yaml`](../chatgpt/action-schema.yaml)
   after replacing `YOUR_DEPLOYMENT_ID` and `YOUR_TOKEN`. Authentication: None. The token rides
   in the query string.
4. Save as **Only me**. Sharing the GPT shares your token.

Known limit: the photo reaches the backend through ChatGPT's `openaiFileIdRefs`, which hasn't
been tested end to end. If it doesn't arrive, the row is still logged with a warning, and you
upload the photo yourself.

## Other agents

Anything that can read a `SKILL.md`, look at an image and run Python can use the skill folder
as-is (Cursor, Gemini CLI, Goose and others). Point the agent at `SKILL.md`. Agents that can't
run code can follow `chatgpt/instructions.md` and call the backend over HTTP.
