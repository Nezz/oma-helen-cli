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

- **`helenservice/helen_session.py` — `HelenSession`**: Handles the multi-step OAuth/form-based login to `login.helen.fi`. Follows HTML form redirects (BeautifulSoup), extracts `access-token` cookie, and stores it in a `requests.Session`. This is the most fragile layer — it scrapes HTML forms and can break when Helen changes their login flow.

- **`helenservice/api_client.py` — `HelenApiClient`**: Main API wrapper. Uses the `access-token` from `HelenSession` as a Bearer token for REST calls to `api.omahelen.fi/v25` and `v26`. Maintains selected contract state (`_selected_contract`, `_selected_delivery_site_id`) and uses `cachetools.TTLCache` (1-hour TTL) for expensive GET requests. Also contains calculation logic for costs and impact-of-usage.

- **`helenservice/price_client.py` — `HelenPriceClient`**: Scrapes market prices and exchange electricity margin from public Helen.fi product pages (no auth required). Results are cached in-memory with a 1-hour TTL via timestamp check.

- **`helenservice/api_response.py`**: Plain Python classes (`MeasurementsWithSpotPriceResponse`, `SpotPriceChartResponse`) that wrap API JSON responses. `**_` in constructors silently ignores unknown fields for forward-compatibility.

- **`helenservice/cli.py` — `HelenCLIPrompt`**: Extends Python's `cmd.Cmd`. Each `do_*` method is a CLI command. JSON output uses `_json_serializer` for `date`/`datetime` objects and dataclass-style objects.

### Key Design Details

**Contract selection**: On login, `HelenApiClient` fetches all contracts and auto-selects the most recently started active contract. Users can override via `select_delivery_site`. The `_selected_contract` dict drives which GSRN is used in measurement API calls.

**Electricity transfer contracts**: When a contract's `domain == "electricity-transfer"`, the measurements API uses channel `"osv"` instead of `"oh"`. The `MeasurementsWithSpotPriceSeries` class normalizes this: it uses `electricity_transfer` value when `electricity` is `None`.

**Time zone handling**: The Oma Helen API uses Helsinki local midnight as interval boundaries. `_get_utc_time_range()` converts date ranges to UTC using `ZoneInfo("Europe/Helsinki")` — midnight Helsinki → 21:00 or 22:00 UTC of the previous day depending on DST.

**API versioning**: Most endpoints use v25, but chart-data (measurements) uses v26. The `HELEN_API_URL_V25/V26` constants on `HelenApiClient` track this.

### Test Structure

Tests in `tests/` use `pytest` with `unittest.mock`. Fixtures in `test_api_client.py` set up a `HelenApiClient` with a mocked session. JSON fixtures in `tests/resources/` represent real API response shapes used by tests.
