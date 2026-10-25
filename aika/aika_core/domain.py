"""The answer-type table.

Six question shapes drive behaviour in nearly fifty places: which evidence is required,
which cards are preferred, which claim types matter, whether the answer must compare
companies or disclose risk. Before this module each rule was re-stated inline with its own
``if plan.answer_type == ...`` chain, so adding a seventh shape (or changing what one
shape needs) meant finding every chain.

Everything that is *declarative* about an answer type lives here. Behaviour that needs code
(how to rank comparison cards, for instance) stays where it is and is dispatched by name.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The shapes a question can take. ``question_planner`` validates LLM output against this.
ANSWER_TYPES: tuple[str, ...] = (
    "topic_to_company",
    "company_compare",
    "risk_analysis",
    "industry_bottleneck",
    "company_profile",
    "thematic_research",
)

DEFAULT_ANSWER_TYPE = "thematic_research"


@dataclass(frozen=True)
class AnswerTypeProfile:
    """What one answer type needs from retrieval, verification and rendering."""

    name: str
    label: str
    coverage: tuple[str, ...] = ()
    claim_types: tuple[str, ...] = ()
    #: relation names this shape prefers, in priority order
    relations: tuple[str, ...] = ()
    needs_comparison: bool = False
    needs_risk: bool = False
    #: true when the answer must name concrete companies to be useful
    needs_company_exposure: bool = False
    #: true when the shape is answered from mechanism/industry commentary, not company rows
    research_oriented: bool = False
    extra: dict[str, str] = field(default_factory=dict)


PROFILES: dict[str, AnswerTypeProfile] = {
    "topic_to_company": AnswerTypeProfile(
        name="topic_to_company",
        label="主题到公司",
        coverage=("company_exposure",),
        claim_types=("company_exposure", "bottleneck"),
        relations=("PRODUCES", "SUPPLIES_TO", "BENEFITS_FROM"),
        needs_company_exposure=True,
    ),
    "company_compare": AnswerTypeProfile(
        name="company_compare",
        label="公司对比",
        coverage=("company_coverage",),
        claim_types=("company_exposure", "risk", "indicator"),
        relations=("PRODUCES", "SUPPLIES_TO", "COMPETES_WITH"),
        needs_comparison=True,
        needs_company_exposure=True,
    ),
    "risk_analysis": AnswerTypeProfile(
        name="risk_analysis",
        label="风险分析",
        coverage=("risk_evidence",),
        claim_types=("risk", "counter_evidence"),
        relations=("DISCLOSES_RISK",),
        needs_risk=True,
    ),
    "industry_bottleneck": AnswerTypeProfile(
        name="industry_bottleneck",
        label="产业瓶颈",
        coverage=("mechanism_evidence",),
        claim_types=("bottleneck", "mechanism", "indicator"),
        relations=("CONSTRAINS", "REQUIRES"),
        research_oriented=True,
    ),
    "company_profile": AnswerTypeProfile(
        name="company_profile",
        label="公司画像",
        # a profile is answered from that company's own rows, so it requires no extra
        # coverage beyond what the retriever already filtered for
        coverage=(),
        claim_types=("company_exposure", "indicator"),
        relations=("PRODUCES", "HAS_METRIC"),
        needs_company_exposure=True,
    ),
    "thematic_research": AnswerTypeProfile(
        name="thematic_research",
        label="主题研究",
        coverage=("mechanism_evidence",),
        claim_types=("mechanism", "bottleneck", "indicator"),
        relations=("CONSTRAINS", "REQUIRES"),
        research_oriented=True,
    ),
}


def profile_for(answer_type: str) -> AnswerTypeProfile:
    """Return the profile for an answer type, falling back to thematic research."""
    return PROFILES.get(str(answer_type or ""), PROFILES[DEFAULT_ANSWER_TYPE])


#: Coverage keys in the order downstream consumers expect them. Keeping the order fixed
#: means a plan's gaps and query suffixes do not reshuffle when a rule is added.
_COVERAGE_ORDER: tuple[str, ...] = (
    "company_coverage",
    "risk_evidence",
    "metric_evidence",
    "company_exposure",
    "mechanism_evidence",
)


def required_coverage(
    answer_type: str,
    *,
    needs_comparison: bool = False,
    needs_risk: bool = False,
    needs_metrics: bool = False,
    relations: tuple[str, ...] | list[str] = (),
) -> list[str]:
    """The coverage keys a plan must satisfy, in a stable order.

    The flags win over the answer type: a thematic question that says "compare A and B"
    still needs company coverage, because that is what the answer will be judged on.
    """
    profile = profile_for(answer_type)
    wanted = set(profile.coverage)
    if needs_comparison or profile.needs_comparison:
        wanted.add("company_coverage")
    if needs_risk or profile.needs_risk:
        wanted.add("risk_evidence")
    if needs_metrics or {"HAS_METRIC", "HAS_INDICATOR"} & set(relations):
        wanted.add("metric_evidence")
    return [key for key in _COVERAGE_ORDER if key in wanted]
