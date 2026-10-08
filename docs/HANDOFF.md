# Courtside — Project Kickoff & Implementation Handoff

**Audience:** the implementing agent (Claude Sonnet) and the project owner.
**Validator:** Claude Opus. At each gate, the owner brings the phase report to a validator session, which checks it against that gate's checklist.
**Written:** 2026-10-08.
**Goal:** paper-trade NBA player props through the start of the 2026–27 season, then decide with data whether to bet real money.

"Courtside" is a placeholder name. If the owner renames the project, replace it everywhere, including resource names.

---

## 0. What we're building and why

**The bet:** projected player stat distributions → P(over/under) → compare to the sportsbook's no-vig probability → paper-bet only when the expected value clears a threshold → measure **closing line value (CLV)**.

**Why player props:** prop lines (points, rebounds, assists) are softer than spreads and totals, especially for non-star players. Feedback is fast, with thousands of props a week. The loss on any single bet is capped at the stake.

**Where the edge comes from, in order:**
1. **Minutes projection.** Role, rest, and teammates being out drive most stat variance.
2. **Injury-news reaction speed.** When a starter is ruled out, books are slow to move lines for secondary players.
3. **Per-minute production** adjusted for pace, opponent, and usage vacated by absent teammates.

**How success is measured:**
- **CLV, not win rate.** Win/loss needs thousands of bets to separate skill from luck. Beating the closing line shows skill within a few hundred bets.
- Break-even at −110 odds is **52.4%**.

**Real limits (stated up front):**
- Books limit winning prop bettors, so the income ceiling is set by account limits, not by model quality.
- Betting is legal in the owner's state (confirmed), and the owner is 21+.
- **This project only paper-trades.** Real money is the owner's decision after Phase 4.

**Lessons carried over from BlackStar (a previous project with the same owner) — these are non-negotiable:**
- Features use only data available **before** the prediction time. BlackStar's model leaked future earnings into history.
- Validate walk-forward by time (train on earlier games, test on later ones), always against simple baselines.
- A new model only goes live if it validates at least as well as the current one (the "champion" check).
- Every scheduled job alerts on failure. BlackStar lost months of data to silent failures.
- Writes are idempotent: re-running a job must never duplicate data.
- Use a simple stack. The data is small (about 100k player-game rows), so no Spark, Glue, or SageMaker.

---

## 1. Rules of engagement (for the implementer)

1. **Execute what is written; make no product or design decisions.** When this doc gives a decision rule ("if X then Y"), apply it. If reality matches no rule, **STOP**.
2. **STOP means:** write the phase report with exactly what you observed, commit, push, and end your turn. Do not improvise workarounds.
3. **Gates are hard stops.** Do not start the next phase until the owner says "Gate N passed".
4. **Paper only.** Never place a real bet. Never automate any action on a sportsbook account. Never store sportsbook credentials.
5. **Secrets:**
   - The Odds API key lives only in SSM Parameter Store `/courtside/odds_api_key` (SecureString), created by the owner.
   - Locally, read it from env var `ODDS_API_KEY`.
   - Never commit keys. Never print them in logs or reports.
