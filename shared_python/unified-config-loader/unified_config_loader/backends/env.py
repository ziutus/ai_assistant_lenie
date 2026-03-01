"""Environment / dotenv configuration backend."""

import logging
import os
from abc import ABC, abstractmethod

try:
    from dotenv import find_dotenv, load_dotenv
except ImportError:
    find_dotenv = None
    load_dotenv = None

logger = logging.getLogger(__name__)


class ConfigBackend(ABC):
    """Base class for configuration backends."""

    @abstractmethod
    def load(self) -> dict[str, str]:
        """Return a mapping of configuration key-value pairs."""


class EnvBackend(ConfigBackend):
    """Loads configuration from ``.env`` file + real environment variables.

    Uses ``find_dotenv(usecwd=True)`` to locate the ``.env`` file starting
    from the current working directory and searching upward.
    """

    def load(self) -> dict[str, str]:
        if load_dotenv is not None:
            env_path = find_dotenv(usecwd=True) if find_dotenv is not None else None
            if env_path:
                logger.debug("EnvBackend: loading .env from %s", env_path)
            else:
                logger.debug("EnvBackend: no .env file found (searched from cwd upward)")
            load_dotenv(dotenv_path=env_path or None)
        return dict(os.environ)
