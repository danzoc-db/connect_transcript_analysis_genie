USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

CREATE OR REPLACE VIEW contact_sentiment_metrics
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: Governed contact-centre sentiment, service and handling KPIs.
source: silver_transcript_sentiment
dimensions:
  - name: contact_date
    expr: contact_date
    comment: Calendar date on which the call started.
  - name: contact_week
    expr: DATE_TRUNC('WEEK', contact_date)
    comment: Monday-starting week containing the contact date.
  - name: contact_month
    expr: DATE_TRUNC('MONTH', contact_date)
    comment: Calendar month containing the contact date.
  - name: queue
    expr: queue
    comment: Amazon Connect queue that handled the contact.
  - name: contact_reason
    expr: contact_reason
    comment: Primary intent assigned to the contact.
  - name: agent_name
    expr: agent_name
    comment: Synthetic display name of the handling agent.
  - name: county
    expr: county
    comment: Synthetic customer county.
  - name: segment
    expr: segment
    comment: Synthetic customer segment.
  - name: sentiment
    expr: sentiment
    comment: "Overall sentiment: positive, negative, neutral, mixed, or NULL."
  - name: sentiment_opening
    expr: sentiment_opening
    comment: Sentiment in the customer's opening problem statement.
  - name: sentiment_mid
    expr: sentiment_mid
    comment: Sentiment while the customer responds to the proposed resolution.
  - name: sentiment_closing
    expr: sentiment_closing
    comment: Sentiment in the customer's final substantive response.
  - name: sentiment_shift
    expr: sentiment_shift
    comment: Recovered, deteriorated, or stable from opening to closing.
  - name: transferred
    expr: transferred
    comment: Whether the contact was transferred.
measures:
  - name: total_contacts
    expr: COUNT(1)
    comment: Number of contacts.
  - name: negative_contacts
    expr: COUNT_IF(sentiment = 'negative')
    comment: Contacts with negative overall sentiment.
  - name: negative_share
    expr: COUNT_IF(sentiment = 'negative') / NULLIF(COUNT_IF(sentiment IS NOT NULL), 0)
    comment: Share of scored contacts with negative overall sentiment.
  - name: positive_share
    expr: COUNT_IF(sentiment = 'positive') / NULLIF(COUNT_IF(sentiment IS NOT NULL), 0)
    comment: Share of scored contacts with positive overall sentiment.
  - name: mixed_share
    expr: COUNT_IF(sentiment = 'mixed') / NULLIF(COUNT_IF(sentiment IS NOT NULL), 0)
    comment: Share of scored contacts with mixed overall sentiment.
  - name: net_sentiment_score
    expr: >
      (COUNT_IF(sentiment = 'positive') - COUNT_IF(sentiment = 'negative'))
      / NULLIF(COUNT_IF(sentiment IS NOT NULL), 0)
    comment: Positive minus negative contacts divided by scored contacts.
  - name: avg_hold_minutes
    expr: AVG(hold_seconds) / 60.0
    comment: Average hold duration in minutes.
  - name: transfer_rate
    expr: COUNT_IF(transferred) / NULLIF(COUNT(1), 0)
    comment: Share of contacts that were transferred.
  - name: avg_handle_minutes
    expr: AVG(duration_seconds) / 60.0
    comment: Average call duration in minutes.
  # Live demo change (intentionally inactive on main):
  # - name: sentiment_recovery_rate
  #   expr: >
  #     COUNT_IF(sentiment_opening IN ('negative', 'mixed') AND sentiment_closing = 'positive')
  #     / NULLIF(COUNT_IF(sentiment_opening IN ('negative', 'mixed')), 0)
  #   comment: Share of calls that started negative or mixed and ended positive.
materialization:
  mode: relaxed
  materialized_views:
    - name: daily_queue_metrics
      type: aggregated
      dimensions:
        - contact_date
        - queue
      measures:
        - total_contacts
        - negative_share
        - net_sentiment_score
        - avg_hold_minutes
        - transfer_rate
$$;
