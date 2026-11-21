# Security Policy

## Sensitive data

Never commit or share:

- NJUPT usernames or passwords
- Browser cookies, `storage_state.json`, or browser profiles
- Elsevier API keys or institutional tokens
- Wiley TDM tokens
- Downloaded licensed PDFs

API credentials belong in environment variables or the operating system's
credential store. Browser sessions belong in the private directory under the
current Windows profile.

## Reporting

If you discover a credential leak or access-control issue, do not open a public
issue containing the secret. Revoke the exposed credential first, then contact
the repository owner with a minimal reproduction that contains no secret.

## Expected behavior

The project must not:

- automate CAPTCHAs, Cloudflare challenges, MFA, or password entry;
- bypass paywalls or DRM;
- copy one user's browser session to another;
- run unattended downloads against licensed databases without official
  TDM/API permission.
