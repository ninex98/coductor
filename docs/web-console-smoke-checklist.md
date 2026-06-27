# Web Console Smoke Checklist

Use this checklist after changing `coductor serve`, local console API routes, log
preview behavior, or run control actions.

## Start

1. Run `coductor serve --host 127.0.0.1 --port 8765`.
2. Open `http://127.0.0.1:8765`.
3. Confirm the page loads and the app shell shows runs without a browser console
   crash.

## Read Paths

1. Call `GET /api/health` and confirm it returns `ok: true`.
2. Call `GET /api/runs` and confirm recent runs are listed.
3. Open one run detail with `GET /api/runs/<run-id>`.
4. Open an artifact preview under `GET /api/runs/<run-id>/artifacts/...`.
5. Confirm path traversal, absolute paths, unsupported suffixes, and run
   directories outside `.coductor/runs/<run-id>` are rejected.

## Sensitive Output

1. Preview a log or artifact containing a sample secret such as
   `OPENAI_API_KEY=sk-test-secret`.
2. Confirm the browser/API response shows `OPENAI_API_KEY=[REDACTED]`.
3. Confirm `Authorization: Bearer token-value` becomes
   `Authorization: Bearer [REDACTED]`.

## Control Actions

1. Confirm `POST /api/runs/<run-id>/actions/<action>` fails without
   `X-Coductor-Token`.
2. Confirm the same request fails when `Origin` does not match `Host`.
3. Confirm a valid token can run an allowed action for the current run state.
4. Confirm a duplicate `run_id + action` request inside the short window returns
   `429`.
5. Confirm a different action for the same run is not blocked by the duplicate
   action window.

## Finish

1. Run `.venv/bin/pytest tests/integration/test_web_api.py tests/integration/test_web_controls.py tests/integration/test_web_console_smoke.py -q`.
2. Run `.venv/bin/ruff check .`.
3. Run `.venv/bin/mypy src`.
