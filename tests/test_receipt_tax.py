"""Run: python -m unittest discover tests"""
import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "receipt-tax" / "scripts"))
import receipt_tax as rt  # noqa: E402

RECEIPT = {
    "date": "2026-11-14", "supplier": "Northside Tech Supplies", "tax_id": "12 345 678 901",
    "what": "Logitech MX Keys keyboard",
    "purpose": "I use it mostly for university and my tutoring work, and sometimes for gaming.",
    "line_items": [{"qty": 1, "description": "MX Keys S", "amount": 179.00}],
    "category": "Equipment", "subtotal": 162.73, "tax": 16.27, "total": 179.00,
    "currency": "AUD", "payment_method": "Visa ••4417", "receipt_number": "48213",
}


def run(argv):
    """Run the CLI, return (exit code, parsed JSON)."""
    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            rt.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if isinstance(e.code, str):
                return 1, {"error": e.code}
    return code, json.loads(buf.getvalue())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg_path = self.dir / "config.json"
        os.environ["RECEIPT_TAX_CONFIG"] = str(self.cfg_path)
        self.image = self.dir / "photo.jpg"
        self.image.write_bytes(b"\xff\xd8 fake jpeg")
        self.receipt = self.dir / "r.json"
        self.receipt.write_text(json.dumps(RECEIPT), encoding="utf-8")

    def tearDown(self):
        os.environ.pop("RECEIPT_TAX_CONFIG", None)
        self.tmp.cleanup()

    def config(self, **over):
        cfg = {"storage": {"type": "local", "dir": str(self.dir / "store"), "format": "xlsx"},
               "accountant": {"name": "Priya"}, "channels": [{"type": "whatsapp", "to": "+61 400 000 000"}]}
        cfg.update(over)
        self.cfg_path.write_text(json.dumps(cfg), encoding="utf-8")


class TaxYear(unittest.TestCase):
    def label(self, d, **region):
        reg = dict(rt.DEFAULTS["region"], **region)
        return rt.fy_label(dt.date.fromisoformat(d), reg)

    def test_australia(self):
        self.assertEqual(self.label("2026-07-01"), "Tax26-27")
        self.assertEqual(self.label("2027-06-30"), "Tax26-27")
        self.assertEqual(self.label("2027-07-01"), "Tax27-28")

    def test_uk_6_april(self):
        self.assertEqual(self.label("2027-04-05", fy_start="04-06", fy_label="{YYYY}-{yy2}"), "2026-27")
        self.assertEqual(self.label("2027-04-06", fy_start="04-06", fy_label="{YYYY}-{yy2}"), "2027-28")

    def test_calendar_year(self):
        self.assertEqual(self.label("2026-12-31", fy_start="01-01", fy_label="Tax{YYYY}"), "Tax2026")
        self.assertEqual(self.label("2027-01-01", fy_start="01-01", fy_label="Tax{YYYY}"), "Tax2027")


class LocalStorage(Base):
    def test_log_xlsx_duplicate_force_answer(self):
        self.config()
        code, res = run(["log", "--json", str(self.receipt), "--image", str(self.image)])
        self.assertEqual(code, 0, res)
        self.assertEqual(res["receipt_id"], "Tax26-27-0001")
        ledger = Path(res["sheet_link"])
        self.assertTrue(ledger.exists())
        self.assertEqual(ledger.parent, self.dir / "store" / "Taxes" / "Tax26-27")
        self.assertTrue(Path(res["file_link"]).exists())

        code, res2 = run(["log", "--json", str(self.receipt), "--image", str(self.image)])
        self.assertEqual(code, 2)
        self.assertEqual(res2["duplicates"][0]["why"], "same image")

        code, res3 = run(["log", "--json", str(self.receipt), "--image", str(self.image), "--force"])
        self.assertEqual(res3["receipt_id"], "Tax26-27-0002")

        code, ans = run(["answer", "--id", "Tax26-27-0001", "--pct", "60", "--claimable", "107.40"])
        self.assertTrue(ans["ok"])
        code, lst = run(["list", "--fy", "Tax26-27"])
        self.assertEqual([r["status"] for r in lst["rows"]], ["Answered", "Asked accountant"])

        from openpyxl import load_workbook
        wb = load_workbook(ledger)
        self.assertEqual(wb.sheetnames, ["Receipts", "Summary"])
        row = [c.value for c in wb["Receipts"][2]]
        self.assertEqual(row[rt.COLUMNS.index("Claimable amount (accountant)")], 107.4)

    def test_csv(self):
        self.config(storage={"type": "local", "dir": str(self.dir / "store"), "format": "csv"})
        code, res = run(["log", "--json", str(self.receipt), "--image", str(self.image)])
        self.assertEqual(code, 0, res)
        self.assertTrue(res["sheet_link"].endswith(".csv"))
        text = Path(res["sheet_link"]).read_text(encoding="utf-8")
        self.assertIn("Northside Tech Supplies", text)

    def test_missing_fields(self):
        self.config()
        self.receipt.write_text(json.dumps({"date": "2026-11-14"}), encoding="utf-8")
        code, res = run(["log", "--json", str(self.receipt), "--image", str(self.image)])
        self.assertEqual(code, 1)
        self.assertIn("missing", res["error"])


