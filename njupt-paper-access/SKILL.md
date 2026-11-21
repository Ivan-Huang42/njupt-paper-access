---
name: njupt-paper-access
description: Find scholarly papers, open authorized publisher pages through Nanjing University of Posts and Telecommunications (NJUPT) WebVPN, and archive PDFs the user is entitled to download. Use for NJUPT full-text access, IEEE Xplore, Elsevier, Springer, ACM, Wiley, CNKI, Wanfang, or WebVPN login and download assistance. Do not use to share accounts, bypass access controls, or bulk-harvest licensed databases.
---

# NJUPT Paper Access

Use the bundled helper for repeatable metadata discovery, licensed backend
requests, open-access collection, and a reviewable manual queue. The helper
uses standard Python libraries only.

Prerequisites are Python 3.10+, Chrome or Edge, an active NJUPT account with the
needed entitlement, and either the campus network or a working NJUPT WebVPN
session.

Another NJUPT student can extract the portable skill package and run
`scripts/install.ps1` once. It installs under `%USERPROFILE%\.agents\skills`
and creates the Codex junction under `%USERPROFILE%\.codex\skills`.

## Required workflow

1. Run `scripts/njupt-paper.ps1 doctor` to show the private data paths,
   publisher connectivity, and whether optional official TDM credentials exist.
2. For discovery, run `collect` or `batch --query`. Prefer a formal publisher
   record and do not substitute an arXiv preprint for the published version.
3. Use `download` only for one explicitly selected paper. It resolves the DOI,
   detects the publisher, tries a stable backend or official API endpoint, and
   writes a PDF only after checking the `%PDF-` signature.
4. Use `batch` for open-access records and official TDM/API-enabled content.
   Publisher records that require a personal browser session are written to
   `manifest.json` with `manual_required` rather than downloaded automatically.
5. For manual records, launch the dedicated browser and let the user use the
   publisher's download control. `watch` validates and archives the resulting
   PDF. Never claim success until the PDF exists locally and opens.
6. Report saved paths, platform, source endpoint, and every deferred item.

Read [references/platform-workflows.md](references/platform-workflows.md) when
selecting the route for IEEE Xplore, Elsevier, Springer, ACM, Wiley, CNKI,
Wanfang, the NJUPT library portal, or a failed WebVPN handoff.

Read [references/backend-routes.md](references/backend-routes.md) before
implementing or extending a direct publisher connector.

## Commands

Windows PowerShell examples:

```powershell
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" doctor
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" collect "graph neural networks for recommendation" --limit 20 --output results.json
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" download 10.1109/TNNLS.2025.3582909 --output-dir ".\papers\single"
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" batch --input results.json --output-dir ".\papers\batch" --rate-limit 5
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" batch --query "safe control barrier functions" --limit 20 --output-dir ".\papers\safe-control"
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" login
& "$HOME\.agents\skills\njupt-paper-access\scripts\njupt-paper.ps1" watch --output ".\papers\gnn-recommendation"
```

Use `--help` on any subcommand. Set `NJUPT_PAPER_CONTACT_EMAIL` to a real
contact address for OpenAlex's polite pool. Set `NJUPT_PAPER_HOME` only when a
non-default private data directory is required.

Official API credentials are optional and read only from environment or an
operating-system secret store outside this skill:

- `ELSEVIER_API_KEY` and, when issued, `ELSEVIER_INST_TOKEN`.
- `WILEY_TDM_TOKEN`.

Do not attempt to substitute browser cookies for a missing official API grant.

## Non-negotiable boundaries

- Use only the user's own NJUPT account and only content covered by their
  current entitlement.
- Do not copy one student's browser profile or encrypted session to another
  person. Each student authenticates independently.
- Do not automate password entry, CAPTCHA solving, paywall avoidance, DRM
  removal, or bulk crawling of licensed databases.
- Do not use browser-session cookies to bypass Cloudflare or another anti-bot
  control on ACM, Wiley, Taylor & Francis, Science, ACS, or similar platforms.
- Do not describe `batch` as a licensed full-text downloader. It downloads only
  open-access copies and content covered by an official TDM/API entitlement;
  everything else remains an explicit manual action.
- Do not place credentials in the skill folder, repository, prompt, shell
  history, output log, or shared cloud storage.
- Keep the helper's dedicated browser profile and downloads directory private
  to the current operating-system user.
- Respect publisher terms and reasonable request limits. Use one paper at a
  time unless the user has an explicitly permitted bulk-export workflow.
