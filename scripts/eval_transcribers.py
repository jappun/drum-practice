"""Compare AI providers at reading beats from photos, on your own photos.

    python scripts/eval_transcribers.py PHOTOS_DIR [--providers claude,openai,gemini]
                                                    [--models claude=claude-sonnet-5-5,...] [--yes]

PHOTOS_DIR holds pairs of files with the same name:
- `groove-a.png` (or .jpg/.jpeg): a photo, already cropped to what should be read;
- `groove-a.json`: the hand-checked answer. Either a beat file as the app saves
  it (enter the groove in the editor, Save, and copy the file from
  ~/Library/Application Support/Drum Practice/my_beats/), or
  {"beats": [beat, beat, ...]} for a photo with several grooves, in reading order.

Every configured provider (one with an API key in Settings) reads every photo.
For each provider and model it reports note accuracy (right drum at the right
position), what it missed or invented, speed, tokens and, where prices are
known, cost. Results are also saved as JSON next to the photos.

This sends your photos to the providers and costs real money, so it asks first
(skip the question with --yes).
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PySide6.QtGui import QImage  # noqa: E402

from drum_practice.ai import keys  # noqa: E402
from drum_practice.ai.evaluate import Score, score, total  # noqa: E402
from drum_practice.ai.providers import PROVIDERS, TranscriptionError, cost  # noqa: E402
from drum_practice.ai.transcription import PROMPT_VERSION, ReplyError, parse_reply, to_beats  # noqa: E402
from drum_practice.model import Beat  # noqa: E402
from drum_practice.ui.photo_import import prepare_image  # noqa: E402

PHOTO_TYPES = (".png", ".jpg", ".jpeg")


def load_cases(folder: Path) -> list[tuple[Path, list[Beat]]]:
    cases = []
    for photo in sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES):
        answer = photo.with_suffix(".json")
        if not answer.exists():
            print(f"  skipping {photo.name}: no {answer.name}")
            continue
        data = json.loads(answer.read_text())
        beats = [Beat.from_dict(b) for b in data["beats"]] if "beats" in data else [Beat.from_dict(data)]
        cases.append((photo, beats))
    return cases


def run(provider_name: str, model: str, cases, key: str) -> dict:
    provider = PROVIDERS[provider_name]()
    scores: list[Score] = []
    rows = []
    seconds = tokens_in = tokens_out = 0.0
    spend: float | None = 0.0
    for photo, answer in cases:
        image, mime = prepare_image(QImage(str(photo)), None)
        row = {"photo": photo.name}
        try:
            reply = provider.read(image, mime, model, key)
            got = [g.beat for g in to_beats(parse_reply(reply.text)).grooves]
            s = score(got, answer)
            scores.append(s)
            seconds += reply.seconds
            if reply.usage:
                tokens_in += reply.usage.input_tokens
                tokens_out += reply.usage.output_tokens
            c = cost(model, reply.usage)
            spend = None if c is None or spend is None else spend + c
            row.update(f1=round(s.f1, 3), found=s.found, missed=s.missed, invented=s.invented, expected=s.expected,
                       seconds=round(reply.seconds, 1))
        except (TranscriptionError, ReplyError) as error:
            expected = sum(len(b.notes) for b in answer)
            scores.append(Score(expected, 0, expected, 0))
            row["error"] = str(error)
        rows.append(row)
        print(f"    {photo.name:30s} " + (f"F1 {row['f1']:.2f}  missed {row['missed']}  invented {row['invented']}  {row['seconds']}s"
                                           if "f1" in row else f"failed: {row['error'][:80]}"))
    overall = total(scores)
    return {
        "provider": provider_name,
        "model": model,
        "f1": round(overall.f1, 3),
        "precision": round(overall.precision, 3),
        "recall": round(overall.recall, 3),
        "missed": overall.missed,
        "invented": overall.invented,
        "expected": overall.expected,
        "avg_seconds": round(seconds / max(1, len(cases)), 1),
        "input_tokens": int(tokens_in),
        "output_tokens": int(tokens_out),
        "cost_usd": None if spend is None else round(spend, 4),
        "photos": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--providers", default=",".join(PROVIDERS), help="comma-separated: claude,openai,gemini")
    parser.add_argument("--models", default="", help="e.g. claude=claude-sonnet-5-5,openai=gpt-6.1-sol")
    parser.add_argument("--yes", action="store_true", help="don't ask before spending money")
    args = parser.parse_args()

    cases = load_cases(args.folder)
    if not cases:
        sys.exit(f"No photo + answer pairs found in {args.folder}.")
    chosen = dict(pair.split("=", 1) for pair in args.models.split(",") if "=" in pair)
    runs = []
    for name in args.providers.split(","):
        name = name.strip()
        if name not in PROVIDERS:
            sys.exit(f"Unknown provider {name!r}; choose from {', '.join(PROVIDERS)}.")
        key = keys.get_key(name)
        if not key:
            print(f"  skipping {name}: no API key saved (add one in the app's Settings)")
            continue
        runs.append((name, chosen.get(name, PROVIDERS[name].models[0]), key))
    if not runs:
        sys.exit("No provider has an API key saved.")

    print(f"{len(cases)} photo(s) × {len(runs)} provider(s): " + ", ".join(f"{n} ({m})" for n, m, _ in runs))
    if not args.yes and input("This sends the photos to those providers and costs money. Continue? [y/N] ").strip().lower() != "y":
        sys.exit("Cancelled.")

    results = []
    for name, model, key in runs:
        print(f"\n  {name} · {model}")
        results.append(run(name, model, cases, key))

    print(f"\n{'provider':10s} {'model':22s} {'F1':>5s} {'prec':>5s} {'recall':>6s} {'missed':>6s} {'invent':>6s} {'sec':>5s} {'tokens in/out':>15s} {'cost':>8s}")
    for r in sorted(results, key=lambda r: -r["f1"]):
        money = "unknown" if r["cost_usd"] is None else f"${r['cost_usd']:.3f}"
        print(f"{r['provider']:10s} {r['model']:22s} {r['f1']:5.2f} {r['precision']:5.2f} {r['recall']:6.2f} "
              f"{r['missed']:6d} {r['invented']:6d} {r['avg_seconds']:5.1f} "
              f"{r['input_tokens']:>7d}/{r['output_tokens']:<7d} {money:>8s}")

    out = args.folder / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps({"prompt_version": PROMPT_VERSION, "when": time.time(), "results": results}, indent=2) + "\n")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
