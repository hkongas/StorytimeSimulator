import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import settings

class PromptLoader:
    """Lataa ja kokoaa system promptit tiedostoista.
    
    Yhdistää hierarkkisesti:
    1. Turvallisuusdirektiivin (safety_directive.txt)
    2. Sävyprofiilin (tone_profiles/<profile>.txt)
    3. Varsinaisen agenttipromptin (<role>/<name>.txt)
    4. Kielidirektiivin (language_directive.txt)
    """

    def __init__(self, base_prompts_dir: Optional[Path] = None):
        self.prompts_dir = base_prompts_dir or (Path(__file__).resolve().parent.parent / "prompts")
        self.custom_dir = self.prompts_dir / "custom"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, str] = {}

    def _safe_path(self, root: Path, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts or ":" in relative_path or relative.suffix != ".txt":
            raise ValueError("Virheellinen promptin polku.")
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Promptti ei ole sallitussa kansiossa.")
        return target

    def get_raw_prompt(self, relative_path: str) -> str:
        """Hakee promptin raakatekstin tiedostosta (tarkistaa ensin custom-kansion)."""
        custom_file = self._safe_path(self.custom_dir, relative_path)
        if custom_file.exists():
            return custom_file.read_text(encoding="utf-8")
        
        standard_file = self._safe_path(self.prompts_dir, relative_path)
        if standard_file.exists():
            return standard_file.read_text(encoding="utf-8")
        
        return ""

    def save_custom_prompt(self, relative_path: str, content: str) -> None:
        """Tallentaa käyttäjän muokkaaman promptin custom-kansioon."""
        target_file = self._safe_path(self.custom_dir, relative_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        # Tyhjennetään välimuisti
        self._cache.clear()

    def reset_custom_prompt(self, relative_path: str) -> bool:
        """Palauttaa muokatun promptin oletusversioon poistamalla custom-tiedoston."""
        custom_file = self._safe_path(self.custom_dir, relative_path)
        if custom_file.exists():
            custom_file.unlink()
            self._cache.clear()
            return True
        return False

    def list_tone_profiles(self) -> List[Dict[str, str]]:
        """Listaa saatavilla olevat sävyprofiilit."""
        tone_dir = self.prompts_dir / "tone_profiles"
        profiles = []
        if tone_dir.exists():
            files = {path.name: path for path in tone_dir.glob("*.txt")}
            files.update({path.name: path for path in (self.custom_dir / "tone_profiles").glob("*.txt")})
            for p_file in files.values():
                name = p_file.stem
                content = self.get_raw_prompt(f"tone_profiles/{p_file.name}")
                # Poimitaan otsikkorivi profiilista
                first_line = content.splitlines()[0] if content else name
                title = first_line.replace("[TONE & NARRATIVE PROFILE:", "").replace("]", "").strip() or name
                profiles.append({
                    "id": name,
                    "title": title,
                    "content": content,
                    "is_custom": (self.custom_dir / "tone_profiles" / p_file.name).exists()
                })
        return profiles

    def get_safety_directive(self) -> str:
        return self.get_raw_prompt("safety_directive.txt")

    def get_language_directive(self) -> str:
        return self.get_raw_prompt("language_directive.txt")

    def get_tone_profile_content(self, profile_id: str = "default") -> str:
        profile_content = self.get_raw_prompt(f"tone_profiles/{profile_id}.txt")
        if not profile_content and profile_id != "default":
            profile_content = self.get_raw_prompt("tone_profiles/default.txt")
        return profile_content

    def compose_system_prompt(
        self,
        prompt_name: str,
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None,
        include_tone: bool = True,
        **variables: Any
    ) -> str:
        """Kokoaa täydellisen system promptin liittämällä turvallisuus-, sävy- ja kielidirektiivit."""
        safety = self.get_safety_directive().strip()
        tone = ((custom_tone_override.strip() if custom_tone_override else self.get_tone_profile_content(tone_profile).strip())
                if include_tone else "")
        raw_body = self.get_raw_prompt(f"{prompt_name}.txt")
        language = self.get_language_directive().strip()

        # Korvataan annetut muuttujat rungossa
        body = raw_body
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            body = body.replace(placeholder, str(value) if value is not None else "")

        parts = []
        if safety:
            parts.append(safety)
        if tone:
            parts.append(tone)
        if body:
            parts.append(body)
        if language:
            parts.append(language)

        return "\n\n".join(parts)

# Yleinen singleton-instanssi
prompt_loader = PromptLoader()
