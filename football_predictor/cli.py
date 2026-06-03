import argparse
import json

from football_predictor.backtest import run_backtest


def build_parser():
    parser = argparse.ArgumentParser(description="Run a football prediction backtest.")
    parser.add_argument("--data", required=True, help="Path to the match dataset JSON file.")
    parser.add_argument("--config", required=True, help="Path to the parameter config JSON file.")
    parser.add_argument("--pretty", action="store_true", help="Print indented JSON.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    report = run_backtest(args.data, args.config)
    indent = 2 if args.pretty else None
    print(json.dumps(report, indent=indent, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
