"""
Google OAuth 2.0 authentication utilities for Google APIs.

This module provides reusable functions for authenticating with Google services
using OAuth 2.0 credentials. Supports token caching and automatic refresh.

Dependencies (install via requirements_all.txt):
    - google-api-python-client
    - google-auth-httplib2
    - google-auth-oauthlib
"""

import sys
from pathlib import Path
from typing import Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError as e:
    print(f"Error: Missing required Google API libraries: {e}")
    print("\nInstall dependencies:")
    print("  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    print("Or use requirements_all.txt:")
    print("  pip install -r requirements_all.txt")
    sys.exit(1)


def get_google_credentials(
    scopes: list[str],
    credentials_file: Path,
    token_file: Path,
    service_name: str = "Google API"
) -> Optional[Credentials]:
    """
    Authenticate and return Google OAuth credentials.

    On first run, opens browser for OAuth consent. Subsequent runs use cached token.
    Automatically refreshes expired tokens when possible.

    Args:
        scopes: List of OAuth scopes to request
        credentials_file: Path to credentials.json from Google Cloud Console
        token_file: Path where token.json will be cached
        service_name: Human-readable name of the service for error messages

    Returns:
        Google OAuth credentials object, or None if authentication fails

    Example:
        >>> scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
        >>> creds_file = Path("credentials.json")
        >>> token_file = Path("token.json")
        >>> creds = get_google_credentials(scopes, creds_file, token_file)
    """
    creds = None

    # Load existing token
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_file.exists():
                print(f"Error: Credentials file not found: {credentials_file}")
                print(f"\nTo set up {service_name}:")
                print("1. Go to https://console.cloud.google.com/")
                print("2. Create a project or select existing one")
                print("3. Enable the required Google API")
                print("4. Create OAuth 2.0 credentials (Desktop application)")
                print(f"5. Download and save as: {credentials_file}")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file), scopes
            )
            creds = flow.run_local_server(port=0)

        # Save token for future runs
        token_file.write_text(creds.to_json())
        print(f"Token saved to: {token_file}")

    return creds


def get_google_service(
    service_name: str,
    version: str,
    scopes: list[str],
    credentials_file: Path,
    token_file: Path,
    api_display_name: Optional[str] = None
):
    """
    Authenticate and build a Google API service.

    Convenience wrapper that combines credential fetching and service building.

    Args:
        service_name: Google API service name (e.g., "calendar", "drive")
        version: API version (e.g., "v3")
        scopes: List of OAuth scopes to request
        credentials_file: Path to credentials.json
        token_file: Path where token.json will be cached
        api_display_name: Human-readable API name for error messages (defaults to service_name)

    Returns:
        Google API service object, or exits on failure

    Example:
        >>> service = get_google_service(
        ...     "calendar", "v3",
        ...     ["https://www.googleapis.com/auth/calendar.readonly"],
        ...     Path("credentials.json"),
        ...     Path("token.json")
        ... )
    """
    display_name = api_display_name or f"{service_name.title()} API"
    creds = get_google_credentials(scopes, credentials_file, token_file, display_name)

    if not creds:
        sys.exit(1)

    return build(service_name, version, credentials=creds)
