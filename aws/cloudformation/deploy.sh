#! /bin/bash
set -x

REGION="us-east-1"
STAGE=""
PWD=$(pwd)
PREFIX="lenie"
EXECUTE_ROLE=""

TEMPLATES=()
COMMON_TEMPLATES=()

command -v aws > /dev/null 2>&1 || { echo >&2 "aws cli not installed. Aborting..."; exit 1; }
command -v jq  > /dev/null 2>&1 || { echo >&2 "jq not installed. Aborting..."; exit 1; }
command -v sponge > /dev/null 2>&1 || { echo >&2 "sponge not installed. Aborting..."; exit 1; }

show_help() {
   echo "Usage:
   $0 -r <aws_region>  [-h]

   -r aws-region - A AWS Region where stack should be created/updated/deleted (default: $REGION)
   -s stage - Deployment stage (one of prod,cob,qa,dev,test,feature,staging) (default: $STAGE)
   -d - change default action from Create/Update to Delete
   -t  - create change-sets instead of apply changes


   -h show this message

  Example usage:
   $0 -r us-east-1

   "
   exit 1
}

parse_config() {
  section_name_pattern="^\[\w*\]$"
  value_pattern="^\w.*"

  while IFS=$'\r\n' read val
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
  templates=("$@")
  for template in "${templates[@]}"
  do
    echo "Processing template ${template}"
#    logger -s "Processing template ${template}"
    stack_name=$(get_stack_name "$template")

  done
}

get_stack_name() {
  template="$1"
  stack_name="${PREFIX}-${STAGE}-$(get_file_name "${template}")"
  echo "${stack_name}"
}

get_file_name() {
  template="$1"
  file_name=${template##*/}
  file_name=${file_name%.*}
  echo "${file_name}"
}

cf_execute() {
  action=$1
  stack_name=$2
  template=$3

  create_section="--template-body file://${PWD}/${template} --capabilities CAPABILITY_NAMED_AIM --role-arn ${EXECUTE_ROLE}"

  parameters_file=$(get_file_name "${template}").json
  parameters_file_full="${PWD}/parameters/${STAGE}/${parameters_file}"

  if [ -f  $parameters_file_full ]; then
    # update timestamp in parameters file
    jq '(.[] | select(.ParameterKey == "timestamp") | .ParameterValue) = '\"$(date +%s)\" $parameters_file_full | sponge $parameters_file_full
    create_section="${create_section} --parameters file://${parameters_file}"
  fi

  if [ "${action}" == "delete" ]; then
    create_section=""
  fi

  echo "finally create section looks like:"
  echo "${create_section}"

  if [ "${CHANGE_SET}" == true ]; then
    change_set_name="changeSet${DATE}"
    logger -s "Creating change Set ${change_set_name}"
    if out=$(aws --region "$REGION" cloudformation create-change-set --stack-name "${stack_name}" ${create_section} --change-set-name "${change_set_name}" --role-arn "${EXECUTION_ROLE}" 2>&1);then
      if cs_waiter "${change_set_name}" "${stack_name}"; then
        cs_details "${change_set_name}" "${stack_name}"
      fi
    else
      logger -s "${out}"
      exit $?
    fi

  # TODO: 150 linia oryginalnie
  else
    if out$(aws --region "${REGION}")

  fi
}


# Parse parameters
while getopts "h:s:r:" opt; do
  case "$opt" in
  h)
      show_help
      ;;
  r) REGION=$OPTARG
    ;;
  s) STAGE=$OPTARG
    ;;
  *) echo "ERROR: Unknown option $opt"
    show_help
    ;;
  esac
done

shift $((OPTIND-1))

[ "${1:-}" = "--" ] && shift


if [ -z "${REGION}" ]; then echo "aws-region is required"; show_help; fi
#if [ -z "${PREFIX}" ]; then echo "prefix is required"; show_help; fi
if [ -z "${STAGE}" ]; then echo "Stage is required"; show_help; fi

parse_config

#logger -s "Create stacks in ${REGION}"
create_update_stack "${TEMPLATES[@]}"

exit 0