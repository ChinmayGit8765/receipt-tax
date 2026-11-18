/**
 * receipt-tax — Google backend (Apps Script web app that runs in YOUR Google account).
 *
 * Files each receipt photo into Drive/<PARENT_FOLDER>/<year label>/ and appends a row to the
 * Google Sheet "<year label> receipts" in the same folder. It stores data only; the message to
 * your accountant is built by the client (scripts/receipt_tax.py, or ChatGPT's instructions).
 *
 * Settings: Config.gs (copy Config.example.gs). Script properties with the same names override.
 *
 * POST JSON {token, action, ...}   (token may also come as ?token= for ChatGPT Actions)
 *   ping
 *   log     {receipt, fy?, image_base64 + mime + filename | image_url | openaiFileIdRefs, force?}
 *   check   same as log, writes nothing, returns duplicates
 *   list    {fy?}
 *   answer  {receipt_id, work_use_pct?, claimable?, notes?}
 */

var COLUMNS = [
  'Receipt ID', 'Date', 'Supplier', 'Supplier tax ID', 'What it is', 'Purpose (my words, cleaned)',
  'Line items', 'Category', 'Subtotal ex tax', 'Tax', 'Total', 'Currency', 'Payment method',
  'Receipt / invoice no.', 'Work-use % (accountant)', 'Claimable amount (accountant)',
  'Accountant notes', 'Status', 'File link', 'Image SHA-256', 'Logged at'
];
var MONEY = ['Subtotal ex tax', 'Tax', 'Total', 'Claimable amount (accountant)'];
var NO_IMAGE = 'no-image';

function doPost(e) {
  try {
    var req = JSON.parse(e.postData.contents);
    var cfg = settings();
    var token = req.token || (e.parameter && e.parameter.token);
    if (!cfg.TOKEN || token !== cfg.TOKEN) return out({ok: false, error: 'bad token'});
    var lock = LockService.getScriptLock();
    lock.waitLock(30000);
    try {
      switch (req.action) {
        case 'ping': return out({ok: true, service: 'receipt-tax', folder: taxesRoot().getUrl()});
        case 'log': return out(logReceipt(req, false));
        case 'check': return out(logReceipt(req, true));
        case 'list': return out(listRows(req.fy || fyLabel(new Date())));
        case 'answer': return out(answer(req));
        default: return out({ok: false, error: 'unknown action ' + req.action});
      }
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return out({ok: false, error: String(err && err.message || err)});
  }
}

function doGet() {
  return out({ok: true, service: 'receipt-tax', hint: 'POST JSON'});
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------- settings ----------

function settings() {
  var base = typeof CONFIG === 'object' ? CONFIG : {};
  var props = PropertiesService.getScriptProperties().getProperties();
  var res = {PARENT_FOLDER: 'Taxes', FY_START: '07-01', FY_LABEL: 'Tax{yy}-{yy2}', CURRENCY: 'AUD'};
  Object.keys(base).forEach(function (k) { res[k] = base[k]; });
  Object.keys(props).forEach(function (k) { if (props[k] !== '') res[k] = props[k]; });
  return res;
}

/** Financial-year label for a date. FY_START "07-01" = 1 July (AU), "04-06" = 6 April (UK), "01-01" = calendar year. */
function fyLabel(d) {
  var cfg = settings();
  var parts = String(cfg.FY_START).split('-');
  var m = +parts[0] - 1, day = +parts[1];
  var startYear = (d.getMonth() > m || (d.getMonth() === m && d.getDate() >= day)) ? d.getFullYear() : d.getFullYear() - 1;
  var endYear = (m === 0 && day === 1) ? startYear : startYear + 1;
  var two = function (n) { return ('0' + (n % 100)).slice(-2); };
  return String(cfg.FY_LABEL)
    .replace('{YYYY}', startYear).replace('{yy}', two(startYear))
    .replace('{YYYY2}', endYear).replace('{yy2}', two(endYear));
}

// ---------- helpers ----------

function parseDate(s) {
  var m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  throw new Error('unreadable date ' + s + ' (use YYYY-MM-DD)');
}

function money(v) {
  if (v === null || v === undefined || v === '') return null;
  return Math.round(parseFloat(String(v).replace(/[^0-9.\-]/g, '')) * 100) / 100;
}

function hex(bytes) {
  return bytes.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}

function taxesRoot() {
  var name = settings().PARENT_FOLDER;
  var it = DriveApp.getRootFolder().getFoldersByName(name);
  return it.hasNext() ? it.next() : DriveApp.getRootFolder().createFolder(name);
}

function folderFor(fy) {
  var parent = taxesRoot();
  var it = parent.getFoldersByName(fy);
  var f = it.hasNext() ? it.next() : parent.createFolder(fy);
  var email = settings().ACCOUNTANT_EMAIL;
  if (email && f.getViewers().map(function (u) { return u.getEmail(); }).indexOf(email) < 0) {
    try { f.addViewer(email); } catch (e) { /* not fatal */ }
  }
  return f;
}

function colLetter(name) {
  return String.fromCharCode(65 + COLUMNS.indexOf(name));
}

function sheetFor(fy) {
  var folder = folderFor(fy);
  var name = fy + ' receipts';
  var it = folder.getFilesByName(name);
  if (it.hasNext()) return SpreadsheetApp.open(it.next());
  var ss = SpreadsheetApp.create(name);
  DriveApp.getFileById(ss.getId()).moveTo(folder);
  var sh = ss.getSheets()[0].setName('Receipts');
  sh.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS])
    .setFontWeight('bold').setFontColor('#ffffff').setBackground('#305496').setWrap(true);
  sh.setFrozenRows(1);
  var col = function (n) { return 'Receipts!' + colLetter(n) + '2:' + colLetter(n); };
  var sum = ss.insertSheet('Summary');
  sum.getRange(1, 1, 6, 2).setValues([
    ['Measure', 'Value'],
    ['Receipts logged', '=COUNTA(Receipts!A2:A)'],
    ['Sum of Total', '=SUM(' + col('Total') + ')'],
    ['Sum of Tax', '=SUM(' + col('Tax') + ')'],
    ['Sum of claimable (accountant)', '=SUM(' + col('Claimable amount (accountant)') + ')'],
    ['Awaiting accountant', '=COUNTIF(' + col('Status') + ',"Asked accountant")']
  ]);
  sum.getRange('B3:B5').setNumberFormat('#,##0.00');
  sum.getRange('A1:B1').setFontWeight('bold');
  sum.setColumnWidth(1, 240);
  return ss;
}

