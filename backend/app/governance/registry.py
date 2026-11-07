from typing import Dict, List, Optional
from backend.app.governance.rules.base import BaseGovernanceRule
from backend.app.governance.schemas import RuleId, GovernanceRuleInfo
from backend.app.governance.rules.rule_001_reuse import ReuseBeforeBuildRule
from backend.app.governance.rules.rule_002_kpi import CanonicalKpiRule
from backend.app.governance.rules.rule_003_owner import OwnerRequiredRule
from backend.app.governance.rules.rule_004_lineage import LineageRequiredRule
from backend.app.governance.rules.rule_005_high_reach import HighReachRequiresTrustRule
from backend.app.governance.rules.rule_006_migration_waste import DoNotMigrateWasteRule
from backend.app.governance.rules.rule_007_ai_readiness import AiReadySemanticsRule
from backend.app.governance.rules.rule_008_explainability import ExplainLifecycleActionRule


class RuleRegistry:
    """
    Central registry for all deterministic governance rules in BIOS.
    Provides lookup, introspection, and instantiation of rules.
    """

    def __init__(self):
        self._rules: Dict[RuleId, BaseGovernanceRule] = {}
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        default_rules = [
            ReuseBeforeBuildRule(),
            CanonicalKpiRule(),
            OwnerRequiredRule(),
            LineageRequiredRule(),
            HighReachRequiresTrustRule(),
            DoNotMigrateWasteRule(),
            AiReadySemanticsRule(),
            ExplainLifecycleActionRule(),
        ]
        for rule in default_rules:
            self.register(rule)

    def register(self, rule: BaseGovernanceRule) -> None:
        self._rules[rule.rule_id] = rule

    def get(self, rule_id: RuleId | str) -> Optional[BaseGovernanceRule]:
        if isinstance(rule_id, str):
            try:
                rule_id = RuleId(rule_id)
            except ValueError:
                return None
        return self._rules.get(rule_id)

    def get_all(self) -> List[BaseGovernanceRule]:
        return list(self._rules.values())

    def get_all_infos(self) -> List[GovernanceRuleInfo]:
        return [rule.get_info() for rule in self._rules.values()]


# Global registry singleton
registry = RuleRegistry()

