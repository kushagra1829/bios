"""
Deterministic answers to business data questions.

Source: the Product_Market_Monthly worksheet, loaded into the product_market_monthly table.
One record per (product, market, month); January-October 2026; all values synthetic.

Every number this module returns is a plain aggregate of source records, with the filters,
aggregation, record coverage and missing periods reported alongside it. It never imputes a
missing value, never extrapolates outside the dataset period and never maps a requested
geography to a broader one (Europe is not EMEA). Where the data cannot answer the question,
it says so and explains what is available instead.

Field facts used here, all from the workbook's Data_Dictionary sheet or verified on the records:
  net_sales_m_eur_syn    synthetic monthly net-sales-like value, million EUR (the "actual-like" value)
  forecast_m_eur_syn     synthetic forecast-like value, million EUR
  forecast_variance_pct  variance between actual-like and forecast-like values, %; equals
                         (net - forecast) / forecast x 100 on every non-null record; 110 records are null
  units_shipped_syn, market_access_coverage_pct_syn, otif_pct_syn, inventory_weeks_syn
"""
import re
from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from backend.app.agents.schemas import (
    BusinessIntent,
    DataAnswer,
    DataCoverage,
    DataFigure,
    GeographyStatus,
)
from backend.app.models.domain import Markets, ProductMarketMonthly, Products

SOURCE_TABLE = "product_market_monthly"
SOURCE_SHEET = "Product_Market_Monthly"
SOURCE_WORKBOOK = "data/source/Bayer_Pharmaceuticals_SinceAI_2026_FINAL_Builder_Data_Pack.xlsx"
GLOBAL_SCOPES = {"global", "worldwide", "international", "all markets"}
PORTFOLIO_SCOPES = {"all pharma"}


@dataclass(frozen=True)
class Measure:
    key: str
    field: str
    label: str
    unit: str
    aggregation: str  # "sum" or "mean"
    kpi_id: Optional[str] = None
    kpi_name: Optional[str] = None

    @property
    def phrase(self) -> str:
        """The label as used mid-sentence: 'net sales', 'on-time in-full (OTIF)'."""
        return self.label[0].lower() + self.label[1:] if not self.label[:4].isupper() else self.label


MEASURES: Dict[str, Measure] = {
    "net_sales": Measure("net_sales", "net_sales_m_eur_syn", "Net sales", "M EUR", "sum", "KPI-001", "Net Sales"),
    "forecast": Measure("forecast", "forecast_m_eur_syn", "Forecast", "M EUR", "sum", None, None),
    "units": Measure("units", "units_shipped_syn", "Units shipped", "units", "sum", "KPI-014", "Units Shipped"),
    "market_access": Measure(
        "market_access", "market_access_coverage_pct_syn", "Market access coverage", "%", "mean", "KPI-027", "Market Access Coverage"
    ),
    "otif": Measure("otif", "otif_pct_syn", "On-time in-full (OTIF)", "%", "mean", "KPI-020", "On-Time In-Full"),
    "inventory": Measure("inventory", "inventory_weeks_syn", "Inventory coverage", "weeks", "mean", "KPI-016", "Inventory Coverage"),
}

# Ordered: earlier patterns win where phrases overlap.
MEASURE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bmarket\s+access(?:\s+coverage)?\b|\baccess\s+coverage\b", "market_access"),
    (r"\botif\b|\bon[-\s]time\s+in[-\s]full\b|\bon[-\s]time\s+delivery\b", "otif"),
    (r"\binventory(?:\s+(?:coverage|weeks|cover))?\b|\bweeks\s+of\s+(?:inventory|cover|supply)\b|\bstock\s+cover\w*\b", "inventory"),
    (r"\bunits?(?:\s+shipped)?\b|\bunit\s+volumes?\b|\bvolumes?\b|\bshipments?\b|\bshipped\b", "units"),
    (r"\bforecast(?:ed|s)?\b(?!\s*(?:vs\.?|versus|against|compared|and|accuracy|bias|variance))(?!\s+(?:sales\s+)?(?:vs\.?|versus))", "forecast"),
    (r"\bnet\s+sales\b|\bsales\b|\brevenues?\b|\bturnover\b|\bperformance\b", "net_sales"),
]

# Metrics people ask for that Product_Market_Monthly has no field for. Each is reported as
# unsupported rather than approximated by a field that merely sounds similar.
UNSUPPORTED_METRICS: List[Tuple[str, str]] = [
    (r"\bmarket\s+share\b|\bshare\s+of\s+market\b", "market share"),
    (r"\bprofit\w*\b|\bmargins?\b|\bebitda?\b|\boperating\s+contribution\b", "profitability (profit, margin, operating contribution)"),
    (r"\bgross[-\s]to[-\s]net\b|\bgross\s+sales\b", "gross-to-net / gross sales"),
    (r"\bprescriptions?\b|\brx\b|\bscripts\b", "prescriptions"),
    (r"\bpatients?\b|\bpatient\s+counts?\b", "patient numbers"),
    (r"\bprices?\b|\bpricing\b", "price"),
    (r"\bbudget(?:\s+variance)?\b", "budget / budget variance"),
    (r"\bshare\s+of\s+voice\b", "share of voice"),
    (r"\badherence\b|\bpersistence\b", "adherence"),
    (r"\bnps\b|\bnet\s+promoter\b|\bsatisfaction\b", "customer satisfaction / NPS"),
    (r"\bcosts?\b|\bspend\w*\b|\bcogs\b|\broi\b", "cost / spend / ROI"),
    (r"\bheadcount\b|\bfte\b|\bsales\s+reps?\b", "headcount"),
    (r"\bdemand\s+forecast\s+accuracy\b|\bforecast\s+accuracy\b", "Demand Forecast Accuracy (KPI-006)"),
    (r"\bforecast\s+bias\b", "Demand Forecast Bias (KPI-010)"),
    (r"\bdigital\s+engagement\b", "Digital Engagement Index (KPI-049)"),
    (r"\blaunch\s+adoption\b", "Launch Adoption Index (KPI-023)"),
    (r"\bcommercial\s+reach\b", "Commercial Reach Index (KPI-046)"),
    (r"\breimbursement\b", "Reimbursement Status Coverage (KPI-031)"),
]

