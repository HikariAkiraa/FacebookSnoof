"""Tier-1 Intent & Noise Filter using Regex patterns for Indonesian Facebook Marketplace listing classification."""

import re
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("FacebookSnoof.Filters")

# Drop intent patterns (WTB / WTT / WTA / Inquiries / Non-Sale posts)
DROP_INTENT_PATTERN = re.compile(
    r"\b(wta|want\s*to\s*ask|wtb|cari|carikk|dibutuhkan|butuh|wtt|barter|tt\b|tukar\s*tambah|cek\s*harga|tanya|help|ask|info\s*donk|info\s*dong)\b",
    re.IGNORECASE
)

# Keep intent patterns (WTS / Sale listings)
KEEP_INTENT_PATTERN = re.compile(
    r"\b(wts|jual|dijual|edisi|bu\b|butuh\s*uang|murah|lepasan|pas\b|nett\b|nego|kondisi|garansi|fullset|batangan|mulus)\b",
    re.IGNORECASE
)

# Price extraction regex helper for Indonesian price notation (e.g., 1.5jt, 500k, Rp 3.200.000, 3,5jt)
PRICE_TAG_PATTERN = re.compile(
    r"(?:rp\.?\s*)?(\d+(?:[.,]\d+)?)\s*(k|rb|ribu|jt|juta)?\b",
    re.IGNORECASE
)


def normalize_price_text(price_str: str, multiplier_str: str) -> int:
    """Normalize raw price string and multiplier to integer IDR value."""
    try:
        clean_num = price_str.replace(".", "").replace(",", ".")
        val = float(clean_num)
        
        mult = (multiplier_str or "").lower()
        if mult in ("k", "rb", "ribu"):
            val *= 1_000
        elif mult in ("jt", "juta"):
            val *= 1_000_000
            
        return int(val)
    except (ValueError, TypeError):
        return 0


def extract_price_hint(text: str) -> int:
    """Extract baseline price tag from listing text as heuristic fallback."""
    matches = PRICE_TAG_PATTERN.findall(text)
    extracted_prices = []
    for raw_price, multiplier in matches:
        price_val = normalize_price_text(raw_price, multiplier)
        if 50_000 <= price_val <= 100_000_000:  # Filter out unrealistic numbers
            extracted_prices.append(price_val)
            
    return extracted_prices[0] if extracted_prices else 0


def is_candidate_listing(text: str) -> bool:
    """Classify listing text using regex rules. Returns True if post indicates sale intent."""
    if not text or len(text.strip()) < 10:
        return False

    # Check drop intent
    if DROP_INTENT_PATTERN.search(text):
        logger.debug("Listing dropped due to drop intent pattern match (WTB/WTT/Ask).")
        return False

    # Check keep intent
    if KEEP_INTENT_PATTERN.search(text):
        return True

    # Default heuristic: if text contains price tags, treat as potential candidate
    if extract_price_hint(text) > 0:
        return True

    return False
