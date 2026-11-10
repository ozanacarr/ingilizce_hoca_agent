"""Öğrenci hafızası: profil, hata defteri, kelime kutusu (aralıklı tekrar), beceri puanları, ders geçmişi.

Her şey data/student.json dosyasında durur. Dosyayı silersen öğretmen seni sıfırdan tanımaya başlar.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

# Aralıklı tekrar kutuları (Leitner sistemi): kelime doğru hatırlandıkça bir üst kutuya çıkar
# ve daha seyrek sorulur. Yanlışta 1. kutuya döner. Değerler gün cinsinden bekleme süresi.
BOX_INTERVALS = [0, 1, 2, 4, 8, 16, 32]

SKILLS = ["grammar", "vocabulary", "speaking", "writing", "listening"]

XP_PER_LEVEL = 100


def _default_state() -> dict:
    return {
        "profile": {
            "name": None,
            "level": None,  # A1..C2, seviye tespitinden sonra dolar
            "goals": [],
            "interests": [],
            "native_language": "Turkish",
        },
        "skills": {s: 0 for s in SKILLS},  # 0-100
        "xp": 0,
        "mistakes": [],  # {category, original, corrected, explanation, count, last_seen}
        "vocab": [],  # {word, meaning_tr, example, box, due, added}
        "lessons": [],  # {date, topic, summary}
        "created": date.today().isoformat(),
    }


class StudentMemory:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        if path.exists():
            self.state = json.loads(path.read_text(encoding="utf-8"))
            # Eski dosyada eksik alan varsa tamamla
            for key, value in _default_state().items():
                self.state.setdefault(key, value)
        else:
            self.state = _default_state()
            self.save()

    # ---------- kayıt ----------
    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    # ---------- profil ----------
    def update_profile(self, field: str, value) -> None:
        profile = self.state["profile"]
        if field in ("goals", "interests"):
            items = value if isinstance(value, list) else [value]
            for item in items:
                if item and item not in profile[field]:
                    profile[field].append(item)
        else:
            profile[field] = value
        self.save()

    # ---------- hata defteri ----------
    def log_mistake(self, category: str, original: str, corrected: str, explanation: str) -> int:
        """Hatayı deftere yazar, bu kategoride kaçıncı kez yapıldığını döndürür."""
        now = datetime.now().isoformat(timespec="seconds")
        for m in self.state["mistakes"]:
            if m["category"] == category and m["original"].strip().lower() == original.strip().lower():
                m["count"] += 1
                m["last_seen"] = now
                self.save()
                return self.category_count(category)
        self.state["mistakes"].append(
            {
                "category": category,
                "original": original,
                "corrected": corrected,
                "explanation": explanation,
                "count": 1,
                "last_seen": now,
            }
        )
        self.save()
        return self.category_count(category)

    def category_count(self, category: str) -> int:
        return sum(m["count"] for m in self.state["mistakes"] if m["category"] == category)

    def top_mistake_categories(self, n: int = 5) -> list[tuple[str, int]]:
        totals: dict[str, int] = {}
        for m in self.state["mistakes"]:
            totals[m["category"]] = totals.get(m["category"], 0) + m["count"]
        return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]

    # ---------- kelimeler ----------
    def add_vocab(self, word: str, meaning_tr: str, example: str) -> bool:
        """Yeni kelimeyi kutuya ekler. Zaten varsa False döner."""
        for v in self.state["vocab"]:
            if v["word"].lower() == word.lower():
                return False
        today = date.today()
        self.state["vocab"].append(
            {
                "word": word,
                "meaning_tr": meaning_tr,
                "example": example,
                "box": 1,
                "due": (today + timedelta(days=BOX_INTERVALS[1])).isoformat(),
                "added": today.isoformat(),
            }
        )
        self.save()
        return True

    def review_vocab(self, word: str, remembered: bool) -> dict | None:
        for v in self.state["vocab"]:
            if v["word"].lower() == word.lower():
                v["box"] = min(v["box"] + 1, len(BOX_INTERVALS) - 1) if remembered else 1
                v["due"] = (date.today() + timedelta(days=BOX_INTERVALS[v["box"]])).isoformat()
                self.save()
                return v
        return None

    def due_vocab(self) -> list[dict]:
        today = date.today().isoformat()
        return [v for v in self.state["vocab"] if v["due"] <= today]

    # ---------- beceriler ve XP ----------
    def update_skill(self, skill: str, delta: int) -> int:
        current = self.state["skills"].get(skill, 0)
        self.state["skills"][skill] = max(0, min(100, current + delta))
        self.save()
        return self.state["skills"][skill]

    def award_xp(self, amount: int) -> int:
        self.state["xp"] += amount
        self.save()
        return self.state["xp"]

    # ---------- ders geçmişi ----------
    def end_lesson(self, topic: str, summary: str) -> None:
        self.state["lessons"].append({"date": date.today().isoformat(), "topic": topic, "summary": summary})
        self.save()

    # ---------- arayüz ve öğretmen için özetler ----------
    def snapshot(self) -> dict:
        """Arayüzün karne ve kelime duvarı için ihtiyaç duyduğu veriler."""
        xp = self.state["xp"]
        return {
            "profile": self.state["profile"],
            "skills": self.state["skills"],
            "xp": xp,
            "xp_level": xp // XP_PER_LEVEL + 1,
            "xp_in_level": xp % XP_PER_LEVEL,
            "xp_per_level": XP_PER_LEVEL,
            "vocab": [
                {"word": v["word"], "meaning_tr": v["meaning_tr"], "box": v["box"]}
                for v in self.state["vocab"][-24:]
            ],
            "vocab_total": len(self.state["vocab"]),
            "due_count": len(self.due_vocab()),
            "lessons": len(self.state["lessons"]),
        }

    def summary_for_teacher(self) -> str:
        """Her dersin başında öğretmene verilen öğrenci özeti."""
        s = self.state
        p = s["profile"]
        lines = ["# Student file"]
        if not p["name"] and not p["level"]:
            lines.append(
                "This is a NEW student. You know nothing about them yet. Start with a short, friendly onboarding: "
                "ask their name, why they want to learn English, and their interests (one question at a time). "
                "Then explain in one sentence that a short placement test comes next and run it with "
                "placement_next / placement_answer. Do NOT teach any topic before the test is finished."
            )
        elif not p["level"]:
            lines.append("Level is unknown: run the placement test (placement_next with restart=true) before teaching.")
        else:
            lines.append(f"- Name: {p['name'] or 'unknown'}")
            lines.append(f"- Level (CEFR): {p['level'] or 'not placed yet - run a quick placement check'}")
            lines.append(f"- Goals: {', '.join(p['goals']) or 'unknown'}")
            lines.append(f"- Interests: {', '.join(p['interests']) or 'unknown'}")
        lines.append(f"- Skills (0-100): " + ", ".join(f"{k} {v}" for k, v in s["skills"].items()))
        lines.append(f"- XP: {s['xp']}")

        weak = s.get("weak_points") or []
        if weak:
            lines.append("\n## Weak topics from the placement test (teach these first, one at a time)")
            lines.append("- " + ", ".join(weak))

        top = self.top_mistake_categories()
        if top:
            lines.append("\n## Recurring mistakes (category: times)")
            for cat, count in top:
                example = next(m for m in reversed(s["mistakes"]) if m["category"] == cat)
                lines.append(f"- {cat}: {count}x - e.g. \"{example['original']}\" -> \"{example['corrected']}\"")

        due = self.due_vocab()
        if due:
            lines.append("\n## Vocabulary due for review today (use review_vocab after asking)")
            for v in due[:10]:
                lines.append(f"- {v['word']} ({v['meaning_tr']}), box {v['box']}")
        if s["vocab"]:
            lines.append(f"\nTotal words learned so far: {len(s['vocab'])}")

        if s["lessons"]:
            lines.append("\n## Last lessons")
            for lesson in s["lessons"][-3:]:
                lines.append(f"- {lesson['date']} - {lesson['topic']}: {lesson['summary']}")
        return "\n".join(lines)