FORECAST_VS_ACTUAL = re.compile(
    r"\bforecast(?:ed)?\s*(?:sales\s+)?(?:vs\.?|versus|against|compared\s+(?:to|with)|and|or)\s*actuals?\b|"
    r"\bactuals?\s*(?:sales\s+)?(?:vs\.?|versus|against|compared\s+(?:to|with)|and)\s*(?:the\s+)?forecasts?\b|"
    r"\b(?:against|vs\.?|versus|relative\s+to|compared\s+(?:to|with))\s+(?:the\s+)?forecasts?\b|"
    r"\bforecast\s+variance\b|\bvariance\b|\b(?:beat|miss(?:ed)?|exceed(?:ed)?|above|below|ahead\s+of|behind)\s+(?:the\s+)?forecasts?\b",
    re.IGNORECASE,
)
YOY = re.compile(r"\byear[-\s]?(?:over|on)[-\s]?year\b|\byoy\b|\bvs\.?\s+(?:the\s+)?(?:last|previous|prior)\s+year\b|\bcompared\s+(?:to|with)\s+(?:the\s+)?(?:last|previous|prior)\s+year\b", re.IGNORECASE)
RANK = re.compile(
    r"\b(?:highest|lowest|top\s*\d*|bottom\s*\d*|best|worst|largest|smallest|biggest|weakest|strongest|rank\w*|leading|most|least)\b",
    re.IGNORECASE,
)
RANK_LOW = re.compile(r"\b(?:lowest|bottom|worst|smallest|weakest|least)\b", re.IGNORECASE)
TOP_N = re.compile(r"\b(?:top|bottom)\s*(\d+)\b", re.IGNORECASE)
TREND = re.compile(r"\btrends?\b|\bmonthly\b|\bby\s+month\b|\bmonth[-\s]by[-\s]month\b|\bover\s+time\b|\beach\s+month\b|\bper\s+month\s+breakdown\b|\btime\s+series\b", re.IGNORECASE)
CHANGE = re.compile(r"\bmonth[-\s]?(?:over|on)[-\s]?month\b|\bmom\b|\bchange[ds]?\b|\bgrowth\b|\bgrew\b|\bgrow\b|\bincreas\w*\b|\bdecreas\w*\b|\bdeclin\w*\b|\bdelta\b|\bdrop\w*\b", re.IGNORECASE)
COMPARE = re.compile(r"\bcompar\w*\b|\bvs\.?\b|\bversus\b|\bagainst\b|\brelative\s+to\b|\bdifference\b", re.IGNORECASE)
AVERAGE = re.compile(r"\baverage\b|\bmean\b|\bavg\b|\bper\s+month\b|\btypical\s+month\b", re.IGNORECASE)
ALL_PRODUCTS = re.compile(r"\b(?:other|all|each|every|the\s+other)\s+(?:products?|brands?|medicines?)\b|\bby\s+(?:product|brand)\b|\bacross\s+(?:the\s+)?(?:portfolio|products|brands)\b|\bper\s+product\b|\bproduct\s+portfolio\b", re.IGNORECASE)
ALL_MARKETS = re.compile(r"\b(?:other|all|each|every)\s+(?:markets?|countries|regions)\b|\bby\s+(?:market|country)\b|\bacross\s+(?:all\s+)?(?:markets|countries)\b|\bper\s+(?:market|country)\b", re.IGNORECASE)
PRODUCT_DIMENSION = re.compile(r"\bwhich\s+(?:product|brand|medicine|drug)s?\b|\b(?:top|best|worst)[-\s](?:\d+\s+)?(?:products?|brands?|sellers?|selling)\b|\bbest[-\s]selling\b|\bproducts?\s+(?:ranked|ranking)\b", re.IGNORECASE)
MARKET_DIMENSION = re.compile(r"\bwhich\s+(?:market|country|countries|region|affiliate)s?\b|\b(?:top|best|worst)\s+(?:\d+\s+)?(?:markets?|countries)\b|\bmarkets?\s+(?:ranked|ranking)\b", re.IGNORECASE)

MONTH_NUMBERS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_ORDINAL_QUARTER = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


@dataclass
class Period:
    start: str  # YYYY-MM
    end: str  # YYYY-MM
    label: str

    @property
    def months(self) -> List[str]:
        return month_range(self.start, self.end)


