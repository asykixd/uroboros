# Security policy

Uroboros has access to a Telegram account, so vulnerabilities here are especially dangerous.

## Reporting

**Don't open a public issue.** Report privately via
[GitHub Security Advisories](https://github.com/asykixd/uroboros/security/advisories/new): what can be done, how to
reproduce it, and the version (`.info`).

Of particular interest:

- running a command as another Telegram user without granted access;
- reaching the web login panel without the tokenized link;
- a third-party module bypassing the install scan or runtime protection (session, `config.json`, dangerous
  requests). It's a heuristic, not a sandbox, but bypasses get fixed;
- tampering with a module during download or update.

## Supported versions

Fixes ship for the latest version on `master`.
