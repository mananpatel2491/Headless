"""Activity scan: the pure logic behind `scripts/activity_scan.py` (spec 009-activity-scan).

Everything here is browser-free and unit-tested: parsing what a Google Maps search
result card and a place page expose (a result link's own embedded coordinates, a
rating label, a card's text lines, a weekly-hours table), the straight-line distance
from a chosen point, the evening-window overlap of a venue's own hours on a chosen
day, the ranking score, duplicate folding, and the report renderers. The script owns
the browser; this module owns the arithmetic and the shapes.

Nothing here is Director data: a venue listing is public. The one Director-supplied
input, the `--near` point, is passed in by the script and echoed only into the report
under `reports/activity/`, which is gitignored like every other `reports/` sub-folder.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import quote_plus, urlencode

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Categories that never make an evening activity for two adults, substring and
# case-insensitive against the card's own category text: the Director's own brief
# rules out a movie or a dinner, and the first live scan (2026-09-09) showed that a
# deep Google result list also pulls in retail (a billiards supply store for
# "billiards pool hall", a wine store for "winery"), trade services (a window
# tinting shop for "glass blowing class", a DJ service for "live music venue"),
# venues for hire, and kid-only places - all rated highly, none an outing.
# Each term matches on word boundaries (verifier finding 2, 2026-09-09): a bare
# "shop" must not swallow "Pottery workshop", and "school" alone would delete the
# very "Dance school" and "Cooking school" categories two default queries exist to
# find - only the kid-only school kinds are named.
EXCLUDED_CATEGORY_TERMS = (
    "movie theater", "cinema", "restaurant", "fast food",
    "store", "shop", "supply", "boutique", "dealer", "repair", "tinting", "roaster",
    "bubble tea", "florist", "framing",
    "wedding venue", "banquet", "coworking", "co-working", "dj service", "event planner",
    "playground", "kids", "children", "toy", "elementary school", "primary school",
    "middle school", "high school", "preschool", "nursery", "day care", "daycare",
    "fitness program", "tutoring",
)

# Query words that carry no venue meaning of their own; the rest of a query's words
# become the relevance stems a venue's name or category must echo.
_GENERIC_QUERY_WORDS = frozenset((
    "near", "with", "and", "the", "indoor", "outdoor", "couples", "class", "center",
    "rental", "venue", "hall", "room", "bar", "club", "trail", "course", "track",
    "range", "studio", "cafe", "alley", "shop", "store", "park",
))

# (tag, query) - the tag groups the report; the query becomes a Google Maps search
# "<query> near <area>". Hand-authored; `--queries-file` replaces the whole list.
DEFAULT_QUERIES: tuple[tuple[str, str], ...] = (
    ("outdoors", "kayak canoe rental"),
    ("outdoors", "paddleboard rental"),
    ("outdoors", "hiking trails nature center"),
    ("outdoors", "metropark"),
    ("outdoors", "botanical garden"),
    ("outdoors", "bike rental trail"),
    ("outdoors", "disc golf course"),
    ("outdoors", "zipline aerial adventure park"),
    ("outdoors", "outdoor mini golf"),
    ("outdoors", "golf driving range"),
    ("outdoors", "go kart track"),
    ("outdoors", "batting cages"),
    ("outdoors", "archery range"),
    ("active", "axe throwing"),
    ("active", "rock climbing gym"),
    ("active", "Topgolf"),
    ("active", "roller skating rink"),
    ("active", "ice skating rink"),
    ("active", "indoor go karts"),
    ("games", "escape room"),
    ("games", "bowling alley"),
    ("games", "duckpin bowling"),
    ("games", "arcade bar"),
    ("games", "billiards pool hall"),
    ("games", "board game cafe"),
    ("creative", "pottery painting studio"),
    ("creative", "paint and sip"),
    ("creative", "glass blowing class"),
    ("creative", "cooking class"),
    ("creative", "couples dance class"),
    ("nightlife", "comedy club"),
    ("nightlife", "live music venue"),
    ("nightlife", "brewery with games"),
    ("nightlife", "winery vineyard"),
    ("nightlife", "cidery"),
)

# Live selectors (recon 2026-09-09, headless Chrome 151, Google Maps list view).
# Role/attribute based on purpose: Google's own class names churn, ARIA roles and
# the `/maps/place/` link shape have not.
FEED_SELECTOR = 'div[role="feed"]'
PLACE_LINK_SELECTOR = 'a[href*="/maps/place/"]'
RATING_SELECTOR = 'span[role="img"][aria-label*="star"]'
END_OF_LIST_TEXT = "reached the end of the list"
HOURS_ROW_SELECTOR = "table tr"
WEBSITE_SELECTOR = 'a[data-item-id="authority"]'
PHONE_SELECTOR = 'button[data-item-id^="phone"]'
ADDRESS_SELECTOR = 'button[data-item-id="address"]'
CHECK_SELECTORS = (FEED_SELECTOR, f"{FEED_SELECTOR} {PLACE_LINK_SELECTOR}", RATING_SELECTOR)

_PLACE_COORDS_RE = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_VIEWPORT_COORDS_RE = re.compile(r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
_RATING_LABEL_RE = re.compile(r"(\d+(?:\.\d+)?)\s+stars?\s+([\d,]+)\s+reviews?", re.IGNORECASE)
_CARD_RATING_RE = re.compile(r"(\d\.\d)\((\d[\d,]*)\)")
# "42.48,-83.38", "+42.48,-83.38", "42.48,-83.38,17z" (a pasted lat,lon,zoom triple):
# anything coordinate-shaped is a pair to parse or refuse, never text for a geocoder.
_LATLON_RE = re.compile(
    r"^\s*\+?(-?\d+(?:\.\d+)?)\s*,\s*\+?(-?\d+(?:\.\d+)?)(?:\s*,\s*-?\d+(?:\.\d+)?z?)?\s*$"
)
# "11 AM to 7 PM", "5 to 9 PM", "10:30 AM to 12 AM"; the dash between the two
# times may be a hyphen or Google's own U+2013 / U+2014 - never typed here as a
# literal, per house style, so the class spells them as escapes.
_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*[\u2013\u2014-]\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
    re.IGNORECASE,
)
_HOURS_STATUS_PREFIXES = ("open", "closed", "temporarily closed", "permanently closed", "opens")


@dataclass
class Venue:
    name: str
    url: str
    tag: str
    query: str
    position: int | None = None  # 0-based place in the query's own result list
    lat: float | None = None
    lon: float | None = None
    rating: float | None = None
    reviews: int | None = None
    category: str = ""
    address: str = ""
    hours_today: str = ""
    sponsored: bool = False
    miles: float | None = None
    drive_minutes: int | None = None
    weekly_hours: dict[str, str] = field(default_factory=dict)
    day_ranges: list[list[int]] = field(default_factory=list)
    window_overlap_minutes: int | None = None
    day_status: str = "unknown"  # "open" | "partial" | "closed" | "unknown"
    website: str = ""
    phone: str = ""
    matched_queries: list[str] = field(default_factory=list)
    relevant: bool | None = None  # does the name/category echo a query stem
    score: float = 0.0
    excluded: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# --- Parsing -------------------------------------------------------------------


def looks_like_coordinates(text: str) -> bool:
    """True for anything shaped `<number>,<number>` (an optional leading `+`, an
    optional trailing `,<zoom>` as pasted from a map URL) - a pair the caller must
    never send to a geocoder as if it were a street address, even when out of range."""
    return _LATLON_RE.match(text or "") is not None


def parse_near(text: str) -> tuple[float, float] | None:
    """`"42.45,-83.42"` -> (42.45, -83.42); an out-of-range pair or anything that is
    not a pair -> None (see `looks_like_coordinates` for telling the two apart)."""
    match = _LATLON_RE.match(text or "")
    if not match:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def parse_place_href(href: str) -> tuple[float, float] | None:
    """The `!3d<lat>!4d<lon>` pair a Google Maps place link carries; a place page's
    own `/@<lat>,<lon>,<zoom>` viewport (a query that redirects straight to one
    place, "Topgolf" on the first live scan) is the fallback."""
    match = _PLACE_COORDS_RE.search(href or "") or _VIEWPORT_COORDS_RE.search(href or "")
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def parse_rating_label(label: str) -> tuple[float, int] | None:
    """`"4.2 stars 726 Reviews"` -> (4.2, 726)."""
    match = _RATING_LABEL_RE.search(label or "")
    if not match:
        return None
    return float(match.group(1)), int(match.group(2).replace(",", ""))


def parse_card_lines(lines: list[str]) -> dict:
    """The text lines of one result card -> category / address / today's hours /
    sponsored flag, plus a rating pair when the card text carries one.

    Observed shapes (2026-09-09):
      ["Name", "Name", "4.6(585)", "Canoe & kayak rental service ·  · 2775 Garden Rd",
       "Closed · Opens 11 AM Sat"]
      ["Name", "Sponsored", "", "Name", "5.0(18)", "Indoor golf course · 169 Clarkston Road",
       "Open 24 hours", "Reserve Your Tee Time", "...ad copy...", "Visit Site"]
    """
    cleaned = [line.strip() for line in lines if line and line.strip()]
    result = {
        "name": cleaned[0] if cleaned else "",
        "sponsored": any(line.lower() == "sponsored" for line in cleaned),
        "rating": None,
        "reviews": None,
        "category": "",
        "address": "",
        "hours_today": "",
    }
    rating_index = None
    for index, line in enumerate(cleaned):
        match = _CARD_RATING_RE.search(line)
        if match:
            result["rating"] = float(match.group(1))
            result["reviews"] = int(match.group(2).replace(",", ""))
            rating_index = index
            break
    # The category/address line is the first "a · b" line after the rating (or,
    # for an unrated venue, the first such line at all); today's hours line is the
    # first line starting with an open/closed status word after that.
    start = (rating_index + 1) if rating_index is not None else 1
    for line in cleaned[start:]:
        lowered = line.lower()
        if not result["category"] and "·" in line:
            parts = [part.strip() for part in line.split("·")]
            parts = [part for part in parts if part and not set(part) <= set("$")]
            if parts:
                result["category"] = parts[0]
                if len(parts) > 1:
                    result["address"] = parts[-1]
            continue
        if not result["hours_today"] and lowered.startswith(_HOURS_STATUS_PREFIXES):
            result["hours_today"] = line
    return result


def _to_minutes(hour: int, minute: int, meridiem: str) -> int:
    hour = hour % 12
    if meridiem.upper() == "PM":
        hour += 12
    return hour * 60 + minute


def parse_hours_text(text: str) -> list[list[int]]:
    """A day's hours text -> [[start_min, end_min], ...] on a 0..1560 minute axis
    (an end past midnight continues past 1440 rather than wrapping).

    "Closed" -> []; "Open 24 hours" -> [[0, 1440]];
    "11 AM-7 PM" -> [[660, 1140]]; "5-9 PM" -> [[1020, 1260]];
    "11 AM-2 PM, 5-9 PM" -> two ranges (Google writes U+2013 for the hyphen).
    """
    lowered = (text or "").strip().lower()
    if not lowered or "closed" in lowered:
        return []
    if "24 hours" in lowered:
        return [[0, 1440]]
    ranges: list[list[int]] = []
    for match in _RANGE_RE.finditer(text):
        start_hour, start_min, start_mer, end_hour, end_min, end_mer = match.groups()
        end = _to_minutes(int(end_hour), int(end_min or 0), end_mer)
        if start_mer:
            start = _to_minutes(int(start_hour), int(start_min or 0), start_mer)
        else:
            # "5-9 PM": the start borrows the end's meridiem unless that would
            # put it after the end ("10-2 PM" is 10 AM to 2 PM).
            start = _to_minutes(int(start_hour), int(start_min or 0), end_mer)
            if start >= end:
                other = "AM" if end_mer.upper() == "PM" else "PM"
                start = _to_minutes(int(start_hour), int(start_min or 0), other)
        if end <= start:
            end += 1440  # closes after midnight
        ranges.append([start, end])
    return ranges


def parse_weekly_rows(row_texts: list[str]) -> dict[str, str]:
    """Place-page hours rows (`"Saturday11 AM-7 PM"`, `"FridayClosed"`) -> {day: text}.
    Rows that do not start with a day name (the review-histogram table shares the
    same `table tr` shape) are ignored."""
    weekly: dict[str, str] = {}
    for raw in row_texts:
        text = (raw or "").strip()
        lowered = text.lower()
        for day in DAYS:
            if lowered.startswith(day) and day not in weekly:
                rest = text[len(day):].strip().lstrip(",").strip()
                weekly[day] = rest
                break
    return weekly


def strip_prefix(text: str, prefix: str) -> str:
    """`"Address: 1 Main St"` with prefix `"Address:"` -> `"1 Main St"` (same for `"Phone:"`)."""
    text = (text or "").strip()
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix):].strip()
    return text


# --- Geography -----------------------------------------------------------------


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_miles * math.asin(math.sqrt(a))


def estimate_drive_minutes(miles: float) -> int:
    """Suburban estimate: road distance about 1.3x straight-line, 30 mph average,
    plus 3 minutes to park. An estimate for ranking and reading, never a promise."""
    return int(round(miles * 1.3 / 30 * 60 + 3))


def nominatim_url(address: str) -> str:
    return "https://nominatim.openstreetmap.org/search?" + urlencode(
        {"q": address, "format": "json", "limit": "1"}
    )


def parse_geocode_response(body: str) -> tuple[float, float] | None:
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    try:
        return float(first["lat"]), float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def search_url(query: str, area: str) -> str:
    return "https://www.google.com/maps/search/" + quote_plus(f"{query} near {area}") + "/"


# --- Window, score, folding ------------------------------------------------------


def window_minutes(start: str, end: str) -> tuple[int, int]:
    """`"17:00"`, `"22:00"` -> (1020, 1320). An end at or before the start is read as
    past midnight."""
    start_h, start_m = (int(part) for part in start.split(":"))
    end_h, end_m = (int(part) for part in end.split(":"))
    for hour, minute in ((start_h, start_m), (end_h, end_m)):
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"time {hour:02d}:{minute:02d} is not a clock time (HH 00-23, MM 00-59)")
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    if end_min <= start_min:
        end_min += 1440
    return start_min, end_min


def overlap_minutes(ranges: list[list[int]], window: tuple[int, int]) -> int:
    window_start, window_end = window
    total = 0
    for start, end in ranges:
        total += max(0, min(end, window_end) - max(start, window_start))
    return total


def apply_day_window(venue: Venue, day: str, window: tuple[int, int]) -> None:
    """Fill `day_ranges`, `window_overlap_minutes`, `day_status` from `weekly_hours`."""
    if day not in venue.weekly_hours:
        venue.day_status = "unknown"
        venue.window_overlap_minutes = None
        venue.day_ranges = []
        return
    text = venue.weekly_hours[day]
    venue.day_ranges = parse_hours_text(text)
    if not venue.day_ranges and "closed" not in text.lower():
        # "Hours might differ", an empty cell, or a shape the range regex does not
        # know: the hours were never really read, so this is unknown, never a
        # closed verdict (verifier finding 3, 2026-09-09).
        venue.day_status = "unknown"
        venue.window_overlap_minutes = None
        return
    overlap = overlap_minutes(venue.day_ranges, window)
    venue.window_overlap_minutes = overlap
    span = window[1] - window[0]
    if overlap == 0:
        venue.day_status = "closed"
    elif overlap >= span * 0.8:
        venue.day_status = "open"
    else:
        venue.day_status = "partial"


# An activity-rental business is the activity itself, whatever Google appends to the
# category ("Bike rental shop", "Kayak & canoe rental shop"): checked before any
# exclusion. Named rentals only (re-verification finding 5, 2026-09-09): a bare
# "rental" rescued "Tuxedo rental shop" and "Party rental store".
KEPT_CATEGORY_TERMS = (
    "kayak rental", "canoe rental", "paddleboard rental", "boat rental",
    "bike rental", "bicycle rental", "ski rental", "skate rental",
)


def _has_word(term: str, text: str) -> bool:
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def is_excluded(category: str) -> bool:
    lowered = (category or "").lower()
    if any(_has_word(term, lowered) for term in KEPT_CATEGORY_TERMS):
        return False
    return any(_has_word(term, lowered) for term in EXCLUDED_CATEGORY_TERMS)


def query_tokens(query: str) -> list[str]:
    """The meaning-carrying words of a query: `"hiking trails nature center"` ->
    `["hiking", "trails", "nature"]`."""
    words = re.findall(r"[a-z]+", (query or "").lower())
    return [word for word in words if len(word) >= 3 and word not in _GENERIC_QUERY_WORDS]


_INFLECTIONS = "(?:e|s|es|ing|ed|er|ers|ery)?"


def _bases(token: str) -> set[str]:
    """A token and the roots its common inflections share: "hiking" -> hik, hike;
    "trails" -> trail; "brewery" -> brew, brewer; "winery" -> win (so "wine" matches)."""
    bases = {token}
    if token.endswith("ing") and len(token) > 5:
        bases.add(token[:-3])
    if token.endswith("ery") and len(token) > 5:
        bases.add(token[:-3])
        bases.add(token[:-1])
    if token.endswith("es") and len(token) > 4:
        bases.add(token[:-2])
    if token.endswith("s") and len(token) > 3:
        bases.add(token[:-1])
    return {base for base in bases if len(base) >= 3}


def relevance_pattern(query: str) -> re.Pattern | None:
    """One compiled pattern per query: any token (or an inflection root of it) as a
    WHOLE word, optionally carrying one common suffix. A whole-word rule, not a
    prefix rule (verifier finding 4, 2026-09-09): "comedy" must not hit
    "Comerica", "mini" must not hit "Mining", "cooking" must not hit "Cookies"."""
    alternatives = sorted({base for token in query_tokens(query) for base in _bases(token)}, key=len, reverse=True)
    if not alternatives:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(base) for base in alternatives) + r")" + _INFLECTIONS + r"\b")


def relevance_hit(venue: Venue) -> bool | None:
    """True when the venue's own name or category contains, as a whole word, a
    meaning-carrying token of any query that surfaced it or one of that token's
    common inflections: "kayak" matches "Kayak Rental", "trails" matches "Trail
    Loop", "paint" matches "Painting studio", "ice" never matches "service",
    "cooking" never matches "Cookies". None (neutral) when no query that surfaced
    the venue carries a meaning-carrying token at all ("cafe bar club").

    Known residuals, both directions: a token that is also an ordinary word
    ("pool", "live", "game", "board", "rock", "mini") matches that word wherever it
    appears as a word ("Board of Education", "Mini Storage"); and a compound or
    coined name that only starts with a token ("Trailhead", "Escapology",
    "Ziplining Adventures", "Brewhouse") misses, costing that venue the 0.6-point
    swing between a hit and a miss. Google's own list position and the rating
    still carry those venues; the term is a nudge, not a gate."""
    text = f"{venue.name} {venue.category}".lower()
    patterns = [relevance_pattern(query) for query in (venue.matched_queries or [venue.query])]
    patterns = [pattern for pattern in patterns if pattern is not None]
    if not patterns:
        return None
    return any(pattern.search(text) for pattern in patterns)


def score_venue(venue: Venue, prior_rating: float = 4.0, prior_weight: int = 25) -> float:
    """Bayesian-shrunk rating, minus distance, minus list position, plus or minus
    relevance, then the day-window verdict.

    A 5.0 with 3 reviews should not outrank a 4.6 with 600, so the rating is shrunk
    toward `prior_rating` by `prior_weight` phantom reviews. Every straight-line
    mile costs 0.04 (a 10-mile difference is worth 0.4 stars). Every place down
    Google's own result list costs 0.015 (the 40th result loses 0.6 - Google ranks
    by relevance and prominence, and the first live scan showed the deep tail is
    where the loosely related results live). A name or category that echoes a
    query stem gains 0.35; one that echoes none loses 0.25. A venue proven closed
    in the window drops a full point; one proven open gains 0.2; unknown hours (not
    enriched) are neutral.
    """
    rating = venue.rating if venue.rating is not None else prior_rating
    reviews = venue.reviews or 0
    shrunk = (rating * reviews + prior_rating * prior_weight) / (reviews + prior_weight)
    miles = venue.miles if venue.miles is not None else 15.0
    score = shrunk - 0.04 * miles
    if venue.position is not None:
        score -= 0.015 * venue.position
    if venue.relevant is True:
        score += 0.35
    elif venue.relevant is False:
        score -= 0.25
    if venue.day_status == "closed":
        score -= 1.0
    elif venue.day_status == "open":
        score += 0.2
    elif venue.day_status == "partial":
        score += 0.05
    return round(score, 4)


def fold_duplicates(venues: list[Venue]) -> list[Venue]:
    """Same name at the same rounded point -> one venue; a non-sponsored copy wins over
    a sponsored one, and every query that surfaced it is kept in `matched_queries`."""
    folded: dict[tuple, Venue] = {}
    for venue in venues:
        key = (
            venue.name.strip().lower(),
            round(venue.lat, 4) if venue.lat is not None else None,
            round(venue.lon, 4) if venue.lon is not None else None,
        )
        existing = folded.get(key)
        if existing is None:
            venue.matched_queries = list(dict.fromkeys(venue.matched_queries or [venue.query]))
            folded[key] = venue
            continue
        for query in venue.matched_queries or [venue.query]:
            if query not in existing.matched_queries:
                existing.matched_queries.append(query)
        # The best (lowest) list position across every query that surfaced it.
        positions = [pos for pos in (existing.position, venue.position) if pos is not None]
        best_position = min(positions) if positions else None
        if existing.sponsored and not venue.sponsored:
            venue.matched_queries = existing.matched_queries
            folded[key] = venue
        folded[key].position = best_position
    return list(folded.values())


def locate(venues: list[Venue], near: tuple[float, float]) -> None:
    for venue in venues:
        if venue.lat is None or venue.lon is None:
            venue.miles = None
            venue.drive_minutes = None
            continue
        venue.miles = round(haversine_miles(near[0], near[1], venue.lat, venue.lon), 1)
        venue.drive_minutes = estimate_drive_minutes(venue.miles)


def rank(venues: list[Venue], radius_miles: float) -> list[Venue]:
    """Exclude ruled-out categories, drop anything beyond the radius, score, sort."""
    kept: list[Venue] = []
    for venue in venues:
        venue.excluded = is_excluded(venue.category)
        if venue.excluded:
            continue
        if venue.miles is not None and venue.miles > radius_miles:
            continue
        venue.relevant = relevance_hit(venue)
        venue.score = score_venue(venue)
        kept.append(venue)
    kept.sort(key=lambda v: (-v.score, v.miles if v.miles is not None else 999, v.name))
    return kept


# --- Rendering -------------------------------------------------------------------


def _fmt_rating(venue: Venue) -> str:
    if venue.rating is None:
        return "no rating"
    return f"{venue.rating:.1f} ({venue.reviews or 0:,})"


def _fmt_distance(venue: Venue) -> str:
    if venue.miles is None:
        return "distance unknown"
    return f"{venue.miles:.1f} mi, ~{venue.drive_minutes} min"


def _fmt_day_hours(venue: Venue, day: str) -> str:
    text = venue.weekly_hours.get(day)
    if text is None:
        return f"{day.title()}: not checked"
    return f"{day.title()}: {text}"


_TABLE_HEADER = "| # | Venue | Rating | Distance | Category | Hours | Address | Found via |"
_TABLE_RULE = "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |"


def _table_row(index: int, venue: Venue, day: str) -> str:
    name = f"[{venue.name}]({venue.website})" if venue.website else venue.name
    via = ", ".join((venue.matched_queries or [venue.query])[:2])
    return (
        f"| {index} | {name} | {_fmt_rating(venue)} | {_fmt_distance(venue)} | "
        f"{venue.category or '?'} | {_fmt_day_hours(venue, day)} | {venue.address or '?'} | {via} |"
    )


def render_markdown(
    venues: list[Venue],
    *,
    near_label: str,
    near: tuple[float, float],
    day: str,
    window_text: str,
    generated_at: str,
    queries_run: int,
    top_overall: int = 15,
    top_per_tag: int = 6,
) -> str:
    lines = [
        "# Activity scan",
        "",
        f"- Near: {near_label} ({near[0]:.4f}, {near[1]:.4f})",
        f"- Window: {day.title()} {window_text}",
        f"- Generated: {generated_at}",
        f"- Source: Google Maps list view via Headless (headless Chrome), {queries_run} queries",
        f"- Venues after folding, exclusions and radius: {len(venues)}",
        "",
        "Distance is straight-line from the point above; the minutes are a suburban",
        "drive estimate. Hours are Google's own listing for the day - confirm before going.",
        "",
        "## Top picks overall",
        "",
        _TABLE_HEADER,
        _TABLE_RULE,
    ]
    for index, venue in enumerate(venues[:top_overall], start=1):
        lines.append(_table_row(index, venue, day))
    by_tag: dict[str, list[Venue]] = {}
    for venue in venues:
        by_tag.setdefault(venue.tag, []).append(venue)
    for tag, group in by_tag.items():
        lines += ["", f"## {tag.title()}", "", _TABLE_HEADER, _TABLE_RULE]
        for index, venue in enumerate(group[:top_per_tag], start=1):
            lines.append(_table_row(index, venue, day))
    lines.append("")
    return "\n".join(lines)


def render_json(venues: list[Venue], **meta) -> str:
    return json.dumps({"meta": meta, "venues": [venue.to_dict() for venue in venues]}, indent=2)
