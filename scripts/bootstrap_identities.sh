#!/usr/bin/env bash
set -euo pipefail

PROFILE=""
GITHUB_REPO=""
CATALOG=""
WAREHOUSE_ID=""
CREATE_OAUTH_SECRET=false

usage() {
  cat <<'EOF'
Usage: bootstrap_identities.sh --profile PROFILE [options]

Options:
  --catalog CATALOG          Grant USE CATALOG to the runtime principal.
  --warehouse-id ID          Grant CAN_USE on the SQL warehouse.
  --github-repo OWNER/REPO  Configure GitHub Actions settings.
  --create-oauth-secret     Create a new deploy-principal OAuth secret.

Creating a new OAuth secret is not idempotent. Use that option only once, and only
with --github-repo so the value is written directly to GitHub Actions secrets.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --github-repo)
      GITHUB_REPO="$2"
      shift 2
      ;;
    --catalog)
      CATALOG="$2"
      shift 2
      ;;
    --warehouse-id)
      WAREHOUSE_ID="$2"
      shift 2
      ;;
    --create-oauth-secret)
      CREATE_OAUTH_SECRET=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PROFILE" ]]; then
  echo "--profile is required" >&2
  exit 2
fi
if [[ "$CREATE_OAUTH_SECRET" == true && -z "$GITHUB_REPO" ]]; then
  echo "--create-oauth-secret requires --github-repo" >&2
  exit 2
fi
command -v databricks >/dev/null
command -v jq >/dev/null

get_or_create_sp() {
  local display_name="$1"
  local existing
  existing="$(
    databricks service-principals list --profile "$PROFILE" --output json |
      jq -c --arg name "$display_name" \
        '.[] | select(.displayName == $name)' |
      first_line
  )"
  if [[ -z "$existing" ]]; then
    databricks service-principals create \
      --display-name "$display_name" \
      --profile "$PROFILE" \
      --output json
  else
    printf '%s\n' "$existing"
  fi
}

get_or_create_group() {
  local display_name="$1"
  local existing
  existing="$(
    databricks groups list --profile "$PROFILE" --output json |
      jq -c --arg name "$display_name" \
        '.[] | select(.displayName == $name)' |
      first_line
  )"
  if [[ -z "$existing" ]]; then
    databricks groups create \
      --display-name "$display_name" \
      --profile "$PROFILE" \
      --output json
  else
    printf '%s\n' "$existing"
  fi
}

first_line() {
  IFS= read -r line || true
  printf '%s' "$line"
}

deploy_sp="$(get_or_create_sp sp-connect-transcript-deploy)"
runtime_sp="$(get_or_create_sp sp-connect-transcript-runtime)"
get_or_create_group contact_centre_engineers >/dev/null
get_or_create_group contact_centre_analysts >/dev/null

deploy_id="$(jq -r '.id' <<<"$deploy_sp")"
deploy_application_id="$(jq -r '.applicationId' <<<"$deploy_sp")"
runtime_application_id="$(jq -r '.applicationId' <<<"$runtime_sp")"

echo "Deploy application ID:  $deploy_application_id"
echo "Runtime application ID: $runtime_application_id"
echo
echo "Set runtime_service_principal_name in the target override to:"
echo "  $runtime_application_id"
echo
echo "An account admin must grant Service Principal User on"
echo "sp-connect-transcript-runtime to sp-connect-transcript-deploy."

if [[ -n "$CATALOG" ]]; then
  grant_body="$(
    jq -cn \
      --arg deploy "$deploy_application_id" \
      --arg runtime "$runtime_application_id" \
      '{
        changes: [
          {principal: $deploy, add: ["USE_CATALOG", "CREATE_SCHEMA"]},
          {principal: $runtime, add: ["USE_CATALOG"]}
        ]
      }'
  )"
  databricks grants update CATALOG "$CATALOG" \
    --profile "$PROFILE" \
    --json "$grant_body" >/dev/null
  echo "Granted deploy and runtime catalog privileges on $CATALOG"
fi

if [[ -n "$WAREHOUSE_ID" ]]; then
  permission_body="$(
    jq -cn --arg principal "$runtime_application_id" \
      '{access_control_list: [{
        service_principal_name: $principal,
        permission_level: "CAN_USE"
      }]}'
  )"
  databricks permissions update warehouses "$WAREHOUSE_ID" \
    --profile "$PROFILE" \
    --json "$permission_body" >/dev/null
  echo "Granted runtime CAN_USE on warehouse $WAREHOUSE_ID"
fi

if [[ -n "$GITHUB_REPO" ]]; then
  command -v gh >/dev/null
  host="$(
    databricks auth env --profile "$PROFILE" |
      jq -r '.env.DATABRICKS_HOST'
  )"
  gh variable set DATABRICKS_HOST --repo "$GITHUB_REPO" --body "$host"
  gh secret set DATABRICKS_CLIENT_ID \
    --repo "$GITHUB_REPO" \
    --body "$deploy_application_id"
  gh variable set DATABRICKS_RUNTIME_CLIENT_ID \
    --repo "$GITHUB_REPO" \
    --body "$runtime_application_id"
fi

if [[ "$CREATE_OAUTH_SECRET" == true ]]; then
  secret="$(
    databricks service-principal-secrets-proxy create "$deploy_id" \
      --profile "$PROFILE" \
      --output json
  )"
  client_secret="$(jq -r '.secret' <<<"$secret")"
  if [[ -z "$client_secret" || "$client_secret" == null ]]; then
    echo "The OAuth secret response did not contain a secret value" >&2
    exit 1
  fi
  gh secret set DATABRICKS_CLIENT_SECRET \
    --repo "$GITHUB_REPO" \
    --body "$client_secret"
  unset client_secret secret
  echo "GitHub Actions OAuth settings configured for $GITHUB_REPO"
fi
