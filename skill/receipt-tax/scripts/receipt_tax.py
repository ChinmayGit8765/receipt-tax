#!/usr/bin/env python3
"""receipt-tax: store a receipt and draft the message to your accountant.

  python receipt_tax.py ping
  python receipt_tax.py log     --json receipt.json --image photo.jpg [--force] [--post]
  python receipt_tax.py check   --json receipt.json --image photo.jpg
  python receipt_tax.py message --json receipt.json [--link URL]      # draft only, stores nothing
  python receipt_tax.py list    [--fy Tax26-27]
  python receipt_tax.py answer  --id Tax26-27-0001 [--pct 60] [--claimable 107.40] [--notes "..."]

Settings come from config.json next to SKILL.md (or the path in RECEIPT_TAX_CONFIG).
Storage:  "google" (Apps Script web app) | "local" (xlsx or csv on this computer).
Channels: whatsapp | telegram | sms | email | discord | slack | copy.
Exit codes: 0 ok, 2 possible duplicate, 1 error.

Standard library only, except openpyxl for local .xlsx (falls back to .csv without it).
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "region": {
        "fy_start": "07-01",          # MM-DD
        "fy_label": "Tax{yy}-{yy2}",  # {YYYY} {yy} {YYYY2} {yy2}
        "currency": "AUD",
        "currency_symbol": "$",
        "tax_name": "GST",
        "tax_id_name": "ABN",
        "date_format": "%d/%m/%Y",
    },
    "storage": {"type": "local", "dir": "~/Receipts", "format": "xlsx"},
    "accountant": {"name": ""},
    "channels": [{"type": "copy"}],
    "message": {
        "intro": "I've bought the following. Here are the details from the receipt:",
        "question": "How much of this can I claim back?",
    },
}

COLUMNS = [
    "Receipt ID", "Date", "Supplier", "Supplier tax ID", "What it is", "Purpose (my words, cleaned)",
    "Line items", "Category", "Subtotal ex tax", "Tax", "Total", "Currency", "Payment method",
    "Receipt / invoice no.", "Work-use % (accountant)", "Claimable amount (accountant)",
    "Accountant notes", "Status", "File link", "Image SHA-256", "Logged at",
]


class Duplicate(Exception):
    pass


# ---------------------------------------------------------------- config

def load_config():
    path = Path(os.environ.get("RECEIPT_TAX_CONFIG") or SKILL_DIR / "config.json")
    user = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = json.loads(json.dumps(DEFAULTS))
    for key, val in user.items():
        if isinstance(val, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(val)
        else:
            cfg[key] = val
    cfg["_path"] = str(path)
    return cfg


def fy_label(date, region):
    month, day = (int(x) for x in region["fy_start"].split("-"))
    start = date.year if (date.month, date.day) >= (month, day) else date.year - 1
    end = start if (month, day) == (1, 1) else start + 1
    return (region["fy_label"]
            .replace("{YYYY2}", str(end)).replace("{yy2}", f"{end % 100:02d}")
            .replace("{YYYY}", str(start)).replace("{yy}", f"{start % 100:02d}"))


def money(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    cleaned = "".join(ch for ch in str(v) if ch.isdigit() or ch in ".-")
    return round(float(cleaned), 2) if cleaned else None


def load_receipt(path, cfg):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in ("date", "supplier", "total", "what", "purpose") if r.get(k) in (None, "")]
    if missing:
        raise SystemExit(f"error: receipt JSON is missing {', '.join(missing)}")
    try:
        r["_date"] = dt.date.fromisoformat(str(r["date"]))
    except ValueError:
        raise SystemExit(f"error: date must be YYYY-MM-DD, got {r['date']!r}")
    for k in ("subtotal", "tax", "total"):
        r[k] = money(r.get(k))
    r["currency"] = r.get("currency") or cfg["region"]["currency"]
    return r


def fmt_money(v, cfg, currency=None):
    if v is None:
        return ""
    reg = cfg["region"]
    if currency and currency != reg["currency"]:
        return f"{v:,.2f} {currency}"
    return f"{reg['currency_symbol']}{v:,.2f}"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def items_text(r, cfg):
    items = r.get("line_items") or []
    if not isinstance(items, list):
        return str(items)
    return "; ".join(
        f"{i.get('qty', 1)} x {i.get('description', '')} {fmt_money(money(i.get('amount')), cfg, r['currency'])}".strip()
        for i in items)


# ---------------------------------------------------------------- storage: google

def google_call(cfg, body):
    st = cfg["storage"]
    url, token = st.get("endpoint", ""), st.get("token", "")
    if not url.startswith("https://") or not token:
        raise SystemExit(f"error: storage.endpoint/token not set in {cfg['_path']} (docs/storage-google.md)")
    body["token"] = token
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        # Apps Script answers POST with a 302 to script.googleusercontent.com; urllib follows it as GET.
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error: backend answered HTTP {e.code}. 401/403 usually means setup() was never "
                         "run in the Apps Script editor, or the deployment access is not 'Anyone'.")
    except urllib.error.URLError as e:
        raise SystemExit(f"error: could not reach the backend ({e.reason}). In the Claude app, allow "
                         "script.google.com and script.googleusercontent.com (docs/clients.md).")
    try:
        res = json.loads(raw)
    except json.JSONDecodeError:
        raise SystemExit("error: backend did not return JSON: " + raw[:200])
    if not res.get("ok") and res.get("reason") != "possible duplicate":
        raise SystemExit("error: backend: " + str(res.get("error")))
    return res


def google_image(path):
    p = Path(path)
    return {"image_base64": base64.b64encode(p.read_bytes()).decode(),
            "mime": mimetypes.guess_type(p.name)[0] or "image/jpeg", "filename": p.name}


# ---------------------------------------------------------------- storage: local

def local_paths(cfg, fy):
    base = Path(os.path.expanduser(cfg["storage"].get("dir", "~/Receipts")))
    fmt = cfg["storage"].get("format", "xlsx")
    if fmt == "xlsx":
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            fmt = "csv"
    folder = base / cfg["storage"].get("parent_folder", "Taxes") / fy
    return folder, folder / f"{fy} receipts.{fmt}", fmt


def local_rows(ledger, fmt):
    if not ledger.exists():
        return []
    if fmt == "csv":
        with open(ledger, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    from openpyxl import load_workbook
    ws = load_workbook(ledger)["Receipts"]
    head = [c.value for c in ws[1]]
    return [dict(zip(head, r)) for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]


def local_write(ledger, fmt, rows):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(ledger.suffix + ".tmp")
    if fmt == "csv":
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLUMNS})
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Receipts"
        ws.append(COLUMNS)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="305496")
        for r in rows:
            ws.append([r.get(c) for c in COLUMNS])
        ws.freeze_panes = "A2"
        s = wb.create_sheet("Summary")
        L = lambda n: chr(65 + COLUMNS.index(n))
        s.append(["Measure", "Value"])
        s.append(["Receipts logged", "=COUNTA(Receipts!A2:A100000)"])
        for n in ("Total", "Tax", "Claimable amount (accountant)"):
            s.append([f"Sum of {n}", f"=SUM(Receipts!{L(n)}2:{L(n)}100000)"])
        s.append(["Awaiting accountant", f'=COUNTIF(Receipts!{L("Status")}2:{L("Status")}100000,"Asked accountant")'])
        wb.save(tmp)
    tmp.replace(ledger)


def local_duplicates(rows, r, digest):
    hits = []
    for row in rows:
        if digest and row.get("Image SHA-256") == digest:
            hits.append({"id": row["Receipt ID"], "why": "same image"})
        elif (str(row.get("Date"))[:10] == r["date"] and money(row.get("Total")) == r["total"]
              and str(row.get("Supplier", "")).lower() == r["supplier"].lower()):
            hits.append({"id": row["Receipt ID"], "why": "same supplier, date and total"})
    return hits


# ---------------------------------------------------------------- storage dispatch

def store(cfg, r, image, force=False, dry_run=False):
    fy = fy_label(r["_date"], cfg["region"])
    kind = cfg["storage"].get("type", "local")
    if kind == "google":
        payload = {k: v for k, v in r.items() if not k.startswith("_")}
        body = {"action": "check" if dry_run else "log", "receipt": payload, "fy": fy, **google_image(image)}
        if force:
            body["force"] = True
        res = google_call(cfg, body)
        if res.get("reason") == "possible duplicate":
            raise Duplicate(res["duplicates"])
        return res
    if kind != "local":
        raise SystemExit(f"error: unknown storage.type {kind!r} (google | local)")

    folder, ledger, fmt = local_paths(cfg, fy)
    rows = local_rows(ledger, fmt)
    digest = sha256_file(image)
    dups = local_duplicates(rows, r, digest)
    if dry_run:
        return {"ok": True, "fy": fy, "duplicates": dups}
    if dups and not force:
        raise Duplicate(dups)
    last = max([int(str(x["Receipt ID"]).rsplit("-", 1)[-1]) for x in rows] or [0])
    rid = f"{fy}-{last + 1:04d}"
    safe = "".join(ch if ch.isalnum() else "-" for ch in r["supplier"]).strip("-")[:30]
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{r['date']}_{safe}_{r['total']:.2f}_{rid}{Path(image).suffix.lower()}"
    shutil.copy2(image, dest)
    rows.append({
        "Receipt ID": rid, "Date": r["date"], "Supplier": r["supplier"], "Supplier tax ID": r.get("tax_id"),
        "What it is": r["what"], "Purpose (my words, cleaned)": r["purpose"], "Line items": items_text(r, cfg),
        "Category": r.get("category"), "Subtotal ex tax": r.get("subtotal"), "Tax": r.get("tax"),
        "Total": r["total"], "Currency": r["currency"], "Payment method": r.get("payment_method"),
        "Receipt / invoice no.": r.get("receipt_number"), "Status": "Asked accountant",
        "File link": str(dest), "Image SHA-256": digest,
        "Logged at": dt.datetime.now().replace(microsecond=0).isoformat(sep=" "),
    })
    local_write(ledger, fmt, rows)
    warnings = []
    if fy != fy_label(dt.date.today(), cfg["region"]):
        warnings.append(f"receipt date falls in {fy}, filed there")
    if fmt != cfg["storage"].get("format", "xlsx"):
        warnings.append("openpyxl not installed: wrote CSV instead of xlsx (pip install openpyxl)")
    return {"ok": True, "receipt_id": rid, "financial_year": fy, "file_link": str(dest),
            "sheet_link": str(ledger), "warnings": warnings}


# ---------------------------------------------------------------- messages

def message_text(cfg, r, link=None):
    reg, msg = cfg["region"], cfg["message"]
    name = cfg["accountant"].get("name")
    lines = [f"Hi {name}," if name else "Hi,", "", msg["intro"], ""]

    def add(label, value):
        if value not in (None, ""):
            lines.append(f"• {label}: {value}")

    add("Item", r.get("what"))
    add("Purpose", r.get("purpose"))
    add("Supplier", r["supplier"] + (f" ({reg['tax_id_name']} {r['tax_id']})" if r.get("tax_id") else ""))
    add("Date", r["_date"].strftime(reg["date_format"]))
    total = fmt_money(r.get("total"), cfg, r["currency"])
    if r.get("tax") is not None:
        total += f" (incl. {fmt_money(r['tax'], cfg, r['currency'])} {reg['tax_name']})"
    add("Total", total)
    add("Paid by", r.get("payment_method"))
    add("Receipt no.", r.get("receipt_number"))
    add("Receipt", link)
    lines += ["", msg["question"]]
    return "\n".join(lines)


def digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def channel_draft(ch, text, subject, link, post=False):
    """Return {type, kind: link|posted|text, value, note}. Link channels never send anything."""
    t = ch.get("type", "copy")
    q = urllib.parse.quote
    if t == "whatsapp":
        return {"type": t, "kind": "link", "value": f"https://wa.me/{digits(ch.get('to'))}?text={q(text)}",
                "note": "opens WhatsApp with the text filled in; you press send. Attach the photo yourself if the link is private."}
    if t == "telegram":
        return {"type": t, "kind": "link",
                "value": f"https://t.me/share/url?url={q(link or '')}&text={q(text)}",
                "note": "opens Telegram's share screen; pick your accountant's chat."}
    if t == "sms":
        return {"type": t, "kind": "link", "value": f"sms:{'+' + digits(ch.get('to')) if ch.get('to') else ''}?&body={q(text)}",
                "note": "opens Messages (SMS/iMessage) with the text filled in. Phones only."}
    if t == "email":
        return {"type": t, "kind": "link",
                "value": f"mailto:{ch.get('to', '')}?subject={q(subject)}&body={q(text)}",
                "note": "opens your mail app with a draft. Attach the photo before sending."}
    if t in ("discord", "slack"):
        url = ch.get("webhook_url", "")
        if not post:
            return {"type": t, "kind": "text", "value": text,
                    "note": f"{t} webhooks send immediately, so nothing was posted. Re-run with --post after you confirm."}
        if not url.startswith("https://"):
            return {"type": t, "kind": "error", "value": "", "note": "webhook_url not set"}
        body = {"content": text[:2000]} if t == "discord" else {"text": text}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "receipt-tax"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            return {"type": t, "kind": "posted", "value": "", "note": f"posted to the {t} channel behind the webhook."}
        except urllib.error.URLError as e:
            return {"type": t, "kind": "error", "value": "", "note": f"{t} webhook failed: {e}"}
    return {"type": "copy", "kind": "text", "value": text, "note": "copy and paste this wherever you message your accountant."}


def drafts(cfg, r, link, post=False):
    text = message_text(cfg, r, link)
    subject = f"Receipt: {r['what']} ({fmt_money(r['total'], cfg, r['currency'])})"
    return text, [channel_draft(ch, text, subject, link, post) for ch in cfg.get("channels") or [{"type": "copy"}]]


# ---------------------------------------------------------------- commands

def emit(obj, code=0):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    sys.exit(code)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    for name in ("log", "check"):
        s = sub.add_parser(name)
        s.add_argument("--json", required=True)
        s.add_argument("--image", required=True)
        if name == "log":
            s.add_argument("--force", action="store_true", help="log even if it looks like a duplicate")
            s.add_argument("--post", action="store_true", help="actually post to discord/slack webhooks")
    s = sub.add_parser("message")
    s.add_argument("--json", required=True)
    s.add_argument("--link")
    s = sub.add_parser("list")
    s.add_argument("--fy")
    s = sub.add_parser("answer")
    s.add_argument("--id", required=True)
    s.add_argument("--pct")
    s.add_argument("--claimable")
    s.add_argument("--notes")
    a = ap.parse_args(argv)
    cfg = load_config()
    kind = cfg["storage"].get("type", "local")

    if a.cmd == "ping":
        if kind == "google":
            emit(google_call(cfg, {"action": "ping"}))
        folder, ledger, fmt = local_paths(cfg, fy_label(dt.date.today(), cfg["region"]))
        emit({"ok": True, "storage": "local", "ledger": str(ledger), "format": fmt})

    if a.cmd == "message":
        r = load_receipt(a.json, cfg)
        text, out = drafts(cfg, r, a.link)
        emit({"ok": True, "message_text": text, "drafts": out})

    if a.cmd in ("log", "check"):
        r = load_receipt(a.json, cfg)
        if not Path(a.image).exists():
            raise SystemExit(f"error: image not found: {a.image}")
        try:
            res = store(cfg, r, a.image, force=getattr(a, "force", False), dry_run=a.cmd == "check")
        except Duplicate as d:
            emit({"ok": False, "reason": "possible duplicate", "duplicates": d.args[0]}, 2)
        if a.cmd == "check":
            emit(res)
        text, out = drafts(cfg, r, res.get("file_link") if kind == "google" else None, post=a.post)
        res["message_text"] = text
        res["drafts"] = out
        emit(res)

    if a.cmd == "list":
        fy = a.fy or fy_label(dt.date.today(), cfg["region"])
        if kind == "google":
            emit(google_call(cfg, {"action": "list", "fy": fy}))
        folder, ledger, fmt = local_paths(cfg, fy)
        emit({"ok": True, "fy": fy, "ledger": str(ledger), "rows": [
            {"id": x["Receipt ID"], "date": x["Date"], "supplier": x["Supplier"], "total": x["Total"],
             "status": x["Status"]} for x in local_rows(ledger, fmt)]})

    if a.cmd == "answer":
        if kind == "google":
            emit(google_call(cfg, {"action": "answer", "receipt_id": a.id, "work_use_pct": a.pct,
                                   "claimable": a.claimable, "notes": a.notes}))
        fy = a.id.rsplit("-", 1)[0]
        folder, ledger, fmt = local_paths(cfg, fy)
        rows = local_rows(ledger, fmt)
        hit = [x for x in rows if x["Receipt ID"] == a.id]
        if not hit:
            emit({"ok": False, "error": f"no receipt {a.id}"}, 1)
        for key, val in (("Work-use % (accountant)", a.pct), ("Claimable amount (accountant)", money(a.claimable)),
                         ("Accountant notes", a.notes)):
            if val not in (None, ""):
                hit[0][key] = val
        hit[0]["Status"] = "Answered"
        local_write(ledger, fmt, rows)
        emit({"ok": True, "receipt_id": a.id})


if __name__ == "__main__":
    main()
