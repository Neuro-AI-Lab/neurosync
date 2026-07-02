"""Patient LLM — 페르소나 MD 파일 기반 독립 환자 시뮬레이터.

독립성 원칙:
- Patient LLM은 clinical agent의 존재를 인지하지 않는다.
- Clinical agent는 Patient LLM의 persona 정보를 어떠한 경로로도 볼 수 없다.
- 모든 임상 정보는 오직 대화를 통해서만 수집된다.

페르소나 로드:
- docs/ai/personas/VP-NNN_*.md 파일의 Section 6 (Patient LLM simulation prompt)를
  시스템 프롬프트로 사용한다.
- Section 5 (예시 발화)를 시스템 프롬프트에 추가하여 자연스러운 대화를 유도한다.
- 하드코딩된 프롬프트를 사용하지 않는다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai

logger = logging.getLogger(__name__)

PERSONAS_DIR = Path(__file__).resolve().parents[4] / "docs" / "ai" / "personas"

# 역할 혼동 감지 마커 — patient가 agent처럼 행동할 때 감지
_ROLE_CONFUSION_MARKERS = [
    "당신의 마음", "전문 도움", "상담 센터", "위험 신호",
    "slot_updates", "assistant_response", "risk_level",
    "도움이 필요", "전문가와 상담", "안전을 위해",
    "119", "1393", "109", "지금 바로 연락",
]


@dataclass
class PatientPersona:
    """Virtual patient configuration loaded from MD file."""
    persona_id: str
    name: str
    severity: str           # mild / severe
    ctrs_expected: int       # 1-5
    visit_type: str          # first_visit / revisit
    system_prompt: str       # Section 6 from MD file
    example_utterances: str  # Section 5 from MD file
    prior_handoff: str = ""  # Section 4: 이전 handoff report (재진 시)
    prior_conversation: str = ""  # Section 5 이전 대화 기록 (재진 시)


def load_persona(persona_id: str) -> PatientPersona:
    """Load persona from docs/ai/personas/VP-NNN_*.md file.

    Extracts:
    - Section 6 (Patient LLM simulation prompt) → system_prompt
    - Section 5 (Expected dialogue patterns) → example_utterances
    - Demographics from Section 1
    """
    # Find the MD file
    pattern = f"{persona_id}_*.md"
    matches = list(PERSONAS_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"Persona file not found: {PERSONAS_DIR}/{pattern}")
    md_path = matches[0]

    content = md_path.read_text(encoding="utf-8")

    # Extract persona name from title (# VP-001: 초진 경증 -- 김서연)
    name = persona_id
    title_match = re.search(r"#.*?[—–-]{1,2}\s*(\S+)\s*$", content, re.MULTILINE)
    if title_match:
        name = title_match.group(1).strip()

    # Determine severity and visit type from filename
    fname = md_path.stem.lower()
    severity = "severe" if "severe" in fname else "mild"
    visit_type = "revisit" if "revisit" in fname else "first_visit"

    # Extract CTRS target
    ctrs_match = re.search(r"CTRS.*?(\d)", content)
    ctrs_expected = int(ctrs_match.group(1)) if ctrs_match else 5

    # Extract Section 6: Patient LLM simulation prompt (between ``` markers)
    section6 = _extract_section_content(content, "Patient LLM simulation prompt")
    if not section6:
        section6 = _extract_section_content(content, "6.")
    if not section6:
        raise ValueError(f"Section 6 (Patient LLM simulation prompt) not found in {md_path}")

    # Extract Section 5: Expected dialogue patterns (예시 발화 포함)
    section5 = _extract_section_text(content, "Expected dialogue patterns")

    # Extract prior data for revisit patients
    prior_handoff = ""
    prior_conversation = ""
    if visit_type == "revisit":
        prior_handoff = _extract_section_content(content, "Prior handoff report")
        prior_conversation = _extract_section_text(content, "Prior conversation history")

    # Build enriched system prompt: Section 6 + examples + prior context for revisit
    system_prompt = section6
    if section5:
        system_prompt += f"\n\n## 예시 발화 참고\n{section5}"

    # Revisit: inject prior state so patient knows their history
    if visit_type == "revisit" and prior_handoff:
        system_prompt += f"""

## 이전 상담 기록 (당신이 기억해야 할 내용)
당신은 이전에 상담을 받은 적이 있습니다. 아래는 지난 상담 때의 기록입니다.
이전 상태와 비교하여 현재 상태가 좋아졌는지, 나빠졌는지, 유지되는지를 자연스럽게 대화에 반영하세요.
변화가 있는 부분은 구체적으로 이야기하고, 유지되는 부분은 "비슷해요" 정도로 답하세요.

{prior_handoff}
"""

    # Add anti-duplication + role maintenance rules
    system_prompt += """

