#!/usr/bin/env bash
set -euo pipefail

PROFILE=""
ACCOUNT_PROFILE=""
GITHUB_REPO=""
CATALOG=""
WAREHOUSE_ID=""
CREATE_OAUTH_SECRET=false

usage() {
  cat <<'EOF'
Usage: bootstrap_identities.sh --profile PROFILE [options]

Options:
  --account-profile PROFILE  Grant Service Principal User through account APIs.
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
    --account-profile)
      ACCOUNT_PROFILE="$2"
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
engineers_group="$(get_or_create_group contact_centre_engineers)"
analysts_group="$(get_or_create_group contact_centre_analysts)"

current_user="$(
  databricks current-user me --profile "$PROFILE" --output json
)"
current_user_id="$(jq -r '.id' <<<"$current_user")"
for group_id in \
  "$(jq -r '.id' <<<"$engineers_group")" \
  "$(jq -r '.id' <<<"$analysts_group")"; do
  if ! databricks groups get "$group_id" --profile "$PROFILE" --output json |
    jq -e --arg user_id "$current_user_id" \
      'any(.members[]?; .value == $user_id)' >/dev/null; then
    membership_patch="$(
      jq -cn --arg user_id "$current_user_id" '{
        schemas: ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        Operations: [{
          op: "add",
          path: "members",
          value: [{value: $user_id}]
        }]
      }'
    )"
    databricks groups patch "$group_id" \
      --profile "$PROFILE" \
      --json "$membership_patch" >/dev/null
  fi
done

deploy_id="$(jq -r '.id' <<<"$deploy_sp")"
deploy_application_id="$(jq -r '.applicationId' <<<"$deploy_sp")"
runtime_application_id="$(jq -r '.applicationId' <<<"$runtime_sp")"

entitlement_patch='{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [{
    "op": "add",
    "path": "entitlements",
    "value": [
      {"value": "workspace-access"},
      {"value": "databricks-sql-access"}
    ]
  }]
}'
for principal_id in "$deploy_id" "$(jq -r '.id' <<<"$runtime_sp")"; do
  databricks service-principals patch "$principal_id" \
    --profile "$PROFILE" \
    --json "$entitlement_patch" >/dev/null
done

echo "Deploy application ID:  $deploy_application_id"
echo "Runtime application ID: $runtime_application_id"
echo
echo "Set runtime_service_principal_name in the target override to:"
echo "  $runtime_application_id"

if ! tag_policy="$(
  databricks tag-policies get-tag-policy customer_experience \
    --profile "$PROFILE" \
    --output json 2>/dev/null
)"; then
  tag_policy="$(
    databricks tag-policies create-tag-policy customer_experience \
      --description "Domain tag for customer experience data products." \
      --profile "$PROFILE" \
      --output json
  )"
fi
tag_policy_id="$(jq -r '.id' <<<"$tag_policy")"

if ! databricks domains get-domain domains/customer-experience \
  --profile "$PROFILE" >/dev/null 2>&1; then
  databricks domains create-domain customer_experience \
    --domain-id customer-experience \
    --subtitle "Customer Experience" \
    --description "Customer interactions, service quality and experience analytics." \
    --profile "$PROFILE" >/dev/null
fi
if ! databricks domains get-domain domains/contact-centre \
  --profile "$PROFILE" >/dev/null 2>&1; then
  databricks domains create-domain "customer_experience/Contact Centre" \
    --domain-id contact-centre \
    --parent-domain-id customer-experience \
    --subtitle "Contact Centre" \
    --description "Governed Amazon Connect transcript, sentiment and service-level analytics." \
    --profile "$PROFILE" >/dev/null
fi
echo "Ensured Customer Experience > Contact Centre domain"

if [[ -n "$ACCOUNT_PROFILE" ]]; then
  account_id="$(
    databricks auth env --profile "$ACCOUNT_PROFILE" |
      jq -r '.env.DATABRICKS_ACCOUNT_ID'
  )"
  current_user="$(
    databricks current-user me --profile "$PROFILE" --output json |
      jq -r '.userName'
  )"
  rule_name="accounts/$account_id/servicePrincipals/$runtime_application_id/ruleSets/default"
  rule_set="$(
    databricks account access-control get-rule-set \
      "$rule_name" "" \
      --profile "$ACCOUNT_PROFILE" \
      --output json
  )"
  rule_update="$(
    jq -c \
      --arg deploy "servicePrincipals/$deploy_application_id" \
      --arg user "users/$current_user" \
      '
      .grant_rules = (
        if any(.grant_rules[]?; .role == "roles/servicePrincipal.user") then
          [.grant_rules[] |
            if .role == "roles/servicePrincipal.user" then
              .principals = ((.principals + [$deploy, $user]) | unique)
            else
              .
            end
          ]
        else
          .grant_rules + [{
            role: "roles/servicePrincipal.user",
            principals: [$deploy, $user]
          }]
        end
      )
      | {
          name: .name,
          rule_set: {
            name: .name,
            etag: .etag,
            grant_rules: .grant_rules
          }
        }
      ' <<<"$rule_set"
  )"
  databricks account access-control update-rule-set \
    --profile "$ACCOUNT_PROFILE" \
    --json "$rule_update" >/dev/null
  echo "Granted Service Principal User on the runtime identity"

  tag_rule_name="accounts/$account_id/tagPolicies/$tag_policy_id/ruleSets/default"
  tag_rule_set="$(
    databricks account access-control get-rule-set \
      "$tag_rule_name" "" \
      --profile "$ACCOUNT_PROFILE" \
      --output json
  )"
  tag_rule_update="$(
    jq -c \
      --arg runtime "servicePrincipals/$runtime_application_id" \
      '
      .grant_rules = (
        if any(.grant_rules[]?; .role == "roles/tagPolicy.assigner") then
          [.grant_rules[] |
            if .role == "roles/tagPolicy.assigner" then
              .principals = ((.principals + [$runtime]) | unique)
            else
              .
            end
          ]
        else
          .grant_rules + [{
            role: "roles/tagPolicy.assigner",
            principals: [$runtime]
          }]
        end
      )
      | {
          name: .name,
          rule_set: {
            name: .name,
            etag: .etag,
            grant_rules: .grant_rules
          }
        }
      ' <<<"$tag_rule_set"
  )"
  databricks account access-control update-rule-set \
    --profile "$ACCOUNT_PROFILE" \
    --json "$tag_rule_update" >/dev/null
  echo "Granted runtime governed tag assignment"
else
  echo
  echo "An account admin must grant Service Principal User on"
  echo "sp-connect-transcript-runtime to sp-connect-transcript-deploy."
fi

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
      '{
        access_control_list: [
          {
            service_principal_name: $principal,
            permission_level: "CAN_USE"
          },
          {
            group_name: "contact_centre_engineers",
            permission_level: "CAN_USE"
          },
          {
            group_name: "contact_centre_analysts",
            permission_level: "CAN_USE"
          }
        ]
      }'
  )"
  databricks permissions update warehouses "$WAREHOUSE_ID" \
    --profile "$PROFILE" \
    --json "$permission_body" >/dev/null
  echo "Granted runtime and demo groups CAN_USE on warehouse $WAREHOUSE_ID"
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