class Messages(Base):
    def drafts(self, channels):
        self.config(channels=channels)
        code, res = run(["message", "--json", str(self.receipt), "--link", "https://drive/x"])
        self.assertEqual(code, 0, res)
        return res

    def test_text(self):
        res = self.drafts([{"type": "copy"}])
        t = res["message_text"]
        self.assertTrue(t.startswith("Hi Priya,"))
        self.assertIn("• Supplier: Northside Tech Supplies (ABN 12 345 678 901)", t)
        self.assertIn("• Total: $179.00 (incl. $16.27 GST)", t)
        self.assertIn("• Date: 14/11/2026", t)
        self.assertIn("• Receipt: https://drive/x", t)
        self.assertTrue(t.endswith("How much of this can I claim back?"))

    def test_link_channels(self):
        res = self.drafts([{"type": "whatsapp", "to": "+61 400 000 000"}, {"type": "telegram"},
                           {"type": "sms", "to": "+61 400 000 000"}, {"type": "email", "to": "a@b.c"}])
        wa, tg, sms, mail = (d["value"] for d in res["drafts"])
        self.assertTrue(wa.startswith("https://wa.me/61400000000?text=Hi%20Priya"))
        self.assertTrue(tg.startswith("https://t.me/share/url?url=https%3A//drive/x&text="))
        self.assertTrue(sms.startswith("sms:+61400000000?&body="))
        self.assertTrue(mail.startswith("mailto:a@b.c?subject=Receipt%3A%20Logitech"))
        self.assertEqual(urllib.parse.unquote(wa.split("text=")[1]), res["message_text"])

    def test_webhooks_never_post_without_flag(self):
        res = self.drafts([{"type": "discord", "webhook_url": "https://discord.invalid/x"}])
        self.assertEqual(res["drafts"][0]["kind"], "text")

    def test_other_region_wording(self):
        self.config(region={"currency": "GBP", "currency_symbol": "£", "tax_name": "VAT",
                            "tax_id_name": "VAT no.", "fy_start": "04-06", "fy_label": "{YYYY}-{yy2}"},
                    channels=[{"type": "copy"}])
        r = dict(RECEIPT, currency="GBP")
        self.receipt.write_text(json.dumps(r), encoding="utf-8")
        code, res = run(["message", "--json", str(self.receipt)])
        self.assertIn("£179.00 (incl. £16.27 VAT)", res["message_text"])
        self.assertIn("(VAT no. 12 345 678 901)", res["message_text"])


class FakeBackend(BaseHTTPRequestHandler):
    """Stands in for the Apps Script web app and a Discord webhook."""
    received = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeBackend.received.append((self.path, body))
        if self.path == "/webhook":
            self.send_response(204)
            self.end_headers()
            return
        if body.get("token") != "t0k":
            res = {"ok": False, "error": "bad token"}
        elif body["action"] == "log":
            res = {"ok": True, "receipt_id": body["fy"] + "-0001", "financial_year": body["fy"],
                   "file_link": "https://drive/file", "sheet_link": "https://sheet", "warnings": []}
        else:
            res = {"ok": True}
        data = json.dumps(res).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class GoogleAndWebhook(Base):
    def setUp(self):
        super().setUp()
        FakeBackend.received = []
        self.srv = HTTPServer(("127.0.0.1", 0), FakeBackend)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_google_log_and_discord_post(self):
        self.config(storage={"type": "google", "endpoint": "https://placeholder", "token": "t0k"},
                    channels=[{"type": "discord", "webhook_url": self.base + "/webhook"}])
        real_urlopen = rt.urllib.request.urlopen

        def fake_urlopen(req, timeout=0):
            # real use requires https; route both fakes back to the local http server
            if req.full_url.startswith("https://placeholder"):
                req.full_url = self.base + "/exec"
            elif req.full_url.startswith("https://127.0.0.1"):
                req.full_url = req.full_url.replace("https://", "http://")
            return real_urlopen(req, timeout=timeout)

        def fake_draft(ch, text, subject, link, post=False):
            ch = dict(ch, webhook_url=ch["webhook_url"].replace("http://", "https://"))
            return orig_draft(ch, text, subject, link, post)

        orig_draft = rt.channel_draft
        try:
            rt.urllib.request.urlopen = fake_urlopen
            rt.channel_draft = fake_draft
            code, res = run(["log", "--json", str(self.receipt), "--image", str(self.image), "--post"])
        finally:
            rt.urllib.request.urlopen = real_urlopen
            rt.channel_draft = orig_draft
        self.assertEqual(code, 0, res)
        self.assertEqual(res["receipt_id"], "Tax26-27-0001")
        path, body = FakeBackend.received[0]
        self.assertEqual(body["fy"], "Tax26-27")
        self.assertTrue(body["image_base64"])
        self.assertNotIn("_date", body["receipt"])
        self.assertEqual(res["drafts"][0]["kind"], "posted")
        self.assertIn("Northside", FakeBackend.received[1][1]["content"])
        self.assertIn("https://drive/file", res["message_text"])


if __name__ == "__main__":
    unittest.main()