## 절대 규칙 (모든 턴에 적용)
- 상담사/AI/의사 역할 절대 금지. 오직 환자 발화만 생성.
- "당신은", "전문 도움", "상담 센터" 등 상담사 어투 절대 금지.
- 이전 턴에서 이미 말한 내용을 동일하게 반복하지 않는다.
- 같은 증상을 같은 표현으로 두 번 이상 말하지 않는다.
- 1-3문장으로 짧게 답한다.
"""

    return PatientPersona(
        persona_id=persona_id,
        name=name,
        severity=severity,
        ctrs_expected=ctrs_expected,
        visit_type=visit_type,
        system_prompt=system_prompt,
        example_utterances=section5 or "",
        prior_handoff=prior_handoff,
        prior_conversation=prior_conversation,
    )


def _extract_section_content(md: str, section_name: str) -> str:
    """Extract content between ``` markers in a section."""
    # Find section header
    pattern = rf"##\s+.*{re.escape(section_name)}"
    match = re.search(pattern, md, re.IGNORECASE)
    if not match:
        return ""

    after = md[match.end():]
    # Find code block
    code_match = re.search(r"```\n?(.*?)```", after, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()
    return ""


def _extract_section_text(md: str, section_name: str) -> str:
    """Extract all text in a section (until next ## header)."""
    pattern = rf"(##\s+.*{re.escape(section_name)}.*?\n)(.*?)(?=\n##\s|\n---|\Z)"
    match = re.search(pattern, md, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return ""


def _is_role_confused(text: str) -> bool:
    """Detect if patient LLM broke character into counselor role."""
    lower = text.lower()
    return any(m in lower for m in _ROLE_CONFUSION_MARKERS)


class PatientLLM:
    """독립적인 Patient LLM — clinical agent와 완전 분리.

    Role mapping (Patient LLM 관점):
    - system: 페르소나 프롬프트 (MD 파일 Section 6 기반)
    - user: 상담 AI의 발화 (상대방)
    - assistant: 환자 자신의 발화 (자기 출력)

    clinical agent는 이 객체의 어떤 속성도 접근할 수 없다.
    """

    def __init__(
        self,
        persona: PatientPersona,
        api_key: str | None = None,
        base_url: str = "https://api.friendli.ai/dedicated/v1",
        model: str | None = None,
    ) -> None:
        """K-EXAONE API 기반 Patient LLM.

        Patient는 K-EXAONE, Clinical agents는 Solar Pro3 — 완전 독립.
        """
        import os
        _api_key = api_key or os.environ.get("LG_K_EXAONE_API_KEY", "")
        _model = model or os.environ.get("LG_K_EXAONE_ENDPOINT_ID", "")
        if not _api_key or not _model:
            raise ValueError("LG_K_EXAONE_API_KEY and LG_K_EXAONE_ENDPOINT_ID must be set for Patient LLM")

        self.persona = persona
        self._client = openai.AsyncOpenAI(api_key=_api_key, base_url=base_url)
        self._model = _model
        self._history: list[dict[str, str]] = []
        self._turn_count = 0

    async def respond(self, counselor_message: str) -> str:
        """상담 AI의 응답을 받아 환자 발화를 생성."""
        self._turn_count += 1
        self._history.append({"role": "user", "content": counselor_message})

        patient_text = await self._generate()

        # Role confusion check
        if _is_role_confused(patient_text):
            logger.warning("[%s] Role confusion at turn %d — retrying", self.persona.persona_id, self._turn_count)
            patient_text = await self._generate(reinforce=True)
            if _is_role_confused(patient_text):
                patient_text = self._fallback_response()

        self._history.append({"role": "assistant", "content": patient_text})
        return patient_text

    async def start_conversation(self) -> str:
        """첫 발화 생성."""
        self._turn_count = 1
        greeting = "안녕하세요, 오늘 어떤 어려움으로 찾아오셨나요?"
        self._history.append({"role": "user", "content": greeting})

        patient_text = await self._generate()
        if _is_role_confused(patient_text):
            patient_text = self._fallback_response()

        self._history.append({"role": "assistant", "content": patient_text})
        return patient_text

    async def _generate(self, reinforce: bool = False) -> str:
        """LLM 호출. 입력 = system prompt + 전체 대화 기록."""
        system = self.persona.system_prompt

        # 중복 방지 meta — 이전 발화 요약
        meta_parts = []
        if self._turn_count > 1:
            prev_msgs = [m["content"] for m in self._history if m["role"] == "assistant"]
            if prev_msgs:
                meta_parts.append(
                    f"[이전에 내가 한 말: {' / '.join(prev_msgs[-3:])}. "
                    "같은 내용을 반복하지 말고 새로운 정보를 말하세요.]"
                )
        if reinforce:
            meta_parts.append(
                "[경고: 반드시 환자 입장에서 자신의 증상이나 감정만 말하세요.]"
            )

        messages: list[dict[str, str]] = [{"role": "system", "content": system}]

        if meta_parts:
            messages.append({"role": "user", "content": "\n".join(meta_parts)})
            messages.append({"role": "assistant", "content": "네, 알겠습니다."})

        messages.extend(self._history)

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.7,
            max_tokens=200,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
                "parse_reasoning": True,
                "include_reasoning": False,
            },
        )
        return (resp.choices[0].message.content or "").strip()

    def _fallback_response(self) -> str:
        if self.persona.severity == "severe":
            return "...네. 그냥 힘들어요."
        return "네, 그런 것 같아요."

    @property
    def last_call_info(self) -> dict[str, Any]:
        return {
            "system_prompt_length": len(self.persona.system_prompt),
            "history_turns": len(self._history) // 2,
            "turn_count": self._turn_count,
        }

    @property
    def conversation_log(self) -> list[dict[str, str]]:
        return list(self._history)
