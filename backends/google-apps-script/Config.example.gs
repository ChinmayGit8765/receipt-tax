// Copy this file to Config.gs (or paste it as a second file in the Apps Script editor) and fill it in.
// Never commit Config.gs: the token is the only thing protecting your web app.
var CONFIG = {
  TOKEN: 'CHANGE-ME-to-a-long-random-string',  // e.g. python -c "import secrets;print(secrets.token_urlsafe(32))"
  PARENT_FOLDER: 'Taxes',        // top-level Drive folder; each tax year gets a subfolder
  FY_START: '07-01',             // MM-DD. AU 07-01, NZ 04-01, UK 04-06, IN 04-01, US/CA 01-01
  FY_LABEL: 'Tax{yy}-{yy2}',     // tokens {YYYY} {yy} {YYYY2} {yy2}. Calendar years: 'Tax{YYYY}'
  CURRENCY: 'AUD',
  ACCOUNTANT_EMAIL: ''           // optional: gets view access to each year folder so links open for them
};
