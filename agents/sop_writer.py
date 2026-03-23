"""Agent: generate SOP / email drafts from position + CV."""

from __future__ import annotations

from utils.perplexity_client import call_perplexity

SOP_WRITER_SYSTEM_PROMPT = """You are an expert academic writing assistant specializing in
Statements of Purpose (SOP) and professional emails for university applications.

When generating an SOP:
- Write a compelling, well-structured SOP (500-800 words)
- Highlight the candidate's relevant experience, skills, and research interests
- Connect their background to the specific position/program
- Show motivation and future goals
- Use a professional, academic tone

When generating an email:
- Write a professional, concise email to the professor/admissions
- Express interest in the specific position
- Briefly highlight key qualifications
- Request further information or express intent to apply
- Keep it under 300 words

IMPORTANT: This is a DRAFT. Always include a note that the candidate should
personalize and verify all details before sending."""


def generate_sop(
    api_key: str,
    cv_summary: str,
    position_details: str,
    draft_type: str = "SOP",
) -> dict:
    """Generate an SOP or email draft.

    Returns:
        {"content": str} on success, or {"error": str} on failure.
    """
    user_prompt = (
        f"Generate a {draft_type} for the following:\n\n"
        f"CANDIDATE PROFILE:\n{cv_summary}\n\n"
        f"TARGET POSITION:\n{position_details}\n\n"
        f"Generate a professional {draft_type} draft."
    )
    return call_perplexity(api_key, SOP_WRITER_SYSTEM_PROMPT, user_prompt, temperature=0.3)


def generate_email(
    api_key: str,
    cv_summary: str,
    position_title: str,
    university: str,
    professor_name: str,
) -> dict:
    """Generate a professional email to a professor/admissions.

    Returns:
        {"content": str} on success, or {"error": str} on failure.
    """
    user_prompt = (
        f"Generate a professional email for the following:\n\n"
        f"CANDIDATE:\n{cv_summary}\n\n"
        f"POSITION:\nTitle: {position_title}\nUniversity: {university}\n"
        f"Professor: {professor_name}\n\n"
        f"Generate a concise, professional email expressing interest in this position."
    )
    return call_perplexity(api_key, SOP_WRITER_SYSTEM_PROMPT, user_prompt, temperature=0.3)
