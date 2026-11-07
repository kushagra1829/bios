from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.governance.schemas import GovernanceFindingCreate, RuleId, GovernanceRuleInfo


class BaseGovernanceRule(ABC):
    """
    Abstract base class for all BIOS deterministic governance rules.
    Every rule must be deterministic, reproducible, independent, and explainable.
    """

    rule_id: RuleId
    rule_name: str
    rule_description: str
    priority: str = "high"
    category: str
    target_entities: List[str]

    def get_info(self) -> GovernanceRuleInfo:
        return GovernanceRuleInfo(
            rule_id=self.rule_id.value,
            rule_name=self.rule_name,
            rule_description=self.rule_description,
            priority=self.priority,
            category=self.category,
            target_entities=self.target_entities,
            thresholds=self.get_thresholds(),
        )

    def get_thresholds(self) -> Dict[str, Any]:
        """Return configurable or standard thresholds used by this rule."""
        return {}

    @abstractmethod
    def evaluate(self, db: Session, context: Optional[Dict[str, Any]] = None) -> List[GovernanceFindingCreate]:
        """
        Execute deterministic rule evaluation against the relational database.
        Returns a list of structured findings with evidence bundles.
        """
        pass

