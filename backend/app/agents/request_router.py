"""
Deterministic request-type routing.

BIOS receives four kinds of request, and they need different workflows:

  DATA_QUESTION        "What were Nubeqa sales in Germany in Q1 2026?"  -> query source records
  ASSET_REQUEST        "I need a Nubeqa sales dashboard for Germany."   -> discover, reuse first
  GOVERNANCE_QUESTION  "Why is AST-0268 blocked?"                        -> read governance findings
  MIGRATION_QUESTION   "Which Tableau workbooks should be migrated?"     -> read migration records

A request can carry several ("Check Nubeqa sales and tell me whether we need a new dashboard"),
so classify() returns every type it finds, primary first, with the phrases that decided it.
The rules are plain regular expressions so the routing is reproducible and independently testable;
no LLM is consulted, which keeps routing identical across providers.
"""
import re
from dataclasses import dataclass, field
from typing import List

from backend.app.agents.schemas import RequestType

ASSET_ID = re.compile(r"\b(?:AST|SM)-\d{3,4}\b", re.IGNORECASE)

# Nouns that name an analytics asset. "view" and "analysis" are deliberately excluded: they are
# as often used for data ("view sales") as for assets.
ASSET_NOUN = re.compile(
    r"\b(?:dashboards?|reports?|scoreboards?|scorecards?|workbooks?|apps?|power\s*bi\s+(?:reports?|apps?|dashboards?)|"
    r"trackers?|cockpits?|analytics\s+(?:assets?|solutions?|products?)|assets?|visuali[sz]ations?|reporting(?:\s+layers?)?)\b",
    re.IGNORECASE,
)
# Verbs that ask BIOS to provision, find, change or rationalise an asset.
ASSET_ACTION = re.compile(
    r"\b(?:build|create|make|develop|design|set\s+up|spin\s+up|stand\s+up|need|want|require|request|"
    r"give\s+me|provide|deliver|produce|new|another|find|locate|search|is\s+there|are\s+there|do\s+we\s+have|"
    r"existing|reuse|re-use|use|recommend|suggest|already\s+have|similar|duplicates?|duplicated|overlapping|"
    r"consolidat\w*|merge|combine|modify|modifi\w*|extend|enhance|update|add|change|replace|replicate|copy|clone|"
    r"promot\w*|approv\w*|evaluat\w*|rationali\w*|decommission\w*|retir\w*)\b",
    re.IGNORECASE,
)
DUPLICATION_QUESTION = re.compile(
    r"\b(?:already\s+have|similar|duplicates?|duplicated|overlapping|overlap|redundant|consolidat\w*|merge|rationali[sz]\w*)\b",
    re.IGNORECASE,
)

GOVERNANCE_TERMS = re.compile(
    r"\b(?:owners?|owns|ownership|owned|unowned|kpis?|(?:is|are)\s+(?:certified|promoted|endorsed)|accountable|steward\w*|blocked|blockers?|blocking|governance|governed|"
    r"compliance|compliant|non-compliant|findings?|violations?|violat\w+|rule-\d{3}|non-canonical|canonical|"
    r"lineage|endorse\w*|unendorsed|certif\w+\s+(?:status|share)|high[-\s]reach|audience\s+reach|waivers?|"
    r"ai[-\s]read\w*|ai\s+readiness|semantic\s+models?|poor\s+names|ambiguous\s+dates|implicit\s+measures|"
    r"definitions?|defined|approved\s+kpis?|kpis?\s+(?:approved|conflict\w*|variants?)|conflicting|conflicts?|"
    r"local\s+variants?|kpi\s+catalog\w*|risk\s+of\s+retirement|explainab\w+|trust(?:ed|worthy)?|"
    r"refresh\s+(?:status|failures?)|failed\s+refresh)\b",
    re.IGNORECASE,
)
# A question that asks about the estate's state, rather than for something to be built.
GOVERNANCE_QUESTION_FORM = re.compile(
    r"^\s*(?:why|which|what|who|how\s+many|list|show|is|are|does|do|has|have|tell\s+me|explain|give\s+me|identify|"
    r"find|count|summari[sz]e)\b",
    re.IGNORECASE,
)

MIGRATION_TERMS = re.compile(
    r"\b(?:migrat\w*|tableau|retire\w*|retirement|decommission\w*|sunset\w*|backlog|modernis\w*|moderniz\w*|"
    r"move\w*\s+(?:\w+\s+){0,3}to\s+power\s*bi|rebuild\s+on\s+(?:a\s+)?shared|replatform\w*)\b",
    re.IGNORECASE,
)

