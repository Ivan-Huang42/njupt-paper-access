# Publisher and Platform Routing

The target is a verified local PDF, not merely a successful login. Discovery
metadata can come from public APIs; licensed full text must come through the
user's current NJUPT entitlement.

## Common route

1. Resolve the title/DOI to the formal publisher record.
2. Start NJUPT WebVPN in the helper's persistent browser profile.
3. Open the publisher landing page and confirm that the page identifies NJUPT
   access, institution access, or an entitled subscription.
4. Download one PDF from the publisher page and place it in the helper's
   download directory.
5. Verify the resulting file begins with `%PDF-` and is not an HTML login page
   with a `.pdf` suffix.

## Platform specifics

### IEEE Xplore

Use the formal article page and its publisher-provided **PDF** control. When
direct DOI resolution leaves the paywall in place, return to the NJUPT WebVPN
portal and open the IEEE resource from the school resource list. Conference and
early-access papers can have different entitlements.

### Elsevier ScienceDirect

Use the article's formal ScienceDirect page. Open-access articles may show
**Download full issue/article**; subscribed articles normally show an
institutional-access label. Prefer the publisher PDF endpoint presented by the
page and reject preview images or HTML fallback pages.

### SpringerLink

Use the article page's **Download PDF** or **Access this chapter** control.
Book chapters and journal articles may have different entitlements. Many older
conference papers have no PDF even when the metadata record exists.

### ACM Digital Library

Use the article landing page's **PDF** control. If a DOI redirects to a
non-entitled view, navigate through the NJUPT WebVPN resource link. Access to
OpenTOC or conference proceedings can vary by year.

### Wiley Online Library

Use the article page's **PDF** download. Confirm the institution indicator or
entitlement before downloading. Never treat an abstract-only page as success.

### CNKI and Wanfang

Use the NJUPT library resource list, then search the CNKI or Wanfang title or
DOI page. Download one item at a time in PDF or CAJ format when the user's
entitlement permits it. This helper verifies PDF files only; if only CAJ is
available, report the path and ask the user which CAJ converter to use.

### NJUPT library discovery

When a DOI route fails, search the title in the library's journal/database
discovery interface and follow the record's publisher or full-text link. Keep
the linked publisher page as the evidence URL; do not invent direct PDF URLs.

## Failure handling

- Login page still visible: wait for human authentication. Do not try alternate
  credentials or automate the verification step.
- Publisher asks for payment: the school subscription probably does not cover
  that item or year. Record this explicitly.
- WebVPN shows an error or empty resource list: report the exact platform and
  page state. The school portal may require reauthentication or maintenance.
- Download is HTML, `.crdownload`, zero bytes, or an access-denied page: do not
  archive it as a paper.
- CAPTCHA, MFA, or anti-bot check: leave it to the user and continue only after
  they complete it.

## Sharing the skill

The complete skill folder contains no account-specific data and can be copied
to another NJUPT student's skill directory. They must create their own browser
profile and authenticate with their own account.

The portable source folder is `%USERPROFILE%\.agents\skills\njupt-paper-access`.
On this machine, `%USERPROFILE%\.codex\skills\njupt-paper-access` is a junction
to the same folder, so Codex and harnesses that scan `~/.agents/skills` see one
maintained package.

After extracting the shared ZIP on another student's computer, run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\njupt-paper-access\scripts\install.ps1
```

The installer copies no credentials or browser sessions.