function readRows(ss) {
  var vals = ss.getSheetByName('Receipts').getDataRange().getValues();
  var head = vals.shift();
  return vals.filter(function (r) { return r[0]; }).map(function (r, i) {
    var o = {_row: i + 2};
    head.forEach(function (h, j) { o[h] = r[j]; });
    return o;
  });
}

function sameDay(a, b) {
  return a instanceof Date && a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function duplicates(ss, r, digest) {
  return readRows(ss).map(function (row) {
    if (digest !== NO_IMAGE && row['Image SHA-256'] === digest) return {id: row['Receipt ID'], why: 'same image'};
    if (sameDay(row['Date'], r._date) && money(row['Total']) === r.total &&
        String(row['Supplier']).toLowerCase() === String(r.supplier).toLowerCase()) {
      return {id: row['Receipt ID'], why: 'same supplier, date and total'};
    }
    return null;
  }).filter(Boolean);
}

function normalise(raw) {
  var r = JSON.parse(JSON.stringify(raw || {}));
  var missing = ['date', 'supplier', 'total', 'what', 'purpose'].filter(function (k) {
    return r[k] === null || r[k] === undefined || r[k] === '';
  });
  if (missing.length) throw new Error('receipt is missing ' + missing.join(', '));
  r._date = parseDate(r.date);
  ['subtotal', 'tax', 'total'].forEach(function (k) { r[k] = money(r[k]); });
  r.currency = r.currency || settings().CURRENCY;
  return r;
}

function imageBlob(req) {
  if (req.image_base64) {
    var b64 = String(req.image_base64).replace(/^data:[^,]+,/, '');
    return Utilities.newBlob(Utilities.base64Decode(b64), req.mime || 'image/jpeg', req.filename || 'receipt.jpg');
  }
  var ref = (req.openaiFileIdRefs || [])[0];
  var url = req.image_url || (ref && ref.download_link);
  if (url) {
    var blob = UrlFetchApp.fetch(url).getBlob();
    if (ref && ref.mime_type) blob.setContentType(ref.mime_type);
    return blob;
  }
  throw new Error('no image sent');
}

// ---------- actions ----------

function logReceipt(req, dryRun) {
  var r = normalise(req.receipt);
  var warnings = [];
  var blob = null, digest = NO_IMAGE;
  try {
    blob = imageBlob(req);
    digest = hex(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, blob.getBytes()));
  } catch (err) {
    warnings.push('photo not received (' + err.message + '): row logged without it, add the photo yourself');
  }
  var fy = req.fy || fyLabel(r._date);
  var ss = sheetFor(fy);
  var dups = duplicates(ss, r, digest);
  if (dryRun) return {ok: true, fy: fy, duplicates: dups};
  if (dups.length && !req.force) return {ok: false, reason: 'possible duplicate', duplicates: dups};
  if (fy !== fyLabel(new Date())) warnings.push('receipt date falls in ' + fy + ', filed there');

  var rows = readRows(ss);
  var last = rows.length ? parseInt(String(rows[rows.length - 1]['Receipt ID']).split('-').pop(), 10) || 0 : 0;
  var rid = fy + '-' + ('000' + (last + 1)).slice(-4);

  var link = '';
  if (blob) {
    var type = blob.getContentType() || '';
    var ext = type.indexOf('png') >= 0 ? '.png' : type.indexOf('pdf') >= 0 ? '.pdf' : '.jpg';
    var safe = String(r.supplier).replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 30);
    link = folderFor(fy).createFile(blob.setName(r.date + '_' + safe + '_' + r.total.toFixed(2) + '_' + rid + ext)).getUrl();
  }

  var items = Array.isArray(r.line_items) ? r.line_items.map(function (i) {
    var amt = money(i.amount);
    return (i.qty || 1) + ' x ' + (i.description || '') + (amt === null ? '' : ' ' + amt.toFixed(2));
  }).join('; ') : (r.line_items || '');

  var v = {
    'Receipt ID': rid, 'Date': r._date, 'Supplier': r.supplier, 'Supplier tax ID': r.tax_id || '',
    'What it is': r.what, 'Purpose (my words, cleaned)': r.purpose, 'Line items': items,
    'Category': r.category || '', 'Subtotal ex tax': r.subtotal, 'Tax': r.tax, 'Total': r.total,
    'Currency': r.currency, 'Payment method': r.payment_method || '',
    'Receipt / invoice no.': r.receipt_number || '', 'Status': 'Asked accountant',
    'File link': link, 'Image SHA-256': digest, 'Logged at': new Date()
  };
  var sh = ss.getSheetByName('Receipts');
  sh.appendRow(COLUMNS.map(function (c) { return v[c] === null || v[c] === undefined ? '' : v[c]; }));
  var n = sh.getLastRow();
  MONEY.forEach(function (c) { sh.getRange(n, COLUMNS.indexOf(c) + 1).setNumberFormat('#,##0.00'); });
  sh.getRange(n, 2).setNumberFormat('yyyy-mm-dd');
  sh.getRange(n, COLUMNS.length).setNumberFormat('yyyy-mm-dd hh:mm');

  return {
    ok: true, receipt_id: rid, financial_year: fy, file_link: link, sheet_link: ss.getUrl(),
    excel_download: 'https://docs.google.com/spreadsheets/d/' + ss.getId() + '/export?format=xlsx',
    warnings: warnings
  };
}

