"""Öğretmenin araçları.

Öğretmen sadece konuşmaz; bu araçları çağırarak sınıfı yönetir. Her araç iki şey yapar:
  1. Arayüze bir olay gönderir (tahtaya yaz, soru kartı göster, kelime duvarına ekle...)
  2. Gerekirse öğrenci hafızasını günceller (hata defteri, kelime kutusu, beceri puanı...)

Yeni bir araç eklemek için: TOOLS listesine tanımını, execute_tool içine de ne yapacağını ekle.
Arayüz tarafında da web/js/main.js içindeki handleEvent'e o olayın nasıl görüneceğini eklemek gerekir.
"""

from __future__ import annotations

import json
from typing import Any

from . import placement
from .memory import SKILLS, StudentMemory

MISTAKE_CATEGORIES = [
    "articles",
    "present_perfect",
    "past_simple",
    "third_person_s",
    "agree",
    "prepositions",
    "word_order",
    "gender_pronoun",
    "make_do",
    "plural",
    "verb_form",
    "tense",
    "spelling",
    "vocabulary_choice",
    "pronunciation_th",
    "pronunciation_w_v",
    "pronunciation_other",
    "other",
]

GESTURES = ["wave", "point_board", "nod", "think", "cheer", "explain"]


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        # Araç girdileri üretildikçe akar; doğrulamayı validate_input ile biz yapıyoruz.
        "eager_input_streaming": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS: list[dict] = [
    _tool(
        "board_write",
        "Write on the classroom blackboard. Replaces what is on the board. Use it for rules, example sentences, "
        "tables and anything the student should see while you talk. Keep it short: a title and at most 6 lines "
        "of up to ~45 characters. Use '__' for a blank and wrap a word in *asterisks* to highlight it in yellow chalk.",
        {
            "title": {"type": "string", "description": "Short heading, e.g. 'Present Perfect'"},
            "lines": {"type": "array", "items": {"type": "string"}, "description": "Lines to write, top to bottom"},
        },
        ["title", "lines"],
    ),
    _tool("board_clear", "Wipe the blackboard clean.", {}, []),
    _tool(
        "ask_question",
        "Put an exercise card on the student's desk. After calling this, finish your turn and wait for the "
        "student's answer. kinds: multiple_choice (give 2-4 options), fill_blank (prompt contains '__'), "
        "open (free writing), speak (the student should answer out loud with the microphone).",
        {
            "kind": {"type": "string", "enum": ["multiple_choice", "fill_blank", "open", "speak"]},
            "prompt": {"type": "string", "description": "The question in English"},
            "options": {"type": "array", "items": {"type": "string"}, "description": "Only for multiple_choice"},
            "hint_tr": {"type": "string", "description": "Optional short hint in Turkish"},
        },
        ["kind", "prompt"],
    ),
    _tool(
        "correct_mistake",
        "Mark a mistake the student made, like a teacher's red pen. Shows the correction on the student's "
        "notebook and records it in their mistake log so it can be reviewed later. Use for real errors only, "
        "at most 2 per turn, most important first.",
        {
            "original": {"type": "string", "description": "What the student wrote/said"},
            "corrected": {"type": "string", "description": "The corrected sentence"},
            "explanation_tr": {"type": "string", "description": "One-sentence explanation in Turkish"},
            "category": {"type": "string", "enum": MISTAKE_CATEGORIES},
        },
        ["original", "corrected", "explanation_tr", "category"],
    ),
    _tool(
        "add_vocab",
        "Pin a new word to the classroom word wall and add it to the student's spaced-repetition box.",
        {
            "word": {"type": "string"},
            "meaning_tr": {"type": "string", "description": "Turkish meaning"},
            "example": {"type": "string", "description": "A short example sentence"},
        },
        ["word", "meaning_tr", "example"],
    ),
    _tool(
        "review_vocab",
        "Record whether the student remembered a word that was due for review.",
        {"word": {"type": "string"}, "remembered": {"type": "boolean"}},
        ["word", "remembered"],
    ),
    _tool(
        "update_skill",
        "Adjust a skill score (0-100) on the student's report card based on evidence from this lesson. "
        "Small steps: usually -5 to +5.",
        {
            "skill": {"type": "string", "enum": SKILLS},
            "delta": {"type": "integer"},
            "reason": {"type": "string"},
        },
        ["skill", "delta", "reason"],
    ),
    _tool(
        "award_xp",
        "Give the student experience points for effort and correct answers (5-20 per good answer).",
        {"amount": {"type": "integer"}, "reason": {"type": "string"}},
        ["amount", "reason"],
    ),
    _tool(
        "update_profile",
        "Save something you learned about the student. field: name, level (A1, A2, B1, B2, C1, C2), "
        "goals or interests (added to a list).",
        {
            "field": {"type": "string", "enum": ["name", "level", "goals", "interests"]},
            "value": {"type": "string"},
        },
        ["field", "value"],
    ),
    _tool(
        "gesture",
        "Make your 3D avatar move: wave, point_board, nod, think, cheer, explain. Use naturally, not every turn.",
        {"kind": {"type": "string", "enum": GESTURES}},
        ["kind"],
    ),
    _tool(
        "end_lesson",
        "Close the lesson: save a short summary to the student's lesson history (used next time).",
        {
            "topic": {"type": "string"},
            "summary": {"type": "string", "description": "2-3 sentences: what was covered, what to review next"},
        },
        ["topic", "summary"],
    ),
]