def _ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def month_range(start: str, end: str) -> List[str]:
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out: List[str] = []
    while (y, m) <= (ey, em):
        out.append(_ym(y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _shift(ym: str, months: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    total = y * 12 + (m - 1) + months
    return _ym(total // 12, total % 12 + 1)


def period_label(start: str, end: str) -> str:
    sy, sm, ey, em = int(start[:4]), int(start[5:7]), int(end[:4]), int(end[5:7])
    if start == end:
        return f"{MONTH_ABBR[sm]} {sy}"
    if sy == ey:
        return f"{MONTH_ABBR[sm]}–{MONTH_ABBR[em]} {sy}"
    return f"{MONTH_ABBR[sm]} {sy}–{MONTH_ABBR[em]} {ey}"


def parse_periods(text: str, dataset_start: str, dataset_end: str) -> Tuple[List[Period], List[str]]:
    """
    Read the time periods a request states. Returns the periods, in order, and the assumptions
    made (such as a month named without a year). Relative phrases are anchored on the last month
    of the dataset, which is also the last complete month before today.
    """
    notes: List[str] = []
    periods: List[Tuple[int, Period]] = []
    spans: List[Tuple[int, int]] = []
    dataset_year = int(dataset_end[:4])
    years_in_text = [(m.start(), int(m.group(1))) for m in re.finditer(r"\b(20\d{2})\b", text)]

    def free(a: int, b: int) -> bool:
        return not any(a < e and b > s for s, e in spans)

    def take(a: int, b: int, period: Period) -> None:
        spans.append((a, b))
        periods.append((a, period))

    def year_after(pos: int, explicit: Optional[str]) -> int:
        if explicit:
            return int(explicit)
        following = [y for p, y in years_in_text if p > pos]
        if following:
            return following[0]
        notes.append(f"No year was stated, so {dataset_year} (the only year in the dataset) was assumed.")
        return dataset_year

    # Relative phrases first, so "last 3 months" is not read as month "mar".
    relative = [
        (r"\b(?:ytd|year[-\s]to[-\s]date|so\s+far\s+this\s+year)\b", lambda m: Period(_ym(dataset_year, 1), dataset_end, f"YTD {dataset_year} ({period_label(_ym(dataset_year, 1), dataset_end)})")),
        (r"\b(?:this|current)\s+year\b", lambda m: Period(_ym(dataset_year, 1), _ym(dataset_year, 12), str(dataset_year))),
        (r"\b(?:last|previous|prior)\s+year\b", lambda m: Period(_ym(dataset_year - 1, 1), _ym(dataset_year - 1, 12), str(dataset_year - 1))),
        (r"\b(?:last|past|trailing|previous)\s+(\d{1,2})\s+months?\b|\bl(\d{1,2})m\b",
         lambda m: Period(_shift(dataset_end, -(int(m.group(1) or m.group(2)) - 1)), dataset_end, f"last {int(m.group(1) or m.group(2))} months")),
        (r"\b(?:last|latest|most\s+recent|previous|current)\s+month\b", lambda m: Period(dataset_end, dataset_end, period_label(dataset_end, dataset_end))),
        (r"\b(?:last|previous|prior)\s+quarter\b", lambda m: _quarter_period(dataset_year, (int(dataset_end[5:7]) - 1) // 3)),
        (r"\b(?:this|current)\s+quarter\b", lambda m: _quarter_period(dataset_year, (int(dataset_end[5:7]) - 1) // 3 + 1)),
    ]
    for pattern, build in relative:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if free(m.start(), m.end()):
                period = build(m)
                if period is not None:
                    take(m.start(), m.end(), period)

    # ISO months: 2026-03
    for m in re.finditer(r"\b(20\d{2})-(0[1-9]|1[0-2])\b(?!-)", text):
        if free(m.start(), m.end()):
            ym = _ym(int(m.group(1)), int(m.group(2)))
            take(m.start(), m.end(), Period(ym, ym, period_label(ym, ym)))

    # Quarters: Q1 2026, Q2, first quarter of 2026
    for m in re.finditer(r"\bq([1-4])(?:\s*(?:of\s+)?(20\d{2}))?\b|\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter(?:\s+(?:of\s+)?(20\d{2}))?\b", text, re.IGNORECASE):
        if not free(m.start(), m.end()):
            continue
        quarter = int(m.group(1)) if m.group(1) else _ORDINAL_QUARTER[m.group(3).lower()]
        year = year_after(m.start(), m.group(2) or m.group(4))
        take(m.start(), m.end(), _quarter_period(year, quarter))
    # Halves: H1 2026, first half
    for m in re.finditer(r"\bh([12])(?:\s*(?:of\s+)?(20\d{2}))?\b|\b(first|second)\s+half(?:\s+(?:of\s+)?(?:the\s+year\s+)?(20\d{2}))?\b", text, re.IGNORECASE):
        if not free(m.start(), m.end()):
            continue
        half = int(m.group(1)) if m.group(1) else (1 if m.group(3).lower() == "first" else 2)
        year = year_after(m.start(), m.group(2) or m.group(4))
        start = _ym(year, 1 if half == 1 else 7)
        end = _ym(year, 6 if half == 1 else 12)
        take(m.start(), m.end(), Period(start, end, f"H{half} {year} ({period_label(start, end)})"))

    # Month ranges: from March to June 2026, Feb–Apr
    month_range_re = rf"\b(?:from\s+|between\s+)?{_MONTH}(?:\s+(20\d{{2}}))?\s*(?:to|through|thru|until|till|-|–|—|and)\s*{_MONTH}(?:\s+(20\d{{2}}))?\b"
    for m in re.finditer(month_range_re, text, re.IGNORECASE):
        if not free(m.start(), m.end()) or not _is_month_word(m.group(1), m.group(2)) or not _is_month_word(m.group(3), m.group(4)):
            continue
        end_year = year_after(m.start(), m.group(4) or m.group(2))
        start_year = int(m.group(2)) if m.group(2) else end_year
        start = _ym(start_year, MONTH_NUMBERS[m.group(1).lower()])
        end = _ym(end_year, MONTH_NUMBERS[m.group(3).lower()])
        if start <= end:
            take(m.start(), m.end(), Period(start, end, period_label(start, end)))

    # Single months: March 2026, in May
    for m in re.finditer(rf"\b{_MONTH}(?:\s+(20\d{{2}}))?\b", text, re.IGNORECASE):
        if not free(m.start(), m.end()) or not _is_month_word(m.group(1), m.group(2)):
            continue
        year = year_after(m.start(), m.group(2))
        ym = _ym(year, MONTH_NUMBERS[m.group(1).lower()])
        take(m.start(), m.end(), Period(ym, ym, period_label(ym, ym)))

    # Year ranges (one period): 2024-2025, 2024 to 2026
    for m in re.finditer(r"\b(20\d{2})\s*(?:-|–|—|to|through|until)\s*(20\d{2})\b", text, re.IGNORECASE):
        if free(m.start(), m.end()):
            a, b = sorted((int(m.group(1)), int(m.group(2))))
            take(m.start(), m.end(), Period(_ym(a, 1), _ym(b, 12), f"{a}–{b}"))
    # Single years. "between 2024 and 2025" yields two periods, for comparison.
    for m in re.finditer(r"\b(20\d{2})\b", text):
        if free(m.start(), m.end()):
            year = int(m.group(1))
            take(m.start(), m.end(), Period(_ym(year, 1), _ym(year, 12), str(year)))

    ordered = [p for _, p in sorted(periods, key=lambda item: item[0])]
    return ordered, list(dict.fromkeys(notes))


def _quarter_period(year: int, quarter: int) -> Optional[Period]:
    if quarter < 1:
        year, quarter = year - 1, 4
    start = _ym(year, (quarter - 1) * 3 + 1)
    end = _ym(year, quarter * 3)
    return Period(start, end, f"Q{quarter} {year} ({period_label(start, end)})")


def _is_month_word(word: str, year: Optional[str]) -> bool:
    """'may' and 'march' are also verbs: lowercase forms count only with a year."""
    if word.lower() in ("may", "march", "mar") and not year:
        return word[0].isupper() and word.lower() != "mar" or word == "Mar"
    return True


def resolve_measures(text: str) -> Tuple[List[Measure], List[str]]:
    """Supported measures stated in the request, and unsupported metrics it asks for."""
    spans: List[Tuple[int, int]] = []
    unsupported: List[Tuple[int, str]] = []
    for pattern, label in UNSUPPORTED_METRICS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            spans.append((m.start(), m.end()))
            unsupported.append((m.start(), label))
    found: List[Tuple[int, str]] = []
    for pattern, key in MEASURE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if not any(m.start() < e and m.end() > s for s, e in spans):
                spans.append((m.start(), m.end()))
                found.append((m.start(), key))
    keys = list(dict.fromkeys(k for _, k in sorted(found)))
    # "Net sales and forecast" is a forecast-vs-actual comparison only when stated as such; a bare
    # "performance" alongside a specific measure adds nothing.
    measures = [MEASURES[k] for k in keys]
    return measures, list(dict.fromkeys(label for _, label in sorted(unsupported)))


def format_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "M EUR":
        sign = "-" if value < 0 else ""
        return f"{sign}€{abs(value):,.2f}M"
    if unit == "units":
        return f"{int(round(value)):,} units"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "weeks":
        return f"{value:.2f} weeks"
    return f"{value:,.2f} {unit}".strip()


@dataclass
class _Record:
    product_id: str
    market_id: str
    month: str
    values: Dict[str, Optional[float]]
    value_type: str


@dataclass
class _Scope:
    product_ids: List[str]
    market_ids: List[str]
    product_groups: List[Tuple[str, List[str]]] = field(default_factory=list)  # (label, product_ids)
    market_groups: List[Tuple[str, List[str]]] = field(default_factory=list)  # (label, market_ids)
    product_note: str = ""
    market_note: str = ""


class DataQueryEngine:
    """Answers DATA_QUESTION requests from source records. Stateless; safe to share."""

    def answer(self, prompt: str, intent: BusinessIntent, db: Session) -> DataAnswer:
        products = {p.product_id: p.product_name for p in db.query(Products).all()}
        markets = {m.market_id: (m.market_name, m.region, m.currency) for m in db.query(Markets).all()}
        records = [
            _Record(
                product_id=r.product_id,
                market_id=r.market_id,
                month=str(r.month)[:7],
                values={key: getattr(r, m.field) for key, m in MEASURES.items()} | {"forecast_variance_pct": r.forecast_variance_pct},
                value_type=r.value_type,
            )
            for r in db.query(ProductMarketMonthly).all()
        ]
        all_months = sorted({r.month for r in records})
        dataset_start, dataset_end = (all_months[0], all_months[-1]) if all_months else ("2026-01", "2026-10")
        dataset_period = period_label(dataset_start, dataset_end)
        source = {
            "table": SOURCE_TABLE,
            "sheet": SOURCE_SHEET,
            "workbook": SOURCE_WORKBOOK,
            "dataset_period": dataset_period,
            "synthetic": True,
        }

        base = dict(
            products=[],
            markets=[],
            source=source,
            coverage=DataCoverage(dataset_period=dataset_period),
        )

        measures, unsupported = resolve_measures(prompt)
        periods, period_notes = parse_periods(prompt, dataset_start, dataset_end)

        # 1. Geography the user stated but the catalog can't resolve: never substitute.
        geography = intent.geography
        if geography and geography.status in (GeographyStatus.NEEDS_CLARIFICATION, GeographyStatus.PARTIALLY_RESOLVED):
            suggestions = list(dict.fromkeys(m for p in geography.phrases for m in p.suggested_market_ids))
            names = ", ".join(f"{markets[m][0]} ({m})" for m in suggestions if m in markets)
            return DataAnswer(
                status="NEEDS_CLARIFICATION",
                operation="NONE",
                headline=(
                    f"BIOS can't answer for '{', '.join(geography.unresolved_geography)}' without guessing which markets you mean."
                ),
                clarification=[
                    geography.explanation,
                    (f"Name the markets you need, for example: {names}. Or ask for EMEA explicitly if that is what you mean." if names else "Name the markets you need."),
                ],
                caveats=["Europe is not treated as EMEA: the catalog records Germany, France, Italy, Spain, Finland, Sweden and the United Kingdom only as EMEA."]
                if any(p.normalized_scope.endswith("Europe") for p in geography.phrases)
                else [],
                **base,
            )

        # 2. Products and markets the request names but the dataset doesn't contain.
        unknown = self._unknown_entities(prompt, intent, products, markets)
        if unknown:
            return DataAnswer(
                status="UNSUPPORTED",
                operation="NONE",
                headline=f"The dataset has no records for {', '.join(unknown)}.",
                clarification=[
                    f"Products in the dataset: {', '.join(sorted(products.values()))}.",
                    f"Markets in the dataset: {', '.join(f'{v[0]} ({k})' for k, v in sorted(markets.items()))}.",
                ],
                **base,
            )

        # 3. Metrics with no source field.
        if unsupported and not measures:
            return DataAnswer(
                status="UNSUPPORTED",
                operation="NONE",
                headline=f"The source data doesn't contain {', '.join(unsupported)}, so BIOS can't calculate it.",
                clarification=[
                    "Product_Market_Monthly supports: net sales (M EUR), forecast (M EUR), forecast vs actual, units shipped, "
                    "market access coverage (%), on-time in-full (%) and inventory coverage (weeks).",
                ],
                caveats=["BIOS does not approximate an unavailable metric with a similar-sounding field."],
                **base,
            )

        scope = self._scope(prompt, intent, products, markets)
        operation = self._operation(prompt, scope, periods)

        if not scope.product_ids and not scope.market_ids:
            return DataAnswer(status="UNSUPPORTED", operation="NONE", headline="No matching records.", **base)

        named_scope = bool(intent.products) or bool(intent.markets) or bool(ALL_PRODUCTS.search(prompt)) or bool(ALL_MARKETS.search(prompt))
        if not named_scope and operation not in ("RANK", "YOY") and not re.search(r"\b(?:total|overall|portfolio|whole|entire|all)\b", prompt, re.IGNORECASE):
            return DataAnswer(
                status="NEEDS_CLARIFICATION",
                operation=operation,
                headline="Which product and market do you mean?",
                clarification=[
                    "The request names no product or market, so any figure would be an assumption.",
                    f"Products: {', '.join(sorted(products.values()))}. Markets: {', '.join(sorted(markets))}.",
                ],
                **base,
            )

        measure = measures[0] if measures else MEASURES["net_sales"]
        caveats: List[str] = list(period_notes)
        if not measures:
            caveats.append("No measure was named, so BIOS used net sales (KPI-001 Net Sales).")
        if unsupported:
            caveats.append(f"Not available in the source data and not calculated: {', '.join(unsupported)}.")
        if scope.product_note:
            caveats.append(scope.product_note)
        if scope.market_note:
            caveats.append(scope.market_note)

        # Year-over-year needs a prior year that the dataset doesn't have.
        if operation == "YOY":
            years = sorted({m[:4] for m in all_months})
            return DataAnswer(
                status="NO_DATA",
                operation="CHANGE",
                measure_field=measure.field,
                measure_label=measure.label,
                unit=measure.unit,
                products=[products[p] for p in scope.product_ids],
                markets=scope.market_ids,
                headline=(
                    f"A year-over-year comparison isn't possible: the dataset covers {dataset_period} only, "
                    f"so there is no prior-year {measure.phrase} to compare against."
                ),
                clarification=["Ask for a month-over-month or period-to-period change within 2026 instead, e.g. Q1 vs Q2 2026."],
                coverage=DataCoverage(dataset_period=dataset_period, months_covered=all_months),
                source=source,
                caveats=caveats,
                **{k: v for k, v in base.items() if k not in ("products", "markets", "coverage", "source")},
            )

        if not periods:
            periods = [Period(dataset_start, dataset_end, f"{dataset_period} (full dataset period)")]
            caveats.append(f"No period was stated, so BIOS used the full dataset period, {dataset_period}.")

        return self._compute(prompt, operation, measure, measures, scope, periods, records, products, markets, all_months, dataset_period, source, caveats)

    # ------------------------------------------------------------------ scope and operation
    @staticmethod
    def _unknown_entities(prompt: str, intent: BusinessIntent, products: Dict[str, str], markets: Dict[str, Tuple]) -> List[str]:
        """Capitalised names in a product or market slot that the catalog doesn't know."""
        known = {n.lower() for n in products.values()} | {v[0].lower() for v in markets.values()} | {k.lower() for k in markets}
        known |= {v[1].lower() for v in markets.values() if v[1]} | {"global", "europe", "european", "emea", "apac", "latam", "all", "pharma",
                                                                     "power", "bi", "tableau", "q1", "q2", "q3", "q4", "h1", "h2", "ytd",
                                                                     "usa", "uk", "britain", "america", "north", "asia", "latin", "pacific"}
        known |= set(MONTH_NUMBERS)
        unknown: List[str] = []
        for m in re.finditer(r"\b(?:in|for|across|within)\s+(?:the\s+)?([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b", prompt):
            phrase = m.group(1)
            if phrase.lower() not in known and phrase.split()[0].lower() not in known and not intent.markets:
                unknown.append(phrase)
        for m in re.finditer(r"\b([A-Z][a-z]{3,})(?='s)?\s+(?:net\s+)?(?:sales|revenue|units|volumes?|forecast|market\s+access|otif|inventory)\b", prompt):
            word = m.group(1)
            if word.lower() not in known and word.lower() not in {"what", "show", "check", "compare", "total", "monthly", "net", "the", "which",
                                                                  "give", "list", "average", "tell", "how", "were", "find", "our", "report",
                                                                  "calculate", "quarterly", "annual", "overall", "latest", "recent", "gross"} and not intent.products:
                unknown.append(word)
        return list(dict.fromkeys(unknown))

    @staticmethod
    def _scope(prompt: str, intent: BusinessIntent, products: Dict[str, str], markets: Dict[str, Tuple]) -> _Scope:
        name_to_id = {v.lower(): k for k, v in products.items()}
        product_groups: List[Tuple[str, List[str]]] = []
        product_note = ""
        for name in intent.products:
            if name.lower() in PORTFOLIO_SCOPES:
                product_groups.append(("All products", sorted(products)))
                product_note = "'All Pharma' is read as all seven products in the dataset."
            elif name.lower() in name_to_id:
                product_groups.append((name, [name_to_id[name.lower()]]))
        all_products = bool(ALL_PRODUCTS.search(prompt))
        if all_products or not product_groups:
            ids = sorted(products)
            if all_products:
                # "Nubeqa and other products": compare every product, keeping the named ones visible.
                product_groups = [(products[p], [p]) for p in ids]
            product_ids = ids
            if not intent.products and not all_products:
                product_note = product_note or f"No product was named, so all {len(ids)} products are included."
        else:
            product_ids = sorted({p for _, ids in product_groups for p in ids})

        region_members: Dict[str, List[str]] = {}
        for market_id, (_, region, _) in markets.items():
            region_members.setdefault((region or "").lower(), []).append(market_id)
        market_groups: List[Tuple[str, List[str]]] = []
        market_note = ""
        for market in intent.markets:
            key = market.lower()
            if key in GLOBAL_SCOPES:
                market_groups.append(("Global (all markets)", sorted(markets)))
                market_note = f"'Global' is read as all {len(markets)} markets in the dataset."
            elif key in region_members:
                members = sorted(region_members[key])
                market_groups.append((f"{market} ({', '.join(members)})", members))
                market_note = f"{market} is read as the catalog markets whose region is {market}: {', '.join(members)}."
            elif market in markets:
                market_groups.append((f"{markets[market][0]} ({market})", [market]))
        all_markets = bool(ALL_MARKETS.search(prompt))
        if all_markets or not market_groups:
            ids = sorted(markets)
            if all_markets:
                market_groups = [(f"{markets[m][0]} ({m})", [m]) for m in ids]
            market_ids = ids
            if not intent.markets and not all_markets:
                market_note = market_note or f"No market was named, so all {len(ids)} markets are included."
        else:
            market_ids = sorted({m for _, ids in market_groups for m in ids})
        return _Scope(product_ids, market_ids, product_groups, market_groups, product_note, market_note)

    @staticmethod
    def _operation(prompt: str, scope: _Scope, periods: List[Period]) -> str:
        if YOY.search(prompt):
            return "YOY"
        if FORECAST_VS_ACTUAL.search(prompt):
            return "FORECAST_VS_ACTUAL"
        if RANK.search(prompt) and (PRODUCT_DIMENSION.search(prompt) or MARKET_DIMENSION.search(prompt) or re.search(r"\b(?:top|bottom)\s*\d*\b|\brank", prompt, re.IGNORECASE)):
            return "RANK"
        if len(scope.product_groups) > 1 or len(scope.market_groups) > 1:
            return "COMPARE"
        if len(periods) > 1 and (COMPARE.search(prompt) or CHANGE.search(prompt) or re.search(r"\bbetween\b", prompt, re.IGNORECASE)):
            return "COMPARE_PERIODS" if not CHANGE.search(prompt) else "CHANGE"
        if CHANGE.search(prompt):
            return "CHANGE"
        if TREND.search(prompt):
            return "TREND"
        if AVERAGE.search(prompt):
            return "AVERAGE"
        if COMPARE.search(prompt) and len(periods) > 1:
            return "COMPARE_PERIODS"
        return "TOTAL"

    # ------------------------------------------------------------------ computation
    @staticmethod
    def _aggregate(rows: Sequence[_Record], measure: Measure) -> Tuple[Optional[float], int]:
        values = [r.values[measure.key] for r in rows if r.values[measure.key] is not None]
        nulls = len(rows) - len(values)
        if not values:
            return None, nulls
        if measure.aggregation == "sum":
            total = sum(values)
            return (round(total) if measure.unit == "units" else round(total, 2)), nulls
        return round(mean(values), 2), nulls

    def _compute(self, prompt, operation, measure, measures, scope, periods, records, products, markets, all_months, dataset_period, source, caveats) -> DataAnswer:
        requested_months = list(dict.fromkeys(m for p in periods for m in p.months))
        available = set(all_months)
        covered = [m for m in requested_months if m in available]
        missing = [m for m in requested_months if m not in available]
        product_set, market_set = set(scope.product_ids), set(scope.market_ids)

        def select(product_ids=None, market_ids=None, months=None) -> List[_Record]:
            ps = set(product_ids) if product_ids is not None else product_set
            ms = set(market_ids) if market_ids is not None else market_set
            mo = set(months) if months is not None else set(covered)
            return [r for r in records if r.product_id in ps and r.market_id in ms and r.month in mo]

        rows = select()
        value_types: Dict[str, int] = {}
        for r in rows:
            value_types[r.value_type] = value_types.get(r.value_type, 0) + 1
        coverage = DataCoverage(
            records_used=len(rows),
            records_expected=len(product_set) * len(market_set) * len(requested_months),
            months_covered=covered,
            months_missing_in_requested_range=missing,
            value_type_counts=value_types,
            dataset_period=dataset_period,
        )
        product_names = [products[p] for p in scope.product_ids]
        scope_text = self._scope_text(scope, products, markets)
        product_text = self._scope_text(scope, products, markets, include_markets=False)
        market_text = self._scope_text(scope, products, markets, include_products=False, capitalize=False)
        subject = f"{product_text} {measure.phrase} in {market_text}"
        requested_label = " and ".join(p.label for p in periods)
        answer = DataAnswer(
            status="ANSWERED",
            operation=operation if operation != "COMPARE_PERIODS" else "COMPARE",
            measure_field=measure.field,
            measure_label=measure.label,
            unit=measure.unit,
            aggregation=self._aggregation_text(measure),
            products=product_names,
            markets=list(scope.market_ids),
            period_start=covered[0] if covered else None,
            period_end=covered[-1] if covered else None,
            coverage=coverage,
            source=source | {
                "fields": [measure.field] + (["forecast_m_eur_syn"] if operation == "FORECAST_VS_ACTUAL" else []),
                "filters": {"product_id": scope.product_ids, "market_id": scope.market_ids, "month": covered},
            },
            caveats=list(caveats),
        )

        if not covered:
            answer.status = "NO_DATA"
            answer.headline = (
                f"There is no {measure.phrase} data for {scope_text} in {requested_label}. "
                f"The source data covers {dataset_period} only, so BIOS can't report figures for that period."
            )
            reference_rows = select(months=all_months)
            ref_value, _ = self._aggregate(reference_rows, measure)
            if ref_value is not None:
                answer.caveats.append(
                    f"For reference only (not the period you asked for): {measure.phrase} for {scope_text} "
                    f"in {dataset_period} was {format_value(ref_value, measure.unit)}."
                )
            answer.clarification = [f"Ask about a period within {dataset_period}."]
            return answer

        if missing:
            answer.status = "PARTIAL"
            answer.caveats.insert(
                0,
                f"Only {len(covered)} of the {len(requested_months)} requested months have data "
                f"({period_label(covered[0], covered[-1])}). Missing: {self._months_text(missing)}. Figures cover the available months only.",
            )
        if measure.aggregation == "mean":
            answer.caveats.append(
                f"{measure.label} is a percentage-type measure, so BIOS reports the unweighted mean of the monthly record values. "
                "The KPI catalog doesn't define a cross-market weighting."
            )
        null_fva = sum(1 for r in rows if r.values.get("forecast_variance_pct") is None)

        period_text = period_label(covered[0], covered[-1]) if len(periods) == 1 else requested_label
        if operation == "FORECAST_VS_ACTUAL":
            actual, _ = self._aggregate(rows, MEASURES["net_sales"])
            forecast, _ = self._aggregate(rows, MEASURES["forecast"])
            variance = round(actual - forecast, 2)
            variance_pct = round((actual - forecast) / forecast * 100, 2) if forecast else None
            answer.measure_field, answer.measure_label, answer.unit = "net_sales_m_eur_syn", "Net sales vs forecast", "M EUR"
            answer.aggregation = "sum of net_sales_m_eur_syn and of forecast_m_eur_syn; variance = net sales - forecast"
            answer.figures = [
                DataFigure(label="Net sales (actual-like)", value=actual, unit="M EUR"),
                DataFigure(label="Forecast", value=forecast, unit="M EUR"),
                DataFigure(label="Variance (net sales - forecast)", value=variance, unit="M EUR"),
                DataFigure(label="Variance %", value=variance_pct, unit="%", detail="(net sales - forecast) / forecast"),
            ]
            direction = "above" if variance >= 0 else "below"
            answer.headline = (
                f"{scope_text}: net sales were {format_value(actual, 'M EUR')} against a forecast of "
                f"{format_value(forecast, 'M EUR')} in {period_text}, {format_value(abs(variance), 'M EUR')} "
                f"({abs(variance_pct or 0):.2f}%) {direction} forecast."
            )
            answer.series = [
                {"month": m, "net_sales": self._aggregate([r for r in rows if r.month == m], MEASURES["net_sales"])[0],
                 "forecast": self._aggregate([r for r in rows if r.month == m], MEASURES["forecast"])[0]}
                for m in covered
            ]
            if null_fva:
                answer.caveats.append(
                    f"{null_fva} of the {len(rows)} records have no forecast_variance_pct recorded; BIOS calculated the variance "
                    "from net sales and forecast instead and did not impute the missing percentages."
                )
            answer.caveats.append("KPI-042 Forecast Variance is catalogued in EUR, which matches the absolute variance above.")
            return answer

        if operation == "RANK":
            by_product = bool(PRODUCT_DIMENSION.search(prompt)) or (not MARKET_DIMENSION.search(prompt) and len(scope.product_ids) > 1)
            if by_product:
                groups = [(products[p], [p], None) for p in scope.product_ids]
            else:
                groups = [(f"{markets[m][0]} ({m})", None, [m]) for m in scope.market_ids]
            ranking = []
            for label, ps, ms in groups:
                value, _ = self._aggregate(select(product_ids=ps, market_ids=ms), measure)
                if value is not None:
                    ranking.append({"label": label, "value": value})
            ranking.sort(key=lambda item: item["value"], reverse=not RANK_LOW.search(prompt))
            n = int(TOP_N.search(prompt).group(1)) if TOP_N.search(prompt) else 1
            leaders = ranking[: max(1, n)]
            answer.series = [{"rank": i + 1, **item} for i, item in enumerate(ranking)]
            answer.figures = [DataFigure(label=item["label"], value=item["value"], unit=measure.unit) for item in leaders]
            word = "lowest" if RANK_LOW.search(prompt) else "highest"
            if by_product:
                market_within = self._scope_text(scope, products, markets, include_products=False, capitalize=False)
                tail = f"{measure.phrase} in {market_within}"
            else:
                tail = f"{self._scope_text(scope, products, markets, include_markets=False)} {measure.phrase}"
            if len(leaders) > 1:
                listing = "; ".join(f"{i + 1}. {item['label']} {format_value(item['value'], measure.unit)}" for i, item in enumerate(leaders))
                answer.headline = f"{'Bottom' if word == 'lowest' else 'Top'} {len(leaders)} {'products' if by_product else 'markets'} by {tail}, {period_text}: {listing}."
            else:
                answer.headline = f"{leaders[0]['label']} had the {word} {tail} in {period_text}: {format_value(leaders[0]['value'], measure.unit)}."
            if len(ranking) > 1:
                runner = ranking[1]
                answer.comparison = f"Next: {runner['label']} at {format_value(runner['value'], measure.unit)}. {len(ranking)} {'products' if by_product else 'markets'} ranked."
            return answer

        if operation == "COMPARE":
            groups: List[Tuple[str, Optional[List[str]], Optional[List[str]]]]
            if len(scope.product_groups) > 1:
                groups = [(label, ids, None) for label, ids in scope.product_groups]
            else:
                groups = [(label, None, ids) for label, ids in scope.market_groups]
            results = []
            for label, ps, ms in groups:
                value, _ = self._aggregate(select(product_ids=ps, market_ids=ms), measure)
                results.append({"label": label, "value": value})
            answer.figures = [DataFigure(label=r["label"], value=r["value"], unit=measure.unit) for r in results]
            answer.series = sorted(results, key=lambda r: (r["value"] is None, -(r["value"] or 0)))
            valid = [r for r in answer.series if r["value"] is not None]
            if valid:
                top = valid[0]
                within = self._scope_text(
                    scope, products, markets,
                    include_products=len(scope.product_groups) <= 1, include_markets=len(scope.product_groups) > 1,
                )
                by = "product" if len(scope.product_groups) > 1 else "market"
                lead = f"{within} {measure.phrase}" if by == "market" and within else f"{measure.label}" + (f" in {within}" if within else "")
                answer.headline = (
                    f"{lead[0].upper() + lead[1:]} by {by}, {period_text}: {top['label']} leads with "
                    f"{format_value(top['value'], measure.unit)}."
                )
                if len(valid) > 1:
                    second = valid[1]
                    diff = round(top["value"] - second["value"], 2)
                    answer.comparison = (
                        f"{top['label']} is {format_value(diff, measure.unit)} ahead of {second['label']} "
                        f"({format_value(second['value'], measure.unit)})."
                    )
                ranked = "; ".join(f"{i + 1}. {r['label']} {format_value(r['value'], measure.unit)}" for i, r in enumerate(valid))
                answer.comparison = (answer.comparison + f" Ranking: {ranked}.").strip()
            return answer

        if operation in ("COMPARE_PERIODS", "CHANGE") and len(periods) > 1:
            results = []
            for period in periods:
                months = [m for m in period.months if m in available]
                value, _ = self._aggregate(select(months=months), measure) if months else (None, 0)
                results.append({"label": period.label, "value": value, "months": months})
            answer.operation = "COMPARE" if operation == "COMPARE_PERIODS" else "CHANGE"
            answer.figures = [DataFigure(label=r["label"], value=r["value"], unit=measure.unit, detail="no data" if r["value"] is None else "") for r in results]
            answer.series = [{"label": r["label"], "value": r["value"]} for r in results]
            no_data = [r["label"] for r in results if r["value"] is None]
            if no_data:
                answer.status = "PARTIAL"
                answer.caveats.insert(0, f"No data for {', '.join(no_data)}: the dataset covers {dataset_period} only.")
            a, b = results[0], results[-1]
            if a["value"] is not None and b["value"] is not None:
                diff = round(b["value"] - a["value"], 2)
                pct = round(diff / a["value"] * 100, 2) if a["value"] else None
                answer.figures.append(DataFigure(label=f"Change {a['label']} → {b['label']}", value=diff, unit=measure.unit))
                if pct is not None:
                    answer.figures.append(DataFigure(label="Change %", value=pct, unit="%"))
                answer.headline = (
                    f"{subject} moved from {format_value(a['value'], measure.unit)} in {a['label']} "
                    f"to {format_value(b['value'], measure.unit)} in {b['label']} ({'+' if diff >= 0 else ''}{format_value(diff, measure.unit)}"
                    f"{f', {pct:+.2f}%' if pct is not None else ''})."
                )
            else:
                answer.headline = f"{scope_text}: a comparison isn't possible because {', '.join(no_data)} has no data in the source."
                if all(r["value"] is None for r in results):
                    answer.status = "NO_DATA"
            return answer

        total, nulls = self._aggregate(rows, measure)
        monthly = [{"month": m, "value": self._aggregate([r for r in rows if r.month == m], measure)[0]} for m in covered]
        answer.series = monthly

        if operation == "CHANGE":
            first, last = monthly[0], monthly[-1]
            if len(monthly) < 2 or first["value"] is None or last["value"] is None:
                answer.status = "NEEDS_CLARIFICATION"
                answer.headline = "A change needs at least two months; name a longer period or two periods to compare."
                return answer
            diff = round(last["value"] - first["value"], 2)
            pct = round(diff / first["value"] * 100, 2) if first["value"] else None
            answer.figures = [
                DataFigure(label=f"{period_label(first['month'], first['month'])}", value=first["value"], unit=measure.unit),
                DataFigure(label=f"{period_label(last['month'], last['month'])}", value=last["value"], unit=measure.unit),
                DataFigure(label="Change", value=diff, unit=measure.unit),
                DataFigure(label="Change %", value=pct, unit="%"),
            ]
            answer.headline = (
                f"{subject} changed from {format_value(first['value'], measure.unit)} in "
                f"{period_label(first['month'], first['month'])} to {format_value(last['value'], measure.unit)} in "
                f"{period_label(last['month'], last['month'])} ({'+' if diff >= 0 else ''}{format_value(diff, measure.unit)}"
                f"{f', {pct:+.2f}%' if pct is not None else ''})."
            )
            answer.caveats.append(
                "This is the arithmetic change between the first and last month of the period. KPI-004 Net Sales Growth "
                "has no formula recorded in the KPI catalog, so BIOS doesn't present this as that KPI."
            )
            return answer

        if operation == "TREND":
            valued = [m for m in monthly if m["value"] is not None]
            high = max(valued, key=lambda m: m["value"])
            low = min(valued, key=lambda m: m["value"])
            answer.figures = [
                DataFigure(label=f"Total, {period_text}" if measure.aggregation == "sum" else f"Mean, {period_text}", value=total, unit=measure.unit),
                DataFigure(label=f"Highest month ({period_label(high['month'], high['month'])})", value=high["value"], unit=measure.unit),
                DataFigure(label=f"Lowest month ({period_label(low['month'], low['month'])})", value=low["value"], unit=measure.unit),
            ]
            answer.headline = (
                f"Monthly {measure.phrase} for {scope_text}, {period_text}: "
                f"{'total' if measure.aggregation == 'sum' else 'mean'} {format_value(total, measure.unit)}, peaking in "
                f"{period_label(high['month'], high['month'])} at {format_value(high['value'], measure.unit)}."
            )
            first, last = valued[0], valued[-1]
            if len(valued) > 1:
                diff = round(last["value"] - first["value"], 2)
                answer.comparison = (
                    f"From {period_label(first['month'], first['month'])} to {period_label(last['month'], last['month'])}: "
                    f"{'+' if diff >= 0 else ''}{format_value(diff, measure.unit)}. Lowest month: "
                    f"{period_label(low['month'], low['month'])} at {format_value(low['value'], measure.unit)}."
                )
            return answer

        if operation == "AVERAGE" and measure.aggregation == "sum":
            months_with_data = len({r.month for r in rows})
            avg = round(sum(r.values[measure.key] for r in rows) / months_with_data, 2) if months_with_data else None
            answer.aggregation = f"sum of {measure.field} divided by the {months_with_data} months with data"
            answer.figures = [
                DataFigure(label=f"Average per month, {period_text}", value=avg, unit=measure.unit),
                DataFigure(label=f"Total, {period_text}", value=total, unit=measure.unit),
            ]
            answer.headline = f"{subject} averaged {format_value(avg, measure.unit)} per month in {period_text}."
            return answer

        # TOTAL (and AVERAGE of a mean-type measure)
        label = "Total" if measure.aggregation == "sum" else "Mean"
        answer.operation = "TOTAL" if measure.aggregation == "sum" else "AVERAGE"
        answer.figures = [DataFigure(label=f"{label} {measure.phrase}, {period_text}", value=total, unit=measure.unit)]
        for extra in measures[1:]:
            value, _ = self._aggregate(rows, extra)
            answer.figures.append(DataFigure(label=f"{'Total' if extra.aggregation == 'sum' else 'Mean'} {extra.phrase}, {period_text}", value=value, unit=extra.unit))
        verb = "were" if measure.aggregation == "sum" else "averaged"
        answer.headline = f"{subject} {verb} {format_value(total, measure.unit)} in {period_text}."
        if len(monthly) > 1:
            valued = [m for m in monthly if m["value"] is not None]
            high = max(valued, key=lambda m: m["value"])
            answer.comparison = (
                f"Across the {len(valued)} months, the highest was {period_label(high['month'], high['month'])} "
                f"at {format_value(high['value'], measure.unit)}."
            )
        return answer

    # ------------------------------------------------------------------ text helpers
    @staticmethod
    def _aggregation_text(measure: Measure) -> str:
        if measure.aggregation == "sum":
            return f"sum of {measure.field} over matching product-market-month records"
        return f"unweighted mean of {measure.field} over matching product-market-month records"

    @staticmethod
    def _months_text(months: List[str]) -> str:
        if len(months) > 4:
            return f"{period_label(months[0], months[0])} … {period_label(months[-1], months[-1])} ({len(months)} months)"
        return ", ".join(period_label(m, m) for m in months)

    @staticmethod
    def _scope_text(scope: _Scope, products: Dict[str, str], markets: Dict[str, Tuple], include_products: bool = True, include_markets: bool = True, capitalize: bool = True) -> str:
        parts: List[str] = []
        if include_products:
            if len(scope.product_ids) == len(products):
                parts.append("All products")
            else:
                parts.append(" + ".join(products[p] for p in scope.product_ids))
        if include_markets:
            if len(scope.market_ids) == len(markets):
                parts.append("all markets")
            elif scope.market_groups and len(scope.market_groups) == 1:
                parts.append(scope.market_groups[0][0])
            else:
                parts.append(", ".join(f"{markets[m][0]} ({m})" for m in scope.market_ids))
        text = " in ".join(p for p in parts if p)
        return text[0].upper() + text[1:] if text and capitalize else text
