"""
Deterministic intent parsing and validation of LLM proposals.

parse_intent() establishes the baseline from the request and the catalog. normalize_intent()
checks each LLM proposal against the request and catalog, records the outcome and reason, and
returns the single BusinessIntent that every later agent receives.

Products and markets are decided by the parser alone: the LLM can confirm them but cannot add
them. That keeps a request's scope, and so its candidate assets, independent of the provider.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from backend.app.agents.entity_catalog import (
    AMBIGUOUS_MARKET_TERMS,
    BROADER_THAN_EUROPE,
    UNCATALOGUED_METRICS,
    EntityCatalog,
    KPI_TERMINOLOGY,
    KpiEntry,
)
from backend.app.agents.schemas import (
    BusinessIntent,
    EnrichmentDecision,
    EnrichmentStatus,
    EntityAmbiguity,
    GeographicPhrase,
    GeographyResolution,
    GeographyStatus,
    IntentExtraction,
    IntentFields,
    IntentResolution,
)

FUZZY_THRESHOLD = 0.85
FUZZY_TIE_MARGIN = 0.03
FUZZY_MIN_LENGTH = 5

# Two-letter market codes that are also ordinary English words.
ENGLISH_COLLISION_CODES = {"us": "the pronoun 'us'", "it": "'it' or Information Technology"}
GEO_PREPOSITIONS = {"in", "across", "within", "throughout"}
GEO_NOUNS = {"market", "markets", "region", "regions", "country", "countries", "affiliate", "geography", "territory"}
PRONOUN_VERBS = {"show", "tell", "give", "help", "let", "send", "email", "ask", "get", "gives", "shows", "helps"}
LIST_CONNECTOR = re.compile(r"^\s*(?:,|/|&|and|or|vs\.?|versus|,\s*and)\s*$", re.IGNORECASE)

DIMENSION_PATTERNS = [
    (r"\b(?:by country|by countries|country-level|per country)\b", "country"),
    (r"\b(?:by region|regional|per region)\b", "region"),
    (r"\b(?:by month|monthly)\b", "month"),
    (r"\b(?:by quarter|quarterly)\b", "quarter"),
    (r"\b(?:by product|product-level)\b", "product"),
    (r"\bby channel\b", "channel"),
]
TIME_PATTERNS = [
    (r"\b(?:monthly|month-over-month)\b", "monthly"),
    (r"\b(?:quarterly|quarter)\b", "quarterly"),
    (r"\b(?:annual|yearly|ytd)\b", "YTD"),
    (r"\b(?:last 12 months|l12m|trailing)\b", "L12M"),
    (r"\bweekly\b", "weekly"),
    (r"\bdaily\b", "daily"),
]
_TIME_TERM = re.compile(
    r"\b(?:q[1-4]|20\d{2}|h[12]|ytd|mtd|qtd|l\d+m|day|days|daily|week|weeks|weekly|month|months|monthly|"
    r"quarter|quarters|quarterly|year|years|yearly|annual|annually|trailing)\b",
    re.IGNORECASE,
)
_STATED_PERIOD = re.compile(r"\b(?:q[1-4](?:\s+20\d{2})?|last\s+\d+\s+(?:days|weeks|months|quarters|years)|20\d{2})\b", re.IGNORECASE)

# Too general to link a user's phrase to a specific catalog KPI on their own.
GENERIC_KPI_WORDS = {
    "commercial", "performance", "market", "report", "reporting", "index", "rate", "status", "coverage",
    "digital", "management", "local", "adjusted", "legacy", "metric", "metrics", "total", "overall", "data",
}


@dataclass
class ParsedIntent:
    fields: IntentFields
    ambiguities: List[EntityAmbiguity] = field(default_factory=list)
    interpretation_notes: List[str] = field(default_factory=list)
    geography: GeographyResolution = field(default_factory=GeographyResolution)


# "Europe" and "European", with any compass qualifier so "Western Europe" isn't read as all of Europe.
_EUROPE_SCOPE = re.compile(
    r"(?<!\w)(?:(?P<qualifier>western|eastern|northern|southern|central)\s+)?(?:europe|european)(?!\w)",
    re.IGNORECASE,
)


def _resolve_europe(phrase: str, qualifier: Optional[str], catalog: EntityCatalog) -> GeographicPhrase:
    """Resolve a European scope using only what Markets.region records. Never substitutes EMEA."""
    verified, broader, unclassified = catalog.europe_classification()
    unverified = [market_id for ids in broader.values() for market_id in ids] + unclassified

    catalog_evidence: List[str] = []
    external_context: List[str] = []
    if verified:
        catalog_evidence.append(f"Markets.region names Europe for {', '.join(verified)}.")
    else:
        catalog_evidence.append("No Markets.region value names Europe.")
    gaps: List[str] = []
    for region, market_ids in broader.items():
        fact = f"The catalog records {', '.join(market_ids)} only as {region}"
        catalog_evidence.append(f"{fact}.")
        context = f"{region} generally means {BROADER_THAN_EUROPE[region]}, which is broader than Europe"
        external_context.append(f"{context}. This is general knowledge, not a catalog fact.")
        gaps.append(f"{fact}. {context} (general knowledge, not a catalog fact), so it wasn't substituted.")
    if unclassified:
        fact = f"{', '.join(unclassified)} have no region recorded in the catalog."
        catalog_evidence.append(fact)
        gaps.append(fact)
    suggestions = (
        f"{', '.join(unverified)} are suggestions only, not verified matches, and need your confirmation."
        if unverified
        else ""
    )
    common = {"catalog_evidence": catalog_evidence, "external_context": external_context}

    if qualifier:
        scope = f"{qualifier.capitalize()} Europe"
        return GeographicPhrase(
            original_phrase=phrase,
            normalized_scope=scope,
            suggested_market_ids=verified + unverified,
            status=GeographyStatus.NEEDS_CLARIFICATION,
            explanation=f"The catalog doesn't record which markets are in {scope}. Please name the markets you need.",
            **common,
        )
    if verified and not unverified:
        return GeographicPhrase(
            original_phrase=phrase,
            normalized_scope="Europe",
            resolved_market_ids=verified,
            status=GeographyStatus.RESOLVED,
            explanation=f"Markets.region verifies {', '.join(verified)} as European.",
            **common,
        )
    if verified:
        return GeographicPhrase(
            original_phrase=phrase,
            normalized_scope="Europe",
            resolved_market_ids=verified,
            suggested_market_ids=unverified,
            status=GeographyStatus.PARTIALLY_RESOLVED,
            explanation=f"Markets.region verifies {', '.join(verified)} as European. {' '.join(gaps)} {suggestions}",
            **common,
        )
    detail = " ".join(gaps) if gaps else "No market in the catalog is classified as European."
    next_step = (
        f"Please confirm the markets you need, or request {' or '.join(broader)} explicitly."
        if broader
        else "Please name the markets you need."
    )
    return GeographicPhrase(
        original_phrase=phrase,
        normalized_scope="Europe",
        suggested_market_ids=unverified,
        status=GeographyStatus.NEEDS_CLARIFICATION,
        explanation=f"Europe was requested, but the catalog verifies no market as European. {detail} {suggestions} {next_step}".replace("  ", " "),
        **common,
    )


def _resolved_phrase(surface: str, canonical: str, catalog: EntityCatalog) -> GeographicPhrase:
    is_region = canonical in catalog.regions
    return GeographicPhrase(
        original_phrase=surface,
        normalized_scope=canonical,
        resolved_market_ids=catalog.markets_in_region(canonical) if is_region else [canonical],
        status=GeographyStatus.RESOLVED,
        explanation=f"'{surface}' matches catalog {'region' if is_region else 'scope'} '{canonical}'.",
    )


def _summarize_geography(phrases: List[GeographicPhrase]) -> GeographyResolution:
    if not phrases:
        return GeographyResolution(explanation="The request names no geography.")
    resolved_ids = _unique([market_id for p in phrases for market_id in p.resolved_market_ids])
    unresolved = [p for p in phrases if p.status != GeographyStatus.RESOLVED]
    if not unresolved:
        status = GeographyStatus.RESOLVED
    elif resolved_ids:
        status = GeographyStatus.PARTIALLY_RESOLVED
    else:
        status = GeographyStatus.NEEDS_CLARIFICATION
    return GeographyResolution(
        status=status,
        phrases=phrases,
        resolved_market_ids=resolved_ids,
        unresolved_geography=_unique([p.original_phrase for p in unresolved]),
        explanation=" ".join(p.explanation for p in unresolved) or "All requested geography matched catalog records.",
    )


def _phrase_pattern(term: str) -> re.Pattern:
    """Whole-phrase match in which spaces and hyphens are interchangeable."""
    parts = [re.escape(part) for part in re.split(r"[\s-]+", term.strip()) if part]
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _overlaps(start: int, end: int, spans: List[Tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def _unique(values: List[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _fuzzy_candidates(token: str, names: List[str]) -> List[str]:
    """Close spellings of a word. More than one result means the spelling is ambiguous."""
    scored = [(SequenceMatcher(None, token.lower(), name.lower()).ratio(), name) for name in names]
    scored = [item for item in scored if item[0] >= FUZZY_THRESHOLD]
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [name for score, name in sorted(scored, key=lambda s: -s[0]) if best - score <= FUZZY_TIE_MARGIN]


def _find_products(
    prompt: str, catalog: EntityCatalog
) -> Tuple[List[str], List[Tuple[int, int]], List[EntityAmbiguity], List[str]]:
    found: List[Tuple[int, str]] = []
    spans: List[Tuple[int, int]] = []
    for term, name in sorted(catalog.product_terms().items(), key=lambda kv: -len(kv[0])):
        for match in _phrase_pattern(term).finditer(prompt):
            if not _overlaps(match.start(), match.end(), spans):
                spans.append((match.start(), match.end()))
                found.append((match.start(), name))

    ambiguities: List[EntityAmbiguity] = []
    notes: List[str] = []
    single_word_names = [name for _, name in catalog.products]
    for match in re.finditer(r"[A-Za-z]{%d,}" % FUZZY_MIN_LENGTH, prompt):
        if _overlaps(match.start(), match.end(), spans):
            continue
        candidates = _fuzzy_candidates(match.group(), single_word_names)
        if len(candidates) == 1:
            spans.append((match.start(), match.end()))
            found.append((match.start(), candidates[0]))
            notes.append(f"Read '{match.group()}' as product '{candidates[0]}' (close spelling).")
        elif candidates:
            spans.append((match.start(), match.end()))
            ambiguities.append(
                EntityAmbiguity(
                    category="product",
                    term=match.group(),
                    candidates=candidates,
                    reason="The spelling is close to more than one catalog product.",
                )
            )
    return _unique([name for _, name in sorted(found)]), spans, ambiguities, notes


def _words_before(prompt: str, position: int, count: int = 2) -> List[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z]+", prompt[:position])[-count:]]


def _word_after(prompt: str, position: int) -> str:
    match = re.match(r"\W*([A-Za-z]+)", prompt[position:])
    return match.group(1).lower() if match else ""


def _find_geography(
    prompt: str, catalog: EntityCatalog, product_spans: List[Tuple[int, int]]
) -> Tuple[List[str], List[EntityAmbiguity], List[str], GeographyResolution]:
    found: List[Tuple[int, str]] = []
    spans: List[Tuple[int, int]] = list(product_spans)
    named_spans: List[Tuple[int, int]] = []
    notes: List[str] = []
    ambiguities: List[EntityAmbiguity] = []
    phrases: List[GeographicPhrase] = []

    catalog_names = {name.lower() for _, name, _ in catalog.markets} | {r.lower() for r in catalog.regions}
    catalog_names |= {s.lower() for s in catalog.market_scopes}

    def flag_ambiguous(term: str, candidates: List[str], reason: str) -> None:
        ambiguities.append(EntityAmbiguity(category="market", term=term, candidates=candidates, reason=reason))
        phrases.append(
            GeographicPhrase(
                original_phrase=term,
                normalized_scope=term,
                suggested_market_ids=candidates,
                status=GeographyStatus.NEEDS_CLARIFICATION,
                explanation=reason,
            )
        )

    # 1. A European scope is resolved per market, never through an alias. A qualified phrase
    # that is itself a catalog region falls through to step 2.
    region_names = {r.lower() for r in catalog.regions}
    for match in _EUROPE_SCOPE.finditer(prompt):
        is_catalog_subregion = match.group("qualifier") and match.group().lower() in region_names
        if is_catalog_subregion or _overlaps(match.start(), match.end(), spans):
            continue
        spans.append((match.start(), match.end()))
        phrase = _resolve_europe(match.group(), match.group("qualifier"), catalog)
        phrases.append(phrase)
        found.extend((match.start(), market_id) for market_id in phrase.resolved_market_ids)
        if phrase.status != GeographyStatus.RESOLVED:
            ambiguities.append(
                EntityAmbiguity(
                    category="market",
                    term=match.group(),
                    candidates=phrase.suggested_market_ids,
                    reason=phrase.explanation,
                )
            )

    # 2. Market names, regions, scopes and aliases. These are unambiguous in any case.
    for term, canonical in sorted(catalog.geography_terms().items(), key=lambda kv: -len(kv[0])):
        for match in _phrase_pattern(term).finditer(prompt):
            if _overlaps(match.start(), match.end(), spans):
                continue
            spans.append((match.start(), match.end()))
            named_spans.append((match.start(), match.end()))
            found.append((match.start(), canonical))
            phrases.append(_resolved_phrase(match.group(), canonical, catalog))
            if term not in catalog_names:
                notes.append(f"Read '{match.group()}' as catalog market scope '{canonical}'.")
            if canonical in catalog.regions:
                members = ", ".join(catalog.markets_in_region(canonical))
                notes.append(f"Region '{canonical}' covers catalog markets: {members}.")

    # 3. Terms that could mean several catalog entries are reported and left unresolved.
    for term, targets in AMBIGUOUS_MARKET_TERMS.items():
        candidates = [t for t in targets if t in catalog.market_ids or t in catalog.regions]
        for match in _phrase_pattern(term).finditer(prompt):
            if not _overlaps(match.start(), match.end(), spans):
                spans.append((match.start(), match.end()))
                flag_ambiguous(
                    match.group(), candidates, f"'{match.group()}' doesn't identify one catalog market or region."
                )

    # 4. Close spellings of single-word market names.
    names_to_ids = {name: market_id for market_id, name, _ in catalog.markets if " " not in name}
    for match in re.finditer(r"[A-Za-z]{%d,}" % FUZZY_MIN_LENGTH, prompt):
        if _overlaps(match.start(), match.end(), spans):
            continue
        candidates = _fuzzy_candidates(match.group(), list(names_to_ids))
        if len(candidates) == 1:
            spans.append((match.start(), match.end()))
            named_spans.append((match.start(), match.end()))
            found.append((match.start(), names_to_ids[candidates[0]]))
            phrases.append(_resolved_phrase(match.group(), names_to_ids[candidates[0]], catalog))
            notes.append(f"Read '{match.group()}' as market '{candidates[0]}' (close spelling).")
        elif candidates:
            spans.append((match.start(), match.end()))
            flag_ambiguous(
                match.group(),
                [names_to_ids[c] for c in candidates],
                f"The spelling of '{match.group()}' is close to more than one catalog market.",
            )

    # 5. Two-letter codes need contextual evidence.
    has_lowercase = any(c.islower() for c in prompt)
    code_ids = {market_id.lower(): market_id for market_id in catalog.market_ids}
    tokens = [
        m for m in re.finditer(r"(?<![\w.'-])[A-Za-z]{2}(?![\w'-])", prompt)
        if m.group().lower() in code_ids and not _overlaps(m.start(), m.end(), spans)
    ]

    def adjacent_to_market(match: re.Match) -> bool:
        partners = list(named_spans)
        for other in tokens:
            if other is match:
                continue
            is_collision = other.group().lower() in ENGLISH_COLLISION_CODES
            # An English word can't vouch for a neighbouring code ("it and us").
            if not is_collision or (other.group().isupper() and has_lowercase):
                partners.append((other.start(), other.end()))
        for start, end in partners:
            between = prompt[end:match.start()] if end <= match.start() else prompt[match.end():start]
            if LIST_CONNECTOR.match(between):
                return True
        return False

    for match in tokens:
        token = match.group()
        key = token.lower()
        market_id = code_ids[key]
        before = _words_before(prompt, match.start())
        previous = before[-1] if before else ""
        after_article = previous == "the" and len(before) > 1
        geo_preposition = previous in GEO_PREPOSITIONS
        the_after_preposition = after_article and before[-2] in (GEO_PREPOSITIONS | {"for", "from", "of"})
        geo_noun = _word_after(prompt, match.end()) in GEO_NOUNS or previous in GEO_NOUNS
        after_product = any(end <= match.start() and not prompt[end:match.start()].strip() for _, end in product_spans)
        in_list = adjacent_to_market(match)
        pronoun_verb = previous in PRONOUN_VERBS
        written_as_code = token.isupper() and has_lowercase

        ambiguous_reason: Optional[str] = None
        if key not in ENGLISH_COLLISION_CODES:
            # An uppercase code is deliberate. A lowercase one needs geographic context.
            accepted = written_as_code or geo_preposition or the_after_preposition or geo_noun or in_list
        elif key == "it":
            accepted = written_as_code and (geo_preposition or the_after_preposition or geo_noun or after_product or in_list)
            if written_as_code and not accepted:
                ambiguous_reason = f"'{token}' could be Italy or Information Technology, and the request doesn't say which."
        else:  # "us"
            if written_as_code:
                accepted = geo_noun or in_list or not pronoun_verb
                if not accepted:
                    ambiguous_reason = f"'{token}' follows '{previous}', so it may be the pronoun rather than the market."
            else:
                accepted = (the_after_preposition or (geo_noun and not pronoun_verb) or (in_list and not pronoun_verb))
                if not accepted and geo_preposition:
                    ambiguous_reason = f"'{token}' could be the pronoun or the market."

        if accepted:
            found.append((match.start(), market_id))
            phrases.append(_resolved_phrase(token, market_id, catalog))
        elif ambiguous_reason and (geo_preposition or the_after_preposition):
            flag_ambiguous(token, [market_id], ambiguous_reason)
        elif ambiguous_reason:
            # No geographic evidence, so the user hasn't stated geography. The word stays an open
            # question about the request, recorded apart from the geography status.
            ambiguities.append(
                EntityAmbiguity(category="term", term=token, candidates=[market_id], reason=ambiguous_reason)
            )

    return _unique([value for _, value in sorted(found)]), ambiguities, notes, _summarize_geography(phrases)


def _find_kpis(prompt: str, catalog: EntityCatalog) -> List[str]:
    """Catalog KPI names and supported terminology. A longer phrase absorbs any phrase inside it."""
    terms = {k.name.lower() for k in catalog.kpis} | set(KPI_TERMINOLOGY) | set(UNCATALOGUED_METRICS)
    spans: List[Tuple[int, int]] = []
    found: List[Tuple[int, str]] = []
    for term in sorted(terms, key=len, reverse=True):
        for match in _phrase_pattern(term).finditer(prompt):
            if not _overlaps(match.start(), match.end(), spans):
                spans.append((match.start(), match.end()))
                found.append((match.start(), term))

    seen_kpis: Set[str] = set()
    result: List[str] = []
    for _, term in sorted(found):
        entry = catalog.resolve_kpi(term)
        key = entry.kpi_id if entry else term
        if key not in seen_kpis:
            seen_kpis.add(key)
            result.append(term)
    return result


def _find_time_periods(prompt: str) -> List[str]:
    periods = [label for pattern, label in TIME_PATTERNS if re.search(pattern, prompt, re.IGNORECASE)]
    periods += [" ".join(m.group().split()) for m in _STATED_PERIOD.finditer(prompt)]
    return _unique(periods)


def assess_completeness(
    products: List[str],
    markets: List[str],
    kpis: List[str],
    time_periods: List[str],
    ambiguities: Optional[List[EntityAmbiguity]] = None,
) -> Tuple[List[str], float]:
    """Deterministic rule. Its output feeds the Decision Agent's clarification gate."""
    ambiguities = ambiguities or []
    missing: List[str] = []

    def add_gap(category: str, present: List[str], gap: str) -> None:
        # An ambiguous term explains the gap, so it replaces the line rather than adding one.
        related = [a for a in ambiguities if a.category == category]
        if present:
            missing.extend(a.reason for a in related)
        elif related:
            missing.extend(a.reason for a in related)
        else:
            missing.append(gap)

    add_gap("product", products, "Product scope is unspecified (e.g., Nubeqa, Xarelto).")
    add_gap("market", markets, "Target geographic market is unspecified.")
    missing.extend(a.reason for a in ambiguities if a.category == "term")
    if not kpis:
        missing.append("Specific metric / KPI calculations are unspecified.")
    if not time_periods:
        missing.append("Time horizon or refresh frequency is unspecified (e.g. monthly, YTD).")

    confidence = max(0.2, min(1.0, 1.0 - (len(missing) * 0.15)))
    return missing, round(confidence, 2)


