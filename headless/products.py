"""Product scan: the pure logic behind `scripts/product_scan.py` (spec 011-product-scan).

Background: a listing the Director was sent (a Walmart lawn-edging listing, 40
ft for $31.58, 100 ft out of stock for $66.49) prompted the question of
whether that pick is the biggest bang for the buck, or whether spending more
buys a product that lasts longer. Amazon's search results page and Home
Depot's search page both render under headless Chrome (recon 2026-09-11);
Walmart, Lowe's, Google Shopping, and Menards refuse it outright (bot walls),
so Walmart is read only as a `--reference-url`/`--reference` listing, never
searched.

Everything here is browser-free and unit-tested: parsing a search card's or
product page's text into a `Listing` (price, rating, review count, and the
title's own physical attributes - height, length, material, stakes), scoring,
duplicate folding, tiering, and the report renderers. The script owns the
browser; this module owns the arithmetic and the shapes.

Nothing here is Director data: every parsed field is public retail listing
text. The one Director-supplied input worth naming, `--reference`/
`--reference-url`, is the listing he was sent - echoed only into the report
under `reports/product/`, which is gitignored like every other `reports/`
sub-folder.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import quote, quote_plus

SITES = ("amazon", "homedepot")

WALL_TITLES = ("Robot or human?", "Access Denied", "Error Page")

REFERENCE_HOSTS = {
    "www.amazon.com": "amazon",
    "amazon.com": "amazon",
    "www.walmart.com": "walmart",
    "walmart.com": "walmart",
}

# --- Live selectors (recon 2026-09-11, headless Chrome 151, shared profile) ----

# Amazon search card (48 per page, verified pages 1-2).
AMAZON_CARD_SELECTOR = 'div[data-component-type="s-search-result"]'
AMAZON_TITLE_SELECTOR = "h2 span"
AMAZON_LINK_SELECTOR = "a.a-link-normal.s-no-outline"
AMAZON_LINK_FALLBACK_SELECTOR = "h2 a"
AMAZON_PRICE_SELECTOR = ".a-price .a-offscreen"
AMAZON_RATING_SELECTOR = 'i[class*="a-icon-star"] .a-icon-alt'
AMAZON_REVIEWS_SELECTOR = '[aria-label$="ratings"]'
AMAZON_REVIEWS_FALLBACK_SELECTOR = '[aria-label$="rating"]'
AMAZON_SPONSORED_SELECTOR = ".puis-sponsored-label-text, span.puis-label-popover-default"

# Amazon product page (reference reader, verified on /dp/B01MG4ARN7).
AMAZON_PRODUCT_TITLE_SELECTOR = "#productTitle"
AMAZON_PRODUCT_PRICE_SELECTOR = "#corePrice_feature_div .a-price .a-offscreen"
AMAZON_PRODUCT_RATING_SELECTOR = "#acrPopover"
AMAZON_PRODUCT_REVIEWS_SELECTOR = "#acrCustomerReviewText"

# Home Depot search pod (verified once, first visit only; pods are duplicated
# in the DOM - fold by canonical URL).
HOMEDEPOT_POD_SELECTOR = '[data-testid="product-pod"]'
HOMEDEPOT_HEADER_SELECTOR = '[data-testid="product-header"]'
HOMEDEPOT_LINK_SELECTOR = 'a[href*="/p/"]'
HOMEDEPOT_PRICE_SELECTOR = '[data-testid="price-simple"]'
HOMEDEPOT_RATING_SELECTOR = '[data-testid*="rating"]'

# Walmart product page (headed only, reference reader - never verified under
# headless Playwright; a bot wall is expected and handled by `wall_reason`).
WALMART_TITLE_SELECTOR = "h1#main-title"
WALMART_PRICE_SELECTOR = 'span[itemprop="price"]'
WALMART_RATING_SELECTOR = '[data-testid="reviews-and-ratings"] span.f7'

# Card/pod-scoped for --check (fix batch B10, 2026-09-11): a page-level
# selector (e.g. bare `h2 span`) can resolve against something that is not
# actually inside a result card at all, so every dependent selector below is
# composed as a descendant of its own card/pod selector.
CHECK_SELECTORS = {
    "amazon": (
        AMAZON_CARD_SELECTOR,
        f"{AMAZON_CARD_SELECTOR} {AMAZON_TITLE_SELECTOR}",
        f"{AMAZON_CARD_SELECTOR} {AMAZON_PRICE_SELECTOR}",
        f"{AMAZON_CARD_SELECTOR} {AMAZON_RATING_SELECTOR}",
    ),
    "homedepot": (
        HOMEDEPOT_POD_SELECTOR,
        f"{HOMEDEPOT_POD_SELECTOR} {HOMEDEPOT_HEADER_SELECTOR}",
        f"{HOMEDEPOT_POD_SELECTOR} {HOMEDEPOT_PRICE_SELECTOR}",
        f"{HOMEDEPOT_POD_SELECTOR} {HOMEDEPOT_RATING_SELECTOR}",
    ),
}

_ASIN_RE = re.compile(r"/dp/([A-Za-z0-9]{10})")


def wall_reason(title: str, url: str) -> str | None:
    """A bot wall is one of the fixed titles this recon found (`WALL_TITLES`) or
    a Walmart-shaped `/blocked?` redirect - never a guess from page content."""
    stripped = (title or "").strip()
    if stripped in WALL_TITLES:
        return stripped
    if "/blocked?" in (url or ""):
        return "blocked"
    return None


def search_url(site: str, query: str, page_number: int) -> str:
    """Amazon: `?k=<query>&page=N`. Home Depot: `/s/<query>` with `?Nao=<24*(N-1)>`
    only for N > 1 (page 1 has no query-string suffix, recon 2026-09-11)."""
    if site == "amazon":
        return f"https://www.amazon.com/s?k={quote_plus(query)}&page={page_number}"
    if site == "homedepot":
        url = f"https://www.homedepot.com/s/{quote(query)}"
        if page_number > 1:
            url += f"?Nao={24 * (page_number - 1)}"
        return url
    raise ValueError(f"unknown site {site!r}")


def canonical_url(site: str, href: str, data_asin: str | None = None) -> str:
    """The fold key for a search result: Amazon -> `/dp/<ASIN>` (from the href,
    else the card's own `data-asin`); Home Depot -> `/p/<slug>/<id>` (query
    string stripped, pods are duplicated in the DOM); an unrecognized site keeps
    whatever href it was given (already absolute, from a reference URL)."""
    href = href or ""
    if site == "amazon":
        match = _ASIN_RE.search(href)
        asin = match.group(1) if match else (data_asin or None)
        if asin:
            return f"https://www.amazon.com/dp/{asin}"
        return href if href.startswith("http") else f"https://www.amazon.com{href}"
    if site == "homedepot":
        path = href.split("?", 1)[0]
        return path if path.startswith("http") else f"https://www.homedepot.com{path}"
    return href


def slugify(query: str) -> str:
    """The report file name's own query slug (fix batch A5/B9, 2026-09-11):
    lower-cased, every run of non-alphanumerics collapsed to one hyphen,
    trimmed of leading/trailing hyphens, cut to 40 characters - so two
    different queries scanned the same UTC day never overwrite each other,
    while the same query the same day still does (documented, unchanged)."""
    slug = _SLUG_NON_ALNUM_RE.sub("-", (query or "").lower()).strip("-")
    return slug[:40]


_SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


# --- Listing --------------------------------------------------------------------


@dataclass
class Listing:
    site: str
    title: str
    url: str
    origin: str  # "search" | "reference-url" | "reference-hand"
    price: float | None = None
    rating: float | None = None
    reviews: int | None = None
    position: int | None = None
    page: int | None = None
    sponsored: bool = False
    height_in: float | None = None
    length_ft: float | None = None
    material: str = "unknown"
    stake_count: int | None = None
    stake_material: str | None = None
    no_dig: bool = False
    excluded_reason: str | None = None
    price_per_ft: float | None = None
    shrunk_rating: float | None = None
    score: float = 0.0
    flags: list[str] = field(default_factory=list)
    found_on_pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --- Parsing: price, rating, count -----------------------------------------------

_PRICE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def parse_price(text: str) -> float | None:
    """`"$43.99"`, Home Depot's split `"$\\n41\\n.\\n97"`, `"Now $22.59"`,
    `"31.58"`, `"$1,234.00"` -> a float; no digits -> None."""
    if not text:
        return None
    collapsed = re.sub(r"\s+", "", text)
    match = _PRICE_RE.search(collapsed)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


_FIRST_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_rating(text: str) -> float | None:
    """`"4.5 out of 5 stars"`, `"4.5 out of 5"`, `"(4.1)"`, `"4.1"` -> the
    leading number (a rating always leads the text it is parsed from)."""
    if not text:
        return None
    match = _FIRST_NUMBER_RE.search(text)
    if not match:
        return None
    return float(match.group(1))


_RATING_COUNT_SLASH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*([\d,]+)")
_RATING_COUNT_STARS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*out of 5\s*stars?\.?\s*([\d,]+)\s*reviews?", re.IGNORECASE
)


def parse_rating_and_count(text: str) -> tuple[float, int] | None:
    """Home Depot's `"(4.5 / 4091)"` and Walmart's
    `"4.1 out of 5 Stars. 15 reviews"` -> (rating, count)."""
    if not text:
        return None
    match = _RATING_COUNT_SLASH_RE.search(text)
    if match:
        return float(match.group(1)), int(match.group(2).replace(",", ""))
    match = _RATING_COUNT_STARS_RE.search(text)
    if match:
        return float(match.group(1)), int(match.group(2).replace(",", ""))
    return None


_COUNT_KM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([KkMm])\b")
_COUNT_PLAIN_RE = re.compile(r"(\d[\d,]*)")


def parse_count(text: str) -> int | None:
    """`"5,118 ratings"`, `"(5,118)"`, `"158"`, `"15 ratings"` -> an int;
    `"5.1K"` -> 5100 (K/M suffix support); no digits -> None."""
    if not text:
        return None
    match = _COUNT_KM_RE.search(text)
    if match:
        multiplier = 1000 if match.group(2).upper() == "K" else 1_000_000
        return int(round(float(match.group(1)) * multiplier))
    match = _COUNT_PLAIN_RE.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


# --- Parsing: title attributes ---------------------------------------------------


def _normalize_title(title: str) -> str:
    text = title or ""
    text = text.replace("×", "x")  # ×
    text = text.replace("‑", "-")  # non-breaking hyphen
    text = text.replace("”", '"').replace("″", '"')  # ” ″
    text = text.replace("’", "'").replace("′", "'")  # ’ ′
    text = text.replace("​", "")  # zero-width space
    text = text.replace("，", ",")  # full-width comma ，
    text = text.replace("（", "(").replace("）", ")")  # full-width parens （）
    text = re.sub(r"\s+", " ", text).strip()
    return text


_STAKE_NOUN_RE = re.compile(r"\b(stakes?|spikes?|nails?|staples?|anchors?|pegs?)\b", re.IGNORECASE)
# Immediately before a stake noun: a count (optionally a "/"-separated range),
# optional pcs/pieces, optional "x ", then up to three descriptive words
# ("Unbreakable Steel", "Stainless Steel") - anchored at the noun's own start
# so an unrelated earlier number (a height, a price) is never in scope. The
# leading `(?<![\d.])` guard (fix batch B13, 2026-09-11) refuses to start the
# count on the trailing digits of a decimal fraction ("7.8In Height Stakes"
# must never read a count of 8 off the ".8").
_STAKE_PRECEDING_RE = re.compile(
    r"(?<![\d.])(\d+(?:\s*/\s*\d+)*)\s*(?:pcs?|pieces?)?\s*(?:x\s*)?((?:[A-Za-z][A-Za-z-]*\s+){0,3})$",
    re.IGNORECASE,
)
_STEEL_STAKE_WORDS = ("stainless", "galvanized", "steel", "metal", "iron")

# Every stake/spike/nail/staple/anchor/peg/pin phrase, counted or not (fix
# batch A2/B5, 2026-09-11) - removed from the working text before material,
# height, and length parsing so an uncounted phrase ("with Metal Stakes") is
# just as invisible to the material rule as a counted one ("150 Stainless
# Steel Stakes" already was).
_STAKE_STRIP_RE = re.compile(
    r"(?:\d+\s*(?:pcs?|pieces?)?\s*)?"
    r"(?:(?:stainless|galvanized|steel|metal|plastic|iron|nylon|u[- ]shaped|anchoring|anchor|"
    r"reinforced|heavy[- ]duty|unbreakable|hard|extra[- ]long|rust[- ]resistant|upgraded?)\s+){0,4}"
    r"(?:stakes?|spikes?|nails?|staples?|anchors?|pegs?|pins?)\b",
    re.IGNORECASE,
)


def _extract_stakes(text: str) -> tuple[int | None, str | None]:
    """The first stake noun in `text` with a valid preceding COUNTED phrase ->
    (count, material). An uncounted phrase ("with Metal Stakes," no digit)
    never contributes a count or a material here - see `_STAKE_STRIP_RE` for
    the separate, broader removal that still keeps such a phrase's own
    material word out of the roll's own material rule."""
    for noun_match in _STAKE_NOUN_RE.finditer(text):
        prefix = text[: noun_match.start()]
        pre_match = _STAKE_PRECEDING_RE.search(prefix)
        if not pre_match:
            continue
        first_number = re.split(r"\s*/\s*", pre_match.group(1))[0]
        try:
            count = int(first_number)
        except ValueError:
            continue
        words = (pre_match.group(2) or "").lower()
        if any(word in words for word in _STEEL_STAKE_WORDS):
            material = "steel"
        elif "plastic" in words:
            material = "plastic"
        else:
            material = None
        return count, material
    return None, None


