"""Promoter/public shareholding via NEPSE's own API.

Two DIFFERENT questions live in this data. Keep them apart:

  promoter_pct  — the ORIGINAL ALLOTMENT ratio. A control proxy, not float.
  float_pct     — how much stock can actually trade today.

ShareHubNepal's promoterShares field is unusable: confirmed 0 for every
hydropower company tested, including Chilime (CHCL), which NEA
majority-owns (real figure: 51% promoter). It is a null field, not data —
its "float market cap" always equals total market cap. NEPSE's own API
(nepalstock.com.np, via the `nepse` package, which handles the site's
scrambled auth-token handshake) is the better source for promoter_pct.

But NEPSE's promoter_pct is NOT current ownership. It does not update when
a company converts promoter shares to ordinary, so it reports the original
allotment indefinitely:

  API Power — NEPSE says 58% promoter. Its 20th/21st/22nd Annual Reports
  state that since Kartik 23, 2075 the lock-in ended, promoter-group shares
  now trade as ordinary, and only one share group remains. API is 100%
  public; NEPSE's 58% is the stale 60/10/30 allotment.

  MEN — NEPSE says 80% promoter, and the annual reports agree: the 80/20
  split is preserved through every bonus issue, with no conversion
  statement anywhere. Here 80% is real.

Conversion is per-company and NEPSE cannot tell you which happened. The
tiebreaker is the company's own annual report — look for the explicit
Nepali lock-in/conversion sentence in the introduction. Do NOT rely on the
audited-accounts phrase "The Company has a single class of equity shares";
that is an NFRS rights disclosure and appears in BOTH API's and MEN's
reports regardless of conversion.

float_pct applies the rule that outside banking/insurance promoter shares
become tradable once the 3yr lock-in expires. promoter_pct is deliberately
never overwritten — that is what keeps NEA's 51% at Chilime intact without
needing a carve-out list of state-owned companies.

float_pct IS AN ASSUMPTION, NOT AN OBSERVATION. Sources conflict on whether
conversion is automatic at expiry: one says promoter shares convert at the
three-year mark, another says the company must pass an AGM resolution, get
SEBON and NEPSE approval, then apply to CDSC — i.e. expiry only makes
conversion permissible. Our own data fits the second reading: MEN's lock
expired 2023-12-02 and NEPSE still classifies 80% as promoter 2.5 years
later, while API converted and documented it as an event. So float_pct=100
means "no regulatory lock remains", NOT "verified converted". Anything
derived this way is flagged float_pct_is_assumed=True — never screen on
float_pct as observed free float without checking that flag.

float_pct is a LEGAL-TRADABILITY claim, not a LIQUIDITY one, and the two
diverge badly:

  UNL — Manufacturing, ~80% held by its multinational parent. Unlocked, so
  float_pct=100, but one hand holds 80% permanently and it never trades.

  MEN — 80% promoter, but never a block: ~1000+ dispersed holders from a
  merger roll-up, no holder ever above 4.17%. Disclosed >1% holdings fell
  38.73% (FY2079/80) -> 20.25% (Ashad 2082) across the unlock. Genuinely
  dispersing, though some of that is repackaging into holding vehicles
  (Leverage 1.44% -> 2.84%, plus Shreevridhi/Shreeniwas/Sajan Sharma at
  ~5.1% combined) rather than true exit.

For actual control (who holds what, are promoters exiting), neither field
is enough: read the annual report's Significant Shareholders table and the
board composition.
"""
import logging
from datetime import date

logger = logging.getLogger(__name__)

PROMOTER_LOCKIN_YEARS = 3

_client = None


def _get_client():
    global _client
    if _client is None:
        import nepse
        _client = nepse.Nepse()
    return _client


