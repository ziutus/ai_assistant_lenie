import hvac
from dotenv import load_dotenv
import os
from pprint import pprint
import requests
import os
from urllib.parse import urlparse


def sprawdz_dostepnosc_vault(url, timeout=2):
    """
    Sprawdza, czy serwer Vault jest dostępny.

    Args:
        url (str): URL serwera Vault
        timeout (int): Timeout w sekundach

    Returns:
        bool: True jeśli serwer odpowiada, False w przeciwnym przypadku
        int: Kod odpowiedzi HTTP lub None w przypadku błędu
    """
    try:
        # Zapytanie do endpointu /v1/sys/health, który jest publicznie dostępny
        health_url = f"{url}/v1/sys/health"
        response = requests.get(health_url, timeout=timeout)
        return True, response.status_code
    except requests.exceptions.ConnectionError:
        return False, None
    except requests.exceptions.Timeout:
        return False, None
    except Exception as e:
        print(f"Błąd podczas sprawdzania dostępności serwera: {e}")
        return False, None

load_dotenv()

def get_vault_client(vault_url, token=None, role_id=None, secret_id=None):
    """
    Utworzenie klienta Vault z elastyczną metodą autoryzacji.
    """
    client = hvac.Client(url=vault_url)

    # Autoryzacja przy użyciu tokenu
    if token:
        client.token = token
    # Autoryzacja przy użyciu AppRole
    elif role_id and secret_id:
        client.auth.approle.login(role_id=role_id, secret_id=secret_id)

    return client


def get_secret(client, path, key=None):
    """
    Pobranie sekretów z określonej ścieżki w Vault.
    """
    try:
        secret_response = client.secrets.kv.v2.read_secret_version(path=path, mount_point="kv", raise_on_deleted_version=True)
        data = secret_response['data']['data']

        if key:
            return data.get(key)
        return data
    except Exception as e:
        print(f"Błąd podczas pobierania sekretu: {e}")
        return None

def list_secrets(client, path, mount_point="kv"):
    """
    Listowanie wszystkich sekretów w określonej ścieżce Vault.
    """
    try:
        # Metoda list_secrets zwraca listę kluczy w podanej ścieżce
        list_response = client.secrets.kv.v2.list_secrets(path=path, mount_point=mount_point)
        return list_response['data']['keys']
    except Exception as e:
        print(f"Błąd podczas listowania sekretów: {e}")
        return []

vault_client = get_vault_client(os.getenv("VAULT_URL"), token=os.getenv("VAULT_TOKEN"))
CLOUDFERRO_SHERLOCK_KEY=get_secret(vault_client, "lenie-ai/dev/cloudferro", "SHERLOCK_KEY")
print(CLOUDFERRO_SHERLOCK_KEY)

pprint(list_secrets(vault_client, "lenie-ai/dev"))

vault_client.secrets.kv.v2.update_metadata(
    path="lenie-ai/dev/aws",
    mount_point="kv",
    max_versions=5
)

health_status = vault_client.sys.read_health_status()

print(health_status)

status = vault_client.sys.read_health_status(method='GET')
print('Vault initialization status is: %s' % status['initialized'])

vault_url = os.getenv("VAULT_URL", "http://127.0.0.1:8200")

dostepny, kod = sprawdz_dostepnosc_vault(vault_url)
if dostepny:
    print(f"Serwer Vault jest dostępny, kod odpowiedzi: {kod}")
    # Tutaj możesz kontynuować z weryfikacją tokenu
else:
    print("Serwer Vault jest niedostępny")

# client = hvac.Client(url='https://127.0.0.1:8200')
# status2 = client.sys.read_health_status(method='GET')
# print('Vault initialization status is: %s' % status2['initialized'])