_HEIGHT_IN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*(?:in\b|inch(?:es)?\b|\"|'')", re.IGNORECASE)
_HEIGHT_H_PAREN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*in\s*\(h\)", re.IGNORECASE)
_HEIGHT_X_IN_RE = re.compile(r"x\s*(\d+(?:\.\d+)?)\s*in\b", re.IGNORECASE)
_TALL_CONTEXT_RE = re.compile(r"tall|high|height|\(h\)|h\b", re.IGNORECASE)
_LENGTH_MARK_RE = re.compile(r"\bl\b|long|length", re.IGNORECASE)
_PAIR_GAP_RE = re.compile(r"^\s*x\s*$", re.IGNORECASE)


def _height_candidates(text: str) -> list[tuple[int, int, float]]:
    """Every raw height-shaped number: (start, end, value), positions from all
    three inch patterns, de-duplicated by start position."""
    seen: dict[int, tuple[int, int, float]] = {}
    for pattern in (_HEIGHT_IN_RE, _HEIGHT_H_PAREN_RE, _HEIGHT_X_IN_RE):
        for match in pattern.finditer(text):
            start = match.start(1)
            if start not in seen:
                seen[start] = (start, match.end(), float(match.group(1)))
    return [seen[key] for key in sorted(seen)]


def _right_context_window(text: str, start: int, max_chars: int) -> str:
    """The text following `start`, capped at `max_chars` - but cut short at
    the FIRST digit encountered (fix batch B11, 2026-09-11: a later
    dimension's own number, e.g. the "2" of a following "2.25\" H", must never
    fall inside an earlier candidate's own context window), and never left
    ending mid-word (fix batch B12: a plain `max_chars` cutoff that happens to
    land inside a word - e.g. right after the "L" of "Landscape" - must never
    manufacture a false `\\bL\\b`/`\\bH\\b` match purely because the window's
    own end looks like a word boundary; extended to that word's own end
    instead, since no digit intervened)."""
    limit = min(start + max_chars, len(text))
    digit_match = re.search(r"\d", text[start:limit])
    if digit_match:
        limit = start + digit_match.start()
    elif limit < len(text) and text[limit - 1 : limit].isalpha() and text[limit : limit + 1].isalpha():
        end_of_word = limit
        while end_of_word < len(text) and text[end_of_word].isalpha():
            end_of_word += 1
        limit = end_of_word
    return text[start:limit]


