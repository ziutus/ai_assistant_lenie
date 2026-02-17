#! /bin/bash
set -eu${DEBUG}o pipefail

OPTIND=1
REGION="us-east-1"
STAGE=""
PWD=$(pwd)
PROJECT_CODE=""
EXECUTE_ROLE=""
DATE=$(date '+%Y%m%d%H%M%S')

TEMPLATES=()
COMMON_TEMPLATES=()
USE_LOGGER=0
CHANGE_SET=false
DELETE_COUNT=0
ACTION=""

command -v aws > /dev/null 2>&1 || { echo >&2 "aws cli not installed. Aborting..."; exit 1; }
command -v jq  > /dev/null 2>&1 || { echo >&2 "jq not installed. Aborting..."; exit 1; }
command -v sponge > /dev/null 2>&1 || { echo >&2 "sponge not installed. For Debian use: apt install moreutils Aborting..."; exit 1; }
#[ -e /dev/log ] || { echo >&2 "deploy.sh: can't use logger, pleas install syslog-ng or similar software"; exit 1;}

show_help() {
   echo "Usage:
   $0 -r <aws_region>  [-h]

   -r aws-region - A AWS Region where stack should be created/updated/deleted (default: $REGION)
   -p PROJECT_CODE - project code (for example: lenie)
   -s stage - Deployment stage (currently: dev) (default: $STAGE)
   -d - change default action from Create/Update to Delete
   -t  - create change-sets instead of apply changes (default: $CHANGE_SET)


   -h show this message

  The configuration file is deploy.ini in current directory.

  In Cloudformation you have main types of actions for stacks: create stack, update stack, delete stack.
  This script can automatically choose action between create or update depends on existing stacks (it is checking names
  of stacks)

  This script can also works with changesets.

  Example usage:
   $0 -r us-east-1 -p lenie -s dev -t

   "
   exit 1
}

log() {
  local message=$*

  echo "$message"

#  [ "${USE_LOGGER}" -eq 1 ] && logger -s $message

}

parse_config() {
  local section_name_pattern="^\[\w*\]$"
  local value_pattern="^\w.*"
  local val
  local section

  while IFS=$'\r\n' read -r val
  do
    if [[ "${val}" =~ $section_name_pattern ]]; then
      section="${val}"
    elif [[ "${val}" =~ $value_pattern ]]; then
      case ${section} in
        "[common]") COMMON_TEMPLATES+=("${val}");;
        "[${STAGE}]") TEMPLATES+=("${val}");;
      esac
    fi
  done < "${PWD}"/deploy.ini

}


create_update_stack() {
  echo "creating or updating stack - inside function"
  local templates=("$@")

  local template

  for template in "${templates[@]}"
  do
    echo "Processing template ${template}"
    log "Processing template ${template}"
    local stack_name
    local stack_count

    stack_name=$(get_stack_name "$template")
    echo "Stack name: ${stack_name}"

    set +e
    stack_count=$(aws --region "${REGION}" cloudformation describe-stacks --stack-name "${stack_name}" --query 'Stacks[*].StackName' --output text 2>/dev/null | wc -l)
    set -e
    cf_action="create"

    if [ "${stack_count}" -eq "0" ]; then
      log "Creating stack ${stack_name}"
      cf_action="create"
    else
      log "Updating stack ${stack_name}"
      cf_action="update"
    fi

    cf_execute "${cf_action}" "${stack_name}" "${template}"
  done
}

get_stack_name() {
  local template="$1"
  local stack_name
  stack_name="${PROJECT_CODE}-${STAGE}-$(get_file_name "${template}")"
  echo "${stack_name}"
}

