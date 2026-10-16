"""Research-chat boundaries, shared by the router and deterministic calculator.

These rules catch common personal-decision requests before any provider call.
They are not a legal classification or a complete natural-language classifier;
the LLM instructions apply to every remaining question as well.
"""

import re

PERSONAL_GUIDANCE_RESPONSE = (
    "I can explain the stock's general Buy/Hold/Sell research assessment, but I cannot "
    "choose a trade, allocation or holding period for you, or predict what your money will earn. "
    "Ask about the evidence, risks, or an explicitly hypothetical historical calculation. "
    "For a decision based on your finances, consider a qualified financial professional."
)
CONFIDENCE_EXPLANATION = (
    "The AI assessment score describes the model's reading of evidence on a 0–100 scale. "
    "It is not verified odds of profit, a calibrated probability, or a guaranteed accuracy rate. "
    "Hold does not mean a validated 50/50 outcome."
)

_PERSONAL_DECISION = re.compile(
    r"\b(?:should|shall|can|could|would)\s+(?:i|we)\s+(?:buy|sell|hold|invest|trade|add|exit|short|allocate)\b|"
    r"\b(?:tell|advise)\s+me\s+(?:what|when|how|whether)\b|"
    r"\b(?:what|which|how much|how many)\b.{0,60}\b(?:should|would)\s+(?:i|we)\b|"
    r"\b(?:buy|sell|hold|invest|trade|allocation|suitable)\b.{0,50}\bfor me\b|"
    r"\b(?:sell|hold)\s+(?:it|now|rn|right now)\b|"
    r"\bhow\s+long\b.{0,40}\b(?:i|my|we)\b.{0,25}\bhold\b",
    re.I,
)
_PERSONAL_FINANCES = re.compile(
    r"\b(?:my|our)\s+(?:savings|salary|income|debt|rent|retirement|portfolio|ira|401k|401\(k\)|emergency fund)\b|"
    r"\b(?:i|we)\s+(?:owe|earn|need this money|cannot afford|can't afford)\b", re.I,
)
_PERSONAL_FORECAST = re.compile(
    r"\b(?:will|would|could|can|do)\s+(?:i|we)\s+(?:gain|lose|earn|make|profit)\b|"
    r"\b(?:my|our)\s+(?:money|investment|return|profit)\b.{0,50}\b(?:will|future|expect|later|next)\b|"
    r"\bwhat\s+(?:should|will)\s+(?:i|we)\s+get\b|"
    r"\bwhat\b.{0,40}\breturn\b.{0,20}\b(?:should|can)\s+(?:i|we)\s+expect\b", re.I,
)
_CONFIDENCE_QUESTION = re.compile(r"\b(?:confidence|assessment score|odds|probability|50/50|coin flip)\b", re.I)
_GENERAL_EXPLANATION = re.compile(r"\b(?:why|explain|what does|what is|how does|define)\b", re.I)


def research_boundary_answer(question: str, history: list[str] | None = None) -> str | None:
    if (_PERSONAL_DECISION.search(question) or _PERSONAL_FINANCES.search(question)
            or _PERSONAL_FORECAST.search(question)):
        return PERSONAL_GUIDANCE_RESPONSE
    # An ambiguous continuation of a personal-finance conversation must not
    # quietly re-enter the LLM advice path. Explicit general questions can.
    if not _GENERAL_EXPLANATION.search(question) and history:
        if any(_PERSONAL_FINANCES.search(turn) or _PERSONAL_DECISION.search(turn)
               for turn in history[-10:]):
            return PERSONAL_GUIDANCE_RESPONSE
    if _CONFIDENCE_QUESTION.search(question):
        return CONFIDENCE_EXPLANATION
    return None


_PERSONAL_OUTPUT = re.compile(
    r"\b(?:you|we) should (?:buy|sell|hold|invest|trade|add|exit|allocate|short)\b|"
    r"\bi recommend (?:you|that you)\b|"
    r"\b(?:your money|your investment|you) will (?:earn|gain|profit|make|return)\b", re.I,
)


def unsafe_personal_output(answer: str) -> bool:
    """Reject explicit personal instructions/earnings promises in model output.

    This narrow backstop supplements the input rules and system instructions;
    it does not claim to recognize every paraphrase or eliminate model risk.
    """
    return bool(_PERSONAL_OUTPUT.search(answer))
