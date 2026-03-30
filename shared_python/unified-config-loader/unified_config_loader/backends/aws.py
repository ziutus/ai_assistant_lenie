"""AWS SSM Parameter Store configuration backend."""

import logging
import os
import sys

from unified_config_loader.backends._bootstrap import BOOTSTRAP_VARS, get_secrets_env, get_project_code

logger = logging.getLogger(__name__)


class AWSSSMBackend:
    """Loads configuration from AWS SSM Parameter Store.

    Path: ``/{PROJECT_CODE}/{SECRETS_ENV}/<key>``.
    """

    def load(self) -> dict[str, str]:
        secrets_env = get_secrets_env()
        aws_region = os.environ.get("AWS_REGION", "eu-central-1")
        project_code = get_project_code()

        try:
            import boto3
        except ImportError:
            logger.error("boto3 package is required for aws backend: pip install boto3")
            sys.exit(1)

        prefix = f"/{project_code}/{secrets_env}/"
        logger.debug("AWS SSM: reading parameters (region: %s)", aws_region)

        try:
            session = boto3.Session(region_name=aws_region)
            ssm = session.client("ssm")

            params: dict[str, str] = {}
            paginator = ssm.get_paginator("get_parameters_by_path")
            for page in paginator.paginate(
                Path=prefix,
                Recursive=False,
                WithDecryption=True,
            ):
                for param in page["Parameters"]:
                    key = param["Name"][len(prefix):]
                    params[key] = param["Value"]

        except Exception as exc:
            logger.error("Failed to load config from AWS SSM: %s", exc)
            sys.exit(1)

        if not params:
            logger.warning("AWS SSM: no parameters found under the configured prefix")

        result = {k: os.environ[k] for k in BOOTSTRAP_VARS if k in os.environ}
        result.update(params)
        return result