def _parse_height(text: str) -> float | None:
    candidates = _height_candidates(text)
    # A candidate immediately followed by "L"/"long"/"length" - within a
    # window that stops at the next digit or after the word it would
    # otherwise cut in half - is a length stated in inches, not a height:
    # drop it outright ("40in L x 6in H" style titles).
    kept = []
    for start, end, value in candidates:
        if _LENGTH_MARK_RE.search(_right_context_window(text, end, 8)):
            continue
        kept.append((start, end, value))
    # An "AxB" pair where both numbers carry their own inch/quote unit
    # (`(20"x5.3")`) is a width-then-height convention: drop the first when the
    # second is itself a plausible height (in range), mirroring the dedicated
    # "x DIGIT in" pattern's own intent for the quote-marked case.
    collapsed = []
    for index, (start, end, value) in enumerate(kept):
        if index + 1 < len(kept):
            next_start, next_end, next_value = kept[index + 1]
            if _PAIR_GAP_RE.match(text[end:next_start]) and 0.5 <= next_value <= 24:
                continue  # this is the first of a pair; the second wins
        collapsed.append((start, end, value))
    valid = [(start, end, value) for start, end, value in collapsed if 0.5 <= value <= 24]
    if not valid:
        return None
    for start, end, value in valid:
        if _TALL_CONTEXT_RE.search(_right_context_window(text, end, 12)):
            return value
    return valid[0][2]