def parse_intent(prompt: str, catalog: EntityCatalog) -> ParsedIntent:
    """The deterministic baseline interpretation of a request."""
    products, product_spans, product_ambiguities, product_notes = _find_products(prompt, catalog)
    markets, market_ambiguities, market_notes, geography = _find_geography(prompt, catalog, product_spans)
    kpis = _find_kpis(prompt, catalog)
    dimensions = _unique([label for pattern, label in DIMENSION_PATTERNS if re.search(pattern, prompt, re.IGNORECASE)])
    time_periods = _find_time_periods(prompt)
    ambiguities = product_ambiguities + market_ambiguities
    missing, confidence = assess_completeness(products, markets, kpis, time_periods, ambiguities)

    purpose = f"Analytics request for {', '.join(products) or 'unspecified product'}"
    if markets:
        purpose += f" across {', '.join(markets)}"
    if kpis:
        purpose += f" covering {', '.join(kpis)}"

    return ParsedIntent(
        fields=IntentFields(
            products=products,
            markets=markets,
            kpis=kpis,
            dimensions=dimensions,
            time_periods=time_periods,
            business_purpose=purpose,
            missing_or_ambiguous=missing,
            confidence=confidence,
        ),
        ambiguities=ambiguities,
        interpretation_notes=product_notes + market_notes,
        geography=geography,
    )