def needs_regulator_approval(regulatory_body):
    """True for sectors where lock-in expiry does NOT free promoter shares.

    Banks and insurers need their regulator's approval to convert promoter
    shares to ordinary, so their float does not open on a fixed date the way
    a hydropower company's does. Keyed off the regulator rather than the
    sector name so new sub-sectors (development banks, microfinance,
    reinsurance) are covered without a list to maintain.
    """
    if not regulatory_body:
        return False
    body = regulatory_body.lower()
    return "rastra bank" in body or "insurance" in body or "beema" in body


def compute_float_pct(public_pct, lockin_expired, conversion_needs_approval=False):
    """Assumed tradable percentage once the lock-in has expired.

    Assumes no promoter remains locked, which is NOT verified — see the
    module docstring. Callers should pair this with float_pct_is_assumed.

    Returns None when there is nothing to base it on, so callers can tell
    "unknown" apart from a real 0.
    """
    if lockin_expired and not conversion_needs_approval:
        return 100.0
    return public_pct


def fetch_shareholding_nepse(symbol):
    """Return promoter/public shares + pct + float + paid-up capital from NEPSE. Empty dict on failure.

    lockin_expired: True once listing_date + PROMOTER_LOCKIN_YEARS has passed.
    float_pct: tradable %, derived from it. promoter_pct stays as NEPSE reports it
    (original allotment) — see module docstring for why it is never overwritten.
    """
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
    result = {out_key: details[src_key] for src_key, out_key in field_map.items() if details.get(src_key) is not None}

    listing_date_str = details.get("security", {}).get("listingDate")
    if listing_date_str:
        listing_date = date.fromisoformat(listing_date_str)
        lockin_end = listing_date.replace(year=listing_date.year + PROMOTER_LOCKIN_YEARS)
        result["listing_date"] = listing_date_str
        result["lockin_expired"] = date.today() >= lockin_end

    sector = details.get("security", {}).get("companyId", {}).get("sectorMaster") or {}
    regulatory_body = sector.get("regulatoryBody")
    if regulatory_body:
        result["regulatory_body"] = regulatory_body

    float_pct = compute_float_pct(
        result.get("public_pct"),
        result.get("lockin_expired"),
        needs_regulator_approval(regulatory_body),
    )
    if float_pct is not None:
        result["float_pct"] = float_pct
        # True when float_pct came from "lock-in expired" rather than an
        # observed conversion, so downstream code can tell the assumption
        # apart from a fact. Verifying it means reading the annual report.
        result["float_pct_is_assumed"] = float_pct != result.get("public_pct")

    return result


def _self_check():
    # MEN: lock-in expired 2023-12-02, promoters still classified at 80% -> all tradable.
    assert compute_float_pct(20.0, True) == 100.0
    # CHCL: NEA's 51% must not leak into float, but the stock still trades freely.
    assert compute_float_pct(49.0, True) == 100.0
    # Still locked: only the public tranche trades.
    assert compute_float_pct(20.0, False) == 20.0
    # No listing date -> lockin_expired is None -> unknown, not 0.
    assert compute_float_pct(None, None) is None
    # BFIs: the 3yr rule does not free their promoter shares, so lock-in
    # expiry must NOT open the float. NABIL-shaped input.
    assert compute_float_pct(41.56, True, True) == 41.56
    assert needs_regulator_approval("Nepal Rastra Bank") is True
    assert needs_regulator_approval("Nepal Insurance Authority") is True
    assert needs_regulator_approval("Securities Board of Nepal") is False
    assert needs_regulator_approval(None) is False
    # float_pct_is_assumed mirrors "did we move off public_pct?"
    assert (compute_float_pct(20.0, True) != 20.0) is True      # MEN: assumed
    assert (compute_float_pct(20.0, False) != 20.0) is False    # locked: observed
    assert (compute_float_pct(41.56, True, True) != 41.56) is False  # BFI: observed
    assert (compute_float_pct(100.0, True) != 100.0) is False   # already all public
    print("nepse_shareholding self-check OK")


if __name__ == "__main__":
    _self_check()
