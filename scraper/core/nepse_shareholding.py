"""Authoritative promoter/public shareholding via NEPSE's own API.

ShareHubNepal's promoterShares field is unreliable for entire sectors —
confirmed 0 for every hydropower company tested, including Chilime (CHCL),
which NEA majority-owns (real figure: 51% promoter). NEPSE's own API
(nepalstock.com.np, accessed via the `nepse` package, which handles the
site's scrambled auth-token handshake) gives the correct split, e.g.
MEN: 80% promoter / 20% public, not ShareHub's implied 0%/100%.
"""
import logging

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        import nepse
        _client = nepse.Nepse()
    return _client


def fetch_shareholding_nepse(symbol):
    """Return promoter/public shares + pct + paid-up capital from NEPSE. Empty dict on failure."""
    try:
        details = _get_client().getCompanyDetails(symbol)
    except Exception as exc:
        logger.warning("NEPSE shareholding fetch failed for %s: %s", symbol, exc)
        return {}

    field_map = {
        "promoterShares": "promoter_shares",
        "publicShares": "public_shares",
        "promoterPercentage": "promoter_pct",
        "publicPercentage": "public_pct",
        "paidUpCapital": "paid_up_capital",
    }
    return {out_key: details[src_key] for src_key, out_key in field_map.items() if details.get(src_key) is not None}
