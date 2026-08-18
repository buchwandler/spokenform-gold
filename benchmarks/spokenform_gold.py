from __future__ import annotations

import argparse
import json

from .spokenform_gold_eval import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.spokenform_gold")
    parser.add_argument("--gold-root", required=True)
    parser.add_argument("--split")
    parser.add_argument("--language")
    parser.add_argument("--locale")
    parser.add_argument("--category")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--profile", default="gold-v1")
    parser.add_argument("--prepare-module", required=True)
    parser.add_argument(
        "--mode", choices=["canonical", "accepted"], default="canonical"
    )
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--show-failures", action="store_true")
    parser.add_argument("--gate", type=float)
    parser.add_argument("--spokenform-version", default="unknown")
    parser.add_argument("--spokenform-commit", default="unknown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_benchmark(
        gold_root=args.gold_root,
        split=args.split,
        language=args.language,
        locale=args.locale,
        category=args.category,
        case_ids=set(args.cases or []),
        prepare_module=args.prepare_module,
        results_dir=args.results_dir,
        mode=args.mode,
        profile_name=args.profile,
        spokenform_version=args.spokenform_version,
        spokenform_commit=args.spokenform_commit,
    )
    primary = summary["summary"]["primary_accuracy"]
    print(
        json.dumps(
            {
                "records": summary["record_count"],
                "mode": summary["mode"],
                "primary_accuracy": primary,
                "results_dir": args.results_dir,
            },
            ensure_ascii=False,
        )
    )
    if args.show_failures:
        print(f"failures={args.results_dir}/failures.jsonl")
    if args.gate is not None and primary < args.gate:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