_LENGTH_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*[-/]\s*\d+(?:\.\d+)?)+\s*(?:ft\b|feet\b|foot\b)", re.IGNORECASE
)
# The foot-quote is always a LONE single quote (fix batch A3/B2, 2026-09-11):
# a quote preceded or followed by another `'` or a `"` is part of a `''`/`"`
# double-prime inch mark, never a foot mark ("4'' X 100'" is 4 inches by 100
# feet, not 4 feet by 100 feet).
_LENGTH_SIMPLE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*-?\s*(?:ft\b|feet\b|foot\b|(?<!['\"])'(?!['\"]))", re.IGNORECASE
)

# A title-stated grand total overrides every other length candidate (fix
# batch A6/B14, 2026-09-11): "(Total 100 Ft)" on a title whose own first
# candidate would otherwise be a smaller per-roll figure ("4\" x 50'").
_TOTAL_LENGTH_RE_A = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|foot|')\s*(?:in\s+)?total", re.IGNORECASE)
_TOTAL_LENGTH_RE_B = re.compile(r"total\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:ft|feet|foot|')", re.IGNORECASE)


def _parse_length(text: str) -> float | None:
    """A title-stated total (`_TOTAL_LENGTH_RE_A`/`_B`) wins outright. Else: a
    `40-100ft` / `20/40/100FT` / `40/100ft` range -> the first number (the
    listed price belongs to the first/default variant, research.md); a plain
    `100ft`/`90'`/`33ft` -> its own number. The FIRST valid candidate by
    position wins overall (`100FT ... 2 x 50FT`)."""
    total_match = _TOTAL_LENGTH_RE_A.search(text) or _TOTAL_LENGTH_RE_B.search(text)
    if total_match:
        value = float(total_match.group(1))
        if 1 <= value <= 1000:
            return value
    spans: list[tuple[int, int]] = []
    candidates: list[tuple[int, float]] = []
    for match in _LENGTH_RANGE_RE.finditer(text):
        spans.append(match.span())
        candidates.append((match.start(), float(match.group(1))))
    for match in _LENGTH_SIMPLE_RE.finditer(text):
        start, end = match.span()
        if any(span_start <= start < span_end for span_start, span_end in spans):
            continue  # already covered by a range match
        candidates.append((start, float(match.group(1))))
    candidates.sort(key=lambda item: item[0])
    for _, value in candidates:
        if 1 <= value <= 1000:
            return value
    return None


_MATERIAL_RULES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"cor-ten|corten|weathering steel", re.IGNORECASE), "steel"),
    (re.compile(r"stainless|galvanized|steel", re.IGNORECASE), "steel"),
    (re.compile(r"aluminum|aluminium", re.IGNORECASE), "aluminum"),
    (re.compile(r"\bmetal\b", re.IGNORECASE), "metal"),
    (re.compile(r"rubber", re.IGNORECASE), "rubber"),
    # Decorative products only (fix batch A1/B4, 2026-09-11): bare "stone" and
    # "paver" were dropped. A plastic roll whose title merely lists "Paver"
    # among its uses ("... Flexible for Garden Flower Beds Lawn Yard Pathway
    # Paver") is not stone-look - it tiers on whatever material word is
    # actually left ("Plastic Mulch" -> plastic).
    (
        re.compile(
            r"faux[- ]stone|stone[- ]effect|stone[- ]look|stone[- ]like|stone texture|polyrock|"
            r"\bbricks?\b|cobblestone|\bconcrete\b",
            re.IGNORECASE,
        ),
        "stone-look",
    ),
    (re.compile(r"wood|timber|bamboo", re.IGNORECASE), "wood"),
    (
        re.compile(r"plastic|hdpe|polyethylene|\bpe\b|\bpoly\b|pvc|polymer|vinyl", re.IGNORECASE),
        "plastic",
    ),
)

_NO_DIG_RE = re.compile(r"no[\s-]dig", re.IGNORECASE)

_EXCLUDED_RULES: tuple[tuple[re.Pattern, str], ...] = (
    (
        # Post-batch live re-run finding (2026-09-11): a bare "fence" substring
        # excluded genuine edging - a brand name ("AggFencer"), a use list
        # ("... for Lawn, Flower Bed, Garden Fence"), a "Mini Fence Border"
        # marketing phrase, and an EasyFlex decorative "Wood-Look Fence Garden
        # Border" kit. A real fence names an animal barrier, "fencing", fence
        # panels (in either order), or a trellis; every one of the 11 real
        # animal-barrier titles from the live runs carries at least one of these.
        re.compile(
            r"animal barrier|\bfencing\b|fence panels?|fence\W{0,3}\d+\s*panels?|"
            r"\bpanels?\b[^|]{0,30}\bfence\b|\btrellis\b",
            re.IGNORECASE,
        ),
        "fence, not edging",
    ),
    (re.compile(r"stakes?\s*only|replacement stakes|spikes?\s*only", re.IGNORECASE), "stakes only"),
)

# A pack/piece count (fix batch A6/B14, 2026-09-11): "5 Piece", "6 Pack", and
# the reversed order real titles also use, "(Pack 6)" - checked on the
# stake-stripped text (`is_pack`) so a stake count stated as "Pcs"
# ("120 Pcs Metal Spikes") is never mistaken for a physical multi-piece pack.
_PACK_RE = re.compile(
    r"\b\d+\s*(?:packs?|pcs?|pieces?|pc)\b|\b(?:packs?|pieces?)\s*\d+\b", re.IGNORECASE
)


def has_total_marker(title: str) -> bool:
    """True when the title states a grand total (`(21ft Total)`, `66FT Total`,
    `Total 100 Ft`) - the length `_parse_length` then returns IS the whole
    pack, so the per-piece caveat must not apply (post-batch live re-run
    finding, 2026-09-11: a "6 Packs ... (21ft Total)" listing was flagged
    per-piece although its own total had been parsed)."""
    text = _normalize_title(title)
    return _TOTAL_LENGTH_RE_A.search(text) is not None or _TOTAL_LENGTH_RE_B.search(text) is not None


def pack_flag_applies(title: str) -> bool:
    """The one rule both listing builders use: a pack/piece count is present
    (`is_pack`) AND no title-stated total overrides it (`has_total_marker`)."""
    return is_pack(title) and not has_total_marker(title)


def is_pack(title: str) -> bool:
    """True when the title names a pack/piece count outside any stake phrase
    - the caller (the script's `_fill_attributes`, and
    `parse_reference_literal` below) appends the `"pack: per-piece length"`
    flag when this is true AND a length was parsed, since such a title's own
    `$/ft` prices one piece, not the whole roll (research.md D6)."""
    text = _normalize_title(title)
    working = _STAKE_STRIP_RE.sub(" ", text)
    return _PACK_RE.search(working) is not None


def parse_attributes(title: str) -> dict:
    """A listing title -> `height_in`, `length_ft`, `material`, `stake_count`,
    `stake_material`, `no_dig`, `excluded_reason`. Pure regex, deterministic,
    testable - no LLM anywhere in this module."""
    text = _normalize_title(title)
    stake_count, stake_material = _extract_stakes(text)
    working = _STAKE_STRIP_RE.sub(" ", text)
    height_in = _parse_height(working)
    length_ft = _parse_length(working)
    material = "unknown"
    for pattern, name in _MATERIAL_RULES:
        if pattern.search(working):
            material = name
            break
    no_dig = _NO_DIG_RE.search(text) is not None
    excluded_reason = None
    for pattern, reason in _EXCLUDED_RULES:
        if pattern.search(text):
            excluded_reason = reason
            break
    return {
        "height_in": height_in,
        "length_ft": length_ft,
        "material": material,
        "stake_count": stake_count,
        "stake_material": stake_material,
        "no_dig": no_dig,
        "excluded_reason": excluded_reason,
    }


def price_per_ft(price: float | None, length_ft: float | None) -> float | None:
    if price is None or not length_ft:
        return None
    return round(price / length_ft, 3)


# --- Scoring, folding, tiers -------------------------------------------------------


def score_listing(
    listing: Listing, prior_rating: float = 4.0, prior_weight: int = 25, price_weight: float = 0.5
) -> float:
    """Bayesian-shrunk rating minus a price-per-foot penalty minus a weak
    list-position term, minus a sponsored penalty.

    A 5.0 with 3 reviews should not beat a 4.6 with 600, so the rating is
    shrunk toward `prior_rating` by `prior_weight` phantom reviews - and an
    unrated listing (no `rating` at all) is flagged `"unrated"` rather than
    silently treated as an average one. A $0.30/ft roll loses 0.15
    (`price_weight * 0.30`); a $0.80/ft roll loses 0.40 - so a strongly
    better-rated product still wins at twice the price per foot, while an
    equal rating goes to the cheaper foot. `price_per_ft` unknown (no
    parsable price or length) costs a flat 0.5 and flags `length unknown`
    (or `price unknown`, whichever is actually missing) rather than crashing
    or guessing a number. Every place further down its own search page's
    result list costs a further 0.005 (a weak nudge, not a ranking driver -
    Amazon and Home Depot already rank for relevance); a sponsored listing
    loses 0.1, since a placement paid for is weaker evidence than an organic
    one.
    """
    if listing.rating is None and "unrated" not in listing.flags:
        listing.flags.append("unrated")
    rating = listing.rating if listing.rating is not None else prior_rating
    reviews = listing.reviews or 0
    shrunk = (rating * reviews + prior_rating * prior_weight) / (reviews + prior_weight)
    listing.shrunk_rating = round(shrunk, 4)
    ppf = price_per_ft(listing.price, listing.length_ft)
    if ppf is None:
        score = shrunk - 0.5
        if listing.price is None:
            if "price unknown" not in listing.flags:
                listing.flags.append("price unknown")
        elif not listing.length_ft:
            if "length unknown" not in listing.flags:
                listing.flags.append("length unknown")
    else:
        score = shrunk - price_weight * ppf
    if listing.position is not None:
        score -= 0.005 * listing.position
    if listing.sponsored:
        score -= 0.1
    return round(score, 4)


def fold_duplicates(listings: list[Listing]) -> list[Listing]:
    """Same URL -> one listing: keep the copy with the lowest `(page, position)`,
    union `found_on_pages`, a non-sponsored copy beats a sponsored one."""

    def rank_key(listing: Listing) -> tuple[int, int]:
        page = listing.page if listing.page is not None else 0
        position = listing.position if listing.position is not None else 0
        return page, position

    folded: dict[str, Listing] = {}
    for listing in listings:
        existing = folded.get(listing.url)
        if existing is None:
            listing.found_on_pages = list(dict.fromkeys(listing.found_on_pages or ([listing.page] if listing.page else [])))
            folded[listing.url] = listing
            continue
        pages = list(existing.found_on_pages)
        if listing.page is not None and listing.page not in pages:
            pages.append(listing.page)
        winner = existing
        if existing.sponsored and not listing.sponsored:
            winner = listing
        elif not existing.sponsored and listing.sponsored:
            winner = existing
        elif rank_key(listing) < rank_key(existing):
            winner = listing
        winner.found_on_pages = pages
        folded[listing.url] = winner
    return list(folded.values())


def tier(material: str) -> str:
    if material in ("plastic", "rubber", "unknown"):
        return "plastic"
    if material in ("steel", "aluminum", "metal"):
        return "metal"
    return "other"


TIERS: tuple[str, ...] = ("plastic", "metal", "other")


@dataclass
class RankResult:
    """`rank()`'s own return shape (fix batch B6, 2026-09-11): the tiered,
    sorted, kept listings, PLUS the excluded and height-dropped ones - so a
    report can be audited (which listing left the ranking, and why) instead
    of only ever seeing a count."""

    tiers: dict[str, list[Listing]]
    excluded: list[Listing]
    dropped_by_height: list[Listing]


def rank(listings: list[Listing], min_height_in: float | None = None) -> RankResult:
    """Order of operations (fix batch B3/B8, 2026-09-11): fold is already done
    by the caller before `rank` is ever called; a listing whose
    `excluded_reason` is set is dropped and recorded FIRST (a short fence is
    always "excluded," never "dropped by height," even when it would also
    fail the height check); then, only when `min_height_in` is given, a
    listing whose known `height_in` falls below it is dropped and recorded,
    while a listing with no parsable height at all is kept and flagged
    `"height unknown"` rather than dropped by this rule alone; the remainder
    is grouped by `tier(material)` and, within each tier, sorted by
    descending `score`, then ascending `price_per_ft` (unknown last), then
    ascending `title`."""
    excluded: list[Listing] = []
    dropped_by_height: list[Listing] = []
    kept: list[Listing] = []
    for listing in listings:
        if listing.excluded_reason:
            excluded.append(listing)
            continue
        if min_height_in is not None:
            if listing.height_in is not None and listing.height_in < min_height_in:
                dropped_by_height.append(listing)
                continue
            if listing.height_in is None and "height unknown" not in listing.flags:
                listing.flags.append("height unknown")
        kept.append(listing)
    by_tier: dict[str, list[Listing]] = {name: [] for name in TIERS}
    for listing in kept:
        by_tier.setdefault(tier(listing.material), []).append(listing)
    for name, group in by_tier.items():
        group.sort(
            key=lambda l: (
                -l.score,
                l.price_per_ft if l.price_per_ft is not None else float("inf"),
                l.title,
            )
        )
    return RankResult(tiers=by_tier, excluded=excluded, dropped_by_height=dropped_by_height)


def parse_reference_literal(text: str) -> Listing:
    """`"Title | price | length_ft [| rating [| reviews]]"` (fix batch A4,
    2026-09-11: an optional 4th part, a rating 0..5, and an optional 5th
    part, a non-negative review count; a 4th part with no 5th is allowed) ->
    a hand-typed `Listing`, origin `"reference-hand"`. `$` on the price and
    `ft`/`'` on the length are both optional. A price must be positive, a
    length must be positive, and a leading `-` on either is refused outright
    (fix batch B7) rather than silently losing its sign to the digit regex.
    Anything else raises `ValueError` (the script turns it into a refusal)."""
    parts = [part.strip() for part in (text or "").split("|")]
    if len(parts) not in (3, 4, 5) or not all(parts):
        raise ValueError('expected "Title | price | length_ft [| rating [| reviews]]"')
    title, price_text, length_text = parts[0], parts[1], parts[2]
    if price_text.startswith("-"):
        raise ValueError(f"price must be positive, got {price_text!r}")
    price = parse_price(price_text)
    if price is None or price <= 0:
        raise ValueError(f"could not parse a positive price from {price_text!r}")
    if length_text.startswith("-"):
        raise ValueError(f"length must be positive, got {length_text!r}")
    length_match = re.search(r"(\d+(?:\.\d+)?)", length_text)
    if not length_match:
        raise ValueError(f"could not parse a length from {length_text!r}")
    length_ft = float(length_match.group(1))
    if length_ft <= 0:
        raise ValueError(f"length must be positive, got {length_text!r}")
    rating: float | None = None
    reviews: int | None = None
    if len(parts) >= 4:
        rating_text = parts[3]
        rating_match = re.search(r"(\d+(?:\.\d+)?)", rating_text)
        if not rating_match or rating_text.startswith("-"):
            raise ValueError(f"could not parse a rating from {rating_text!r}")
        rating = float(rating_match.group(1))
        if not (0 <= rating <= 5):
            raise ValueError(f"rating must be between 0 and 5, got {rating!r}")
    if len(parts) == 5:
        reviews_text = parts[4]
        reviews_match = re.search(r"(\d+)", reviews_text)
        if not reviews_match or reviews_text.startswith("-"):
            raise ValueError(f"could not parse a review count from {reviews_text!r}")
        reviews = int(reviews_match.group(1))
        if reviews < 0:
            raise ValueError(f"reviews must not be negative, got {reviews!r}")
    listing = Listing(
        site="reference", title=title, url="", origin="reference-hand",
        price=price, rating=rating, reviews=reviews,
    )
    attributes = parse_attributes(title)
    attributes["length_ft"] = length_ft
    for key, value in attributes.items():
        setattr(listing, key, value)
    listing.price_per_ft = price_per_ft(price, length_ft)
    if pack_flag_applies(title):
        listing.flags.append("pack: per-piece length")
    return listing


# --- Rendering --------------------------------------------------------------------


def _fmt_price(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "-"


def _fmt_ppf(value: float | None) -> str:
    return f"${value:.3f}" if value is not None else "-"


def _fmt_height(value: float | None) -> str:
    return f'{value:g}"' if value is not None else "-"


def _fmt_length(value: float | None) -> str:
    return f"{value:g} ft" if value is not None else "-"


def _fmt_length_cell(listing: Listing) -> str:
    """`_fmt_length`, with `" (per piece)"` appended when the title names a
    pack/piece count (fix batch A6, 2026-09-11) - the report's own `$/ft` for
    such a listing prices one piece, not the whole roll, by design."""
    text = _fmt_length(listing.length_ft)
    if listing.length_ft is not None and "pack: per-piece length" in listing.flags:
        text += " (per piece)"
    return text


def _fmt_material(listing: Listing) -> str:
    if listing.stake_count:
        material = listing.stake_material or "?"
        return f"{listing.material} ({listing.stake_count} {material} stakes)"
    return listing.material


def _fmt_rating(listing: Listing) -> str:
    if listing.rating is None:
        return "-"
    return f"{listing.rating:.1f} ({listing.reviews or 0:,})"


def _escape_pipe(text: str) -> str:
    """A `|` inside a title breaks a Markdown table row (fix batch B1,
    2026-09-11: 28 of 78 rows in one live run) - escaped before the title
    ever enters a table cell."""
    return text.replace("|", "\\|")


_TABLE_HEADER = "| # | Listing | Site | Price | $/ft | Height | Length | Material | Stakes | Rating | Score |"
_TABLE_RULE = "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |"


def _table_row(index, listing: Listing, *, bold: bool = False) -> str:
    title = _escape_pipe(listing.title[:90])
    name = f"[{title}]({listing.url})" if listing.url else title
    if bold:
        name = f"**{name} (REFERENCE)**"
    stakes = f"{listing.stake_count} {listing.stake_material or '?'}" if listing.stake_count else "-"
    cells = [
        str(index),
        name,
        listing.site,
        _fmt_price(listing.price),
        _fmt_ppf(listing.price_per_ft),
        _fmt_height(listing.height_in),
        _fmt_length_cell(listing),
        listing.material,
        stakes,
        _fmt_rating(listing),
        f"{listing.score:.4f}",
    ]
    return "| " + " | ".join(cells) + " |"


def _reference_rank(reference: Listing, group: list[Listing]) -> tuple[int, int]:
    """Where `reference` would land if inserted into `group` (already sorted
    by `rank()`) by its own score: 1-based rank, and the total including it."""
    better = sum(1 for listing in group if listing.score > reference.score)
    return better + 1, len(group) + 1


def render_markdown(rank_result: RankResult, reference: Listing | None, meta: dict) -> str:
    read = meta.get("read", meta.get("total_read", 0))
    unique = meta.get("unique", sum(len(group) for group in rank_result.tiers.values()))
    excluded = meta.get("excluded", len(rank_result.excluded))
    dropped_by_height = meta.get("dropped_by_height", len(rank_result.dropped_by_height))
    ranked = meta.get("ranked", sum(len(group) for group in rank_result.tiers.values()))
    lines = [
        "# Product scan",
        "",
        f"- Query: {meta.get('query', '')}",
        f"- Sites: {', '.join(meta.get('sites', []))}",
        f"- Pages: {meta.get('pages', '')}",
        f"- Generated: {meta.get('generated_at', '')}",
        f"- Listings: {read} read, {unique} unique after fold, {excluded} excluded, "
        f"{dropped_by_height} dropped by height, {ranked} ranked",
        "",
    ]
    reference_tier = tier(reference.material) if reference is not None else None
    reference_rank_index = None
    if reference is not None:
        group = rank_result.tiers.get(reference_tier, [])
        reference_rank_index, rank_total = _reference_rank(reference, group)
        lines += [
            "## Reference listing",
            "",
            f"- Origin: {reference.origin}",
            f"- Title: {reference.title}",
            f"- Price: {_fmt_price(reference.price)}",
            f"- $/ft: {_fmt_ppf(reference.price_per_ft)}",
            f"- Height: {_fmt_height(reference.height_in)}",
            f"- Length: {_fmt_length_cell(reference)}",
            f"- Material: {_fmt_material(reference)}",
            f"- Rating: {_fmt_rating(reference)}",
            f"- Score: {reference.score:.4f}",
            "",
            f"Your pick would rank #{reference_rank_index} of {rank_total} in the {reference_tier} tier.",
            "",
        ]
    for name in TIERS:
        group = rank_result.tiers.get(name, [])
        if not group and name != reference_tier:
            continue
        lines += ["", f"## {name.title()}", "", _TABLE_HEADER, _TABLE_RULE]
        rows = list(group)
        insert_at = None
        if name == reference_tier:
            insert_at = reference_rank_index - 1  # 0-based position in `rows`
            rows = rows[:insert_at] + [reference] + rows[insert_at:]
        for index, listing in enumerate(rows, start=1):
            is_reference = insert_at is not None and index - 1 == insert_at
            lines.append(_table_row(index, listing, bold=is_reference))
    notes = meta.get("notes", [])
    lines += ["", "## Notes", ""]
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- (none)")
    lines += ["", "## Excluded", ""]
    if rank_result.excluded:
        by_reason: dict[str, list[Listing]] = {}
        for listing in rank_result.excluded:
            by_reason.setdefault(listing.excluded_reason or "unknown", []).append(listing)
        for reason, group in by_reason.items():
            lines.append(f"- {reason}: {len(group)}")
            for listing in group:
                lines.append(f"  - {listing.title[:60]}")
    else:
        lines.append("- (none)")
    lines += ["", "## Dropped by height", ""]
    if rank_result.dropped_by_height:
        for listing in rank_result.dropped_by_height:
            lines.append(f"- {listing.title[:60]}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def render_json(rank_result: RankResult, reference: Listing | None, meta: dict) -> str:
    reference_payload = None
    if reference is not None:
        reference_payload = reference.to_dict()
        reference_tier = tier(reference.material)
        group = rank_result.tiers.get(reference_tier, [])
        rank_index, tier_size = _reference_rank(reference, group)
        reference_payload["rank"] = rank_index
        reference_payload["tier"] = reference_tier
        reference_payload["tier_size"] = tier_size
    payload = {
        "meta": meta,
        "reference": reference_payload,
        "tiers": {name: [listing.to_dict() for listing in group] for name, group in rank_result.tiers.items()},
        "excluded": [listing.to_dict() for listing in rank_result.excluded],
    }
    return json.dumps(payload, indent=2)
