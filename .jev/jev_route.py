#!/usr/bin/env python3
"""
Jev yönlendirici — hangi göreve hangi Claude modeli ve effort?

Kararı TypeSafe'in Jev modeli verir. Jev görevi atomik sorularla puanlar,
puanları birleştirme ve eşikler ise bu dosyadaki koddadır (TypeSafe'in
önerdiği "composite scoring" + "confidence-gated routing" deseni).

Kullanım:
  Claude Code hook :  python3 jev_route.py --hook      (stdin: hook JSON'u)
  Terminal / Cursor:  python3 jev_route.py "görev metni"
  Ham çıktı       :  python3 jev_route.py --json "görev metni"

Ortam değişkenleri:
  TYPESAFE_API_KEY  (zorunlu)  https://console.typesafe.ai/keys
  JEV_MODEL         varsayılan: jev-latest
  JEV_TIMEOUT       saniye, varsayılan: 6
  JEV_DISABLED=1    Jev'i geçici kapatır
  JEV_LOG           karar günlüğü, varsayılan: ~/.jev/decisions.jsonl

Sadece Python standart kütüphanesi kullanır.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = os.environ.get("JEV_MODEL", "jev-latest")
TIMEOUT = float(os.environ.get("JEV_TIMEOUT", "6"))
LOG_PATH = os.path.expanduser(os.environ.get("JEV_LOG", "~/.jev/decisions.jsonl"))

# ---------------------------------------------------------------- kademeler
TIERS = [
    {"key": "hizli",   "label": "⚡ Hızlı",   "agent": "jev-hizli",   "model": "haiku",  "effort": None,     "cost": "düşük"},
    {"key": "dengeli", "label": "⚖️ Dengeli", "agent": "jev-dengeli", "model": "sonnet", "effort": "medium", "cost": "düşük-orta"},
    {"key": "guclu",   "label": "💪 Güçlü",   "agent": "jev-guclu",   "model": "sonnet", "effort": "high",   "cost": "orta"},
    {"key": "derin",   "label": "🧠 Derin",   "agent": "jev-derin",   "model": "opus",   "effort": "high",   "cost": "orta-yüksek"},
    {"key": "usta",    "label": "🏛️ Usta",    "agent": "jev-usta",    "model": "fable",  "effort": "high",   "cost": "yüksek"},
]

# ------------------------------------------------ ayarlanabilir eşikler
WEIGHTS = {"scope": 1.0, "ambiguity": 1.0, "risk": 1.5, "reasoning": 1.5, "duration": 1.0}  # maks 12 puan
TIER_CUTS = [2.5, 4.5, 6.5, 9.0]   # bu değerlerin altı: hızlı, dengeli, güçlü, derin; üstü: usta
TRIVIAL_AT = 0.8                   # bu noul üstü + düşük risk => kart yok
PREF_AT = 0.7                      # hız/kalite isteği eşiği
UNSURE_AT = 0.5                    # risk/zorluk güveni bunun altındaysa güvenli tarafa kay
RISK_FLOORS = [(1.5, 2), (0.75, 1)]  # risk >= 1.5 => en az Güçlü, risk >= 0.75 => en az Dengeli

# --------------------------------------------------------- Jev'e sorular
# Jev literal okur: her soru tek bir şeyi, açık kriterlerle sorar. Aritmetik kodda.
def _score(instr, levels):
    return {"type": "score", "instructions": instr, "criteria": levels}

def _noul(instr, true, false):
    return {"type": "noul", "instructions": instr, "criteria": {"true": true, "false": false}}

QUESTIONS = {
    "trivial": _noul(
        "Is `coding_task` a quick question or a tiny edit that needs no planning?",
        "Explaining code, answering a short question, fixing a typo, renaming one symbol, a one-line change",
        "Anything that needs changes across a file, a design choice, debugging, or several steps",
    ),
    "scope": _score(
        "How much of the codebase does `coding_task` need to change?",
        ["A few lines in a single file",
         "Several files (2 to 5) in one area",
         "Many files, multiple modules, or several services"],
    ),
    "ambiguity": _score(
        "How clear is the path to a solution for `coding_task`?",
        ["It is clear what to do and how to do it",
         "The goal is clear but an approach must be chosen",
         "The root cause or the design is unknown and must be investigated first"],
    ),
    "risk": _score(
        "How costly would a mistake in `coding_task` be?",
        ["Cosmetic or trivially reverted (text, styling, comments, docs)",
         "Changes program behavior that tests should cover",
         "Touches security, authentication, payments, data integrity, concurrency, or database migrations"],
    ),
    "reasoning": _score(
        "How much reasoning does `coding_task` require?",
        ["Mechanical work: search, rename, format, boilerplate, commit messages",
         "Standard software engineering",
         "Hard reasoning: algorithms, architecture, performance, or subtle debugging"],
    ),
    "duration": _score(
        "How long is `coding_task` as a unit of work?",
        ["A single step",
         "A few steps",
         "Long multi-stage work that needs planning and self-verification"],
    ),
    "wants_speed": _noul(
        "Does `coding_task` explicitly ask for speed, a rough result, or saving cost or quota?",
        "Words like quick, fast, rough, cheap, save quota, hızlı, kabaca, tasarruf, ucuz",
        "No request about speed or cost",
    ),
    "wants_quality": _noul(
        "Does `coding_task` explicitly ask for maximum quality or say the work is critical?",
        "Words like critical, production, must be correct, best possible, kritik, production, emin ol, en iyisi",
        "No request about quality level",
    ),
}


def ask_jev(task: str) -> dict:
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY tanımlı değil")
    body = json.dumps({"state": {"coding_task": task}, "model": MODEL, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    last = None
    for attempt in range(2):  # 429/529 için tek kısa tekrar; hook bekletmesin
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 529) and attempt == 0:
                time.sleep(0.8)
                continue
            raise
    raise last


# ------------------------------------------------------------ karar (kod)
def decide(answers: dict) -> dict:
    sc = {k: float(answers[k]["score"]) for k in WEIGHTS}
    conf = {k: float(answers[k].get("confidence", 1.0)) for k in WEIGHTS}
    trivial = float(answers["trivial"]["noul"])
    speed = float(answers["wants_speed"]["noul"])
    quality = float(answers["wants_quality"]["noul"])

    if trivial >= TRIVIAL_AT and sc["risk"] < 0.75:
        return {"trivial": True, "scores": sc}

    points = sum(sc[k] * w for k, w in WEIGHTS.items())
    tier = next((i for i, cut in enumerate(TIER_CUTS) if points < cut), len(TIER_CUTS))
    notes = []

    shift = 0
    if speed >= PREF_AT:
        shift -= 1
        notes.append("hız/tasarruf isteği → bir kademe aşağı")
    unsure = min(conf["risk"], conf["reasoning"]) < UNSURE_AT
    if quality >= PREF_AT or unsure:
        shift += 1
        notes.append("kalite isteği → bir kademe yukarı" if quality >= PREF_AT
                     else "Jev risk/zorlukta emin değil → güvenli tarafa bir kademe")
    tier += shift

    floor = next((f for r, f in RISK_FLOORS if sc["risk"] >= r), 0)
    if tier < floor:
        tier = floor
        notes.append("risk tabanı uygulandı")
    tier = max(0, min(len(TIERS) - 1, tier))

    return {
        "trivial": False, "tier": TIERS[tier], "points": round(points, 2),
        "scores": {k: round(v, 2) for k, v in sc.items()},
        "confidence": {k: round(v, 2) for k, v in conf.items()},
        "notes": notes,
    }


def card(d: dict) -> str:
    t, s = d["tier"], d["scores"]
    effort = t["effort"] or "— (Haiku effort desteklemez)"
    lines = [
        "🎯 JEV KARARI",
        f"Kademe  : {t['label']}  →  {t['agent']}",
        f"Model   : {t['model']}   Effort: {effort}",
        f"Puan    : {d['points']}/12  (kapsam {s['scope']} · belirsizlik {s['ambiguity']} · "
        f"risk {s['risk']} · akıl yürütme {s['reasoning']} · süre {s['duration']})",
        f"Maliyet : {t['cost']}",
    ]
    if d["notes"]:
        lines.append("Not     : " + "; ".join(d["notes"]))
    return "\n".join(lines)


def log(task: str, d: dict):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task[:300],
               "tier": None if d.get("trivial") else d["tier"]["key"],
               "points": d.get("points"), "scores": d.get("scores"), "notes": d.get("notes")}
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------- modlar
def hook_mode():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    task = (payload.get("prompt") or "").strip()
    if not task or task.startswith("/") or os.environ.get("JEV_DISABLED") == "1":
        return
    try:
        d = decide(ask_jev(task)["answers"])
    except Exception as e:  # fail-open: Jev yoksa oturum normal devam eder
        print(json.dumps({"systemMessage": f"Jev'e ulaşılamadı ({e}); bu prompt yönlendirilmeden devam ediyor."}, ensure_ascii=False))
        return
    log(task, d)
    if d["trivial"]:
        return

    t = d["tier"]
    c = card(d)
    extra = ""
    if t["key"] == "usta":
        extra = ("\n- Bu Usta kademesi: Fable bazı planlarda kullanım kredisinden düşebilir. "
                 "Devretmeden önce kullanıcıdan onay al; onay yoksa `jev-derin` kullan.")
    ctx = (
        "JEV KARARI — bu karar TypeSafe Jev modeli tarafından verildi ve uygulanmalı.\n\n"
        f"{c}\n\n"
        "Talimat:\n"
        "- Yanıtına yukarıdaki kartı kod bloğu içinde aynen göstererek başla.\n"
        f"- Ardından işi Agent aracıyla `{t['agent']}` subagent'ına devret. Subagent bu konuşmayı görmez; "
        "ona amaç, ilgili dosya yolları, kısıtlar ve kabul kriterlerini içeren eksiksiz bir brif ver.\n"
        "- Subagent `⬆️ YÜKSELT` ile dönerse bir üst kademedeki subagent'a aynı brif ve öğrenilenlerle devret.\n"
        "- Kullanıcı bu mesajda açıkça belirli bir model istediyse onun isteği geçerlidir."
        f"{extra}"
    )
    print(json.dumps({
        "systemMessage": f"🎯 Jev: {t['label']} → {t['agent']} ({t['model']}"
                         + (f", {t['effort']}" if t["effort"] else "") + ")",
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx},
    }, ensure_ascii=False))


def cli_mode(args):
    raw = "--json" in args
    task = " ".join(a for a in args if a != "--json").strip() or sys.stdin.read().strip()
    if not task:
        sys.exit("Kullanım: jev_route.py [--json] \"görev metni\"")
    resp = ask_jev(task)
    d = decide(resp["answers"])
    log(task, d)
    if raw:
        print(json.dumps({"decision": d, "jev": resp}, ensure_ascii=False, indent=2))
        return
    if d["trivial"]:
        print("⚡ Jev: Bu kısa bir iş, mevcut modelle doğrudan yapılabilir.")
        return
    t = d["tier"]
    print(card(d))
    print(f"\nClaude Code'da elle geçmek için:\n  /model {t['model']}")
    if t["effort"]:
        print(f"  /effort {t['effort']}")


if __name__ == "__main__":
    if "--hook" in sys.argv[1:]:
        hook_mode()
    else:
        cli_mode(sys.argv[1:])
