#!/bin/bash
set -eu${DEBUG:+x}o pipefail

# -e exit on Error
# -u (undefined) Using Undefined variables exit script
# -x (xtrace) show all comamands and outputs
# -o pipefail - if in any pipe will be error on any level, fail the whole pipe

VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200/"}
VAULT_TOKEN=${VAULT_TOKEN:-$(cat ~/.vault-token)}
tools=("vault" "jq")

log_filename="log.log"
echo "$(date): starting $0" > $log_filename

function tool_is_installed {
  if command -v $1 &> /dev/null; then
    echo "$1 is installed [OK]"
    return 0
  else
    echo "$1 is not installed [ERROR]"
    return 1
  fi
}

function validate_tools {
  all_installed=true
  echo "Checking if tools needed tools are needed"

  for tool in "${tools[@]}"; do
    if ! tool_is_installed "$tool"; then
      all_installed=false
    fi
  done

  echo "All installed status: $all_installed"
}

function vault_validate {
  echo "Running command against $VAULT_ADDR/v1/sys/health"

  # -s silient (doesn't show progress information)
  # -f (fail) - return not zero exit code in case of 4xx or 5xx
  # -L (location) follow redirections
  # -m 10 (max-time) for 10 seconds

  curl -sfL -m 10 -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/auth/token/lookup-self | jq ".data.polices" || \
    ( echo "ERROR: A Vault Token is wrong or Vault server is unavailable, contact administrator..." | exit 1)
  echo $?

  echo "Checking if token has needed policy"
  policies=$(curl -sfL -m 10 -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/auth/token/lookup-self | jq -r '.data.policies|join(" ")')

  policy_root=false
  for policy in ${policies[@]}; do
    if [[ $policy == "root" ]]; then
      policy_root=true
      continue
    fi
  done

  if [[ $policy_root != true ]]; then
    echo "ERROR, Vault token doesn't have policy 'root'"
  else
    echo "Policy exist, OK"
  fi
}

function vault_check_secret_exists {
  local path=$1
  echo "Checking if path $path exist in vault" >> $log_filename

  if secret_metadata=$(curl -sfL -m 10 -X GET -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/kv/metadata/$path | jq -r '.data'); then
    echo "Secret have versions in vault" >> $log_filename
    echo $secret_metadata >> $log_filename
    latest_version=$(echo $secret_metadata | jq -r '.current_version')
    echo "latest version is : $latest_version" >> $log_filename
    deletion_time="$(echo $secret_metadata | jq --arg version "$latest_version" -r '.versions[$version].deletion_time')"
    echo "deletion_time: $deletion_time" >> $log_filename
    test -z $deletion_time
  fi


}

validate_tools
vault_validate
echo "bla bla bla"
if vault_check_secret_exists "lenie-ai/dev/cloudferro"; then
  echo "secret ABC exist"
else
  echo "secret ABC doesn't exist"
fi

exit 0
