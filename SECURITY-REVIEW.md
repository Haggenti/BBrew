# Security review

## Finding

| Severity | Location | Finding | Confidence | Status |
|---|---|---|---:|---|
| MEDIUM | `bbrew/settings.py`, session configuration | Authentication sessions used the persistent database session backend and browser cookies had no browser-close expiry. As a result, users could remain authenticated after closing the browser, and stored sessions remained valid after the application restarted. | 9/10 | Fixed |

## Impact

A browser retaining its session cookie could continue to use the account without
re-entering its password. Because session records are stored in the persistent
SQLite database, restarting the application did not by itself invalidate those
sessions.

## Remediation

- Enable browser-close expiry for the session cookie with
  `SESSION_EXPIRE_AT_BROWSER_CLOSE`.
- Invalidate persisted sessions when the local Django development server starts.
- Invalidate persisted sessions in the Docker entrypoint after migrations and
  before starting the application server.

The browser must be closed, rather than just a tab, to expire its session
cookie. A server restart also invalidates sessions even if the browser restores
its previous session cookie.
