-- DATA PRIVACY: the source files are synthetic and generated at runtime by
-- src/connect_sentiment/generator.py. No real transcripts or personal data are ingested.
-- Auto Loader incrementally ingests multiline Contact Lens JSON from the UC volume.
CREATE OR REFRESH STREAMING TABLE bronze_connect_transcripts
COMMENT 'Raw Amazon Connect Contact Lens post-call analysis JSON with ingestion metadata. Synthetic demo data only; contains no real personal data.'
AS
SELECT
  *,
  _metadata.file_path AS source_file,
  _metadata.file_modification_time AS source_modified_at,
  current_timestamp() AS ingested_at
FROM STREAM read_files(
  '${volume_path}/connect/Analysis/Voice',
  format => 'json',
  multiLine => true,
  schemaEvolutionMode => 'addNewColumns'
);
