// Runs backends/google-apps-script/Code.gs against small fakes of the Apps Script services.
// Run: node tests/apps-script.test.js
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const src = fs.readFileSync(path.join(__dirname, '..', 'backends', 'google-apps-script', 'Code.gs'), 'utf8');

function load(config) {
  const iter = a => { let i = 0; return { hasNext: () => i < a.length, next: () => a[i++] }; };
  let idc = 0;
  const files = {};
  function Sheet(name) {
    const g = [];
    const sh = {
      name, g,
      set(r, c, v) { while (g.length < r) g.push([]); g[r - 1][c - 1] = v; },
      setName(n) { sh.name = n; return sh; },
      getRange(r, c) {
        const rng = {
          setValues(v) { v.forEach((row, i) => row.forEach((x, j) => sh.set(r + i, c + j, x))); return rng; },
          setValue(x) { sh.set(r, c, x); return rng; },
          setFontWeight: () => rng, setFontColor: () => rng, setBackground: () => rng, setWrap: () => rng, setNumberFormat: () => rng,
        };
        return rng;
      },
      setFrozenRows() {}, setColumnWidth() {},
      appendRow(row) { g.push(row.slice()); },
      getLastRow: () => g.length,
      getDataRange: () => ({ getValues: () => g.map(r => r.slice()) }),
    };
    return sh;
  }
  function Spreadsheet(name) {
    const id = 'ss' + (++idc), sheets = [Sheet('Sheet1')];
    const ss = { name, getId: () => id, getUrl: () => 'https://sheet/' + id, getSheets: () => sheets,
      insertSheet(n) { const s = Sheet(n); sheets.push(s); return s; },
      getSheetByName: n => sheets.find(s => s.name === n) };
    files[id] = ss;
    return ss;
  }
  function Folder(name) {
    const kids = [], subs = [], viewers = [];
    return { name, kids, subs, getUrl: () => 'https://drive/folder/' + name,
      getFoldersByName: n => iter(subs.filter(s => s.name === n)),
      createFolder(n) { const s = Folder(n); subs.push(s); return s; },
      getFilesByName: n => iter(kids.filter(k => k.name === n)),
      createFile(blob) { const k = { name: blob.name, getUrl: () => 'https://drive/' + blob.name }; kids.push(k); return k; },
      getViewers: () => viewers.map(e => ({ getEmail: () => e })), addViewer(e) { viewers.push(e); } };
  }
  const root = Folder('root');
  const toSigned = buf => Array.from(buf).map(b => (b > 127 ? b - 256 : b));
  const g = {
    CONFIG: config,
    PropertiesService: { getScriptProperties: () => ({ getProperties: () => ({}) }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: s => ({ setMimeType: () => JSON.parse(s) }) },
    DriveApp: { getRootFolder: () => root,
      getFileById: id => ({ moveTo(folder) { folder.kids.push({ name: files[id].name, ss: files[id] }); } }) },
    SpreadsheetApp: { create: n => Spreadsheet(n), open: k => k.ss },
    Utilities: {
      base64Decode: s => toSigned(Buffer.from(s, 'base64')),
      newBlob: (bytes, mime, name) => { const b = { name, getBytes: () => bytes, getContentType: () => mime, setName(n) { b.name = n; return b; }, setContentType() { return b; } }; return b; },
      computeDigest: (_, bytes) => toSigned(crypto.createHash('sha256').update(Buffer.from(bytes.map(x => x & 255))).digest()),
      DigestAlgorithm: { SHA_256: 1 },
    },
    UrlFetchApp: {}, Logger: { log() {} },
  };
  const fns = new Function(...Object.keys(g), src + '\nreturn {doPost, fyLabel};')(...Object.values(g));
  const post = b => fns.doPost({ postData: { contents: JSON.stringify({ token: config.TOKEN, ...b }) } });
  return { post, root, fyLabel: fns.fyLabel, doPost: fns.doPost };
}

let failed = 0;
const check = (name, cond, extra) => {
  console.log((cond ? 'PASS ' : 'FAIL ') + name);
  if (!cond) { failed++; console.log(JSON.stringify(extra, null, 2)); }
};

const AU = { TOKEN: 't0k', PARENT_FOLDER: 'Taxes', FY_START: '07-01', FY_LABEL: 'Tax{yy}-{yy2}', CURRENCY: 'AUD', ACCOUNTANT_EMAIL: 'acc@example.com' };
const receipt = { date: '2026-11-14', supplier: 'Northside Tech Supplies', tax_id: '12 345 678 901', what: 'Logitech MX Keys keyboard',
  purpose: 'I use it mostly for university.', line_items: [{ qty: 1, description: 'MX Keys S', amount: 179 }],
  category: 'Equipment', subtotal: 162.73, tax: 16.27, total: '$179.00', payment_method: 'Visa 4417', receipt_number: '48213' };
const img = s => Buffer.from(s).toString('base64');

{
  const { post, root, doPost } = load(AU);
  check('bad token rejected', doPost({ postData: { contents: '{"token":"no","action":"ping"}' } }).error === 'bad token');
  check('token via ?token=', doPost({ postData: { contents: '{"action":"ping"}' }, parameter: { token: 't0k' } }).ok);
  const r1 = post({ action: 'log', receipt, image_base64: img('a'), mime: 'image/jpeg' });
  check('first log', r1.ok && r1.receipt_id === 'Tax26-27-0001' && r1.financial_year === 'Tax26-27', r1);
  const year = root.getFoldersByName('Taxes').next().getFoldersByName('Tax26-27').next();
  check('photo filed under Taxes/Tax26-27', year.kids.some(k => k.name.startsWith('2026-11-14_Northside-Tech-Supplies_179.00_Tax26-27-0001')), year.kids.map(k => k.name));
  check('folder shared with accountant', year.getViewers()[0].getEmail() === 'acc@example.com');
  check('same image is a duplicate', post({ action: 'log', receipt, image_base64: img('a') }).duplicates[0].why === 'same image');
  check('same supplier/date/total is a duplicate', post({ action: 'log', receipt, image_base64: img('b') }).duplicates[0].why === 'same supplier, date and total');
  check('check writes nothing', post({ action: 'check', receipt, image_base64: img('b') }).duplicates.length === 1 && post({ action: 'list' , fy: 'Tax26-27'}).rows.length === 1);
  check('force logs #2', post({ action: 'log', receipt, image_base64: img('b'), force: true }).receipt_id === 'Tax26-27-0002');
  check('client-supplied fy wins', post({ action: 'log', receipt: { ...receipt, supplier: 'X' }, fy: 'Custom', image_base64: img('c') }).receipt_id === 'Custom-0001');
  const n1 = post({ action: 'log', receipt: { ...receipt, supplier: 'NoPhoto1', total: 1 } });
  const n2 = post({ action: 'log', receipt: { ...receipt, supplier: 'NoPhoto2', total: 2 } });
  check('no photo logs with warning, no false duplicate', n1.ok && n2.ok && /photo not received/.test(n1.warnings[0]), [n1, n2]);
  const a = post({ action: 'answer', receipt_id: 'Tax26-27-0001', work_use_pct: 60, claimable: '107.40', notes: 'ok' });
  const l = post({ action: 'list', fy: 'Tax26-27' });
  check('answer then list', a.ok && l.rows[0].status === 'Answered', [a, l]);
  check('missing fields rejected', /missing/.test(post({ action: 'log', receipt: { date: '2026-11-14' } }).error));
}
{
  const uk = load({ TOKEN: 't', FY_START: '04-06', FY_LABEL: '{YYYY}-{yy2}' });
  check('UK year starts 6 April', uk.fyLabel(new Date(2027, 3, 5)) === '2026-27' && uk.fyLabel(new Date(2027, 3, 6)) === '2027-28');
  const us = load({ TOKEN: 't', FY_START: '01-01', FY_LABEL: 'Tax{YYYY}' });
  check('calendar year', us.fyLabel(new Date(2026, 11, 31)) === 'Tax2026' && us.fyLabel(new Date(2027, 0, 1)) === 'Tax2027');
}

console.log(failed ? `${failed} failed` : 'all passed');
process.exit(failed ? 1 : 0);
