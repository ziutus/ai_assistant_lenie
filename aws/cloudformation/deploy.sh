#! /bin/bash

command -v aws --version > /dev/null 2>&1 || { echo >&2 "aws cli not installed. Aborting..."; exit 1; }



exit 0