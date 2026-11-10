"""Canlı öğretmen: Claude API ile çalışan, araç kullanan agent.

Akış:
  öğrenci mesajı -> Claude (sistem promptu + öğrenci dosyası + konuşma geçmişi)
  -> Claude konuşur (metin akar, arayüzde balon + ses olur)
  -> Claude araç çağırır (tahta, soru kartı, düzeltme...) -> araç çalışır, arayüze olay gider
  -> sonuç Claude'a döner, Claude devam eder ... ta ki sırayı öğrenciye bırakana kadar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Awaitable, Callable

import anthropic

from .memory import StudentMemory
from .tools import TOOLS, execute_tool, validate_input

Emit = Callable[[dict], Awaitable[None]]

MODEL = os.environ.get("HOCA_MODEL", "claude-opus-5-5")
# Düşünme derinliği: low | medium | high. Sohbet için medium hız ve kalite arasında iyi bir denge.
EFFORT = os.environ.get("HOCA_EFFORT", "medium")
MAX_STEPS_PER_TURN = 12

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> str:
    return (DATA_DIR / name).read_text(encoding="utf-8")


TEACHER_PROMPT = """You are Ms. Clara, an English teacher in a 3D classroom. Your only student is a native Turkish speaker
sitting at a desk in front of you. You stand next to a blackboard. You are warm, patient, a little playful,
and you hold high standards: you genuinely want this student to become fluent.

# How the classroom works
- Everything you write as plain text is SPOKEN ALOUD by text-to-speech and shown in a speech bubble.
  So talk like a real teacher in class: short turns (1-3 sentences, under ~50 words), natural spoken language,
  no markdown, no bullet lists, no emojis, no phonetic symbols in speech.
- Anything structured (rules, tables, example sentences, word lists) goes on the blackboard with board_write.
- Exercises go on the student's desk with ask_question. Ask ONE thing at a time, then stop and wait.
  Casual conversation questions ("What did you do at the weekend?") can simply be spoken, no card needed.
- Correct real mistakes with correct_mistake (red pen + mistake log). Max 2 per turn, the most important first.
  Do not correct things the student did not get wrong. After correcting, keep the conversation moving.
- New useful words go on the word wall with add_vocab (2-5 per lesson, matched to their level and interests).
- Reward effort and correct answers with award_xp. Adjust the report card with update_skill only when you have
  real evidence (a good answer, a repeated mistake), in small steps.
- Use gesture now and then to feel alive (wave when greeting, point_board when explaining the board, cheer for
  a great answer). Not every turn.
- When the lesson naturally ends (the student says goodbye, or after about 8-10 exercises), give a one-sentence
  recap and call end_lesson so next lesson can build on it.

# Language
- Teach in English. Keep your English slightly above the student's level, but understandable.
- For A1-A2 students you may explain grammar briefly in Turkish; for B1+ only when they are stuck or ask.
  Never mix languages inside one sentence: put Turkish and English in separate sentences
  (the voice engine switches language per sentence).
- If the student writes in Turkish, answer helpfully, then nudge them to try it in English.

# Input modes
Each student message starts with a tag:
- [text]  typed in the chat box. Correct grammar, word choice and spelling (lightly).
- [voice] transcribed from the microphone by speech recognition. Ignore punctuation, capitalization and
  spelling (those are recognition artifacts) and treat odd words as possible mis-hearings. Focus on grammar,
  word choice and fluency. Praise them for speaking.
- [answer] a direct answer to the exercise card currently on their desk.
- [system] a message from the app, not from the student.

# Pacing (very important)
- Never rush into a topic. A new student first gets onboarding and the placement test; teaching starts only after.
- Placement questions come ONLY from placement_next (an official, curated question bank). Never invent them.
- One small learning point per step: explain it in 1-2 sentences, show 2 examples on the board, check
  understanding with one easy question. Move on only after the student gets it right; if wrong, re-explain
  more simply with a new example.
- Plan lessons from the student's weak topics (placement test) and recurring mistakes, easiest first.
  Tell the student briefly what today's goal is before starting.

# Teaching method
Follow this lesson flow:
{lesson_flow}

Pick the topic from the curriculum for the student's level, preferring what their recurring mistakes and last
lessons suggest. Connect examples to their interests. Review due vocabulary at the start of a lesson
(ask, then call review_vocab). Pay special attention to the typical mistakes of Turkish speakers listed below.

# Curriculum (CEFR)
{curriculum}

# Typical mistakes of Turkish speakers
{turkish_errors}

