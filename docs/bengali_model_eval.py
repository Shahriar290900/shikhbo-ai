#!/usr/bin/env python3
"""
Shikhbo — Bengali LLM Evaluation
=================================
Compares 3 candidate models on 20 NCTB SSC ICT (Bengali) questions to decide
which model powers the premium tier.

RUNS ENTIRELY LOCALLY ON YOUR MAC VIA OLLAMA — costs $0, no GPU rental.

Prerequisites:
    1. Install Ollama: https://ollama.com
    2. Pull the three models (one-time download):
         ollama pull gemma2:2b
         ollama pull gemma2:9b          # the 9B is just "gemma2" default tag too
         ollama pull qwen2.5:7b
    3. pip install ollama anthropic

Usage:
    # Mode A — generate answers + auto-score with Claude as judge (needs ANTHROPIC_API_KEY)
    export ANTHROPIC_API_KEY=sk-ant-...
    python bengali_model_eval.py --judge claude

    # Mode B — generate answers only, score them yourself by reading the report
    python bengali_model_eval.py --judge manual

Output:
    bengali_eval_report.md   — side-by-side answers + scores
"""

import argparse
import json
import time
from pathlib import Path

try:
    import ollama
except ImportError:
    raise SystemExit("Run: pip install ollama")

# ---------------------------------------------------------------------------
# 20 NCTB SSC ICT Chapter-1 questions (তথ্য ও যোগাযোগ প্রযুক্তি ও আমাদের বাংলাদেশ)
# Mix of factual recall, conceptual explanation, and application.
# ---------------------------------------------------------------------------
QUESTIONS = [
    {"id": 1,  "type": "concept",     "q": "তথ্য ও যোগাযোগ প্রযুক্তি (ICT) কাকে বলে? সহজ ভাষায় ব্যাখ্যা করো।"},
    {"id": 2,  "type": "concept",     "q": "একুশ শতকে জ্ঞানকে কেন সবচেয়ে বড় সম্পদ হিসেবে বিবেচনা করা হয়?"},
    {"id": 3,  "type": "factual",     "q": "গ্লোবাল ভিলেজ বা বিশ্বগ্রাম বলতে কী বোঝায়?"},
    {"id": 4,  "type": "application", "q": "শিক্ষাক্ষেত্রে তথ্য ও যোগাযোগ প্রযুক্তির তিনটি ব্যবহার উদাহরণসহ লেখো।"},
    {"id": 5,  "type": "application", "q": "চিকিৎসা ক্ষেত্রে ICT কীভাবে সাহায্য করছে? টেলিমেডিসিন ব্যাখ্যা করো।"},
    {"id": 6,  "type": "concept",     "q": "ই-কমার্স কী? এর দুটি সুবিধা উল্লেখ করো।"},
    {"id": 7,  "type": "factual",     "q": "ভার্চুয়াল রিয়েলিটি (Virtual Reality) বলতে কী বোঝায়?"},
    {"id": 8,  "type": "application", "q": "কৃষিক্ষেত্রে তথ্যপ্রযুক্তির ব্যবহার কীভাবে কৃষকদের উপকার করছে?"},
    {"id": 9,  "type": "concept",     "q": "ডিজিটাল বাংলাদেশ ধারণাটি ব্যাখ্যা করো।"},
    {"id": 10, "type": "factual",     "q": "আউটসোর্সিং (Outsourcing) কী? উদাহরণ দাও।"},
    {"id": 11, "type": "concept",     "q": "ক্রায়োসার্জারি (Cryosurgery) কী এবং এটি কীভাবে কাজ করে?"},
    {"id": 12, "type": "application", "q": "অফিস ও ব্যবসা ক্ষেত্রে ICT ব্যবহারের ফলে কী কী পরিবর্তন এসেছে?"},
    {"id": 13, "type": "concept",     "q": "বায়োমেট্রিক্স (Biometrics) কী? এর ব্যবহার কোথায় হয়?"},
    {"id": 14, "type": "factual",     "q": "রোবট কী? শিল্পক্ষেত্রে রোবটের ব্যবহার কেন বাড়ছে?"},
    {"id": 15, "type": "application", "q": "তথ্যপ্রযুক্তি ব্যবহার করে কীভাবে কর্মসংস্থানের নতুন সুযোগ তৈরি হচ্ছে?"},
    {"id": 16, "type": "concept",     "q": "ন্যানোটেকনোলজি (Nanotechnology) সম্পর্কে সংক্ষেপে লেখো।"},
    {"id": 17, "type": "concept",     "q": "জেনেটিক ইঞ্জিনিয়ারিং বলতে কী বোঝায়?"},
    {"id": 18, "type": "application", "q": "বিনোদন ক্ষেত্রে তথ্য ও যোগাযোগ প্রযুক্তির প্রভাব আলোচনা করো।"},
    {"id": 19, "type": "factual",     "q": "আর্টিফিশিয়াল ইন্টেলিজেন্স বা কৃত্রিম বুদ্ধিমত্তা কী?"},
    {"id": 20, "type": "application", "q": "তথ্যপ্রযুক্তি ব্যবহারে কী কী নৈতিক সমস্যা বা ঝুঁকি তৈরি হতে পারে?"},
]

MODELS = ["gemma2:2b", "gemma2:9b", "qwen2.5:7b"]

SYSTEM_PROMPT = (
    "তুমি 'শিখবো' — বাংলাদেশের NCTB কারিকুলামের একজন সহায়ক শিক্ষক। "
    "SSC শ্রেণির শিক্ষার্থীদের জন্য সহজ, সঠিক এবং প্রাঞ্জল বাংলায় উত্তর দাও। "
    "উত্তর সংক্ষিপ্ত কিন্তু সম্পূর্ণ হবে। ভুল তথ্য দেবে না।"
)

