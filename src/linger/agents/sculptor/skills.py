"""Explicit assignment of Sculptor's proposal tasks and their contracts."""

from src.linger.agents.sculptor.chapter_cue_models import (
    ChapterCueRevision,
    ChapterCueRevisionInput,
)
from src.linger.agents.sculptor.research_models import (
    ErrorAnalysis,
    ErrorAnalysisInput,
    ResearchInput,
    ResearchSpecification,
)
from src.linger.agents.sculptor.models import (
    AccountScopedMemories,
    CurationProposal,
    NoCurationProposal,
    SculptorResponse,
)
from src.linger.agents.sculptor.surfacing_models import (
    Defer,
    DoNotSurface,
    SurfaceNow,
    SurfacingDecision,
    SurfacingInput,
)
from src.linger.agents.skills import RuntimeSkill, load_instructions
from src.linger.prompts import load_prompt

PACKAGE = "src.linger.agents.sculptor"
SHARED_INSTRUCTIONS = load_prompt("agents", "sculptor")

MEMORY_CURATION = RuntimeSkill[AccountScopedMemories, SculptorResponse](
    role="Sculptor",
    name="memory-curation",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/memory-curation/SKILL.md"),
    input_type=AccountScopedMemories,
    output_type=(CurationProposal, NoCurationProposal),
    validators=(
        "SCULPTOR_RESPONSE_ADAPTER",
        "src.linger.orchestration.curation.propose_curation",
    ),
)

MEMORY_SURFACING = RuntimeSkill[SurfacingInput, SurfacingDecision](
    role="Sculptor",
    name="memory-surfacing",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/memory-surfacing/SKILL.md"),
    input_type=SurfacingInput,
    output_type=(SurfaceNow, Defer, DoNotSurface),
    validators=(
        "src.linger.agents.sculptor.surfacing_models.validate_surfacing_decision",
    ),
)

CHAPTER_CUES = RuntimeSkill[ChapterCueRevisionInput, ChapterCueRevision](
    role="Sculptor",
    name="chapter-cues",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/chapter-cues/SKILL.md"),
    input_type=ChapterCueRevisionInput,
    output_type=ChapterCueRevision,
    validators=("src.linger.agents.sculptor.chapter_cue_models.task_errors",),
    # Thirty-six chapters of word counts leave more room for a budget slip.
    output_retries=2,
)

RETRIEVAL_ERROR_ANALYSIS = RuntimeSkill[ErrorAnalysisInput, ErrorAnalysis](
    role="Sculptor",
    name="retrieval-error-analysis",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/retrieval-error-analysis/SKILL.md"),
    input_type=ErrorAnalysisInput,
    output_type=ErrorAnalysis,
    validators=("src.linger.agents.sculptor.research_models.error_analysis_errors",),
    output_retries=2,
)

RETRIEVAL_RESEARCH = RuntimeSkill[ResearchInput, ResearchSpecification](
    role="Sculptor",
    name="retrieval-research",
    shared_instructions=SHARED_INSTRUCTIONS,
    instructions=load_instructions(PACKAGE, "skills/retrieval-research/SKILL.md"),
    input_type=ResearchInput,
    output_type=ResearchSpecification,
    tools=("web_search", "get_page"),
    capabilities=("src.linger.agents.sculptor.research_search.ResearchSearch",),
    validators=("src.linger.agents.sculptor.research_models.specification_errors",),
    output_retries=2,
)

SKILLS = (MEMORY_CURATION, MEMORY_SURFACING, CHAPTER_CUES, RETRIEVAL_ERROR_ANALYSIS, RETRIEVAL_RESEARCH)
