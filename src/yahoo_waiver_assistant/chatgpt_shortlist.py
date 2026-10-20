"""Low-confidence screening, not automatic waiver bids or start recommendations."""
from __future__ import annotations
import json
from pathlib import Path
from .chatgpt_feed import build_feed

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
UNAVAILABLE = {"O", "IR", "IR-R", "NA", "SUSP", "D"}


def build_shortlist(snapshot: dict, limit: int = 12) -> dict:
    feed = build_feed(snapshot)
    roster = feed["my_team"]["players"]
    pools = {}
    for position in POSITIONS:
        eligible = [p for p in feed["available_players"]
                    if p.get("primary_position") == position
                    and p.get("status") not in UNAVAILABLE
                    and p.get("bye_week") != feed["week"]
                    and isinstance(p.get("recent_estimate"), (int, float))
                    and len(p.get("recent_estimate_sample_weeks", [])) >= 2]
        eligible.sort(key=lambda p: (p["recent_estimate"], len(p["recent_estimate_sample_weeks"])), reverse=True)
        pools[position] = [{
            "player_key": p["player_key"], "name": p["name"],
            "team": p["team"], "availability": p["availability"],
            "injury_status": p["status"], "estimated_points": p["recent_estimate"],
            "sample_weeks": p["recent_estimate_sample_weeks"],
        } for p in eligible[:limit]]
    return {
        "generated_at": feed["generated_at"], "snapshot_captured_at": feed["captured_at"],
        "week": feed["week"], "league": feed["league"]["name"],
        "team": feed["my_team"]["name"], "acquisitions": feed["acquisitions"],
        "roster": roster, "candidates_by_position": pools,
        "method": "Recent 2-4 non-bye game actual points, recency-weighted. Not Yahoo predictions.",
        "confidence": "Low",
        "cautions": [
            "Historical scoring may not reflect current starting role, injuries, opponent, or snap count.",
            "Waiver status and eligibility require refresh before making claims.",
            "Players omitted for sparse data are not necessarily poor candidates.",
            "No bid amount, projected lineup gain, or game-day readiness is inferred."
        ],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    shortlist = build_shortlist(json.loads(args.snapshot.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(shortlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote low-confidence waiver screening shortlist:", args.output)


if __name__ == "__main__":
    main()