MEASURE_TERMS = re.compile(
    r"\b(?:sales|numbers|figures|revenue|revenues|net\s+sales|units?|unit\s+volumes?|volumes?|shipped|shipments?|forecasts?|forecasted|"
    r"actuals?|variance|market\s+access(?:\s+coverage)?|access\s+coverage|otif|on[-\s]time\s+in[-\s]full|"
    r"inventory|weeks\s+of\s+(?:inventory|cover|supply)|growth|market\s+share|profit\w*|margins?|"
    r"gross[-\s]to[-\s]net|prescriptions?|patients?|price|pricing|budget|operating\s+contribution|ebitda?|"
    r"share\s+of\s+voice|adherence|nps|roi|costs?|spend|headcount)\b",
    re.IGNORECASE,
)
DATA_QUESTION_FORM = re.compile(
    r"\b(?:what\s+(?:were|was|is|are|did)|how\s+(?:much|many|did|does|do|has|have)|show(?:\s+me)?|compare|comparison|"
    r"versus|vs\.?|trend\w*|total|sum|average|avg|mean|rank\w*|top\s+\d+|highest|lowest|largest|smallest|best|worst|"
    r"biggest|check|give\s+me\s+(?:the\s+)?(?:[\w-]+\s+){0,3}(?:numbers|figures)|calculate|tell\s+me\s+(?:the\s+)?(?:sales|numbers)|"
    r"year[-\s]over[-\s]year|yoy|month[-\s]over[-\s]month|mom|change|increase|decrease|growth|"
    r"which\s+(?:product|market|country|brand|medicine)s?\s+(?:had|has|have|was|were|is|are|did|shows?|sold|recorded|generated|delivered|performed))\b",
    re.IGNORECASE,
)
IMPERATIVE_BUILD = re.compile(
    r"^\s*(?:please\s+)?(?:build|create|develop|design|set\s+up|make|stand\s+up|spin\s+up|produce)\b", re.IGNORECASE
)
IMPERATIVE_CHANGE = re.compile(
    r"^\s*(?:please\s+)?(?:approve|promote|update|modify|extend|add|change|publish|edit|enhance|certify|endorse|include)\b",
    re.IGNORECASE,
)
COMPARISON_FORM = re.compile(
    r"\b(?:compare|comparison|versus|vs\.?|rank\w*|highest|lowest|top\s+\d+|best[-\s]selling|which\s+(?:product|market|country|brand)s?\b)",
    re.IGNORECASE,
)
# "...and tell me whether we need a new dashboard", "Show sales and recommend a dashboard"
COMBINED_ASSET_CLAUSE = re.compile(
    r"\b(?:whether|if|do|should)\s+(?:we|i)\s+(?:still\s+)?(?:need|build|create|require|want)\b|\bnew\s+(?:dashboard|report|scoreboard|scorecard)\b|"
    r"\b(?:and\s+)?(?:recommend|find|suggest|look\s+for|check\s+for)\s+(?:an?\s+)?(?:existing\s+)?(?:certified\s+)?(?:dashboards?|reports?|scoreboards?|scorecards?|assets?)\b",
    re.IGNORECASE,
)
TEMPORAL_DATA_FILTER = re.compile(
    r"\b(?:(?:in|of|for|during)\s+(?:20\d\d|q[1-4](?:\s+20\d\d)?|h[1-2](?:\s+20\d\d)?|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)|20\d\d)\b",
    re.IGNORECASE,
)
# Requests to put data into an asset: "a dashboard showing sales", "sales dashboard".
ASSET_PROVISION = re.compile(
    r"\b(?:build|create|make|develop|design|set\s+up|need|want|require|request|give\s+me|provide|deliver|produce|"
    r"new|another|replicate|copy|clone)\b[^.?!]*\b(?:dashboards?|reports?|scoreboards?|scorecards?|workbooks?|apps?|"
    r"trackers?|cockpits?|visuali[sz]ations?)\b",
    re.IGNORECASE,
)
ASSET_CHANGE = re.compile(
    r"\b(?:modify|extend|enhance|update|add|change|consolidat\w*|merge|combine|reuse|re-use|use)\b",
    re.IGNORECASE,
)
ASSET_DISCOVERY = re.compile(
    r"\b(?:find|locate|search\s+for|is\s+there|are\s+there|do\s+we\s+have|any\s+existing|existing|which\s+(?:dashboard|report|asset)s?\s+should\s+i\s+use|"
    r"recommend\s+(?:a|an)\s+(?:dashboard|report))\b",
    re.IGNORECASE,
)


@dataclass
class RouteResult:
    request_types: List[RequestType] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    asset_ids: List[str] = field(default_factory=list)
    duplication_question: bool = False

    @property
    def primary(self) -> RequestType:
        return self.request_types[0] if self.request_types else RequestType.ASSET_REQUEST


