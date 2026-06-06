"""CTFAgent — Autonomous LLM-driven CTF penetration testing system.

Usage:
    python main.py --goal "攻破 http://target.com 获取flag"
    python main.py --goal "Find the flag on http://localhost:8080" --max-rounds 15
    python main.py --goal "..." --model claude-sonnet-4-6
"""

import argparse
import json
import sys

from orchestrator.engine import Engine
from config import validate_config


def main():
    parser = argparse.ArgumentParser(
        description="CTFAgent — Autonomous Penetration Testing Swarm"
    )
    parser.add_argument(
        "--goal", "-g", type=str, required=True,
        help="Mission goal in natural language"
    )
    parser.add_argument(
        "--max-rounds", "-n", type=int, default=10,
        help="Maximum Commander-Worker rounds (default: 10)"
    )
    parser.add_argument(
        "--model", "-m", type=str, default="deepseek-chat",
        help="LLM model for agents (default: deepseek-chat)"
    )
    parser.add_argument(
        "--data-dir", "-d", type=str, default="data",
        help="Directory for blackboard persistence (default: data)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="",
        help="Save final report to JSON file"
    )

    args = parser.parse_args()

    validate_config()#检查是否有API key&base url

    engine = Engine(
        model=args.model,
        max_rounds=args.max_rounds,
        data_dir=args.data_dir,
    )

    try:
        report = engine.run(args.goal)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)

    # Output
    print(f"\n{'='*60}")
    print(f"FINAL REPORT")
    print(f"{'='*60}")
    print(f"Outcome: {report['outcome']}")
    print(f"Rounds:  {report['total_rounds']}")
    print(f"Flag:    {report['flag'] or '(not found)'}")
    print(f"Findings: {len(report['findings'])}")
    for f in report["findings"]:
        print(f"  [{f['type']}] {f['title']}")

    if args.output:#如果指定了output file,则保存report到json文件
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
