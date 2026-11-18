# Messaging your accountant

The message text is the same on every channel. Only the way it reaches your accountant changes.
List one or more channels in `config.json`:

```json
"accountant": { "name": "Priya" },
"channels": [
  { "type": "whatsapp", "to": "61400000000" },
  { "type": "email", "to": "priya@example.com" }
],
"message": {
  "intro": "I've bought the following. Here are the details from the receipt:",
  "question": "How much of this can I claim back?"
}
```

## Two kinds of channel

- **Draft links** (WhatsApp, Telegram, SMS, email): the assistant gives you a link, you tap it,
  and your own app opens with the message typed in. **You** press send. Nothing leaves your
  phone until you do.
- **Webhooks** (Discord, Slack): a webhook posts straight into a channel, and there is no draft
  step. The skill only posts when the run includes `--post`, which the assistant adds only after
  you said yes at "Log it?". To keep a review step, point the webhook at a private channel you
  forward from.

## Channels

### WhatsApp
```json
{ "type": "whatsapp", "to": "61400000000" }
```
- `to`: international format, digits only (Australia `61` + mobile without the leading 0; UK `44`…).
- Leave `to` empty and WhatsApp asks which chat to use.
- Uses `https://wa.me/<number>?text=…`, which works with the phone app, WhatsApp Desktop and WhatsApp Web.
- **The photo can't be attached through a link.** Either set `ACCOUNTANT_EMAIL` in the Google
  backend so the Drive link in the message opens for them, or attach the photo yourself.
- WhatsApp Business API sending is deliberately not supported. It needs a Meta business account
  and approved templates, and it would send without your tap.

### Telegram
```json
{ "type": "telegram" }
```
Uses `https://t.me/share/url?url=<file link>&text=…`, which opens Telegram's share sheet so you
can pick the chat. For a fully automatic post, a bot (`api.telegram.org/bot<token>/sendMessage`)
is an easy addition to `channel_draft()`. Keep the bot token in config.json.

### SMS / iMessage
```json
{ "type": "sms", "to": "+61400000000" }
```
Uses `sms:<number>?&body=…`, which works on iOS (iMessage or SMS) and Android. On a desktop the
link usually does nothing.

### Email
```json
{ "type": "email", "to": "priya@example.com" }
```
Uses `mailto:`, which opens your default mail app with subject and body filled in. Attach the
photo before sending. Very long messages can be cut off by some mail apps (around 2,000
characters, well above a receipt message).

### Discord
```json
{ "type": "discord", "webhook_url": "https://discord.com/api/webhooks/…" }
```
1. Server Settings → **Integrations → Webhooks → New Webhook**. Pick the channel, then **Copy
   Webhook URL**.
2. Messages are capped at 2,000 characters (the skill trims longer ones).
3. In the Claude app, allow `discord.com`.

Discord has no draft link. Without `--post` you get the text to paste yourself.

### Slack
```json
{ "type": "slack", "webhook_url": "https://hooks.slack.com/services/…" }
```
Create an app at api.slack.com/apps → **Incoming Webhooks** → add to a channel. In the Claude
app, allow `hooks.slack.com`.

### Copy (anything else)
```json
{ "type": "copy" }
```
Plain text for Signal, Microsoft Teams, LinkedIn, your accountant's client portal, and so on.
Signal and Teams have no way to fill in a message from a link, so copy is the honest option.

## Changing the wording

`message.intro` and `message.question` are yours to change. Examples:

- *"Could you tell me whether this is claimable and roughly how much?"*
- *"Logging this for my 2026–27 return. Anything I should know?"*

The bullet lines (item, purpose, supplier, date, total, paid by, receipt number, link) are
built from the receipt. Lines with no value are left out. The **purpose** is your own words,
with spelling and grammar fixed and nothing added.

## Adding a channel

Add a branch to `channel_draft()` in
[`receipt_tax.py`](../skill/receipt-tax/scripts/receipt_tax.py). It gets the message text, a
subject and the file link, and returns `{type, kind: link|text|posted|error, value, note}`.
Add a test in `tests/test_receipt_tax.py`.
