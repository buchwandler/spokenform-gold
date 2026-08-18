import argparse
import json
from pathlib import Path
import sys

from .io import read_jsonl, write_jsonl
from .validation import validate_records, load_categories
from .coverage import build_coverage, load_targets
from .conflicts import find_conflicts
from .discover import discover
from .importers.async_tn import import_async

def cmd_validate(args):
    records = read_jsonl(args.path)
    cats = load_categories(args.categories) if args.categories else None
    errors = validate_records(records, judge=args.judge, categories=cats)
    if errors:
        print(f"INVALID: {len(errors)} error(s)")
        for e in errors:
            print(f"- {e}")
        return 1
    print(f"OK: {len(records)} record(s)")
    return 0

def cmd_coverage(args):
    records = []
    for p in args.paths:
        records.extend(read_jsonl(p))
    result = build_coverage(records, load_targets(args.targets))
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"records={result['records']} observed_categories={result['categories_observed']} gaps={len(result['gaps'])}")
    for gap in result["gaps"][:100]:
        print(json.dumps(gap, ensure_ascii=False))
    return 0

def cmd_conflicts(args):
    records = []
    for p in args.paths:
        records.extend(read_jsonl(p))
    conflicts = find_conflicts(records, args.mode)
    print(json.dumps(conflicts, ensure_ascii=False, indent=2))
    return 2 if conflicts and args.fail_on_conflict else 0

def cmd_discover(args):
    records = read_jsonl(args.against)
    text = Path(args.corpus).read_text(encoding="utf-8")
    items = discover(text, records, args.rare_below)
    if args.out:
        write_jsonl(args.out, items)
    else:
        for item in items:
            print(json.dumps(item, ensure_ascii=False))
    print(f"# candidates={len(items)}", file=sys.stderr)
    return 0

def cmd_import_async(args):
    records = import_async(args.path, args.language, args.locale)
    write_jsonl(args.out, records)
    print(f"wrote {len(records)} candidate records to {args.out}")
    return 0

def build_parser():
    p = argparse.ArgumentParser(prog="spokenform-gold")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate")
    v.add_argument("path")
    v.add_argument("--judge", action="store_true")
    v.add_argument("--categories")
    v.set_defaults(func=cmd_validate)

    c = sub.add_parser("coverage")
    c.add_argument("paths", nargs="+")
    c.add_argument("--targets")
    c.add_argument("--json")
    c.set_defaults(func=cmd_coverage)

    x = sub.add_parser("conflicts")
    x.add_argument("paths", nargs="+")
    x.add_argument("--mode", choices=["unit","record"], default="unit")
    x.add_argument("--fail-on-conflict", action="store_true")
    x.set_defaults(func=cmd_conflicts)

    d = sub.add_parser("discover")
    d.add_argument("corpus")
    d.add_argument("--against", required=True)
    d.add_argument("--out")
    d.add_argument("--rare-below", type=int, default=3)
    d.set_defaults(func=cmd_discover)

    a = sub.add_parser("import-async")
    a.add_argument("path")
    a.add_argument("--out", required=True)
    a.add_argument("--language", default="en")
    a.add_argument("--locale", default="en-US")
    a.set_defaults(func=cmd_import_async)
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
