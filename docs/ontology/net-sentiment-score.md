# Net Sentiment Score (NSS)

Domain: Customer Experience > Contact Centre

Synonyms:

- NSS
- net sentiment
- net sentiment index

Description: The normalized balance of positive and negative customer sentiment across scored
contact-centre calls.

## Definition

Net Sentiment Score (NSS) shows whether positive or negative customer sentiment dominates a
selected set of calls. It is calculated from the overall sentiment assigned to customer speech,
not from agent speech.

## Governed calculation

The authoritative measure is `net_sentiment_score` in the metric view
`contact_centre_analytics.connect_analytics.contact_sentiment_metrics`.

Formula:

```text
(positive contacts - negative contacts) / scored contacts
```

`scored contacts` includes every contact whose overall sentiment is positive, negative, neutral,
or mixed. Contacts with NULL sentiment are excluded.

The result ranges from -1 to 1:

- 1 means every scored contact is positive.
- 0 means positive and negative contacts are balanced.
- -1 means every scored contact is negative.

## How to use NSS

Use NSS to compare queues, agents, contact reasons, customer segments, counties, or time periods.
Always use the governed metric-view measure with `MEASURE(net_sentiment_score)` instead of
recalculating it from raw rows.

Useful analytical questions include:

- What is NSS by queue this month?
- Which queue has the lowest NSS?
- How has NSS changed by week for Billing?
- Which agents improved NSS while keeping transfer rate low?

## Interpretation guardrails

- NSS is not Net Promoter Score (NPS) and does not use survey responses.
- NSS describes the sentiment mix in the selected calls; it does not measure customer loyalty.
- Neutral and mixed calls affect the denominator but not the positive-minus-negative numerator.
- Compare groups with their contact counts. A high or low score based on very few contacts can be
  unstable.
- Sentiment follows the governed four-label contract: positive, negative, neutral, mixed, or NULL.

## Page relationships

Related assets:

- `contact_centre_analytics.connect_analytics.contact_sentiment_metrics`
- Production Contact Centre Sentiment and Service Intelligence Genie Agent

Source:

- `contact_centre_analytics.connect_analytics.contact_sentiment_metrics`

## Genie One demo question

Ask:

```text
What does NSS mean for the Contact Centre, and which queue currently has the lowest NSS?
```

The expected response should cite this Page for the definition and use the governed
`net_sentiment_score` measure for the queue comparison.