def _stem(word: str) -> str:
    word = word.lower()
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
        return word[:-1]
    return word


def _stems(text: str) -> List[str]:
    return [_stem(w) for w in re.findall(r"[A-Za-z0-9]+", text)]


def _stated_in(term: str, prompt: str) -> bool:
    """True when the term's words appear together, in order, in the request."""
    needle, haystack = _stems(term), _stems(prompt)
    if not needle:
        return False
    return any(haystack[i:i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


class _Recorder:
    def __init__(self) -> None:
        self.decisions: List[EnrichmentDecision] = []

    def add(self, category: str, proposed: str, status: EnrichmentStatus, reason: str, normalized: Optional[str] = None) -> None:
        self.decisions.append(
            EnrichmentDecision(category=category, proposed=proposed, normalized=normalized, status=status, reason=reason)
        )

    def reject(self, category: str, proposed: str, reason: str) -> None:
        self.add(category, proposed, EnrichmentStatus.REJECTED, reason)

    def confirm(self, category: str, proposed: str, normalized: str) -> None:
        self.add(category, proposed, EnrichmentStatus.CONFIRMED_BASELINE, "Already in the deterministic baseline.", normalized)

    def accept(self, category: str, proposed: str, normalized: str, reason: str) -> None:
        self.add(category, proposed, EnrichmentStatus.ACCEPTED, reason, normalized)


def _validate_scope(recorder: _Recorder, proposals: List[str], baseline: List[str], category: str, canonical) -> None:
    """Products and markets: the LLM can confirm the baseline, never extend it."""
    catalog_name = "Products" if category == "product" else "Markets"
    for term in proposals:
        value = canonical(term)
        if value is None:
            recorder.reject(category, term, f"Not in the {catalog_name} catalog or approved aliases.")
        elif value in baseline:
            recorder.confirm(category, term, value)
        else:
            recorder.reject(category, term, f"'{value}' is in the catalog, but the request gives no evidence for it.")


def normalize_intent(
    prompt: str,
    baseline: ParsedIntent,
    proposal: Optional[IntentExtraction],
    catalog: EntityCatalog,
) -> BusinessIntent:
    """Build the one validated intent from the baseline and any LLM proposal."""
    base = baseline.fields
    recorder = _Recorder()
    kpis = list(base.kpis)
    dimensions = list(base.dimensions)
    time_periods = list(base.time_periods)
    purpose = base.business_purpose
    unresolved: List[str] = []

    if proposal is not None:
        _validate_scope(recorder, proposal.products, base.products, "product", catalog.canonical_product)
        # A requested scope such as Europe can be confirmed, but only its verified markets enter the intent.
        requested = {p.original_phrase.lower(): p.normalized_scope for p in baseline.geography.phrases}
        _validate_scope(
            recorder,
            proposal.markets,
            base.markets + list(requested.values()),
            "market",
            lambda term: catalog.canonical_market(term) or requested.get(term.strip().lower()),
        )

        known_kpi_ids = {e.kpi_id for e in (catalog.resolve_kpi(k) for k in kpis) if e}
        for mapping in proposal.kpi_mappings:
            label = f"{mapping.requested_phrase} -> {mapping.catalog_kpi_name}"
            entry = _resolve_kpi_mapping(recorder, label, mapping.requested_phrase, mapping.catalog_kpi_name, prompt, catalog)
            if entry is None:
                continue
            longer_phrase = next((k for k in base.kpis if _stated_in(mapping.requested_phrase, k)), None)
            if entry.kpi_id in known_kpi_ids:
                recorder.confirm("kpi", label, entry.name)
            elif longer_phrase:
                # "Net Sales" inside "Net Sales Local" isn't a second request, and adding the approved
                # KPI beside an unapproved one would change the decision.
                recorder.reject("kpi", label, f"'{mapping.requested_phrase}' is part of '{longer_phrase}', which the parser already matched.")
            else:
                known_kpi_ids.add(entry.kpi_id)
                kpis.append(entry.name)
                recorder.accept("kpi", label, entry.name, f"Stated in the request and maps to approved KPI {entry.kpi_id}.")

        for metric in proposal.unmapped_metrics:
            if _stated_in(metric, prompt):
                unresolved.append(metric)
                recorder.reject("kpi", metric, "Stated in the request, but no catalog KPI matches. Listed as unresolved.")
            else:
                recorder.reject("kpi", metric, "Not stated in the request.")

        for dimension in proposal.dimensions:
            _validate_dimension(recorder, dimension, dimensions, prompt, catalog)

        for period in proposal.time_periods:
            if period in time_periods or period.lower() in {t.lower() for t in time_periods}:
                recorder.confirm("time_period", period, period)
            elif not _TIME_TERM.search(period):
                recorder.reject("time_period", period, "Not a time period.")
            elif not _stated_in(period, prompt):
                recorder.reject("time_period", period, "Not stated in the request.")
            else:
                time_periods.append(period.strip())
                recorder.accept("time_period", period, period.strip(), "Stated in the request.")

        purpose = _validate_purpose(recorder, proposal.business_purpose, purpose, base.products, base.markets, kpis, catalog)

    missing, confidence = assess_completeness(base.products, base.markets, kpis, time_periods, baseline.ambiguities)
    decisions = recorder.decisions
    return BusinessIntent(
        raw_prompt=prompt,
        products=base.products,
        markets=base.markets,
        kpis=kpis,
        dimensions=dimensions,
        time_periods=time_periods,
        business_purpose=purpose,
        missing_or_ambiguous=missing,
        confidence=confidence,
        ambiguities=baseline.ambiguities,
        interpretation_notes=baseline.interpretation_notes,
        geography=baseline.geography,
        unresolved_terms=_unique(unresolved),
        resolution=IntentResolution(
            original_request=prompt,
            deterministic_intent=base,
            llm_proposal=proposal,
            accepted=[d for d in decisions if d.status == EnrichmentStatus.ACCEPTED],
            confirmed=[d for d in decisions if d.status == EnrichmentStatus.CONFIRMED_BASELINE],
            rejected=[d for d in decisions if d.status == EnrichmentStatus.REJECTED],
        ),
    )


def _resolve_kpi_mapping(
    recorder: _Recorder, label: str, phrase: str, kpi_name: str, prompt: str, catalog: EntityCatalog
) -> Optional[KpiEntry]:
    if not _stated_in(phrase, prompt):
        recorder.reject("kpi", label, f"'{phrase}' is not stated in the request.")
        return None
    entry = catalog.resolve_kpi(kpi_name)
    if entry is None or entry.name.lower() != kpi_name.strip().lower():
        recorder.reject("kpi", label, f"'{kpi_name}' is not a catalog KPI name.")
        return None
    if not entry.canonical_approved:
        recorder.reject("kpi", label, f"{entry.kpi_id} is not an approved canonical KPI.")
        return None
    shared = (set(_stems(phrase)) & set(_stems(kpi_name))) - GENERIC_KPI_WORDS
    if not shared:
        recorder.reject("kpi", label, f"The phrase shares no specific word with '{kpi_name}'.")
        return None
    return entry


def _validate_dimension(
    recorder: _Recorder, dimension: str, dimensions: List[str], prompt: str, catalog: EntityCatalog
) -> None:
    if dimension.lower() in {d.lower() for d in dimensions}:
        recorder.confirm("dimension", dimension, dimension)
    elif not _stated_in(dimension, prompt):
        recorder.reject("dimension", dimension, "Not stated in the request.")
    elif catalog.canonical_product(dimension) or catalog.canonical_market(dimension) or catalog.resolve_kpi(dimension):
        recorder.reject("dimension", dimension, "This is a product, market or KPI, not a dimension.")
    else:
        dimensions.append(dimension.strip())
        recorder.accept("dimension", dimension, dimension.strip(), "Stated in the request.")


def _validate_purpose(
    recorder: _Recorder,
    proposed: str,
    fallback: str,
    products: List[str],
    markets: List[str],
    kpis: List[str],
    catalog: EntityCatalog,
) -> str:
    """The purpose is descriptive, but it must not introduce scope the intent doesn't have."""
    text = proposed.strip()
    if not text:
        recorder.reject("business_purpose", proposed, "Empty.")
        return fallback
    mentioned = parse_intent(text, catalog).fields
    known_kpi_ids = {e.kpi_id for e in (catalog.resolve_kpi(k) for k in kpis) if e}
    extra_kpis = [k for k in mentioned.kpis if (e := catalog.resolve_kpi(k)) and e.kpi_id not in known_kpi_ids]
    extra = (
        [p for p in mentioned.products if p not in products]
        + [m for m in mentioned.markets if m not in markets]
        + extra_kpis
    )
    if extra:
        recorder.reject("business_purpose", text, f"Introduces scope absent from the intent: {extra}.")
        return fallback
    recorder.accept("business_purpose", text, text, "Descriptive only. It doesn't affect any decision.")
    return text


def llm_prompt_vocabulary(catalog: EntityCatalog) -> Dict[str, List[str]]:
    """The catalog terms offered to the model."""
    return {
        "products": [name for _, name in catalog.products] + list(catalog.product_scopes),
        "markets": list(catalog.market_ids) + list(catalog.regions) + list(catalog.market_scopes),
        "canonical_kpis": catalog.canonical_kpi_names,
    }