get_file_name() {
  local template="$1"
  local file_name
  file_name=${template##*/}
  file_name=${file_name%.*}
  echo "${file_name}"
}

cf_waiter() {
  local action=$1
  local stack_name=$2
  log "Waiting for stack ${stack_name}"
  if ! aws --region "${REGION}" cloudformation wait stack-"${action}"-complete --stack-name "${stack_name}"; then
    exit $?
  fi
}

cs_waiter() {
  local change_set_name=$1
  local stack_name=$2
  log "Waiting for change set ${change_set_name} on ${stack_name}"
  if ! aws --region "${REGION}" cloudformation wait change-set-create-complete --stack-name "${stack_name}" --change-set-name "${change_set_name}" 2>/dev/null; then
    log "$(aws --region "${REGION}" cloudformation describe-change-set --change-set-name "${change_set_name}" --stack-name "${stack_name}" --query 'StatusReason' --output text)"
    aws --region "${REGION}" cloudformation delete-change-set --stack-name "${stack_name}" --change-set-name "${change_set_name}"
    return 1
  else
    return 0
  fi
}

cs_details() {
  local change_set_name=$1
  local stack_name=$2

  log "Details for changeset ${change_set_name} on ${stack_name}"
  aws --region "${REGION}" cloudformation describe-change-set --change-set-name "${change_set_name}" --stack-name "${stack_name}" --query 'Changes[].{Type:Type,Action:ResourceChange.Action,LogicalId:ResourceChange.LogicalResourceId,PhysicalId:ResourceChange.PhysicalResourceId,Replacement:ResourceChange.Replacement,Scope:ResourceCHange.Scope[],Details:ResourceChange.Details[]}' --output table

  printf "%s\n" "Do you wish to install execute change-set?"

  timeout --foreground 60 bash -c '
    select sel in "yes" "no"
    do
      echo "$REPLY"
      break
    done' | while read -r answer; do
      echo ">>Got answer from user: $answer"
      case "$answer" in
        "yes") logger -s "Executing changeset ${change_set_name} on ${stack_name}"
               aws --region "${REGION}" cloudformation execute-change-set --change-set-name "${change_set_name}" --stack-name "${stack_name}"
               aws --region "${REGION}" cloudformation wait stack-update-complete --stack-name "${stack_name}"
               break;;

        "no" ) break;;
      esac
    done
}

cf_execute() {
  local action=$1
  local stack_name=$2
  local template=$3
  local create_section
  local parameters_file
  local parameters_file_full
  local out

  echo "action: ${action}"

  create_section="--template-body file://${PWD}/${template} --capabilities CAPABILITY_NAMED_IAM"
  [ -n "$EXECUTE_ROLE"  ] && local creation_section="${creation_section} --role-arn ${EXECUTE_ROLE}"

  parameters_file=$(get_file_name "${template}").json
  parameters_file_full="${PWD}/parameters/${STAGE}/${parameters_file}"

  if [ -f  "$parameters_file_full" ]; then
    # update timestamp in parameters file
    jq '(.[] | select(.ParameterKey == "timestamp") | .ParameterValue) = '\"$(date +%s)\" $parameters_file_full | sponge $parameters_file_full
    create_section="${create_section} --parameters file://${parameters_file_full}"
  fi

  if [ "${action}" == "delete" ]; then
    create_section=""
  fi

  echo "finally create section looks like:"
  echo "${create_section}"

  if [ "${CHANGE_SET}" == true ]; then
    local change_set_name="changeSet${DATE}"
    log "Creating change Set ${change_set_name}"
#    if out=$(aws --region "$REGION" cloudformation create-change-set --stack-name "${stack_name}" ${create_section} --change-set-name "${change_set_name}" --role-arn "${EXECUTION_ROLE}" 2>&1);then
    if out=$(aws --region "$REGION" cloudformation create-change-set --stack-name "${stack_name}" ${create_section} --change-set-name "${change_set_name}" 2>&1);then
      if cs_waiter "${change_set_name}" "${stack_name}"; then
        cs_details "${change_set_name}" "${stack_name}"
      fi
    else
      log "${out}"
      exit $?
    fi

  else
    echo "Calling: aws --region \"${REGION}\" cloudformation ${action}-stack --stack-name \"${stack_name}\" ${create_section}"
    if out=$(aws --region "${REGION}" cloudformation ${action}-stack --stack-name "${stack_name}" ${create_section} 2>&1); then
      cf_waiter "${action}" "${stack_name}"
    else
      if [[ "${out}" == "No updates are to be performed" ]]; then
        log "Stack ${stack_name} is up to date"
      else
        log "${out}"
        exit $?
      fi
    fi
  fi
}

