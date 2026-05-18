# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`oma-helen-cli` is a Python library and interactive CLI for the [Oma Helen](https://www.helen.fi/kirjautuminen) user portal — a Finnish electricity company's customer portal. It authenticates via a multi-step web login flow and exposes electricity contract data, consumption measurements, and price calculations.

## Development Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```sh
uv sync                    # Install runtime dependencies
uv sync --extra test       # Install with test dependencies
uv run oma-helen-cli       # Run the CLI (prompts for credentials)
uv run oma-helen-cli --debug    # Enable DEBUG logging
uv run oma-helen-cli --verbose  # Enable INFO logging
```

Credentials can also be passed via environment variables to skip prompts:
```sh
HELEN_USERNAME=... HELEN_PASSWORD=... uv run oma-helen-cli
```

## Testing

```sh
uv run pytest                              # Run all tests
uv run pytest tests/test_api_client.py     # Run a specific file
uv run pytest tests/test_api_client.py -v  # Verbose output
uv run pytest -k test_name                 # Run a single test by name
```

## Linting

```sh
uv run ruff check .        # Lint
uv run ruff format .       # Format
uv run ruff check --fix .  # Auto-fix lint issues
```

Ruff is configured in `pyproject.toml` with rules: E, F, I (isort), B (bugbear), UP (pyupgrade). Line length is 120.

## Architecture

### Module Responsibilities

- **`helenservice/helen_session.py` — `HelenSession`**: Ubisecure OAuth login and cookie-based session renewal. Most fragile layer — scrapes HTML forms that can break when Helen changes their login UI.
- **`helenservice/api_client.py` — `HelenApiClient`**: Bearer-token REST client for `api.omahelen.fi/v25` and `v26`. `login_and_init()` tries cookie-based renewal first, falls back to full login; `close()` saves cookies for the next renewal attempt. Uses `cachetools.TTLCache` (1-hour TTL) for expensive GETs. Also contains cost/impact calculation logic.
- **`helenservice/price_client.py` — `HelenPriceClient`**: Scrapes market prices from public Helen.fi pages (no auth). 1-hour in-memory TTL cache.
- **`helenservice/api_response.py`**: Response wrapper classes; `**_` in constructors silently drops unknown fields for forward-compatibility.
- **`helenservice/cli.py` — `HelenCLIPrompt`**: `cmd.Cmd` subclass; one `do_*` method per CLI command.

### Key Design Details

**Login flow (5 steps via `login.helen.fi` / Ubisecure):**
1. POST auth endpoint → scrape login-form URL from response HTML
2. POST credentials → response contains OAuth `code` + `state` hidden form
3. GET `www.helen.fi/continue?code&state` → page with a `<a href>` link
4. GET the link (`_fix_url` normalises stale API version and legacy domain) → second code+state form
5. GET code exchange → `access-token` cookie set at `.oma.helen.fi`

**Session renewal:** `close()` saves all cookies (including `JSESSIONID` at `login.helen.fi`) via `get_all_cookies()`. The next `login_and_init()` calls `refresh()`, which replays them all against `HELEN_SESSION_RENEWAL_URL`. When `JSESSIONID` is still alive server-side (~1–2 h of inactivity), Ubisecure returns an "Access granted" page with an auto-submit JS form containing a new OAuth `code`. `refresh()` submits it manually (requests doesn't run JS). If `JSESSIONID` has expired, the page is a login form (no `code` input) → `refresh()` returns `False` → fall back to full credential login.

**Two OAuth `client_id`s:** full login uses `239967c8-c1b3-4786-9cc9-035b181bfa75`; renewal uses `7cde929b-a93b-4bea-985e-6782994d4114` (the Oma Helen web client registered at `api.oma.helen.fi/v20/`).

**Contract selection:** On login, `HelenApiClient` auto-selects the most recently started active contract. Override via `select_delivery_site`. `_selected_contract` drives which GSRN is used in measurement calls.

**Electricity transfer contracts:** `domain == "electricity-transfer"` → channel `"osv"` instead of `"oh"`. `MeasurementsWithSpotPriceSeries` normalises this by falling back to `electricity_transfer` when `electricity` is `None`.

**Time zone handling:** API uses Helsinki local midnight as boundaries. `_get_utc_time_range()` converts via `ZoneInfo("Europe/Helsinki")` → 21:00Z or 22:00Z of the previous UTC day depending on DST.

**API versioning:** Most endpoints use v25; chart-data (measurements) uses v26.

### Test Structure

- `tests/test_helen_session.py` — `HelenSession`: login flow (5-step mock), cookie renewal (code-exchange path), `is_token_valid()`, HTML helper edge cases
- `tests/test_api_client.py` — `HelenApiClient`: measurement/contract endpoints, HTTP error handling, transfer channel, cookie save/restore
- `tests/resources/` — JSON fixtures representing real API response shapes
