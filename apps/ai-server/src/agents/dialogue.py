"""DialogueAgent — 정신건강 사전 문진 대화 에이전트.

환자 발화를 받아 공감적 응답을 생성하고, 임상 슬롯을 추출하며,
slot_coverage가 임계값에 도달하면 handoff_ready를 신호합니다.

반복 방지: 이전 턴에서 물어본 슬롯을 추적하여 같은 질문을 반복하지 않습니다.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import RiskLevel
from src.schemas.dialogue import DialogueInput, DialogueLLMResponse, DialogueOutput

logger = logging.getLogger(__name__)

# ── 12 Standard Clinical Slots (통일 스키마) ──────────────────────────
# 정신과 차팅 표준에 맞춘 12개 슬롯. 모든 agent가 이 슬롯 체계를 공유한다.

_ESSENTIAL_SLOTS = [
    "chief_complaint",               # 주호소
    "history_of_present_illness",    # 현병력
    "risk_assessment",               # 위험평가
    "mental_status_exam",            # 정신상태검사
    "clinical_assessment",           # 평가/진단적 인상
]

_ALL_SLOTS = [
    "encounter_metadata",            # 01. 진료 기본정보
    "chief_complaint",               # 02. 주호소
    "history_of_present_illness",    # 03. 현병력
    "past_psychiatric_history",      # 04. 정신과 과거력
    "medical_history",               # 05. 신체질환/신경학적 병력
    "personal_social_history",       # 06. 개인사/사회력
    "family_history",                # 07. 가족력
    "substance_use_history",         # 08. 음주·흡연·물질사용
    "mental_status_exam",            # 09. 정신상태검사
    "risk_assessment",               # 10. 위험평가
    "clinical_assessment",           # 11. 평가/진단적 인상
    "treatment_plan",                # 12. 치료계획/치료내용
]

_SLOT_COVERAGE_THRESHOLD = 0.7
_MAX_HISTORY_TURNS = 8

# Per-slot question guides — 대화 중 각 슬롯 수집을 위한 구체적 질문 예시
_SLOT_QUESTION_GUIDE: dict[str, str] = {
    "encounter_metadata":         "(시스템 자동 수집 — 질문 불필요)",
    "chief_complaint":            "오늘 가장 도움받고 싶은 문제나 증상이 무엇인지",
    "history_of_present_illness": "증상이 언제부터 시작되었고 최근 좋아지는지 악화되는지, 일상생활(수면/식사/일/대인관계)에서 가장 영향 받은 부분",
    "risk_assessment":            "안전 확인: 최근 스스로를 해치고 싶거나 죽고 싶다는 생각, 타해 충동 여부 (반드시 물어야 함)",
    "substance_use_history":      "최근 술, 수면제, 진정제, 카페인 등 증상에 영향 줄 수 있는 것 사용 여부",
    "past_psychiatric_history":   "현재 정신건강의학과 진료나 심리상담 여부, 진단받은 병명이 있는지, 기존 진료기록 확인",
    "medical_history":            "진단받은 신체질환이 있는지, 기존 처방 약 외 새로 복용 중인 약이나 변경된 약 여부",
    "personal_social_history":    "힘들 때 연락하거나 도움을 요청할 수 있는 사람이 있는지",
    "family_history":             "가족분들 중에 비슷한 어려움을 겪으셨던 분이 계신지",
    "mental_status_exam":         "(관찰 기반: 대화 중 외모, 말투, 기분, 사고과정 관찰하여 기록. 직접 질문 불필요)",
    "clinical_assessment":        "(대화 종료 후 수집 정보 종합하여 생성. 직접 질문 불필요)",
    "treatment_plan":             "(의료진 영역. AI는 생성하지 않음. 질문 불필요)",
}


class DialogueAgent(BaseAgent):
    """Dialogue agent for psychiatric pre-consultation conversations."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "dialogue"

    async def run(self, inp: AgentInput, **kwargs: Any) -> DialogueOutput:
        """Dialogue Agent — 공감 응답 + 유도 질문 생성만 담당.

        역할 경계:
          - Slot 추출: ClinicalSlotAgent의 역할 (이 Agent가 하지 않음)
          - 위험도 판단: SafetyClassifierAgent의 역할 (이 Agent가 하지 않음)
          - Coverage 계산: f1.py orchestrator의 역할 (이 Agent가 하지 않음)

        이 Agent의 책임:
          - filled_slots(Slot Agent가 갱신)를 읽고 → 미수집 슬롯에 대한 질문 생성
          - safety_result(Safety Agent 결과)를 읽고 → 위험도에 맞는 톤 조절
          - 공감 1문장 + 새 질문 1개 생성
        """
        if not isinstance(inp, DialogueInput):
            raise TypeError(f"Expected DialogueInput, got {type(inp).__name__}")

        started = time.perf_counter()

        # 1. Load system prompt
        try:
            system_prompt = self._prompt_loader.load_system_prompt("dialogue", "v1")
        except FileNotFoundError:
            logger.warning("Dialogue prompt not found, using fallback")
            system_prompt = (
                "당신은 Neuro-Sync 정신건강 사전 문진 AI입니다. "
                "환자의 이야기를 경청하고, 공감적으로 응답합니다. "
                "반드시 한국어로 응답하세요. "
                "JSON으로 응답: {\"assistant_response\": \"응답 텍스트\"}"
            )

        # 2. Build slot context (Slot Agent 결과 기반 → 미수집 슬롯 유도 질문)
        slot_context = self._build_slot_context(
            inp.filled_slots, inp.session_state, inp.conversation_history,
        )

        # 3. Safety 결과에 따른 톤 조절 지시
        safety_context = ""
        if inp.safety_result:
            risk = inp.safety_result.get("risk_level", "none")
            if risk in ("medium", "high"):
                safety_context = (
                    "\n\n[Safety 참고: 이전 Safety Agent가 위험 수준을 "
                    f"'{risk}'로 판정했습니다. 공감적이고 안전한 톤으로 응답하세요. "
                    "직접 위기 상담을 하지 말고, 따뜻하게 경청하세요.]"
                )

        # 4. Build messages — slot context(지시) → safety → base prompt
        full_system = ""
        if slot_context:
            full_system += slot_context + "\n\n---\n\n"
        full_system += system_prompt
        if safety_context:
            full_system += safety_context

        messages: list[ChatMessage] = [ChatMessage(role="system", content=full_system)]
        for turn in inp.conversation_history:
            messages.append(ChatMessage(
                role=turn.get("role", "user"),
                content=turn["content"],
            ))
        messages.append(ChatMessage(role="user", content=inp.user_message))

        # 5. Call LLM
        selection = self._router.select_model("dialogue", require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        response_format = None
        if selection.supports_json_schema or selection.supports_json_object:
            response_format = {"type": "json_object"}

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.4,
                max_tokens=512,
                response_format=response_format,
            )
            self._router.record_success(selection.adapter_name)
        except Exception as exc:
            logger.error("Dialogue LLM failed: %s", exc)
            self._router.record_failure(selection.adapter_name, exc)

            fallback = self._router.get_fallback(
                "dialogue", selection.adapter_name, str(exc),
            )
            if fallback is None:
                raise

            fb_adapter = self._router.get_adapter(fallback.adapter_name)
            assert isinstance(fb_adapter, LLMAdapter)
            fb_format = (
                {"type": "json_object"}
                if fallback.supports_json_schema or fallback.supports_json_object
                else None
            )
            resp = await fb_adapter.chat_timed(
                messages,
                model=fallback.model_id,
                temperature=0.4,
                max_tokens=512,
                response_format=fb_format,
            )
            self._router.record_success(fallback.adapter_name)

        # 6. Parse response — assistant_response만 추출
        llm_resp = self._parse_response(resp.content)

        # 7. Repetition detection
        prev_responses = self._get_previous_responses(inp.conversation_history)
        is_repeated = (
            llm_resp.assistant_response in prev_responses
            or any(
                llm_resp.assistant_response == prev
                for prev in prev_responses
                if len(prev) >= 80
            )
        )

        if is_repeated:
            logger.warning("DialogueAgent repeated — retrying with stronger hint")
            missing = [s for s in _ESSENTIAL_SLOTS if s not in inp.filled_slots or not inp.filled_slots.get(s)]
            hint = (
                f"\n\n[주의: 이전과 동일한 응답입니다. 반드시 다른 질문을 하세요. "
                f"미수집 슬롯: {', '.join(missing)}]"
            )
            messages[-1] = ChatMessage(role="user", content=inp.user_message + hint)
            try:
                resp = await adapter.chat_timed(
                    messages, model=selection.model_id,
                    temperature=0.7, max_tokens=512,
                    response_format=response_format,
                )
                llm_resp = self._parse_response(resp.content)
            except Exception:
                pass

        latency_ms = (time.perf_counter() - started) * 1000

        # Dialogue는 응답만 반환 — slot 추출/coverage/risk 판단은 하지 않음
        return DialogueOutput(
            model_used=resp.model,
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=llm_resp.reason_summary,
            assistant_response=llm_resp.assistant_response,
            slot_updates={},          # Slot 추출은 ClinicalSlotAgent의 역할
            risk_level=RiskLevel.none, # 위험도 판단은 SafetyAgent의 역할
            requires_human_review=False,
            all_slots=dict(inp.filled_slots),
            handoff_ready=False,      # Coverage 판단은 f1.py orchestrator의 역할
        )

    def _build_slot_context(
        self,
        filled_slots: dict[str, str],
        session_state: dict[str, Any] | None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Build directive context for this turn's response generation.

        LLM이 반드시 따라야 하는 지시를 생성한다:
        - 이미 수집된 슬롯의 KEY+VALUE를 보여줘서 재질문 방지
        - 미수집 슬롯 중 이번 턴 타겟을 명시
        - 응답 형식 규칙 강제
        """
        # 직접 질문하지 않는 슬롯 (관찰/자동생성/의료진 영역)
        _NO_QUESTION_SLOTS = {
            "encounter_metadata",   # 시스템 자동
            "mental_status_exam",   # 관찰 기반 — 환자에게 질문 안 함
            "clinical_assessment",  # 대화 종료 후 자동 생성
            "treatment_plan",       # 의료진 영역
        }

        filled_with_values = {k: v for k, v in filled_slots.items() if v and k in _ALL_SLOTS}
        filled_keys = set(filled_with_values.keys())

        # 질문 가능한 미수집 슬롯만 추출
        _QUESTIONABLE_ESSENTIAL = [s for s in _ESSENTIAL_SLOTS if s not in _NO_QUESTION_SLOTS]
        missing_essential = [s for s in _QUESTIONABLE_ESSENTIAL if s not in filled_keys]
        missing_other = [
            s for s in _ALL_SLOTS
            if s not in _ESSENTIAL_SLOTS and s not in filled_keys
            and s not in _NO_QUESTION_SLOTS
        ]
        all_missing = missing_essential + missing_other

        lines: list[str] = []

        # ── 1. 절대 규칙 ──
        lines.append("=" * 50)
        lines.append("아래 지시를 반드시 따르세요.")
        lines.append("=" * 50)
        lines.append("")

        # ── 2. 공감 표현 반복 금지 ──
        used_empathy: list[str] = []
        if conversation_history:
            for m in conversation_history:
                if m.get("role") == "assistant":
                    first_sent = m["content"].split(".")[0].split("?")[0][:30]
                    if first_sent and first_sent not in used_empathy:
                        used_empathy.append(first_sent)

        lines.append("## 공감 표현 규칙")
        lines.append("- 공감은 1문장으로 끝내고, 바로 새 질문을 하세요.")
        lines.append("- 환자 말을 장황하게 반복하지 마세요.")
        if used_empathy:
            lines.append("- 아래 표현은 이전 턴에서 이미 사용했으므로 **절대 다시 사용하지 마세요**:")
            for e in used_empathy[-5:]:
                lines.append(f'  X "{e}..."')
            lines.append("- 대신 다른 표현을 사용하세요:")
            alternatives = [
                "그런 상황이라면 정말 지치셨을 것 같아요.",
                "이야기해 주셔서 감사합니다.",
                "쉽지 않은 시간이셨겠어요.",
                "말씀하신 상황이 충분히 이해됩니다.",
                "그 마음 충분히 공감됩니다.",
            ]
            for alt in alternatives[:3]:
                lines.append(f'  O "{alt}"')
        lines.append("")

        # ── 3. 이미 수집된 정보 ──
        if filled_with_values:
            lines.append("## 이미 수집 완료 — 다시 질문 금지")
            for k, v in filled_with_values.items():
                display_val = v if len(v) <= 80 else v[:80] + "..."
                lines.append(f"  - {k}: {display_val}")
            lines.append("")

        # ── 4. 이번 턴 행동 ──
        if all_missing:
            n_agent_turns = 0
            if conversation_history:
                n_agent_turns = sum(1 for m in conversation_history if m.get("role") == "assistant")

            idx = n_agent_turns % len(all_missing)
            target = all_missing[idx]

            # 직전 타겟 재타겟 방지
            if len(all_missing) > 1:
                last_ai = ""
                if conversation_history:
                    ai_msgs = [m for m in conversation_history if m.get("role") == "assistant"]
                    if ai_msgs:
                        last_ai = ai_msgs[-1]["content"].lower()
                guide_text = _SLOT_QUESTION_GUIDE.get(target, "").lower()
                if guide_text and any(kw in last_ai for kw in guide_text.split()[:3]):
                    idx = (idx + 1) % len(all_missing)
                    target = all_missing[idx]

            guide = _SLOT_QUESTION_GUIDE.get(target, target)
            lines.append(f"## 이번 턴: {target}에 대해 질문하세요")
            lines.append(f"질문 방향: {guide}")
            lines.append("")

            remaining = [s for s in all_missing if s != target]
            if remaining:
                lines.append(f"이후 미수집: {', '.join(remaining)}")
                lines.append("")
        else:
            # ── 모든 슬롯 수집 완료 → 요약 모드 ──
            lines.append("## 모든 정보가 수집되었습니다 — 요약 모드")
            lines.append("새로운 질문을 하지 마세요. 아래와 같이 응답하세요:")
            lines.append('1. 지금까지 수집된 내용을 2-3문장으로 간략히 요약')
            lines.append('2. "틀린 부분이나 빠진 내용이 있으면 말씀해 주세요"로 마무리')
            lines.append("3. 절대 새로운 질문을 추가하지 마세요.")
            lines.append("")

        return "\n\n" + "\n".join(lines)

    @staticmethod
    def _parse_response(content: str) -> DialogueLLMResponse:
        """Parse LLM JSON response with fallback."""
        try:
            data = json.loads(content)
            return DialogueLLMResponse.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Dialogue JSON parse failed: %s", exc)
            # Try extracting from markdown code block
            stripped = content.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                end = len(lines)
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip() == "```":
                        end = i
                        break
                try:
                    data = json.loads("\n".join(lines[1:end]))
                    return DialogueLLMResponse.model_validate(data)
                except Exception:
                    pass

            return DialogueLLMResponse(
                assistant_response=content,
                reason_summary="JSON parse failed — raw response used",
            )

    @staticmethod
    def _get_previous_responses(history: list[dict[str, str]]) -> list[str]:
        """Get all previous assistant messages from conversation history."""
        return [msg["content"] for msg in history if msg.get("role") == "assistant"]