delete_stack(){
  local templates=("$@")
  local idx

  if [ -z "${DELETE_COUNT}" ] || (( DELETE_COUNT > ${#templates[@]} )); then
    DELETE_COUNT=${#TEMPLATES[@]}
  fi

  for (( idx=${#templates[@]}-1 ; idx>=${#templates[@]}-${DELETE_COUNT}; idx-- )) ; do
    log "Processing template ${templates[idx]} ($idx)"
    stack_name=$(get_stack_name "${templates[idx]}")

    cf_execute "delete" "${stack_name}"
  done
}

# Parse parameters
while getopts "h:s:r:dc:p:t" opt; do
  case "$opt" in
  h)
      show_help
      ;;
  d) ACTION="delete"
    ;;
  p) PROJECT_CODE=$OPTARG
    ;;
  r) REGION=$OPTARG
    ;;
  s) STAGE=$OPTARG
    ;;
  t) CHANGE_SET=true
    ;;
  *) echo "ERROR: Unknown option $opt"
    show_help
    ;;
  esac
done

shift $((OPTIND-1))

[ "${1:-}" = "--" ] && shift


if [ -z "${REGION}" ]; then echo "aws-region is required"; show_help; fi
if [ -z "${PROJECT_CODE}" ]; then echo "PROJECT_CODE is required"; show_help; fi
if [ -z "${STAGE}" ]; then echo "Stage is required"; show_help; fi

# Display AWS account information
log "=== AWS Account Information ==="
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "Unable to retrieve")
AWS_USER_ARN=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null || echo "Unable to retrieve")
AWS_USER_ID=$(aws sts get-caller-identity --query UserId --output text 2>/dev/null || echo "Unable to retrieve")
log "Account ID: ${AWS_ACCOUNT_ID}"
log "User/Role ARN: ${AWS_USER_ARN}"
log "User ID: ${AWS_USER_ID}"
log "Region: ${REGION}"
log "Project: ${PROJECT_CODE}"
log "Stage: ${STAGE}"
log "==============================="
log ""

parse_config

if [ ${#TEMPLATES[@]} -eq 0 ] && [ ${#COMMON_TEMPLATES[@]} -eq 0 ]; then
    echo "Błąd: Nie znaleziono żadnych templates do przetworzenia dla stage '${STAGE}'"
    echo "Sprawdź plik deploy.ini i upewnij się, że sekcja [${STAGE}] lub [common] zawiera templates"
    exit 1
fi

if [ "$ACTION" == "delete" ]; then
  if [ -z "${DELETE_COUNT}" ]; then
    read -p "Removing ALL stacks. Are you sure? (y/n)" -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
  fi
  log "Deleting stacks in ${REGION}"
  delete_stack "${TEMPLATES[@]}"
else
  log "Create stacks in ${REGION}"
  if [ "${STAGE}" == "prod" ]; then
    log "As STAGE is prod, I'm analyzing also COMMON templates"
    echo "Liczba elementów w COMMON_TEMPLATES: ${#COMMON_TEMPLATES[@]}"
    temp_stage="${STAGE}"
    STAGE="all"
    create_update_stack "${COMMON_TEMPLATES[@]}"
    STAGE="${temp_stage}"
  fi
  echo "Liczba elementów w TEMPLATES: ${#TEMPLATES[@]}"
  create_update_stack "${TEMPLATES[@]}"
fi

exit 0