def _first(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    return match.group(0) if match else ""


def classify(prompt: str) -> RouteResult:
    """Classify a request. Deterministic: the same text always yields the same route."""
    text = " ".join((prompt or "").split())
    result = RouteResult()
    result.asset_ids = list(dict.fromkeys(m.upper() for m in ASSET_ID.findall(text)))
    if not text:
        result.request_types = [RequestType.ASSET_REQUEST]
        result.evidence.append("Empty request: defaulted to the asset workflow, which asks for clarification.")
        return result

    asset_noun = _first(ASSET_NOUN, text)
    provision = _first(ASSET_PROVISION, text)
    change = _first(ASSET_CHANGE, text)
    discovery = _first(ASSET_DISCOVERY, text)
    governance = _first(GOVERNANCE_TERMS, text)
    migration = _first(MIGRATION_TERMS, text)
    measure = _first(MEASURE_TERMS, text)
    data_form = _first(DATA_QUESTION_FORM, text)
    question_form = bool(GOVERNANCE_QUESTION_FORM.search(text)) or text.rstrip().endswith("?")
    combined = _first(COMBINED_ASSET_CLAUSE, text)
    # A question about existing overlap ("We already have three similar dashboards"), not a request
    # to create a duplicate ("Create a duplicate monthly report"), which is an ordinary build request.
    creating = re.search(r"\b(?:build|create|make|develop|design|set\s+up|new|another|replicate|clone)\b", text, re.IGNORECASE)
    result.duplication_question = bool(DUPLICATION_QUESTION.search(text)) and bool(asset_noun) and not creating

    types: List[RequestType] = []

    def add(kind: RequestType, why: str) -> None:
        if kind not in types:
            types.append(kind)
            result.evidence.append(why)

    # 0. Imperative requests to build something, or to change a named asset, are asset requests
    # whatever nouns follow ("Build new Power BI reporting layer...", "Promote AST-0088 to certified").
    imperative_build = IMPERATIVE_BUILD.match(text)
    imperative_change = IMPERATIVE_CHANGE.match(text)
    if imperative_build and not re.search(r"\b(?:replacement|replace|migrat\w*)\b", text, re.IGNORECASE):
        add(RequestType.ASSET_REQUEST, f"Imperative build request: '{imperative_build.group(0).strip()}'.")
    elif imperative_change and (result.asset_ids or imperative_change.group(0).strip().lower().endswith("approve")):
        add(RequestType.ASSET_REQUEST, f"Imperative change to {', '.join(result.asset_ids)}: '{imperative_change.group(0).strip()}'.")

    # 1. Migration and lifecycle questions. "Retire" and "migrate" outrank asset nouns, because
    # "Which dashboards should be migrated?" is about existing assets, not a new one.
    if migration and not provision:
        if (asset_noun or result.asset_ids) and not question_form:
            add(RequestType.ASSET_REQUEST, f"Asks to evaluate or act on asset lifecycle: '{migration}'.")
        add(RequestType.MIGRATION_QUESTION, f"Migration/lifecycle term '{migration}'.")
    elif migration and provision and re.search(r"\b(?:migrat\w*|replace\w*|replacement|replatform\w*)\b", text, re.IGNORECASE):
        # "Create a Power BI replacement for our Tableau workbook" asks for an asset AND is a migration.
        add(RequestType.ASSET_REQUEST, f"Asks to provision '{provision}' as part of a migration.")
        add(RequestType.MIGRATION_QUESTION, f"Migration term '{migration}'.")

    # 2. Asset provisioning, discovery, change and duplication requests.
    if provision and not (types and types[0] == RequestType.MIGRATION_QUESTION and not re.search(r"\b(?:build|create|new|need)\b", text, re.IGNORECASE)):
        if combined and (data_form or measure) and not provision.lower().startswith(("build", "create", "make", "develop", "design")):
            pass  # handled as a combined data + asset request below
        else:
            add(RequestType.ASSET_REQUEST, f"Asks to provision an asset: '{provision}'.")
    if asset_noun and (discovery or result.duplication_question) and RequestType.ASSET_REQUEST not in types:
        if combined and (measure or data_form):
            pass  # handled as a combined data + asset request below
        elif not (governance and question_form and not discovery and not result.duplication_question):
            add(RequestType.ASSET_REQUEST, f"Asks about existing assets: '{discovery or 'duplicate/similar assets'}'.")
    if result.asset_ids and change and RequestType.ASSET_REQUEST not in types and not (governance and question_form and re.match(r"^\s*(?:why|what|which|who|is|are|does)\b", text, re.IGNORECASE)):
        add(RequestType.ASSET_REQUEST, f"Asks to change asset {', '.join(result.asset_ids)} ('{change}').")
    if (asset_noun and change and RequestType.ASSET_REQUEST not in types and not question_form):
        add(RequestType.ASSET_REQUEST, f"Asks to change an asset ('{change}').")

    # A bare noun phrase such as "Xarelto US net sales dashboard, monthly." is an asset request,
    # even when it also contains instructions about governance.
    if asset_noun and not question_form and not types and not migration:
        add(RequestType.ASSET_REQUEST, f"Names an asset ('{asset_noun}') without asking a question.")

    # 3. Governance questions: about owners, rules, KPIs, lineage, endorsement, readiness or an asset ID.
    if governance and (question_form or not types):
        if RequestType.ASSET_REQUEST not in types or question_form and not provision:
            add(RequestType.GOVERNANCE_QUESTION, f"Governance term '{governance}' in a question.")
        elif re.search(r"\b(?:owner|unowned|accountable|blocked|blocker)\b", text, re.IGNORECASE):
            # "Build a dashboard using an asset with no accountable owner": an asset request whose
            # governance constraint must be explained. The asset workflow stays primary.
            add(RequestType.GOVERNANCE_QUESTION, f"Governance constraint '{governance}' stated in an asset request.")
    if result.asset_ids and not types:
        add(RequestType.GOVERNANCE_QUESTION, f"Asks about asset {', '.join(result.asset_ids)}.")

    # 4. Business data questions: requests asking for actual business metrics, sales, revenue,
    # performance, trends, quantities, forecasts or comparisons, unless the user explicitly requests an asset.
    comparison_only = bool(COMPARISON_FORM.search(text)) and not asset_noun
    temporal_filter = _first(TEMPORAL_DATA_FILTER, text)
    is_data_inquiry = (
        bool(measure)
        and (bool(data_form) or bool(temporal_filter) or (question_form and not governance))
        and not asset_noun
        and not provision
        and not imperative_build
        and not (result.asset_ids and change)
    )
    is_data = is_data_inquiry or comparison_only
    if is_data or (combined and measure):
        if combined:
            # Combined intent: answer data question first, and evaluate asset request second
            if RequestType.BUSINESS_DATA_QUESTION not in types and RequestType.DATA_QUESTION not in types:
                types.insert(0, RequestType.BUSINESS_DATA_QUESTION)
                result.evidence.insert(0, f"Asks for measure '{measure or 'figures'}'.")
            if RequestType.ASSET_REQUEST not in types:
                add(RequestType.ASSET_REQUEST, f"Asks separately to evaluate or recommend an asset: '{combined}'.")
        elif not types:
            add(RequestType.BUSINESS_DATA_QUESTION, f"Asks for measure '{measure or 'unspecified'}' ('{data_form or temporal_filter or 'stated measure'}').")

    if not types:
        # Nothing decisive: the asset workflow asks the clarifying questions.
        add(RequestType.ASSET_REQUEST, "No decisive data, governance or migration signal; using the asset workflow.")

    result.request_types = types
    return result


# ---------------------------------------------------------------------------- title topics
TITLE_SUFFIXES = {"copy", "final", "v2", "legacy", "new", "monthly"}
TITLE_MARKET_TOKENS = {"us", "global", "emea"}


def title_topic_vocabulary(asset_names: List[str], product_names: List[str]) -> List[str]:
    """Topics that asset titles carry after the product, market tag and version suffix are removed."""
    products = sorted((p.lower() for p in product_names), key=len, reverse=True)
    topics = set()
    for name in asset_names:
        text = name.lower().replace(" - ", " ")
        for product in products:
            if text.startswith(product + " "):
                text = text[len(product) + 1:]
                break
        tokens = [t for t in text.split() if t not in TITLE_SUFFIXES and t not in TITLE_MARKET_TOKENS]
        if tokens:
            topics.add(" ".join(tokens))
    return sorted(topics, key=lambda t: (-len(t), t))


def _topic_pattern(topic: str) -> re.Pattern:
    parts = [re.escape(p) for p in re.split(r"[\s-]+", topic) if p]
    parts = [r"(?:mgmt|management)" if p == "mgmt" else p for p in parts]
    return re.compile(r"(?<!\w)" + r"[\s-]+".join(parts) + r"(?!\w)", re.IGNORECASE)


def find_title_topics(prompt: str, vocabulary: List[str]) -> List[str]:
    """Longest asset-title topics the request states, without overlaps. 'Budget Management' -> 'budget mgmt'."""
    spans: List[tuple] = []
    found: List[tuple] = []
    for topic in vocabulary:
        for m in _topic_pattern(topic).finditer(prompt):
            if not any(m.start() < e and m.end() > s for s, e in spans):
                spans.append((m.start(), m.end()))
                found.append((m.start(), topic))
    return [t for _, t in sorted(found)]


def title_has_topic(asset_name: str, topic: str) -> bool:
    return bool(_topic_pattern(topic).search(asset_name))