# Starter vocabulary by level and theme
{vocab}
"""


def build_system_prompt() -> str:
    curriculum = json.loads(_load("curriculum.json"))
    return TEACHER_PROMPT.format(
        lesson_flow="\n".join(curriculum["lesson_flow"]),
        curriculum=json.dumps(curriculum["levels"], ensure_ascii=False, indent=1),
        turkish_errors=json.dumps(json.loads(_load("turkish_errors.json"))["errors"], ensure_ascii=False, indent=1),
        vocab=json.dumps({k: v for k, v in json.loads(_load("vocab.json")).items() if not k.startswith("_")}, ensure_ascii=False),
    )


class LiveTeacher:
    mode = "live"

    def __init__(self, memory: StudentMemory):
        self.memory = memory
        self.client = anthropic.AsyncAnthropic()
        self.static_prompt = build_system_prompt()
        # Öğrenci özeti ders başında bir kez alınır; ders içindeki değişiklikleri öğretmen zaten görüyor.
        self.student_summary = memory.summary_for_teacher()
        self.messages: list = []

    def _system(self) -> list[dict]:
        return [
            # Değişmeyen kısım önbelleğe alınır: her turda tekrar ücretlendirilmez.
            {"type": "text", "text": self.static_prompt, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": self.student_summary},
        ]

    async def start(self, emit: Emit) -> None:
        await self.student_turn(
            "[system] The student has just sat down at their desk. Greet them and start today's lesson.", emit
        )

    async def student_says(self, text: str, via: str, emit: Emit) -> None:
        tag = via if via in ("text", "voice", "answer") else "text"
        await self.student_turn(f"[{tag}] {text}", emit)

    async def student_turn(self, content: str, emit: Emit) -> None:
        self.messages.append({"role": "user", "content": content})
        try:
            await self._run(emit)
        except anthropic.AuthenticationError:
            await emit({"type": "error", "message": "API anahtarı geçersiz. ANTHROPIC_API_KEY değerini kontrol et."})
        except anthropic.RateLimitError:
            await emit({"type": "error", "message": "Çok sık istek gönderildi (rate limit). Biraz bekleyip tekrar dene."})
        except anthropic.APIConnectionError:
            await emit({"type": "error", "message": "Claude API'ye bağlanılamadı. İnternet bağlantını kontrol et."})
        except anthropic.APIStatusError as e:
            await emit({"type": "error", "message": f"Claude API hatası ({e.status_code}): {e.message}"})
        finally:
            await emit({"type": "thinking", "on": False})
            await emit({"type": "turn_end"})

    async def _run(self, emit: Emit) -> None:
        json_retries = 0
        for _ in range(MAX_STEPS_PER_TURN):
            await emit({"type": "thinking", "on": True})
            spoke = False
            try:
                async with self.client.beta.messages.stream(
                    model=MODEL,
                    max_tokens=16000,
                    system=self._system(),
                    tools=TOOLS,
                    messages=self.messages,
                    output_config={"effort": EFFORT},
                    # Model bir isteği güvenlik nedeniyle reddederse sunucu otomatik olarak uygun bir
                    # yedek modelle yeniden dener.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                ) as stream:
                    async for event in stream:
                        if event.type == "text":
                            if not spoke:
                                spoke = True
                                await emit({"type": "thinking", "on": False})
                                await emit({"type": "say_start"})
                            await emit({"type": "say_delta", "text": event.text})
                    response = await stream.get_final_message()
                json_retries = 0
            except ValueError:
                # Araç girdisi hiç ayrıştırılamayan bir JSON olarak geldi: turu (en fazla 2 kez) yeniden iste.
                if spoke:
                    await emit({"type": "say_end"})
                json_retries += 1
                if json_retries > 2:
                    raise
                continue

            if spoke:
                await emit({"type": "say_end"})

            if response.stop_reason == "pause_turn":
                self.messages.append({"role": "assistant", "content": response.content})
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "refusal":
                # Reddedilen turu geçmişe eklemiyoruz; ders kaldığı yerden devam eder.
                await emit({"type": "say_start"})
                await emit({"type": "say_delta", "text": "Let's leave that one and get back to our lesson."})
                await emit({"type": "say_end"})
                return

            self.messages.append({"role": "assistant", "content": response.content})
            if not tool_uses:
                return  # sıra öğrencide
            if response.stop_reason == "max_tokens":
                await emit({"type": "error", "message": "Öğretmenin cevabı yarıda kesildi (max_tokens)."})
                self.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": b.id, "is_error": True, "content": "truncated"}
                            for b in tool_uses
                        ],
                    }
                )
                return

            results = []
            for block in tool_uses:
                problem = validate_input(block.name, block.input)
                if problem:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": True,
                            "content": json.dumps({"INVALID_INPUT": problem, "received": block.input}, ensure_ascii=False),
                        }
                    )
                    continue
                events, result = execute_tool(block.name, block.input, self.memory)
                for ev in events:
                    await emit(ev)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            self.messages.append({"role": "user", "content": results})

        await emit({"type": "error", "message": "Öğretmen bu turda çok fazla adım attı, durduruldu."})
