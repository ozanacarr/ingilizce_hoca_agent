"""Demo öğretmen: API anahtarı olmadan arayüzü göstermek için hazır yazılmış bir ders.

Gerçek yapay zeka DEĞİLDİR. Cevaplarını basit kurallarla kontrol eder. Ama canlı öğretmenle aynı
araçları (tools.py) aynı şekilde çağırır, yani arayüz ve hafıza tam olarak canlı moddaki gibi çalışır.
"""

from __future__ import annotations

import asyncio
import re

from .memory import StudentMemory
from .teacher import Emit
from .tools import execute_tool

# Sık yapılan "have + V2" hatalarını yakalamak için: V2 -> V3
V2_TO_V3 = {
    "went": "gone", "did": "done", "saw": "seen", "ate": "eaten", "wrote": "written", "took": "taken",
    "gave": "given", "came": "come", "drank": "drunk", "spoke": "spoken", "began": "begun", "forgot": "forgotten",
}


def _norm(text: str) -> str:
    """Küçük harfe çevirir, noktalamayı atar, boşlukları sadeleştirir."""
    return " ".join(re.sub(r"[^a-z' ]", " ", text.lower()).split())


class DemoTeacher:
    mode = "demo"

    def __init__(self, memory: StudentMemory):
        self.memory = memory
        self.step = "name"
        self.name = "friend"
        self.score = 0

    # ---------- yardımcılar ----------
    async def _tool(self, emit: Emit, name: str, **args) -> None:
        events, _ = execute_tool(name, args, self.memory)
        for ev in events:
            await emit(ev)
        await asyncio.sleep(0.35)

    async def _say(self, emit: Emit, text: str) -> None:
        await emit({"type": "say_start"})
        for word in re.findall(r"\S+\s*", text):
            await emit({"type": "say_delta", "text": word})
            await asyncio.sleep(0.045)
        await emit({"type": "say_end"})
        await asyncio.sleep(0.25)

    async def _think(self, emit: Emit, seconds: float = 0.9) -> None:
        await emit({"type": "thinking", "on": True})
        await asyncio.sleep(seconds)
        await emit({"type": "thinking", "on": False})

    # ---------- ders ----------
    async def start(self, emit: Emit) -> None:
        await self._think(emit)
        await self._tool(emit, "gesture", kind="wave")
        await self._say(emit, "Good morning, and welcome to class! I'm Ms. Clara, your English teacher.")
        await self._say(emit, "Bu bir demo dersi. Şu an hazır yazılmış bir senaryoyu oynuyorum.")
        await self._say(emit, "Before we start, what's your name?")
        await emit({"type": "turn_end"})

    async def student_says(self, text: str, via: str, emit: Emit) -> None:
        handler = getattr(self, f"_step_{self.step}")
        await self._think(emit, 0.7)
        await handler(text.strip(), via, emit)
        await emit({"type": "turn_end"})

    async def _step_name(self, text: str, via: str, emit: Emit) -> None:
        m = re.search(r"(?:name is|i am|i'm|ben|adım)\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)", text, re.I)
        words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text)
        if m:
            self.name = m.group(1).capitalize()
        elif words:
            self.name = words[-1].capitalize()
        await self._tool(emit, "update_profile", field="name", value=self.name)
        await self._say(emit, f"Nice to meet you, {self.name}! Today we're learning the present perfect.")
        await self._tool(
            emit,
            "board_write",
            title="Present Perfect",
            lines=[
                "have / has + V3",
                "I *have seen* that film.",
                "She *has* never *been* to Paris.",
                "Zaman belli değil -> Present Perfect",
                "Zaman belli -> Past Simple",
                "I *saw* it *yesterday*.",
            ],
        )
        await self._tool(emit, "gesture", kind="point_board")
        await self._say(emit, "Look at the board. We use have or has, plus the third form of the verb.")
        await self._say(emit, "Zaman belli değilse present perfect, belliyse past simple kullanırız.")
        await self._say(emit, "Let's try one. Choose the right answer on your desk.")
        await self._tool(
            emit, "ask_question", kind="multiple_choice", prompt="I __ to London last year.",
            options=["have gone", "went", "have went"], hint_tr="'last year' bitmiş bir zaman.",
        )
        self.step = "q1"

    async def _step_q1(self, text: str, via: str, emit: Emit) -> None:
        answer = _norm(text)
        if "went" in answer and "have" not in answer:
            await self._tool(emit, "gesture", kind="cheer")
            await self._say(emit, "Exactly! Last year is a finished time, so we say went.")
            await self._tool(emit, "award_xp", amount=10, reason="Past simple ile doğru cevap")
            await self._tool(emit, "update_skill", skill="grammar", delta=3, reason="q1 correct")
            self.score += 1
        else:
            await self._tool(
                emit, "correct_mistake", original=f"I {text} to London last year.",
                corrected="I went to London last year.",
                explanation_tr="'last year' bitmiş bir zamanı gösterir, bu yüzden past simple (went) kullanılır.",
                category="present_perfect",
            )
            await self._say(emit, "Not quite. Look at the red pen on your notebook.")
        await self._say(emit, "Next one. Fill in the blank.")
        await self._tool(
            emit, "ask_question", kind="fill_blank", prompt="She __ (never / see) snow.",
            hint_tr="has + never + V3",
        )
        self.step = "q2"

    async def _step_q2(self, text: str, via: str, emit: Emit) -> None:
        answer = _norm(text)
        if "has never seen" in answer:
            await self._tool(emit, "gesture", kind="nod")
            await self._say(emit, "Perfect. She has never seen snow.")
            await self._tool(emit, "award_xp", amount=15, reason="Present perfect + never")
            await self._tool(emit, "update_skill", skill="grammar", delta=4, reason="q2 correct")
            self.score += 1
        else:
            await self._tool(
                emit, "correct_mistake", original=f"She {text} snow.", corrected="She has never seen snow.",
                explanation_tr="Yapı: has + never + fiilin 3. hali. 'see' fiilinin 3. hali 'seen'.",
                category="present_perfect",
            )
            await self._say(emit, "Almost. Has, then never, then the third form, seen.")
        await self._tool(emit, "gesture", kind="explain")
        await self._say(emit, "Now it's your turn. You can type, or press the microphone and say it.")
        await self._tool(
            emit, "ask_question", kind="open", prompt="Tell me something you have done this week. Start with: This week I have...",
            hint_tr="Yazabilir ya da mikrofona söyleyebilirsin.",
        )
        self.step = "q3"

    async def _step_q3(self, text: str, via: str, emit: Emit) -> None:
        lowered = text.lower()
        m = re.search(r"\b(have|has)\s+(" + "|".join(V2_TO_V3) + r")\b", lowered)
        if m:
            wrong = m.group(0)
            right = f"{m.group(1)} {V2_TO_V3[m.group(2)]}"
            await self._tool(
                emit, "correct_mistake", original=text, corrected=re.sub(re.escape(wrong), right, text, flags=re.I),
                explanation_tr=f"have/has'ten sonra fiilin 3. hali gelir: '{m.group(2)}' değil '{V2_TO_V3[m.group(2)]}'.",
                category="present_perfect",
            )
            await self._say(emit, "Good try! Just one small thing, look at your notebook.")
        elif re.search(r"\bi am agree\b", lowered):
            await self._tool(
                emit, "correct_mistake", original=text, corrected=re.sub(r"(?i)\bi am agree\b", "I agree", text),
                explanation_tr="'agree' bir fiildir, önüne 'am' gelmez.", category="agree",
            )
            await self._say(emit, "Nice sentence. One small fix on your notebook.")
        else:
            await self._tool(emit, "gesture", kind="cheer")
            await self._say(emit, "Lovely! That sounds very natural.")
            self.score += 1
        skill = "speaking" if via == "voice" else "writing"
        await self._tool(emit, "update_skill", skill=skill, delta=3, reason="free production")
        await self._tool(emit, "award_xp", amount=10, reason="Kendi cümleni kurdun")
        await self._say(emit, "Here are three new words for our word wall.")
        await self._tool(emit, "add_vocab", word="already", meaning_tr="zaten, çoktan", example="I have already eaten.")
        await self._tool(emit, "add_vocab", word="yet", meaning_tr="henüz (olumsuz/soru)", example="Have you finished yet?")
        await self._tool(emit, "add_vocab", word="experience", meaning_tr="deneyim", example="It was a great experience.")
        await self._tool(emit, "update_skill", skill="vocabulary", delta=2, reason="3 new words")
        await self._say(emit, "Last question. Which word fits?")
        await self._tool(
            emit, "ask_question", kind="multiple_choice", prompt="Have you finished your homework __?",
            options=["yet", "already", "ago"], hint_tr="Soru cümlesinin sonunda...",
        )
        self.step = "q4"

    async def _step_q4(self, text: str, via: str, emit: Emit) -> None:
        if _norm(text) == "yet":
            await self._say(emit, "Yes! Yet goes at the end of questions and negatives.")
            await self._tool(emit, "award_xp", amount=10, reason="yet doğru kullanıldı")
            self.score += 1
        else:
            await self._tool(
                emit, "correct_mistake", original=f"Have you finished your homework {text}?",
                corrected="Have you finished your homework yet?",
                explanation_tr="Soru ve olumsuz cümlelerin sonunda 'yet' kullanılır.", category="present_perfect",
            )
            await self._say(emit, "The answer is yet. It goes at the end of questions.")
        await self._tool(emit, "gesture", kind="cheer")
        await self._say(emit, f"Great job today, {self.name}! You got {self.score} out of 4.")
        await self._tool(
            emit, "end_lesson", topic="Present Perfect vs Past Simple",
            summary=f"Demo dersi: present perfect / past simple farkı. Skor {self.score}/4. Yeni kelimeler: already, yet, experience.",
        )
        await self._say(emit, "Demo ders burada bitiyor. Gerçek öğretmenle ders yapmak için API anahtarını ekleyip sunucuyu yeniden başlat.")
        self.step = "done"

    async def _step_done(self, text: str, via: str, emit: Emit) -> None:
        await self._say(emit, "Our demo lesson is over. Refresh the page to start it again.")
        await self._say(emit, "Sayfayı yenilersen demo baştan başlar.")