function listRows(fy) {
  var ss = sheetFor(fy);
  return {ok: true, fy: fy, sheet_link: ss.getUrl(), rows: readRows(ss).map(function (r) {
    return {id: r['Receipt ID'], date: r['Date'], supplier: r['Supplier'], total: r['Total'], status: r['Status']};
  })};
}

function answer(req) {
  var fy = String(req.receipt_id).replace(/-\d+$/, '');
  var ss = sheetFor(fy);
  var row = readRows(ss).filter(function (r) { return r['Receipt ID'] === req.receipt_id; })[0];
  if (!row) return {ok: false, error: 'no receipt ' + req.receipt_id};
  var sh = ss.getSheetByName('Receipts');
  var set = function (c, v) { if (v !== undefined && v !== null && v !== '') sh.getRange(row._row, COLUMNS.indexOf(c) + 1).setValue(v); };
  set('Work-use % (accountant)', req.work_use_pct);
  set('Claimable amount (accountant)', money(req.claimable));
  set('Accountant notes', req.notes);
  set('Status', 'Answered');
  return {ok: true, receipt_id: req.receipt_id};
}

/** Run once from the editor: creates the folders and sheet and triggers Google's permission prompt. */
function setup() {
  var cfg = settings();
  if (!cfg.TOKEN || cfg.TOKEN.indexOf('CHANGE') === 0) throw new Error('Set TOKEN in Config.gs first');
  Logger.log('Sheet: ' + sheetFor(fyLabel(new Date())).getUrl());
}