TOOLS += [
    _tool(
        "placement_next",
        "Placement test: put the next question from the official question bank on the student's desk. "
        "Never write placement questions yourself. Call it once (with restart=true the first time), then end "
        "your turn and wait. The student's answer comes back as an [answer] message: pass it to placement_answer.",
        {"restart": {"type": "boolean", "description": "true to start a fresh test"}},
        [],
    ),
    _tool(
        "placement_answer",
        "Placement test: grade the student's answer to the current placement question. Tells you whether it "
        "was correct and, when the test is finished, the CEFR level and the weak topics (also saved to the "
        "student file). Do not explain the right answer during the test; just encourage and continue.",
        {"answer": {"type": "string", "description": "The student's answer, exactly as given"}},
        ["answer"],
    ),
]

_SCHEMAS = {t["name"]: t["input_schema"] for t in TOOLS}
_PY_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}


def validate_input(name: str, args: Any) -> str | None:
    """Araç girdisini şemaya göre kontrol eder. Sorun varsa açıklamasını, yoksa None döndürür."""
    schema = _SCHEMAS.get(name)
    if schema is None:
        return f"unknown tool {name}"
    if not isinstance(args, dict):
        return "input is not an object"
    for key in schema["required"]:
        if key not in args:
            return f"missing field '{key}'"
    for key, value in args.items():
        prop = schema["properties"].get(key)
        if prop is None:
            return f"unexpected field '{key}'"
        expected = _PY_TYPES[prop["type"]]
        if prop["type"] == "integer" and isinstance(value, bool):
            return f"'{key}' must be an integer"
        if not isinstance(value, expected):
            return f"'{key}' must be {prop['type']}"
        if "enum" in prop and value not in prop["enum"]:
            return f"'{key}' must be one of {prop['enum']}"
        if prop["type"] == "array" and not all(isinstance(i, str) for i in value):
            return f"'{key}' must be a list of strings"
    return None


def execute_tool(name: str, args: dict, memory: StudentMemory) -> tuple[list[dict], str]:
    """Aracı çalıştırır. (arayüz olayları, öğretmene dönecek sonuç metni) döndürür."""
    if name == "board_write":
        return [{"type": "board", "title": args["title"], "lines": args["lines"][:8]}], "Written on the board."

    if name == "placement_next":
        if args.get("restart") or not memory.state.get("placement"):
            placement.start(memory)
        q = placement.next_question(memory)
        if q is None:
            return [], "The placement test is already finished. Use placement_next with restart=true to retake it."
        event = {"type": "question", "kind": "multiple_choice", "prompt": q["prompt"], "options": q["options"],
                 "hint_tr": f"Seviye tespit sınavı · Soru {q['number']}"}
        return [event], (f"Question {q['number']} ({q['level']}) is on the desk: \"{q['prompt']}\". "
                         "End your turn now and wait for the answer.")

    if name == "placement_answer":
        r = placement.answer(memory, args["answer"])
        if "error" in r:
            return [], r["error"]
        if r["done"]:
            note = (f"Test finished. Score {r['score']}. Level: {r['level']}. Weak topics: "
                    f"{', '.join(r['weak_points']) or 'none'}. Tell the student their level kindly, then build "
                    "the next lessons on the weak topics, one small topic at a time.")
            return [{"type": "state", "state": memory.snapshot()}], note
        return [], f"{'Correct' if r['correct'] else 'Wrong'}. Now call placement_next for the next question."

    if name == "board_clear":
        return [{"type": "board", "title": "", "lines": []}], "Board wiped."

    if name == "ask_question":
        event = {
            "type": "question",
            "kind": args["kind"],
            "prompt": args["prompt"],
            "options": args.get("options", []),
            "hint_tr": args.get("hint_tr", ""),
        }
        return [event], "The card is on the student's desk. End your turn now and wait for their answer."

    if name == "correct_mistake":
        total = memory.log_mistake(args["category"], args["original"], args["corrected"], args["explanation_tr"])
        event = {"type": "correction", **{k: args[k] for k in ("original", "corrected", "explanation_tr", "category")}}
        note = f"Logged. The student has made '{args['category']}' mistakes {total} time(s) in total."
        if total >= 3:
            note += " This is a recurring problem: consider a short focused mini-exercise on it soon."
        return [event, {"type": "state", "state": memory.snapshot()}], note

    if name == "add_vocab":
        added = memory.add_vocab(args["word"], args["meaning_tr"], args["example"])
        if not added:
            return [], f"'{args['word']}' is already in the student's word box."
        event = {"type": "vocab_added", "word": args["word"], "meaning_tr": args["meaning_tr"], "example": args["example"]}
        return [event, {"type": "state", "state": memory.snapshot()}], "Pinned to the word wall."

    if name == "review_vocab":
        v = memory.review_vocab(args["word"], args["remembered"])
        if v is None:
            return [], f"'{args['word']}' is not in the student's word box."
        return [{"type": "state", "state": memory.snapshot()}], f"Recorded. Next review on {v['due']} (box {v['box']})."

    if name == "update_skill":
        value = memory.update_skill(args["skill"], max(-15, min(15, args["delta"])))
        return [{"type": "state", "state": memory.snapshot()}], f"{args['skill']} is now {value}/100."

    if name == "award_xp":
        amount = max(0, min(50, args["amount"]))
        memory.award_xp(amount)
        events = [
            {"type": "xp", "amount": amount, "reason": args["reason"]},
            {"type": "state", "state": memory.snapshot()},
        ]
        return events, f"+{amount} XP given."

    if name == "update_profile":
        memory.update_profile(args["field"], args["value"])
        return [{"type": "state", "state": memory.snapshot()}], "Saved to the student file."

    if name == "gesture":
        return [{"type": "gesture", "kind": args["kind"]}], "ok"

    if name == "end_lesson":
        memory.end_lesson(args["topic"], args["summary"])
        return [{"type": "lesson_end", "topic": args["topic"], "summary": args["summary"]}], "Lesson saved."

    return [], json.dumps({"error": f"unknown tool {name}"})
