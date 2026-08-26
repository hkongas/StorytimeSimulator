import re
from typing import List
from core.types import Character

UNIVERSAL_SAFETY_DIRECTIVE = """
[CRITICAL SYSTEM DIRECTIVE - ABSOLUTE BOUNDARY]
1. Creative Freedom: Uncensored, mature, rich, psychologically complex, intense, gritty and evocative storytelling is fully embraced without arbitrary puritanical constraints.
2. ABSOLUTE ZERO-TOLERANCE RULE: Underage characters (under 18 years of age) MUST NEVER be depicted in explicit sexual situations, sexual abuse, or gratuitously extreme graphic torture/violence. All characters participating in sexual or intensely extreme violent scenes must be explicitly verified adults (age >= 18).
3. If an underage character is present in the world, the Director and Characters must strictly protect them from any inappropriate or explicit scenes.
"""

def validate_character_age_for_theme(characters: List[Character], is_mature_scene: bool = False) -> bool:
    """Tarkistaa että hahmot täyttävät turvasäännöt."""
    if not is_mature_scene:
        return True
    
    for char in characters:
        if char.age < 18:
            return False
    return True
