# FPL Helper

A full-stack Fantasy Premier League analytics tool that helps managers make better weekly decisions — team building, player analysis, and personalized squad recommendations, all powered by the official FPL API.

**Live site:** [web-production-4a2ed.up.railway.app]

## Features

- **Player Search** — live search across all Premier League players with full stats (form, xG, xA, ICT index, ownership) and accent-insensitive matching
- **Top Players** — filter and sort by position, form, points per game, expected points, and more
- **Team Builder** — builds a valid 15-player squad within a £100m budget using 5 strategies (Balanced, Attack, Defense, Budget, Form), factoring in both player form and upcoming fixture difficulty
- **Transfer Tips** — most transferred-in players and hidden differential picks (high form, low ownership)
- **My Team** — enter your FPL Team ID to pull your real squad and get:
  - Personalized suggestions (injury alerts, tough fixture warnings, benched in-form players)
  - Optimized lineup — best formation and captain choice from your existing 15 players
  - Suggested transfer — a specific "transfer this player out for this player in" recommendation based on your free transfer and budget
  - Find Replacement — algorithm-suggested alternatives or manual search for any player, position-matched
  - Compare to Optimal — see how your squad stacks up against an algorithmically ideal team
- **Live gameweek deadline countdown**
- **Mobile responsive** with bottom navigation

## Architecture

```
fpl-helper/
├── app.py            Flask routes and API endpoints
├── fpl_api.py         FPL API integration, caching, player data enrichment
├── team_builder.py     Squad-building algorithm and scoring logic
├── team_lookup.py       Real user team lookup and personalized analysis
├── ai_summary.py        Rule-based player recommendation summaries
├── templates/
│   └── index.html      Single-page frontend (vanilla JS, no framework)
├── static/
│   └── placeholder.svg   Fallback player silhouette
└── Procfile             Gunicorn config for Railway deployment
```

## How the Team Builder Works

The scoring algorithm combines:
- **Form** — recent performance (last 5 gameweeks)
- **Expected points** — FPL's own projected points for the next gameweek
- **Fixture difficulty (FDR)** — 1.25x boost for very easy fixtures down to 0.8x penalty for very hard ones
- **Home advantage** — 1.05x boost for home fixtures
- **Premium player reliability** — a boost for highly-owned, high-scoring players to reflect real-world reliability (penalties, set pieces) that raw stats alone don't fully capture

Squad construction happens in two passes:
1. Fill all 15 required slots (2 GKP, 5 DEF, 5 MID, 3 FWD) with the cheapest eligible players — this guarantees a valid squad every time
2. Upgrade players one at a time by score, as long as budget allows — this uses the remaining budget to bring in the best possible players without ever breaking the squad size

## My Team Analysis

Given a public FPL Team ID, the app pulls the user's actual current squad via the official `entry/{id}/event/{gw}/picks/` endpoint and layers analysis on top:

- **Optimize My Lineup** re-runs the same formation logic used in Team Builder, but restricted to the players the user already owns
- **Suggest My Transfer** finds the single best transfer by comparing the user's weakest starter (from the optimized lineup, so recommendations stay consistent) against all available players at that position within budget
- All suggestions are personalized per Team ID — no two users see the same results

## Data Source

All player, team, fixture, and squad data comes from the official Fantasy Premier League API (`fantasy.premierleague.com/api`), which is free and requires no authentication. Data is cached in memory for one hour to reduce API load and improve performance.

## Tech Stack

- **Backend:** Python, Flask, Gunicorn
- **Frontend:** Vanilla JavaScript, HTML, CSS (no framework)
- **Data:** Official Fantasy Premier League REST API
- **Deployment:** Railway

## Status

Actively developed based on real user feedback. Known limitation: player photos are pulled directly from FPL's official photo database, which is sometimes slow to update after transfers — this is a data source limitation, not a bug in the app.

## Author

Eduardo Maticorena
