# ResultPresentation 的稳定公开导入面。

from product.backend.core.verification.breakpoints import BreakpointLocator

from .builder import (
    _actual_identity,
    _breakpoint_detail,
    ResultPresentationBuilder,
    build_result_presentation,
    locate_published_breakpoints,
)
from .explanations import _claim_boundary_with_repair
from .models import (
    PresentedCaseVerdict,
    ResultClaimBoundary,
    ResultConfirmedImpact,
    ResultChangeVerification,
    ResultDiagnosis,
    ResultEvidenceExplanation,
    ResultEvidenceSource,
    ResultPresentation,
    ResultPresentationIssue,
    ResultRelevantIntent,
    ResultWitnessItem,
)

__all__ = [
    "BreakpointLocator",
    "locate_published_breakpoints",
    "PresentedCaseVerdict",
    "ResultClaimBoundary",
    "ResultConfirmedImpact",
    "ResultChangeVerification",
    "ResultDiagnosis",
    "ResultEvidenceExplanation",
    "ResultEvidenceSource",
    "ResultPresentation",
    "ResultPresentationBuilder",
    "ResultPresentationIssue",
    "ResultRelevantIntent",
    "ResultWitnessItem",
    "build_result_presentation",
]
