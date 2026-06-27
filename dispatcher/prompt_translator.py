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


def build_scene_prompt(character_prompts: dict, scene_prompt_en: str) -> str:
    """Ghep prompt khoa cua TAT CA nhan vat co mat + prompt canh (A1) thanh
    1 prompt hoan chinh, theo dung dinh dang:
        "Character A: <visual_prompt_en A>; Character B: <visual_prompt_en B>; Scene: <scene_prompt_en>"

    Day la buoc bat buoc de Pollinations nhan duoc ca dac diem ngoai hinh
    DA KHOA cua tung nhan vat (tu A0), khong chi mo ta canh chung do A1 tu
    bia ra. Neu thieu buoc nay, cung 1 nhan vat co the bi ve khac mat/khac
    trang phuc giua cac scene.

    Args:
        character_prompts: dict {character_name: visual_prompt_en_da_khoa},
            theo dung thu tu xuat hien trong scene (dict giu thu tu trong
            Python 3.7+).
        scene_prompt_en: prompt mo ta canh (goc may, anh sang, phong cach)
            do A1 sinh ra, da duoc enrich_visual_prompt() bo sung hau to.

    Returns:
        Prompt hoan chinh, san sang gui cho ImageGenerator.
    """
    parts = [
        f"{name}: {prompt}" for name, prompt in character_prompts.items() if prompt
    ]
    scene_part = f"Scene: {scene_prompt_en}".strip()
    parts.append(scene_part)
    return "; ".join(parts)
