-- One quality-controlled row per contact. Hidden QA labels do not leave bronze.
CREATE OR REFRESH STREAMING TABLE silver_connect_transcripts (
  CONSTRAINT valid_contact_id EXPECT (contact_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT has_customer_turns EXPECT (customer_turn_count > 0) ON VIOLATION DROP ROW,
  CONSTRAINT completed_job EXPECT (job_status = 'COMPLETED') ON VIOLATION DROP ROW,
  CONSTRAINT known_queue EXPECT (
    queue IN (
      'Account Services',
      'Billing',
      'Boiler Care',
      'Complaints',
      'Moving Home',
      'Payments',
      'Sales',
      'Smart Meters'
    )
  ),
  CONSTRAINT plausible_duration EXPECT (duration_seconds BETWEEN 10 AND 7200)
)
COMMENT 'Cleansed contact transcripts with customer-only early, middle, late and overall text. Synthetic demo data only; contains no real personal data.'
AS
WITH ordered AS (
  SELECT
    CustomerMetadata.ContactId AS contact_id,
    CAST(ContactAttributes.InitiationTimestamp AS TIMESTAMP) AS contact_ts,
    JobStatus AS job_status,
    ContactAttributes.Queue AS queue,
    ContactAttributes.ContactReason AS contact_reason,
    ContactAttributes.AgentId AS agent_id,
    ContactAttributes.AgentName AS agent_name,
    ContactAttributes.CustomerCounty AS county,
    ContactAttributes.CustomerSegment AS segment,
    CAST(ContactAttributes.HoldDurationSeconds AS INT) AS hold_seconds,
    CAST(ContactAttributes.Transferred AS BOOLEAN) AS transferred,
    CAST(ConversationCharacteristics.TotalConversationDurationMillis / 1000.0 AS DOUBLE)
      AS duration_seconds,
    array_sort(
      Transcript,
      (left_turn, right_turn) ->
        CASE
          WHEN left_turn.BeginOffsetMillis < right_turn.BeginOffsetMillis THEN -1
          WHEN left_turn.BeginOffsetMillis > right_turn.BeginOffsetMillis THEN 1
          ELSE 0
        END
    ) AS ordered_turns,
    source_file,
    ingested_at
  FROM STREAM(bronze_connect_transcripts)
),
turn_arrays AS (
  SELECT
    *,
    transform(
      ordered_turns,
      turn -> concat(turn.ParticipantId, ': ', turn.Content)
    ) AS transcript_lines,
    transform(
      filter(ordered_turns, turn -> turn.ParticipantId = 'CUSTOMER'),
      turn -> turn.Content
    ) AS customer_lines
  FROM ordered
),
window_sizes AS (
  SELECT
    *,
    size(ordered_turns) AS turn_count,
    size(customer_lines) AS customer_turn_count,
    filter(
      customer_lines,
      line -> trim(line) <> 'No, that is everything. Goodbye.'
    ) AS substantive_customer_lines
  FROM turn_arrays
),
analysis_windows AS (
  SELECT
    *,
    CASE
      WHEN size(substantive_customer_lines) >= 3
        THEN slice(substantive_customer_lines, 2, size(substantive_customer_lines) - 2)
      ELSE CAST(array() AS ARRAY<STRING>)
    END AS middle_customer_lines
  FROM window_sizes
)
SELECT
  contact_id,
  contact_ts,
  CAST(contact_ts AS DATE) AS contact_date,
  job_status,
  queue,
  contact_reason,
  agent_id,
  agent_name,
  county,
  segment,
  hold_seconds,
  transferred,
  duration_seconds,
  turn_count,
  customer_turn_count,
  array_join(transcript_lines, '\n') AS full_transcript,
  array_join(substantive_customer_lines, ' ') AS customer_text,
  element_at(substantive_customer_lines, 1) AS customer_opening_text,
  CASE
    WHEN size(middle_customer_lines) > 0
      THEN array_join(middle_customer_lines, ' ')
    ELSE NULL
  END AS customer_mid_text,
  element_at(substantive_customer_lines, -1) AS customer_closing_text,
  source_file,
  ingested_at
FROM analysis_windows;
