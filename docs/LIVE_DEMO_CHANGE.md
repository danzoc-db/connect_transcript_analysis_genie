# Live Demo Change: add "sentiment recovery rate" with Genie Code

The one change made live in the room. It must be built and tested during the build (Phase 4),
then removed from `main` so it can be added again live. The exact prompt and expected diff are
kept here, and the measure is also left **commented out** in `sql/contact_sentiment_metrics.sql`
as a safety net.

## What it measures

Of the calls where the customer **started** unhappy (opening sentiment `negative` or `mixed`),
the share that **ended** `positive`. It answers "how often do our agents turn a bad call round?"

## Before the session

- [ ] Endpoint warmed (send one request through the model service about 15 minutes before; the change itself does not call the model).
- [ ] Git folder open at `/Workspace/Users/<you>/connect_transcript_analysis_genie`, on `main`, pulled.
- [ ] GitHub repo open on the Actions tab.
- [ ] Genie space open; confirm the question below currently cannot be answered (no such measure).
- [ ] Timings from the last rehearsal recorded below.

## Steps in the room

1. In the Git folder, create branch `feat/sentiment-recovery-rate`.
2. Open `sql/contact_sentiment_metrics.sql`, open Genie Code, paste the prompt below.
3. Review the diff Genie Code proposes (should match "Expected diff").
4. Commit and push from the Git folder dialog. Open the PR on GitHub (link from the push).
5. Show CI: lint + `bundle validate` go green. Merge (squash).
6. Show the deploy workflow: `bundle deploy -t prod`, then the metric-view publish.
7. In Genie: ask the question below.

## Genie Code prompt

```
In this metric view, add a measure called sentiment_recovery_rate: of the contacts whose
sentiment_opening is 'negative' or 'mixed', the fraction whose sentiment_closing is 'positive'.
Return a value between 0 and 1. Add a short comment and a description so Genie can explain it.
Do not change any other measure or dimension.
```

## Expected diff (finalise after the Phase 4 test)

```yaml
    - name: sentiment_recovery_rate
      expr: >
        COUNT_IF(sentiment_opening IN ('negative', 'mixed') AND sentiment_closing = 'positive')
        / NULLIF(COUNT_IF(sentiment_opening IN ('negative', 'mixed')), 0)
      comment: "Share of calls that started negative or mixed and ended positive."
```

## Genie questions to ask after deploy

- "What is our sentiment recovery rate by queue over the last 30 days?"
- "Which agents have the highest sentiment recovery rate on Complaints calls?"

## Rehearsal timings

| Step | Target | Last rehearsal |
|---|---|---|
| Genie Code edit + review | 2 min | |
| Commit, push, open PR | 1 min | |
| CI green | 2 min | |
| Merge to deploy complete | 3 min | |
| Genie answer | 1 min | |
