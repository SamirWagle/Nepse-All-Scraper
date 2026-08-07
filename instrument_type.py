"""
Classify a NEPSE listing by instrument type.

ShareSansar's registry mixes ordinary shares with debentures, bonds, mutual
fund schemes and promoter shares. The analyser only deals in ordinary shares,
so search hides the rest. Classification is name-based: NEPSE symbols carry no
reliable instrument marker (SEF is a fund, SEOS is a company).
"""

import re

EQUITY = "equity"
DEBT = "debt"
MUTUAL_FUND = "mutual_fund"
PROMOTER_SHARE = "promoter_share"

_DEBT_RE = re.compile(r"\b(debenture|bond|rinpatra)\b", re.I)
_PROMOTER_RE = re.compile(r"\bpromoter\b", re.I)
_FUND_EXPLICIT_RE = re.compile(r"\b(mutual fund|retirement fund|provident fund)\b", re.I)
_FUND_WORD_RE = re.compile(r"\b(fund|yojana|sip)\b", re.I)

# A fund-management or investment *company* is ordinary equity ("Rajdhani
# Investment Fund Limited"); a scheme is not ("Nabil Growth Fund"). The
# corporate suffix is what separates them.
_CORPORATE_RE = re.compile(r"\b(limited|ltd|company|management)\b", re.I)

# company_names.json stores names as "Example Limited ( XYZ )".
_TRAILING_SYMBOL_RE = re.compile(r"\(\s*[A-Z0-9./%_-]+\s*\)\s*$")


def _normalise(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", name or "").strip()
    return _TRAILING_SYMBOL_RE.sub("", collapsed).strip()


def classify(name: str) -> str:
    """Return the instrument type for a listing's display name."""
    base = _normalise(name)
    if not base:
        return EQUITY  # unknown name: keep it visible rather than hide a company

    if _DEBT_RE.search(base):
        return DEBT
    if _PROMOTER_RE.search(base):
        return PROMOTER_SHARE
    if _FUND_EXPLICIT_RE.search(base):
        return MUTUAL_FUND
    if _FUND_WORD_RE.search(base) and not _CORPORATE_RE.search(base):
        return MUTUAL_FUND
    return EQUITY


def is_equity(name: str) -> bool:
    """True for ordinary shares — the only instruments the analyser handles."""
    return classify(name) == EQUITY


def _self_check() -> None:
    cases = {
        "Solu Hydropower Limited ( SOHL )": EQUITY,
        "Nabil Bank Limited ( NABIL )": EQUITY,
        "Rajdhani Investment Fund Limited ( RAJDHANI )": EQUITY,
        "Aadhyanta Fund Management Limited ( AADHYANTA )": EQUITY,
        "10.25% BOK Debenture 2086 ( 1025BOKL86 )": DEBT,
        "4% Agricultural Bond 2086 ( ADBLB86 )": DEBT,
        "4% NMB Urja Rinpatra (Energy Bond II) 2093/94 ( NMBUR93/94 )": DEBT,
        "Bank of Kathmandu Limited Promoter Share ( BOKLPO )": PROMOTER_SHARE,
        "Citizens Super 30 Mutual Fund ( C30MF )": MUTUAL_FUND,
        "Nabil Bank Limited Retirement Fund ( NBLRF )": MUTUAL_FUND,
        "Nabil Growth Fund ( NGF )": MUTUAL_FUND,
        "Citizens Sadabahar Yojana ( CSBY )": MUTUAL_FUND,
        "Machhapuchchhre SIP Yojana ( MSIP )": MUTUAL_FUND,
        "": EQUITY,
    }
    for name, expected in cases.items():
        actual = classify(name)
        assert actual == expected, f"{name!r}: expected {expected}, got {actual}"
    print("instrument_type self-check OK")


if __name__ == "__main__":
    _self_check()
