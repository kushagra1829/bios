import logging
from typing import Dict, Any, Optional
from backend.app.approvals.schemas import ApprovalActionType, UserRole

logger = logging.getLogger(__name__)


class ApprovalRoutingEngine:
    """
    Intelligent routing engine for human approvals.
    Maps consequential action requests to the designated authority role based on:
      - Action type
      - Asset criticality
      - Endorsement / certification status
      - Downstream lineage dependencies
      - Governance risk level
    """

    @classmethod
    def resolve_required_role(
        cls,
        action_type: ApprovalActionType,
        evidence: Optional[Dict[str, Any]] = None,
        blockers: Optional[list] = None,
    ) -> UserRole:
        evidence = evidence or {}
        blockers = blockers or []

        # 1. Governance Exceptions and Active Blockers strictly require Governance Reviewer
        if action_type == ApprovalActionType.GOVERNANCE_EXCEPTION or len(blockers) > 0:
            return UserRole.BI_GOVERNANCE_REVIEWER

        # 2. Retirement Routing
        if action_type == ApprovalActionType.RETIRE:
            # If asset is endorsed, high-reach, or has downstream dependents -> BI_GOVERNANCE_REVIEWER
            is_endorsed = evidence.get("endorsement") in ("certified", "promoted")
            downstream = evidence.get("lineage", {}).get("downstream_dependent_count", 0)
            audience = evidence.get("reach", {}).get("estimated_audience", 0)

            if is_endorsed or downstream > 0 or audience >= 500:
                return UserRole.BI_GOVERNANCE_REVIEWER
            return UserRole.ASSET_OWNER

        # 3. KPI / Semantic Model Changes -> DOMAIN_STEWARD
        if action_type in (ApprovalActionType.CHANGE_KPI, ApprovalActionType.CHANGE_MODEL):
            return UserRole.DOMAIN_STEWARD

        # 4. Migration Routing
        if action_type == ApprovalActionType.MIGRATE:
            complexity = evidence.get("complexity", "medium")
            if complexity == "high" or evidence.get("business_value") == "high":
                return UserRole.BI_GOVERNANCE_REVIEWER
            return UserRole.DOMAIN_STEWARD

        # 5. Consolidation Routing
        if action_type == ApprovalActionType.CONSOLIDATE:
            if evidence.get("is_cross_domain", False) or evidence.get("endorsement") == "certified":
                return UserRole.BI_GOVERNANCE_REVIEWER
            return UserRole.ASSET_OWNER

        # 6. Artifact Publication
        if action_type == ApprovalActionType.PUBLISH_ARTIFACT:
            if evidence.get("is_certified_request", False) or evidence.get("estimated_audience", 0) >= 500:
                return UserRole.BI_GOVERNANCE_REVIEWER
            return UserRole.ASSET_OWNER

        # 7. Asset Reuse and Modification
        if action_type in (ApprovalActionType.REUSE, ApprovalActionType.MODIFY):
            return UserRole.ASSET_OWNER

        # 8. New Asset Provisioning
        if action_type == ApprovalActionType.BUILD_NEW:
            return UserRole.DOMAIN_STEWARD

        # Default fallback
        return UserRole.BI_GOVERNANCE_REVIEWER


routing_engine = ApprovalRoutingEngine()

