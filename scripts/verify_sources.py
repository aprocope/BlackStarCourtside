"""P0.3: verify data sources V1-V5 and print PASS/FAIL with details.

Reads the Odds API key from the ODDS_API_KEY env var. The key is never printed.
Run: .venv/bin/python scripts/verify_sources.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

import requests

ODDS_BASE = "https://api.the-odds-api.com"
ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
MARKETS = "player_points,player_rebounds,player_assists"

results: dict[str, str] = {}
state: dict = {}


def report(check: str, status: str, details: str) -> None:
    results[check] = status
    print(f"\n=== {check}: {status} ===\n{details}")


def v1() -> None:
    from nba_api.stats.endpoints import leaguegamelog

    try:
        df = leaguegamelog.LeagueGameLog(
            season="2025-26",
            season_type_all_star="Regular Season",
            player_or_team_abbreviation="P",
            timeout=60,
        ).get_data_frames()[0]
    except Exception as e:  # noqa: BLE001
        report("V1", "STOP", f"LeagueGameLog error: {type(e).__name__}: {e}")
        return
    n = len(df)
    state["game_ids"] = sorted(df["GAME_ID"].unique()) if n else []
    detail = f"rows={n}, distinct games={len(state['game_ids'])}, columns={list(df.columns)}"
    report("V1", "PASS" if n >= 25_000 else "STOP", detail)


def _five_per_team(df, team_col: str, pos_col: str) -> tuple[bool, dict]:
    nonempty = df[df[pos_col].fillna("").astype(str).str.strip() != ""]
    counts = Counter(nonempty[team_col])
    teams = df[team_col].unique()
    per_team = {str(t): counts.get(t, 0) for t in teams}
    return len(teams) == 2 and all(v == 5 for v in per_team.values()), per_team


def v2() -> None:
    from nba_api.stats.endpoints import boxscoretraditionalv2, boxscoretraditionalv3

    game_ids = state.get("game_ids") or []
    if not game_ids:
        report("V2", "STOP", "No game id available from V1.")
        return
    gid = game_ids[len(game_ids) // 2]
    lines = [f"game_id={gid}"]
    try:
        time.sleep(1.5)
        p3 = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=gid, timeout=60).get_data_frames()[0]
        ok3, per3 = _five_per_team(p3, "teamId", "position")
        lines.append(f"V3 non-empty position per team: {per3}")
        if ok3:
            state["starter_source"] = "BoxScoreTraditionalV3"
            report("V2", "PASS", "\n".join(lines + ["Starter source: BoxScoreTraditionalV3"]))
            return
    except Exception as e:  # noqa: BLE001
        lines.append(f"V3 error: {type(e).__name__}: {e}")
    try:
        time.sleep(1.5)
        p2 = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=gid, timeout=60).get_data_frames()[0]
        ok2, per2 = _five_per_team(p2, "TEAM_ID", "START_POSITION")
        lines.append(f"V2 non-empty START_POSITION per team: {per2}")
        if ok2:
            state["starter_source"] = "BoxScoreTraditionalV2"
            report("V2", "PASS", "\n".join(lines + ["Starter source: BoxScoreTraditionalV2"]))
            return
    except Exception as e:  # noqa: BLE001
        lines.append(f"V2 error: {type(e).__name__}: {e}")
    report("V2", "STOP", "\n".join(lines + ["Neither endpoint had exactly 5 starters per team."]))


def _odds_get(path: str, params: dict) -> requests.Response:
    params = {**params, "apiKey": os.environ["ODDS_API_KEY"]}
    return requests.get(f"{ODDS_BASE}{path}", params=params, timeout=30)


def v3() -> None:
    if not os.environ.get("ODDS_API_KEY"):
        report("V3", "NOT RUN", "ODDS_API_KEY is not set (owner action O2 pending).")
        return
    r = _odds_get("/v4/sports/basketball_nba/events", {})
    remaining = r.headers.get("x-requests-remaining")
    if r.status_code in (401, 402):
        report("V3", "STOP", f"HTTP {r.status_code} on /events. x-requests-remaining={remaining}")
        return
    if r.status_code != 200:
        report("V3", "FAIL", f"HTTP {r.status_code} on /events (no decision rule). body={r.text[:300]}")
        return
    events = r.json()
    if not events:
        report("V3", "FAIL", f"No events listed. x-requests-remaining={remaining}")
        return
    events.sort(key=lambda e: e["commence_time"])
    lines = [
        f"events listed={len(events)}",
        f"earliest commence_time={events[0]['commence_time']} "
        f"({events[0]['away_team']} @ {events[0]['home_team']})",
    ]
    ev = events[0]
    r2 = _odds_get(
        f"/v4/sports/basketball_nba/events/{ev['id']}/odds",
        {"regions": "us", "markets": MARKETS, "oddsFormat": "decimal"},
    )
    remaining = r2.headers.get("x-requests-remaining", remaining)
    if r2.status_code in (401, 402):
        report("V3", "STOP", f"HTTP {r2.status_code} on event odds. x-requests-remaining={remaining}")
        return
    data = r2.json() if r2.status_code == 200 else {}
    books = data.get("bookmakers", [])
    lines.append(f"event odds HTTP {r2.status_code}, event={ev['id']}")
    lines.append(f"bookmaker keys={sorted(b['key'] for b in books)}")
    example = None
    for b in books:
        for m in b.get("markets", []):
            if m.get("outcomes"):
                o = m["outcomes"][0]
                example = {"book": b["key"], "market": m["key"],
                           **{k: o.get(k) for k in ("description", "name", "point", "price")}}
                break
        if example:
            break
    lines.append(f"example outcome={json.dumps(example)}" if example else "no props yet")
    lines.append(f"x-requests-remaining={remaining}")
    report("V3", "PASS", "\n".join(lines))


def v4() -> None:
    if not os.environ.get("ODDS_API_KEY"):
        report("V4", "NOT RUN", "ODDS_API_KEY is not set (owner action O2 pending).")
        return
    r = _odds_get("/v4/historical/sports/basketball_nba/events", {"date": "2026-03-15T18:00:00Z"})
    rem = r.headers.get("x-requests-remaining")
    if r.status_code == 200:
        report("V4", "PASS", f"historical available. x-requests-remaining={rem}")
    elif 400 <= r.status_code < 500:
        report("V4", "PASS", f"not on plan (HTTP {r.status_code}). x-requests-remaining={rem}")
    else:
        report("V4", "FAIL", f"HTTP {r.status_code} (no decision rule). body={r.text[:300]}")


def v5() -> None:
    try:
        r = requests.get(ESPN_INJURIES, timeout=30)
    except requests.RequestException as e:
        report("V5", "STOP", f"request error: {e}")
        return
    if r.status_code != 200:
        report("V5", "STOP", f"HTTP {r.status_code}")
        return
    data = r.json()
    teams = data.get("injuries")
    if not isinstance(teams, list) or not teams:
        report("V5", "STOP", f"No 'injuries' team list. top-level keys={list(data)}")
        return
    team = next((t for t in teams if t.get("injuries")), None)
    if team is None:
        report("V5", "STOP", f"{len(teams)} teams, none with injuries.")
        return
    inj = team["injuries"][0]
    if "status" not in inj:
        report("V5", "STOP", f"Injury entry has no status field. keys={list(inj)}")
        return
    n_inj = sum(len(t.get("injuries", [])) for t in teams)
    statuses = Counter(i.get("status") for t in teams for i in t.get("injuries", []))
    details = [
        f"teams={len(teams)}, injury entries={n_inj}, statuses={dict(statuses)}",
        "Paths:",
        "  team name    : injuries[i].displayName  (example: %r)" % team.get("displayName"),
        "  team id      : injuries[i].id  (example: %r)" % team.get("id"),
        "  player name  : injuries[i].injuries[j].athlete.displayName  (example: %r)"
        % inj.get("athlete", {}).get("displayName"),
        "  player team  : injuries[i].injuries[j].athlete.team.abbreviation  (example: %r)"
        % inj.get("athlete", {}).get("team", {}).get("abbreviation"),
        "  status       : injuries[i].injuries[j].status  (example: %r)" % inj.get("status"),
        f"  entry keys   : {sorted(inj)}",
        f"  athlete keys : {sorted(inj.get('athlete', {}))}",
    ]
    report("V5", "PASS", "\n".join(details))


def main() -> int:
    for fn in (v1, v2, v3, v4, v5):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            report(fn.__name__.upper(), "ERROR", f"{type(e).__name__}: {e}")
    print("\n=== SUMMARY ===")
    for k, v in results.items():
        print(f"{k}: {v}")
    if "starter_source" in state:
        print(f"Starter source: {state['starter_source']}")
    return 0 if all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
