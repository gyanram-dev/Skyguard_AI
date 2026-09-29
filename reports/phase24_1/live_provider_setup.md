# Live provider setup (Phase 24.1)

The configured adapter is the official IMD WIS2 OGC API at
`https://wis2box.imd.gov.in/oapi`. Its published collection API does not
document API-key, bearer-token, or client-secret authentication; this setup
therefore does not invent credential variables. Configure the provider URL
and, only when required by deployment trust, a PEM CA bundle. TLS verification
is always enabled.

1. Copy `Backend/.env.example` to a deployment-managed `.env` file outside Git.
2. Set `LIVE_SOURCE_MODE=LIVE_IMD`, `LIVE_PROVIDER=IMD_WIS2`, and
    `IMD_BASE_URL` to the authorized endpoint. Set `IMD_CA_BUNDLE` only when a
    provider-issued CA chain is needed.
3. If a protected provider documents header authentication, set
   `IMD_REQUEST_HEADERS` to a JSON object of its required headers, such as an
   `Authorization` or API-key header. For documented mutual TLS, set
   `IMD_CLIENT_CERT` and `IMD_CLIENT_KEY`. These values are optional, are not
   required by public WIS2, and must come from the provider's contract.
4. Start the backend with `python -m src.api.run` from `Backend/`; the entry
   point loads `.env` (or `SKYGUARD_ENV_FILE`) before app initialization.
5. Start ingestion from the Live page or `POST /api/v1/live/start`.
6. The adapter contacts the WIS2 station-observation collection. An empty
    result is still a successful connection; credentials alone never imply
    `CONNECTED`.
7. The adapter normalizes WIS2 fields to canonical observations. The existing
    data-quality, causal history, inference, spatial context, alert episode,
    and SQLite persistence flow then runs without provider fields downstream.
8. Check `/api/v1/live/status`: `NOT_CONFIGURED` means required endpoint
   configuration is absent; `CONFIGURED` means the endpoint is set but no
   successful heartbeat has completed; `CONNECTION_FAILED` means a configured
   request failed; `CONNECTED` is reported only after a successful provider
   response.

If IMD later supplies a protected endpoint, follow its published auth contract.
No secret is currently required by the public WIS2 OGC API. Provider auth
headers and client-certificate paths are never included in logs, structured
errors, or API status. `IMD_ARG` remains a separate contract-only adapter
until IMD publishes an authorized endpoint/schema.
