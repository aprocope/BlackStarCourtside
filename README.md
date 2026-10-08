# Courtside

Paper-trades NBA player props (points, rebounds, assists) and measures closing line value.
See [docs/HANDOFF.md](docs/HANDOFF.md) for the full plan and phase gates.

## Local setup

```bash
python3.13 -m venv .venv          # Windows: py -3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The Odds API key is read from the `ODDS_API_KEY` environment variable locally,
and from SSM `/courtside/odds_api_key` in the cloud. Never commit it.
- macOS: `brew install libomp` is required for LightGBM.
