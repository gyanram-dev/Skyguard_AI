"""Bounded OGC API client for the official IMD wis2box service.

TLS verifies against the caller's CA bundle (stock certifi lacks the
CCA-India/emSign chain, so deployments must provide it, e.g. via the
IMD_CA_BUNDLE environment variable). Every failure mode maps to a
structured IMDWIS2Error: timeout, connection, HTTP status, malformed
payload, empty result, rate limiting (429). No stack traces escape.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("skyguard.imd_wis2")

DEFAULT_BASE_URL = "https://wis2box.imd.gov.in/oapi"
DEFAULT_TIMEOUT_S = 30
MAX_LIMIT = 1000

SYNOP_COLLECTION = "urn:wmo:md:in-imd:surface-based-observations.synop"
STATIONS_COLLECTION = "stations"


class IMDWIS2Error(Exception):
    """Structured adapter failure (code, detail)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _request(url: str, params: dict, ca_bundle: str | None,
             timeout_s: int, headers: dict[str, str] | None = None,
             client_cert: str | None = None,
             client_key: str | None = None) -> dict:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}" if query else url
    request_headers = {"Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(full, headers=request_headers)
    try:
        import ssl

        context = ssl.create_default_context(cafile=ca_bundle)
        if client_cert:
            context.load_cert_chain(client_cert, keyfile=client_key)
        with urllib.request.urlopen(req, timeout=timeout_s,
                                    context=context) as response:
            try:
                return json.load(response)
            except ValueError:
                raise IMDWIS2Error("malformed_response",
                                   "IMD API returned non-JSON content.") from None
    except IMDWIS2Error:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise IMDWIS2Error("rate_limited",
                               "IMD API rate limit hit; retry later.") from None
        raise IMDWIS2Error("http_error",
                           f"IMD API HTTP {exc.code}.") from None
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if "timed out" in reason.lower():
            raise IMDWIS2Error("timeout", "IMD API request timed out.") from None
        raise IMDWIS2Error("connection_failed",
                           "IMD API unreachable.") from None
    except TimeoutError:
        raise IMDWIS2Error("timeout", "IMD API request timed out.") from None
    except Exception as exc:  # noqa: BLE001 - normalized, never leaked
        raise IMDWIS2Error("connection_failed",
                           f"IMD API request failed: {type(exc).__name__}.") from None


class IMDWIS2Client:
    """Small bounded client (station filter, limit, offset pagination)."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 ca_bundle: str | None = None,
                 timeout_s: int = DEFAULT_TIMEOUT_S,
                 headers: dict[str, str] | None = None,
                 client_cert: str | None = None,
                 client_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        # Stock certifi lacks the CCA-India/emSign chain; deployments
        # provide it via IMD_CA_BUNDLE (PEM bundle path).
        self.ca_bundle = ca_bundle or os.environ.get("IMD_CA_BUNDLE") or None
        self.timeout_s = timeout_s
        self.headers = dict(headers or {})
        self.client_cert = client_cert or os.environ.get("IMD_CLIENT_CERT") or None
        self.client_key = client_key or os.environ.get("IMD_CLIENT_KEY") or None

    def get_stations(self, limit: int = 1000, offset: int = 0) -> dict:
        """One raw station catalogue page."""
        self._check_page(limit, offset)
        return _request(f"{self.base_url}/collections/{STATIONS_COLLECTION}/items",
                        {"limit": limit, "offset": offset},
                        self.ca_bundle, self.timeout_s, self.headers,
                        self.client_cert, self.client_key)

    def get_observations(self, wigos_id: str, limit: int = 1000,
                         offset: int = 0) -> dict:
        """One raw SYNOP page for a station (bounded)."""
        if not isinstance(wigos_id, str) or not wigos_id.strip():
            raise IMDWIS2Error("invalid_station", "A WIGOS station ID is required.")
        self._check_page(limit, offset)
        return _request(
            f"{self.base_url}/collections/{SYNOP_COLLECTION}/items",
            {"wigos_station_identifier": wigos_id.strip(),
             "limit": limit, "offset": offset},
            self.ca_bundle, self.timeout_s, self.headers,
            self.client_cert, self.client_key)

    def iter_observations(self, wigos_id: str, max_records: int = 3000,
                          page_size: int = 1000):
        """Yield raw record pages up to max_records (bounded, stops early)."""
        if max_records < 1:
            raise IMDWIS2Error("invalid_limit", "max_records must be positive.")
        fetched = 0
        offset = 0
        while fetched < max_records:
            requested = min(page_size, max_records - fetched)
            page = self.get_observations(wigos_id, limit=requested, offset=offset)
            features = page.get("features", [])
            if not features:
                return
            yield features
            fetched += len(features)
            offset += len(features)
            if len(features) < requested:
                return

    @staticmethod
    def _check_page(limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) \
                or not 1 <= limit <= MAX_LIMIT:
            raise IMDWIS2Error("invalid_limit",
                               f"limit must be 1..{MAX_LIMIT}.")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise IMDWIS2Error("invalid_limit", "offset must be >= 0.")