6. **Shells (Windows machine):**
   - Use the PowerShell tool for the `aws` CLI, and pass any JSON argument via `file://` from `$env:TEMP\courtside\`.
   - If PowerShell is unavailable, Bash with `export MSYS_NO_PATHCONV=1` also works for `aws`.
7. **Terraform:** always `plan -out` → compare against the expected list in this doc → `apply <planfile>`. Never `-auto-approve` without a plan file. Never `-target`.
8. **Respect source rate limits:**
   - stats.nba.com: at most 1 request per 1.5 seconds, with browser-like headers.
   - The Odds API: track the `x-requests-remaining` header and stop polling below the floor in §6.
9. **Git:** branch per phase (named in each phase), one commit per task ID, PR per phase. Never force-push. Follow your harness's attribution rules.
10. **Reports:** write `docs/reports/phase-N.md` using the template below.

**Report template**
```markdown
# Phase N report
## Status: COMPLETE | STOPPED at <task>
## Tasks — one line each with commit sha
## Evidence — exactly what the gate checklist asks for
## Deviations — "None" or what/why
## Observed, not touched
```

---

## 2. Fixed decisions

| Area | Decision |
|---|---|
| Language | Python 3.13 everywhere (`py -3.13` locally; Lambda container base `public.ecr.aws/lambda/python:3.13`) |
| Data processing | pandas + DuckDB over Parquet. No Spark. |
| Models | LightGBM (regression). Distributions via Monte Carlo (§5). |
| Cloud | AWS account `495599764458`, region `us-east-1`. Lambda **container images** (one image, several handlers) in ECR `courtside`. |
| Infra as code | Terraform in `infra/`. State in the existing bucket `blackstar-terraform-state`, key `courtside/terraform.tfstate`, lock table `blackstar-analytics-tf-lock`. |
| Storage | S3 bucket `courtside-data-495599764458` (versioning on). Bet log in DynamoDB `courtside-bets` (on-demand). |
| NBA stats source | `nba_api` (stats.nba.com), **fetched from the owner's home machine** (stats.nba.com commonly blocks cloud IPs), then uploaded to S3. |
| Odds source | The Odds API v4 (`https://api.the-odds-api.com`), paid plan at the 20k-credit tier or above. Markets: `player_points`, `player_rebounds`, `player_assists`. Region `us`. `oddsFormat=decimal`. |
| Injury source | ESPN JSON `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries` (unofficial). |
| Schedule / tip-off times | From The Odds API `/events` (`commence_time`). The cloud never calls stats.nba.com. |
| Alerts | SNS topic `courtside-alerts` with email subscription to the owner. Every Lambda gets an error alarm. The home runner emails on failure through the same topic (it publishes with the owner's AWS credentials). |
| Seasons for history | Regular seasons 2022-23, 2023-24, 2024-25, 2025-26 |
| Monthly cost target | About $30 for The Odds API plus under $10 for AWS |

**Repo layout (create exactly this):**
```
courtside/
  README.md
  pyproject.toml
  .gitignore
  config/
    books.yaml            # sportsbooks the owner can use (owner fills in, P0)
    name_overrides.csv    # odds-API player name → NBA player_id fixes
  docs/HANDOFF.md  docs/reports/
  src/courtside/
    __init__.py
    nba/          # nba_api fetchers + curation (home runner uses these)
    features/     # as-of feature builder
    models/       # training, distributions, champion gate
    odds/         # Odds API client, no-vig math, name matching
    betting/      # edge calc, paper bet logging, CLV, settlement
    handlers/     # Lambda entry points
  home_runner/
    nightly.py
    backfill.py
    register_task.ps1
  infra/          # Terraform root + modules
  tests/
  Dockerfile
```

---

## Phase 0 — Setup and source verification

**Branch:** `p0-setup` (the first commit creates the repo).

### Owner actions (the implementer lists these and waits for them only where marked ⏸)
- ⏸ **O1.** Create a GitHub repo `courtside` (private) and tell the implementer its URL.
- ⏸ **O2.** Sign up for The Odds API, paid tier with ≥ 20k credits/month. Create the SSM parameter:
  `aws ssm put-parameter --name /courtside/odds_api_key --type SecureString --value <KEY>`
  Also set `ODDS_API_KEY` in the local user environment.
- ⏸ **O3.** Fill in `config/books.yaml`: the sportsbooks the owner has or will open accounts with, using Odds API bookmaker keys. The implementer prints the list of keys seen in V3 to choose from.
- **O4.** Install Docker Desktop if `docker version` fails.

### Tasks
- **P0.1 Scaffold.**
  - Create the repo layout.
  - `pyproject.toml` with dependencies: `nba_api`, `pandas`, `pyarrow`, `duckdb`, `lightgbm`, `numpy`, `scipy`, `requests`, `boto3`, `pyyaml`; dev dependencies: `pytest`.
  - Create the venv: `py -3.13 -m venv .venv`, then `pip install -e .[dev]`.
  - `.gitignore` covers: `.venv/`, `data/`, `__pycache__/`, `*.tfplan`, `*-plan.txt`, `.terraform/`, `build/`, `*.zip`, `.env`.
- **P0.2 Tool check.** Record the versions of python, terraform, aws, docker, and gh. If docker is missing, list O4 and continue; docker is only needed from Phase 2.
- **P0.3 Verify sources.** Write a script `scripts/verify_sources.py` that runs V1–V5 below and prints PASS/FAIL with details. Run it locally.

| ID | Check | Decision rule |
|---|---|---|
| V1 | `nba_api` `LeagueGameLog(season="2025-26", season_type_all_star="Regular Season", player_or_team_abbreviation="P")` returns rows | ≥ 25,000 rows → PASS. Fewer, or an error → **STOP**. |
| V2 | Starter flag. Pick any 2025-26 game id from V1. Call `BoxScoreTraditionalV3(game_id)`. | If exactly 5 players per team have a non-empty `position`, use **V3** as the starter source. Else try `BoxScoreTraditionalV2` `START_POSITION`; if that has 5 per team, use **V2**. Neither → **STOP**. Record the choice in the report. |
| V3 | Odds API: `GET /v4/sports/basketball_nba/events`, then for one event `GET /v4/sports/basketball_nba/events/{id}/odds?regions=us&markets=player_points,player_rebounds,player_assists&oddsFormat=decimal` | Events listed → PASS. If outcomes exist, record one example outcome (fields `description`, `name`, `point`, `price`) and the list of bookmaker keys. Empty player markets during preseason are **not** a failure; record "no props yet". HTTP 401/402 → **STOP**. Record `x-requests-remaining`. |
| V4 | Odds API historical: `GET /v4/historical/sports/basketball_nba/events?date=2026-03-15T18:00:00Z` | 200 → record "historical available" (enables the optional backtest in Phase 4). 4xx → record "not on plan". Neither result is a failure. |
| V5 | ESPN injuries JSON | 200 with a list of teams containing injuries with a status field → PASS. Record the exact JSON path to player name, team, and status. Else **STOP**. |

- **P0.4** Write `docs/reports/phase-0.md`, commit, push, and open a PR.

### ⛔ GATE 0. Validator checklist
- All V-checks have a result, and the V2 starter source is recorded.
- Example odds outcome JSON (or "no props yet"), the bookmaker key list, and `x-requests-remaining`.
- The ESPN JSON paths.
- `config/books.yaml` filled in by the owner.

---

## Phase 1 — Historical data and offline model (local only, no cloud)

**Branch:** `p1-model`

### P1.1 Backfill (`home_runner/backfill.py`)
For each season in §2, write to `data/raw/` (gitignored):
- `LeagueGameLog` for player rows (P) and team rows (T), regular season, saved as Parquet `data/raw/gamelog_{P|T}_{season}.parquet`.
- The starter flag for every game id, using the V2-chosen endpoint (~1,230 games/season, ≥ 1.5 s between calls).
  - Save `data/raw/starters_{season}.parquet` with columns `game_id, player_id, starter (bool)`.
  - Make it resumable: skip game ids already saved.
  - Retry each call 3 times with 10 s backoff. After that, log the game id to `data/raw/failed_games.txt` and continue.
- At the end, print row counts per season and the failed-game count. More than 1% of games failed → **STOP**.

### P1.2 Curated table (`src/courtside/nba/curate.py`)
Build `data/curated/player_games.parquet`, one row per player-game:
- `season, game_id, game_date, player_id, player_name, team_id, team_abbr, opp_abbr, home (bool), starter (bool), min (float minutes), pts, reb, ast, fga, fta, tov, fg3a, plus_minus, team_pts, opp_pts`
- Parse `MATCHUP`: `"BOS vs. NYK"` means home, `"BOS @ NYK"` means away.
- Parse `MIN` as a float; handle `"MM:SS"` strings too.
- Uniqueness check on `(game_id, player_id)`: duplicates → **STOP**.

Also build `data/curated/team_games.parquet`:
- `season, game_id, game_date, team_abbr, opp_abbr, fga, fta, oreb, tov, pts`
- `poss = fga + 0.44*fta - oreb + tov`

### P1.3 As-of features (`src/courtside/features/build.py`)
**Rule:** every feature for a row uses only that player's/team's games with `game_date < row.game_date`.
- Implement with groupby + `shift(1)` before every rolling window.
- Add a unit test that fails if any feature uses the current game.

Player features:
| Feature | Definition |
|---|---|
| `min_l3, min_l5, min_l10` | Mean minutes over the last 3/5/10 games played |
| `min_szn` | Season-to-date mean minutes; NaN before the first game |
| `start_last` | Started the previous game (0/1) |
| `start_rate_l10` | Share of starts in the last 10 |
| `days_rest` | Days since the previous game, capped at 7 |
| `b2b` | `days_rest == 1` |
| `games_since_gap` | Games since the last gap of more than 10 days (proxy for return from injury), capped at 20 |
| `{stat}_pm_ewm` for pts, reb, ast | Exponentially weighted (halflife 10 games) per-minute rate. Exclude games under 5 minutes from rate history. |
| `usg_pm_ewm` | Same smoothing of `(fga + 0.44*fta + tov) / min` |
| `fg3a_pm_ewm` | Same smoothing of `fg3a / min` |
| `home` | 0/1 |

Team and opponent features (from team_games, same as-of rule):
| Feature | Definition |
|---|---|
| `team_pace_l10, opp_pace_l10` | Mean `poss` over the last 10 |
| `opp_pts_allowed_l10, opp_reb_allowed_l10, opp_ast_allowed_l10` | Opponent's mean allowed over the last 10. Allowed = the other team's totals in that game, computed from player_games summed per team. |

Availability features (the injury lever):
- **Rotation player:** `min_l10 ≥ 15` as of that game.
- `team_rot_out_min`: the sum of `min_l10` over the team's rotation players who did **not** appear in this game.
- `team_rot_out_usg`: the sum of `usg_pm_ewm * min_l10` over those same players.
- **Known hindsight caveat:** in history, "did not appear" is known after the game; live, it comes from the injury report. Accepted, and noted in the report.

### P1.4 Models (`src/courtside/models/train.py`)
Four LightGBM regressors. Params: `objective=regression_l1` for minutes, `regression` for rates; `n_estimators=600`, `learning_rate=0.03`, `num_leaves=31`, `min_child_samples=50`, `subsample=0.8`, `subsample_freq=1`, `colsample_bytree=0.8`, `random_state=7`. No tuning in this phase.

| Model | Target | Rows | Weight |
|---|---|---|---|
| minutes | `min` | All rows with `min_l10` not NaN | 1 |
| pts_rate | `pts/min` | `min ≥ 5` | `min` |
| reb_rate | `reb/min` | `min ≥ 5` | `min` |
| ast_rate | `ast/min` | `min ≥ 5` | `min` |

All features from P1.3 go to every model.

### P1.5 Distributions (`src/courtside/models/distribution.py`)
- **Minutes noise:** σ per predicted-minutes bucket `[0,15), [15,25), [25,32), [32,48]`. σ = std of the residuals (actual − predicted) on the training rows of that fold.
- **Stat given minutes:** negative binomial with mean `μ = rate_pred × m`. Dispersion `k` per stat is fit by MLE (`scipy.optimize.minimize_scalar` on the NB log-likelihood) on training rows, with `μ` = rate_pred × actual minutes. Parameterization: `var = μ + μ²/k`.
- **Simulation:** 10,000 draws.
  - `m ~ Normal(min_pred, σ_bucket)`, clipped to [0, 48].
  - `stat ~ NB(mean = rate_pred × m, k)`.
  - Use numpy's Generator with seed 7.
- **Output:** `P(stat > line)`, `P(stat < line)`, `P(stat == line)` (non-zero only for integer lines).

### P1.6 Walk-forward evaluation (`src/courtside/models/evaluate.py`)
- **Folds:** every calendar month Nov–Apr of the 2024-25 and 2025-26 regular seasons, 12 folds in all. Each fold trains on all rows dated before the first day of that month and tests on the month's rows.
- **Baselines:**
  - **B1:** last-10 mean of the stat and of minutes.
  - **B2:** season-to-date mean (prior-season mean if fewer than 5 games).
- **Point metrics:** MAE of `min, pts, reb, ast` (stat prediction = min_pred × rate_pred) for model, B1, and B2. Report per fold and pooled.
- **Probabilistic metrics** (stand-in for book lines, since historical lines aren't used here):
  - For each test row and stat, set the proxy line `L = floor(B1_stat) + 0.5`.
  - Model `P(over L)` comes from P1.5.
  - The baseline P(over) uses an NB with mean `B1_stat` and the same `k`.
  - Report log loss and Brier score for both, pooled per stat.
  - Calibration table: 10 bins of model P(over), each with count, mean predicted, and actual over-rate.
- Write `data/eval/eval_report.md` and `eval_metrics.json`, and paste them into the phase report.

### P1.7 Champion artifact
- Train on all data through the end of 2025-26.
- Save `models/` locally (4 LightGBM text models, σ table, `k` per stat, feature list) plus `champion.json`:
  `{ "version": "<UTC timestamp>", "trained_through": "<date>", "features": [...], "metrics": <pooled eval>, "files": {...} }`
- Upload happens in Phase 2.

### P1.8 Tests (pytest)
- As-of test: perturb a row's own stats and assert its features don't change.
- MATCHUP parsing.
- MIN parsing.
- NB sampling mean is within 2% of μ for μ=20, k=10 over 100k draws.
- No-vig math: see §4. Write the functions now, under `odds/`.

### ⛔ GATE 1. Validator checklist
- Backfill row counts per season and the failed-game count (≤ 1%).
- Curated uniqueness passed.
- As-of test passed.
- Pooled MAE table (model vs B1/B2) and calibration tables.

**Gate pass guidance for the validator:**
- Model MAE ≤ 0.97 × B1 for pts, reb, and ast.
- Model log loss < baseline log loss for every stat.
- Calibration bins with ≥ 200 rows are within ±3 percentage points.
- If these aren't met, the validator decides between targeted fixes and proceeding.

---

## Phase 2 — Cloud MVP: odds capture, paper bets, CLV, settlement

**Branch:** `p2-cloud`. **Target:** live before opening night. The implementer reads the exact 2026-27 opening date from the Odds API events list and states it in the report.

### P2.1 Infrastructure (`infra/`)
Terraform root with backend `s3 { bucket = "blackstar-terraform-state", key = "courtside/terraform.tfstate", region = "us-east-1", dynamodb_table = "blackstar-analytics-tf-lock", encrypt = true }`.

Resources:
- **S3** `courtside-data-495599764458`: versioning on, public access blocked, lifecycle moving `raw/odds/` objects to Glacier Instant Retrieval after 90 days.
- **ECR** repo `courtside` (scan on push, lifecycle keeps the last 10 images).
- **DynamoDB** `courtside-bets`: on-demand, hash key `bet_id` (S), point-in-time recovery on.
- **SNS** `courtside-alerts` + email subscription (owner email from a tfvars variable `owner_email`).
- **IAM** Lambda role: S3 read/write on the data bucket, DynamoDB CRUD on the table, `ssm:GetParameter` on `/courtside/*` with KMS decrypt for the default key, `sns:Publish` on alerts, `lambda:InvokeFunction` on `courtside-projector`, plus basic logs.
- **Lambda** functions, all from image `courtside:<git sha>`, with different `image_config.command`:

| Function | Handler | Timeout | Memory |
|---|---|---|---|
| `courtside-odds-poller` | `courtside.handlers.odds_poller.handler` | 300 | 512 |
| `courtside-projector` | `courtside.handlers.projector.handler` | 300 | 2048 |
| `courtside-settler` | `courtside.handlers.settler.handler` | 300 | 1024 |
| `courtside-reporter` | `courtside.handlers.reporter.handler` | 120 | 1024 |

- **EventBridge Scheduler** (`aws_scheduler_schedule`, timezone `America/New_York`):
  - poller every 15 minutes from 10:00 to 23:45 daily;
  - settler daily 11:00;
  - reporter daily 11:30.
- **CloudWatch alarms:** `Errors ≥ 1` per function per hour → SNS. Also a "poller silent" alarm: `Invocations < 1` over 1 hour between 10:00 and 23:00 ET. Implement it as a metric alarm with `treat_missing_data = breaching` on a 1-hour period, enabled only during the season. Expected noise is accepted.
- **Dockerfile:** base `public.ecr.aws/lambda/python:3.13`, `pip install .`, copy `config/`.
- **Build/push script** `scripts/deploy_image.ps1`: docker build → tag with git sha → ECR login → push. It prints the tag for `terraform apply -var image_tag=<sha>`.

Expected first plan: only creates. Any destroy → **STOP**.

### P2.2 Home runner (`home_runner/nightly.py` + `register_task.ps1`)
- Runs daily at 08:00 local via Windows Task Scheduler, registered by `register_task.ps1` (it runs whether or not the user is logged on, with the AWS profile available).
- Steps:
  1. Fetch `LeagueGameLog` (P and T) for the current season.
  2. Fetch the starter flag for any game ids not yet in S3.
  3. Rebuild curated tables for the current season, idempotently (overwrite the season file).
  4. Upload to `s3://courtside-data-…/curated/player_games/season=2026-27/data.parquet` (and the team equivalent).
  5. Upload all prior seasons once.
- On any exception: publish to `courtside-alerts` with the traceback, then exit non-zero.
- Weekly on Mondays it also runs training (P2.6).

### P2.3 Odds poller (`handlers/odds_poller.py`)
1. `GET /events`. Keep events with `commence_time` within the next 6 hours that have not started. If there are none, exit (0 credits used beyond the events call).
2. Credit floor: if `x-requests-remaining < 2000`, publish an alert once per day and exit.
3. For each kept event, call the event odds endpoint (3 markets, region `us`, decimal).
   - Write the raw JSON to `raw/odds/date=<ET date>/event=<id>/ts=<UTC iso>.json`.
4. Invoke `courtside-projector` asynchronously with `{"event_ids": [...], "snapshot_ts": "..."}`.

### P2.4 Name matching (`odds/names.py`)
- **Normalize:** NFKD → ASCII, lowercase, strip `.`, `'`, `-`, remove suffixes `jr, sr, ii, iii, iv`, collapse spaces.
- **Match** an odds `description` to a player on either team's recent roster: players appearing for that team in the last 30 days of curated data.
- Overrides in `config/name_overrides.csv` (`odds_name,player_id`) are applied first.
- Unmatched names: log them and write `ops/unmatched_names/date=<d>.csv` to S3. No bet for those players. The reporter lists them daily so the owner can add overrides.

### P2.5 Projector and paper bets (`handlers/projector.py`, `betting/`)
1. **Inputs:**
   - `champion.json` and the model files from `s3://…/models/champion/`.
   - Curated player and team games.
   - ESPN injuries, fetched live on each run and saved to `raw/injuries/ts=<iso>.json`.
2. **Who plays:** players matched to props, excluding anyone ESPN lists as `Out`.
   - `team_rot_out_*` features count rotation players listed `Out`.
   - `Doubtful` counts as out for teammates' features. That player gets no bets.
   - `Questionable` players get no bets themselves and are **not** counted as out.
3. **Projection:** build features as of today (same code path as training) → models → distribution (P1.5) at each offered line.
4. **No-vig market probability** (§4) per book, then the **consensus** = median no-vig P(over) across all books offering that exact line.
5. **Candidate bet** for each side at each book in `config/books.yaml`:
   - `EV = p_model_side × price − 1`.
   - **Log a paper bet when:**
     - EV ≥ 0.04;
     - `0.30 ≤ p_model_side ≤ 0.80`;
     - `min_pred ≥ 20`;
     - `|p_model_side − consensus_side| ≤ 0.15` (larger gaps usually mean the model is missing news);
     - tip-off is within 3 hours.
   - Only the **first** qualifying trigger per `(game, player, stat, side)` is logged, using the best-priced eligible book at that moment.
6. **Bet record** (DynamoDB):
   - `bet_id = sha1(game_id|player_id|stat|side)`;
   - `logged_at, event_id, commence_time, player_id, player_name, stat, side, line, book, price, p_model, p_consensus_novig, ev, min_pred, model_version, injury_snapshot_ts, status="open"`.
   - Use a conditional put (`attribute_not_exists(bet_id)`) so re-runs never duplicate.
7. **Stake:** paper, 1 unit flat. Also store `kelly_quarter = max(0, (p×price−1)/(price−1)) / 4`, capped at 0.01, for later analysis.

### P2.6 Weekly retrain + champion gate (home runner, Mondays)
- Retrain on all curated data through yesterday.
- Evaluate on the **last 28 days**, comparing MAE for pts/reb/ast against the current champion's predictions on those same rows.
- **Promote** if the new model's mean MAE across the 3 stats ≤ champion's × 1.01. If so, upload to `models/champion/` and move the old one to `models/history/<version>/`.
- Alert with the decision either way.

### P2.7 Settler (`handlers/settler.py`, daily 11:00 ET)
For each `open` bet whose game is in curated data:
- **Closing line:** the last odds snapshot before `commence_time`, at the **same book**.
  - `close_line`, `close_price_side`, and `close_novig_side` (no-vig at that book, if both sides exist).
  - Also `close_consensus_novig_side` at the bet's line, if it is still offered at close.
- **CLV fields:**
  - `clv_line`: for overs, `close_line − line`; for unders, `line − close_line`. Positive means the line moved our way.
  - `clv_prob`: if `close_line == line`, `close_novig_side − p_market_at_bet_side` (the no-vig at the same book at bet time); else null.
  - `beat_close`: `clv_line > 0`, or (`clv_line == 0` and `clv_prob > 0`).
- **Result:** from curated actual stats. Win, loss, push (integer line hit exactly), or **void** if the player did not play (`min == 0` or absent).
- **P&L:** `price − 1` for a win, −1 for a loss, 0 for a push or void.
- Set `status="settled"`.

### P2.8 Reporter (daily 11:30 ET)
Email via SNS covering yesterday and season to date:
- bets, wins/losses/pushes/voids, units P&L, ROI;
- **beat-close rate**, mean `clv_prob` and the n it was computed on, mean `clv_line`;
- the same numbers by stat;
- unmatched-names count.

Also write `reports/daily/date=<d>.json`.

### P2.9 Tests
- No-vig math.
- EV and bet filters (table-driven).
- Bet id idempotency.
- Settlement outcomes, including push and void.
- CLV sign conventions for over and under.
- Name normalization cases: `"Luka Dončić"`, `"Jaren Jackson Jr."`, `"De'Aaron Fox"`.

### ⛔ GATE 2. Validator checklist
- Terraform plan summary (creates only) and apply output.
- Image tag deployed.
- One full game day observed (preseason is fine if props exist; otherwise the first regular-season day):
  - poller invocation count;
  - snapshot count in S3;
  - projector run log excerpt;
  - number of paper bets logged with 3 sample records;
  - unmatched names.
- A settler run on that day's games, with 3 settled records showing CLV fields.
- The reporter email text.
- Home runner Task Scheduler entry plus one successful nightly log.
- The test run output.

---

## Phase 3 — Injury reactivity

**Branch:** `p3-injuries`

1. **Injury poller.** `courtside-injury-poller`, every 10 minutes from 10:00 to 23:30 ET on days with games. It reads the ESPN injuries, diffs them against the last snapshot (`raw/injuries/latest.json`), and saves both.
2. **Trigger.** A status change (into or out of `Out`/`Doubtful`) for any **rotation** player (`min_l10 ≥ 15`) on a team playing today invokes the projector for that game's event. The projector fetches fresh odds for that one event first (3 credits) so it compares against current lines.
3. **Tag the bets.** Bets logged within 30 minutes after a triggering change get `post_news=true` and `news_player_id`.
4. **Reporter.** Add CLV and ROI split by `post_news`.

### ⛔ GATE 3. Validator checklist
- At least one real triggered re-projection, with:
  - the injury diff;
  - before/after minutes projections for 3 teammates;
  - the bets logged as a result.
- Credit usage per day versus the floor.

---

## Phase 4 — Evaluation and go/no-go (paper results)

Runs after **≥ 300 settled paper bets** or 6 weeks of season, whichever is later.

1. **Analysis script** `scripts/evaluate_paper.py`:
   - beat-close rate with a 95% Wilson interval;
   - mean `clv_prob` with a t-stat;
   - ROI with a bootstrap 95% interval;
   - everything split by stat, by `post_news`, by EV bucket (4–6%, 6–10%, 10%+), and by book.
2. **Optional** (only if V4 said historical odds are available and the owner approves the credit cost): a historical backtest over 2025-26 regular-season props using closing lines only.
3. **Go/no-go recommendation rule** (this is a written recommendation; the owner decides):
   - **GO small** if beat-close rate ≥ 55% **and** mean `clv_prob` > +1.5pp with t > 2 **and** the ROI lower bound > −10%.
   - **Extend paper trading 4 weeks** if beat-close rate is 50–55%.
   - **NO-GO** below 50%. Investigate by segment before continuing.
4. **If GO, these are the live rules** (owner-executed, manual bet placement):
   - only the segments that cleared the bar;
   - stake = quarter Kelly capped at 1% of bankroll;
   - a daily exposure cap of 5% of bankroll;
   - keep logging every real bet in the same table with `real=true`.

### ⛔ GATE 4. Validator checklist
- Full evaluation output and the recommendation per the rule.

---

## 3. Known risks (and what we already decided about them)

| Risk | Decision |
|---|---|
| stats.nba.com blocks cloud IPs | Home runner fetches. The cloud never depends on it in real time. |
| ESPN injury JSON changes or disappears | V5 paths are recorded. Projector failures alarm. Fallback (official NBA injury report PDF) is out of scope until it's needed. |
| Odds API credit burn | Floor at 2,000 with an alert. Polling only within 6 hours of tip. ~3 credits per event per poll. |
| Name mismatches silently drop bets | The unmatched report runs daily, and the overrides CSV fixes them. |
| Late scratches after a bet is logged | Books void the bet when the player doesn't play, so settlement marks it `void`. |
| Hindsight in historical availability features | Accepted for training. Live uses the injury report. Noted in the reports. |
| Account limits | Out of scope for the model. A reason to spread bets across books if the project goes live. |

## 4. Reference formulas

- **Implied probability** from a decimal price: `q = 1 / price`.
- **No-vig (two-way):** `p_over = q_over / (q_over + q_under)`, `p_under = 1 − p_over`. Requires both sides at the same book and line. Otherwise the book is excluded from consensus for that line.
- **EV per unit:** `p × price − 1`.
- **Quarter Kelly:** `((p × price − 1) / (price − 1)) / 4`.
- **Break-even at −110 (decimal 1.909):** 52.4%.
