# Backend Direct-Access Audit

Audit date: 2026-11-20. Test only from a network that has NJUPT's licensed
entitlement. HTTP status can change when the campus network or VPN client is not
active.

## NJUPT policy constraint

The library's database landing page states that readers may not use automatic
download programs to continuously search or download licensed database content.
Accordingly:

- A single DOI explicitly selected by the user may use a stable backend download
  route when the entitlement is active.
- Multi-record `batch` downloads are limited to open access and official
  TDM/API-enabled content.
- Paid records without an official API path are emitted as `manual_required`.
- CAPTCHA, Cloudflare, MFA, and access-control pages are never solved or
  bypassed.

## Verified routes

### IEEE Xplore

1. Resolve `https://doi.org/{doi}`. The IEEE redirect exposes
   `https://ieeexplore.ieee.org/document/{arnumber}`.
2. The stable PDF endpoint is
   `https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}`.
3. The endpoint returned `application/pdf` and a valid PDF in testing.

Use this for a single explicit paper or when the institution provides an
official IEEE API/TDM license. Do not run it as an unattended institutional
download loop.

### Springer Nature

Use `https://link.springer.com/content/pdf/{doi}.pdf`. A valid PDF was returned
in testing, including for a record OpenAlex marks as closed, when institutional
access was active. Use this for one explicit paper; use official licensing for
multi-record retrieval.

### Nature

The DOI landing page normally maps to
`https://www.nature.com/articles/{article-id}`. The corresponding
`{landing-page}.pdf` endpoint returned a valid PDF in testing.

### IOPscience

Use `https://iopscience.iop.org/article/{doi}/pdf`. A valid PDF was returned in
testing.

### Elsevier

- The DOI redirect exposes the PII through
  `linkinghub.elsevier.com/retrieve/pii/{PII}`.
- The standard ScienceDirect `pdfft` endpoint returned HTTP 403 without an
  authenticated browser or TDM grant.
- Official full-text route:
  `https://api.elsevier.com/content/article/doi/{doi}`
  with `X-ELS-APIKey`, `Accept: application/pdf`, and, if issued,
  `X-ELS-Insttoken`.
- Batch use requires the official API/insttoken entitlement. A campus IP alone
  does not authorize automated retrieval.

### Wiley

- Direct `pdfdirect` requests encountered Cloudflare HTTP 403 in testing.
- The supported route is the Wiley TDM API with a
  `Wiley-TDM-Client-Token` issued under an applicable agreement:
  `https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}`.
- Do not use a browser clearance cookie as a substitute for this token.

### ACM, Taylor & Francis, Science, and ACS

Direct landing/PDF requests returned Cloudflare or connection failures in
testing. Use an institutional TDM agreement or the publisher's normal website.
Do not attempt to bypass the challenge.

### SAGE

The DOI resolver in testing redirected through `sage.cnpereading.com`. Its
`/doi/pdf/{doi}` path returned an HTML page rather than a PDF. Use the normal
article download or an official arrangement.

### CNKI

`https://kns.cnki.net/` redirected to a block-puzzle verification page in
testing. There is no stable credential-free backend PDF route. Do not automate
the CAPTCHA; use the normal authenticated interface and ordinary institutional
use limits.

### Wanfang

The search frontend uses gRPC-web POST endpoints, including
`/SearchService.SearchService/search`, and the response carries NJUPT
institutional context. The API payloads are Protocol Buffers, and full-text
download is entitlement-gated. Do not build a continuous downloader from this
private web API; use the normal interface or an official export/API agreement.

## Public metadata and OA

Crossref and OpenAlex are suitable for metadata discovery. OpenAlex can provide
OA PDF or repository URLs. This skill skips arXiv, bioRxiv, and medRxiv links by
default and prefers the formal published version.
