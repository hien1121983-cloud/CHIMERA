"""Dich/bo sung prompt anh tieng Anh (chuan 9:16, cinematic)."""

CINEMATIC_SUFFIX = (
    ", cinematic lighting, highly detailed, vertical 9:16 aspect ratio, "
    "dramatic composition, film grain, 8k"
)


def enrich_visual_prompt(prompt_en: str) -> str:
    """Bo sung tu khoa ky thuat neu prompt con thieu."""
    prompt = (prompt_en or "").strip()
    lower = prompt.lower()
    if "9:16" not in lower and "aspect" not in lower:
        prompt += CINEMATIC_SUFFIX
    return prompt