JUDGE_PROMPT = """You are evaluating a Bengali-language answer from an educational AI tutor for SSC (grade 9-10) students in Bangladesh, studying ICT.

Question (Bengali): {question}

Model's answer (Bengali): {answer}

Score the answer on these 4 dimensions, each 1-5 (5 = best):
1. bengali_fluency — Is the Bengali natural, grammatically correct, and readable? (Penalize awkward/machine-translated Bengali, English code-switching, or broken script.)
2. factual_accuracy — Is the ICT content correct for the NCTB curriculum?
3. completeness — Does it fully answer the question at an SSC level?
4. clarity — Would a 15-year-old Bangladeshi student understand it easily?

Return ONLY valid JSON, no other text:
{{"bengali_fluency": N, "factual_accuracy": N, "completeness": N, "clarity": N, "comment": "one short sentence"}}"""


def generate_answer(model: str, question: str) -> tuple[str, float]:
    """Generate one answer from an Ollama model. Returns (answer, seconds)."""
    start = time.time()
    try:
        resp = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            options={"temperature": 0.3, "num_predict": 400},
        )
        answer = resp["message"]["content"].strip()
    except Exception as e:
        answer = f"[ERROR: {e}]"
    return answer, round(time.time() - start, 1)


def judge_with_claude(question: str, answer: str) -> dict:
    """Score one answer using Claude as an LLM judge."""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(question=question, answer=answer),
        }],
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"bengali_fluency": 0, "factual_accuracy": 0,
                "completeness": 0, "clarity": 0, "comment": "judge parse failed"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["claude", "manual"], default="manual")
    ap.add_argument("--models", nargs="+", default=MODELS)
    args = ap.parse_args()

    results = []  # list of {question, model, answer, seconds, scores}
    print(f"Running {len(QUESTIONS)} questions × {len(args.models)} models "
          f"= {len(QUESTIONS) * len(args.models)} generations...\n")

    for qobj in QUESTIONS:
        for model in args.models:
            print(f"  Q{qobj['id']:>2} · {model:<12} ... ", end="", flush=True)
            answer, secs = generate_answer(model, qobj["q"])
            scores = None
            if args.judge == "claude" and not answer.startswith("[ERROR"):
                scores = judge_with_claude(qobj["q"], answer)
            results.append({
                "qid": qobj["id"], "qtype": qobj["type"], "question": qobj["q"],
                "model": model, "answer": answer, "seconds": secs, "scores": scores,
            })
            print(f"{secs}s")

    # ---- Aggregate scores per model ----
    summary = {}
    if args.judge == "claude":
        for model in args.models:
            rows = [r for r in results if r["model"] == model and r["scores"]]
            if not rows:
                continue
            dims = ["bengali_fluency", "factual_accuracy", "completeness", "clarity"]
            avg = {d: round(sum(r["scores"][d] for r in rows) / len(rows), 2) for d in dims}
            avg["overall"] = round(sum(avg[d] for d in dims) / 4, 2)
            avg["avg_seconds"] = round(sum(r["seconds"] for r in rows) / len(rows), 1)
            summary[model] = avg

    # ---- Write markdown report ----
    out = Path("bengali_eval_report.md")
    with out.open("w", encoding="utf-8") as f:
        f.write("# Shikhbo — Bengali Model Evaluation Report\n\n")

        if summary:
            f.write("## Summary Scores (averaged across 20 questions, 1-5 scale)\n\n")
            f.write("| Model | Bengali Fluency | Accuracy | Completeness | Clarity | **Overall** | Avg Speed |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            ranked = sorted(summary.items(), key=lambda x: x[1]["overall"], reverse=True)
            for model, s in ranked:
                f.write(f"| {model} | {s['bengali_fluency']} | {s['factual_accuracy']} | "
                        f"{s['completeness']} | {s['clarity']} | **{s['overall']}** | {s['avg_seconds']}s |\n")
            winner = ranked[0][0]
            f.write(f"\n**Recommended premium model: `{winner}`** "
                    f"(highest overall Bengali quality score)\n\n")
            f.write("> Note: also weigh speed. If the top model is much slower, "
                    "the second place may be the better demo choice.\n\n")
        else:
            f.write("## Manual Scoring Mode\n\n")
            f.write("Read each answer and score 1-5 on Bengali fluency, accuracy, "
                    "completeness, and clarity. Tally per model at the end.\n\n")

        f.write("---\n\n## Full Answers (side by side)\n\n")
        for qobj in QUESTIONS:
            f.write(f"### Q{qobj['id']} ({qobj['type']})\n")
            f.write(f"**{qobj['q']}**\n\n")
            for model in args.models:
                r = next(x for x in results if x["qid"] == qobj["id"] and x["model"] == model)
                f.write(f"**`{model}`** _({r['seconds']}s)_\n\n")
                f.write(f"{r['answer']}\n\n")
                if r["scores"]:
                    s = r["scores"]
                    f.write(f"> Scores — fluency {s['bengali_fluency']}, "
                            f"accuracy {s['factual_accuracy']}, complete {s['completeness']}, "
                            f"clarity {s['clarity']}. {s['comment']}\n\n")
            f.write("---\n\n")

    # Save raw JSON too
    Path("bengali_eval_raw.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Done. Report: {out.resolve()}")
    if summary:
        print("\nRanking:")
        for model, s in sorted(summary.items(), key=lambda x: x[1]['overall'], reverse=True):
            print(f"  {model:<12} overall {s['overall']}  ({s['avg_seconds']}s avg)")


if __name__ == "__main__":
    main()
