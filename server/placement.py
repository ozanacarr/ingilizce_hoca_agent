"""Seviye tespit sınavı: soruları öğretmen uydurmaz, data/placement_test.json bankasından gelir.

Yöntem: A1'den başlar, her seviyeden 3 soru sorar. Bir seviyede en az 2 doğru yapan bir üst seviyeye geçer.
2'den az doğru yapılan ilk seviyede sınav biter. Öğrencinin seviyesi geçtiği en yüksek seviyedir.
Yanlış yapılan konular "eksikler" olarak hafızaya yazılır; öğretmen dersleri bunlara göre planlar.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

BANK_FILE = Path(__file__).resolve().parent.parent / "data" / "placement_test.json"
PER_LEVEL = 3
PASS = 2


def _bank() -> dict:
    return json.loads(BANK_FILE.read_text(encoding="utf-8"))


def start(memory) -> None:
    memory.state["placement"] = {"level_index": 0, "asked": [], "results": [], "current": None, "done": False}
    memory.save()


def next_question(memory) -> dict | None:
    """Sıradaki soruyu seçer ve hafızaya 'current' olarak yazar. Sınav bittiyse None."""
    p = memory.state.get("placement")
    if not p or p["done"]:
        return None
    bank = _bank()
    level = bank["levels"][p["level_index"]]
    pool = [q for q in bank["questions"] if q["level"] == level and q["id"] not in p["asked"]]
    q = random.choice(pool)
    p["asked"].append(q["id"])
    p["current"] = q["id"]
    memory.save()
    options = q["options"][:]
    random.shuffle(options)
    return {"id": q["id"], "level": level, "prompt": q["prompt"], "options": options,
            "number": len(p["asked"])}


def answer(memory, given: str) -> dict:
    """Cevabı kontrol eder; seviye geçişini ve sınav sonunu hesaplar."""
    p = memory.state.get("placement")
    if not p or not p.get("current"):
        return {"error": "No placement question is open. Call placement_next first."}
    bank = _bank()
    q = next(x for x in bank["questions"] if x["id"] == p["current"])
    correct = given.strip().lower() == q["answer"].lower()
    p["results"].append({"id": q["id"], "level": q["level"], "topic": q["topic"], "correct": correct, "given": given})
    p["current"] = None

    level = bank["levels"][p["level_index"]]
    at_level = [r for r in p["results"] if r["level"] == level]
    result = {"correct": correct, "right_answer": q["answer"], "done": False}
    if len(at_level) >= PER_LEVEL:
        passed = sum(r["correct"] for r in at_level) >= PASS
        if passed and p["level_index"] < len(bank["levels"]) - 1:
            p["level_index"] += 1
        else:
            p["done"] = True
            levels = bank["levels"]
            passed_levels = [lv for lv in levels
                             if sum(r["correct"] for r in p["results"] if r["level"] == lv) >= PASS]
            final = passed_levels[-1] if passed_levels else "A1"
            weak = sorted({r["topic"] for r in p["results"] if not r["correct"]})
            memory.update_profile("level", final)
            memory.state["weak_points"] = weak
            memory.save()
            score = sum(r["correct"] for r in p["results"])
            result.update(done=True, level=final, weak_points=weak, score=f"{score}/{len(p['results'])}")
    memory.save()
    return result
