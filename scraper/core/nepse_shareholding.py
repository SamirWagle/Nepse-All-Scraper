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

  MEN — NEPSE says 80% promoter with no conversion statement in any annual
  report, but the company confirmed by phone (2026-08-10) that it is 100%
  public. A private hydro promoter has no reason to stay locked in an
  illiquid stake once free to convert — MEN just never bothered writing it
  down. This is the HYDRO RULE below, not the annual-report registry.

Conversion is per-company and NEPSE cannot tell you which happened from its
own field. The tiebreaker, in order:

  1. An annual report's explicit Nepali lock-in/conversion sentence in the
     introduction (see promoter_conversions.json) — hard evidence, wins.
     Do NOT rely on the audited-accounts phrase "The Company has a single
     class of equity shares"; that is an NFRS rights disclosure and appears
     whether or not conversion happened.
  2. HYDRO RULE (hydro sector only): once listing + 3yr lock-in has expired
     and no annual report documents conversion, assume 100% public anyway —
     UNLESS NEA is a promoter (see nea_promoter_hydro.json), in which case
     the reported stake is left as-is until a source expressly says
     otherwise. A state promoter does not exit like a private one does.
  3. Everything else (non-hydro, or hydro still locked): report NEPSE's
     allotment plainly as unverified current ownership.

promoter_pct_source records which of the three fired: "annual_report",
"lockin_expired_hydro", or "nepse_allotment".

float_pct is a separate, older mechanism (compute_float_pct) that still
applies the lock-in-expiry assumption broadly across ALL non-BFI sectors,
not just hydro — kept for backward compatibility, but promoter_pct/
public_pct/promoter_pct_source above are the fields to trust for hydro.

float_pct is a LEGAL-TRADABILITY claim, not a LIQUIDITY one, and the two
diverge badly:

  UNL — Manufacturing, ~80% held by its multinational parent. Unlocked, so
  float_pct=100, but one hand holds 80% permanently and it never trades.

  MEN — 80% NEPSE-reported promoter, but never a block: ~1000+ dispersed
  holders from a merger roll-up, no holder ever above 4.17%. Disclosed >1%
  holdings fell 38.73% (FY2079/80) -> 20.25% (Ashad 2082) across the unlock.
  Genuinely dispersing, though some of that is repackaging into holding
  vehicles (Leverage 1.44% -> 2.84%, plus Shreevridhi/Shreeniwas/Sajan
  Sharma at ~5.1% combined) rather than true exit.

For actual control (who holds what, are promoters exiting), neither field
is enough: read the annual report's Significant Shareholders table and the
board composition.
"""
import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PROMOTER_LOCKIN_YEARS = 3

CONVERSIONS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "promoter_conversions.json"
NEA_PROMOTER_HYDRO_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "nea_promoter_hydro.json"
HYDRO_REGULATOR = "Nepal Hydropower Board"

_client = None
_conversions = None
_nea_promoter_hydro = None


def load_promoter_conversions():
    """Tickers whose promoter->ordinary conversion was verified in an annual report.

    NEPSE never updates promoterPercentage on conversion, so this hand-curated
    file is the only way to correct it. Missing/broken file means "nothing
    verified" — the scraper still works, it just reports NEPSE's allotment.
    """
    global _conversions
    if _conversions is None:
        try:
            _conversions = json.loads(CONVERSIONS_PATH.read_text()).get("conversions", {})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("promoter conversions unreadable (%s): %s", CONVERSIONS_PATH, exc)
            _conversions = {}
    return _conversions


def load_nea_promoter_hydro():
    """Hydro tickers where NEA is a promoter — excluded from the hard 100%-public override.

    Missing/broken file means "none known" — every hydro ticker with an
    expired lock-in and no conversion note gets the override, per the rule.
    """
    global _nea_promoter_hydro
    if _nea_promoter_hydro is None:
        try:
            _nea_promoter_hydro = set(json.loads(NEA_PROMOTER_HYDRO_PATH.read_text()).get("tickers", {}))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("NEA promoter hydro list unreadable (%s): %s", NEA_PROMOTER_HYDRO_PATH, exc)
            _nea_promoter_hydro = set()
    return _nea_promoter_hydro


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

    # NEPSE reports the ORIGINAL allotment forever. Where an annual report has
    # been read and conversion confirmed, correct it. Otherwise, for hydro
    # only: once the lock-in has expired and NEA is not a promoter, hard-note
    # 100% public — no private promoter has reason to stay locked in an
    # illiquid stake once free to convert. NEA is a state promoter and does
    # not behave that way, so it keeps its reported stake unless a source
    # expressly says otherwise. Every other case reports NEPSE's allotment
    # plainly, as unverified current ownership.
    symbol_upper = symbol.upper()
    conversion = load_promoter_conversions().get(symbol_upper, {})
    is_hydro = regulatory_body == HYDRO_REGULATOR
    if conversion.get("converted"):
        total_shares = (result.get("promoter_shares") or 0) + (result.get("public_shares") or 0)
        result = {
            **result,
            "promoter_pct": 0.0,
            "public_pct": 100.0,
            "promoter_shares": 0,
            "public_shares": total_shares or result.get("public_shares"),
            "promoter_pct_source": "annual_report",
        }
    elif is_hydro and result.get("lockin_expired") and symbol_upper not in load_nea_promoter_hydro():
        total_shares = (result.get("promoter_shares") or 0) + (result.get("public_shares") or 0)
        result = {
            **result,
            "promoter_pct": 0.0,
            "public_pct": 100.0,
            "promoter_shares": 0,
            "public_shares": total_shares or result.get("public_shares"),
            "promoter_pct_source": "lockin_expired_hydro",
        }
    else:
        result["promoter_pct_source"] = "nepse_allotment"

    if is_hydro:
        # The hydro rule above already resolved public_pct correctly (including
        # the NEA carve-out) — mirror it directly instead of re-deriving float
        # via the legacy calc below, which doesn't know about NEA and would
        # wrongly report 100% float for a real state promoter stake (CHCL).
        float_pct = result.get("public_pct")
        # Only the hard-noted lock-in-expiry branch is an assumption. Both
        # "annual_report" (observed conversion) and "nepse_allotment" (raw
        # NEPSE figure, e.g. CHCL's real 49% with NEA still locked in) are
        # as-reported, not derived — flag neither as assumed.
        float_pct_is_assumed = result.get("promoter_pct_source") == "lockin_expired_hydro"
    else:
        float_pct = compute_float_pct(
            result.get("public_pct"),
            result.get("lockin_expired"),
            needs_regulator_approval(regulatory_body),
        )
        # True when float_pct came from "lock-in expired" rather than an
        # observed conversion, so downstream code can tell the assumption
        # apart from a fact. Verifying it means reading the annual report.
        float_pct_is_assumed = float_pct != result.get("public_pct") if float_pct is not None else None

    if float_pct is not None:
        result["float_pct"] = float_pct
        result["float_pct_is_assumed"] = float_pct_is_assumed

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
    # API's conversion is documented in its annual reports; MEN's is not.
    conversions = load_promoter_conversions()
    assert conversions.get("API", {}).get("converted") is True
    assert "MEN" not in conversions
    # NEA promoter hydro list: CHCL keeps its reported stake, MEN gets no carve-out.
    nea_hydro = load_nea_promoter_hydro()
    assert "CHCL" in nea_hydro
    assert "MEN" not in nea_hydro
    print("nepse_shareholding self-check OK")


if __name__ == "__main__":
    _self_check()
