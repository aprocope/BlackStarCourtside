# Phase 0 report

## Status: STOPPED at P0.3 (V3 and V4 not run; waiting on owner actions O2 and O3)

V1, V2 and V5 pass. V3 and V4 need the Odds API key, which is not yet set (O2).
`config/books.yaml` needs the bookmaker key list that V3 produces (O3).
Once O2 is done, rerun `.venv/bin/python scripts/verify_sources.py` and fill in the V3/V4 rows below.

## Tasks — one line each with commit sha
- P0.1 Scaffold repo layout, pyproject, gitignore, venv — `5f07d10`
- P0.2 Tool check (`scripts/tool_check.sh`) — `b6833bf`
- P0.3 Source verification (`scripts/verify_sources.py`) — `2185fcd`, run 2026-10-08
- P0.4 This report — see the commit that adds this file
- Base commit on `main` with `docs/HANDOFF.md` only, so the phase PR has a base — `62ef739`

## Evidence

### Tool versions (P0.2)
| Tool | Version |
|---|---|
| python | 3.13.12 (`python3.13`) |
| terraform | 1.15.6 |
| aws | aws-cli 2.34.9 |
| docker | 29.6.0 client, 29.5.2 server (O4 not needed) |
| gh | 2.95.0 (not authenticated) |

### Source checks (P0.3)
| ID | Result | Details |
|---|---|---|
| V1 | PASS | `LeagueGameLog` 2025-26 regular season, players: 26,651 rows, 1,230 distinct games |
| V2 | PASS | Game `0022500616`: `BoxScoreTraditionalV3` has non-empty `position` for exactly 5 players per team. **Starter source: BoxScoreTraditionalV3.** |
| V3 | NOT RUN | `ODDS_API_KEY` not set. Example outcome, bookmaker keys and `x-requests-remaining` pending. |
| V4 | NOT RUN | `ODDS_API_KEY` not set. |
| V5 | PASS | 27 teams, 101 injury entries. Status values seen: `Out` 18, `Day-To-Day` 83. |

### ESPN injury JSON paths (V5)
| Field | Path | Example |
|---|---|---|
| Team name | `injuries[i].displayName` | `Atlanta Hawks` |
| Team id (ESPN) | `injuries[i].id` | `1` |
| Player name | `injuries[i].injuries[j].athlete.displayName` | `Aaron Wiggins` |
| Player team | `injuries[i].injuries[j].athlete.team.abbreviation` | `ATL` |
| Status | `injuries[i].injuries[j].status` | `Day-To-Day` |
| Status type | `injuries[i].injuries[j].type.name` | `INJURY_STATUS_DAYTODAY` |
| Fantasy status | `injuries[i].injuries[j].details.fantasyStatus.abbreviation` | `GTD` |

### books.yaml
Not filled in yet (owner action O3, after V3 lists the keys).

## Deviations
- **Platform is macOS, not Windows.** Used `python3.13` instead of `py -3.13`, and Bash instead of PowerShell. No PowerShell is installed. `home_runner/register_task.ps1` (Windows Task Scheduler) will not work on this machine as written. The validator should decide the home-runner scheduler (for example launchd or cron) before Phase 2.
- **LightGBM needed `brew install libomp`** on macOS. Installed, and noted in the README.
- **Repo name.** The owner's GitHub repo is `aprocope/BlackStarCourtside`, not `courtside`. The repo root is used as the `courtside/` layout root. Resource names still use `courtside`.
- **Base commit on main.** `docs/HANDOFF.md` was committed alone to `main` so the `p0-setup` PR has a base branch.
- **`scripts/` directory** and `scripts/tool_check.sh` added. The layout in §2 does not list `scripts/`, but P0.3 and P2.1 put scripts there.
- **`*.egg-info/` and `.DS_Store`** added to `.gitignore`.
- **PR not opened.** `gh` is not authenticated on this machine. The branch is pushed. The owner can open the PR, or run `gh auth login` so the implementer can.

## Observed, not touched
- **ESPN statuses do not include Questionable or Doubtful right now.** Top-level `status` is only `Out` or `Day-To-Day`, and `fantasyStatus` is `OUT`, `OFS` or `GTD`. One entry has status `Out` with fantasy status `GTD`. P2.5 rules depend on `Doubtful` and `Questionable`. This is preseason data, so those values may appear later, but the validator should define how `Day-To-Day`/`GTD` maps before Phase 2.
- **AWS SSO token has expired** on this machine. Phase 0 does not need AWS, but O2's `aws ssm put-parameter` and all of Phase 2 do. Run `aws sso login` first.
- V1 took one call; no rate-limit or IP block was seen from this machine.

## Owner actions still open
- ⏸ **O2.** Odds API key: create SSM `/courtside/odds_api_key` and set `ODDS_API_KEY` locally.
- ⏸ **O3.** Fill in `config/books.yaml` from the V3 bookmaker key list.
- **O4.** Not needed. Docker is installed.
