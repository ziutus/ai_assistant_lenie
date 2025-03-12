import boto3
import time
import os
from dotenv import load_dotenv

# Ładowanie zmiennych z pliku .env
load_dotenv()

# Konfiguracja z pliku .env
HOSTED_ZONE_ID = os.getenv("AWS_HOSTED_ZONE_ID")
DOMAIN_NAME = os.getenv("OPENVPN_DOMAIN_NAME")
INSTANCE_ID = os.getenv("OPENVPN_AWS_INSTANCE_ID")


def start_ec2_instance(instance_id):
    """Uruchamia instancję EC2"""
    ec2 = boto3.client("ec2")
    print(f"Uruchamiam instancję EC2 o ID: {instance_id}")
    ec2.start_instances(InstanceIds=[instance_id])

    # Czekamy, aż instancja zostanie uruchomiona
    print("Czekam na uruchomienie instancji...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("Instancja EC2 została uruchomiona!")


def get_instance_public_ip(instance_id):
    """Pobiera publiczny adres IP instancji EC2"""
    ec2 = boto3.client("ec2")
    print(f"Pobieram informacje o instancji o ID: {instance_id}")
    response = ec2.describe_instances(InstanceIds=[instance_id])

    # Pobieranie publicznego adresu IP
    public_ip = response["Reservations"][0]["Instances"][0].get("PublicIpAddress")
    if not public_ip:
        print("Publiczny adres IP nie jest jeszcze dostępny. Czekam chwilę...")
        time.sleep(10)  # Czekamy na przydzielenie publicznego adresu IP
        return get_instance_public_ip(instance_id)

    print(f"Publiczny adres IP instancji: {public_ip}")
    return public_ip


def update_route53_record(hosted_zone_id, domain_name, public_ip):
    """Aktualizuje rekord A w Route 53"""
    route53 = boto3.client("route53")
    print(f"Aktualizuję rekord A w Route 53 dla domeny: {domain_name}")

    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain_name,
                        "Type": "A",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": public_ip}],
                    },
                }
            ]
        },
    )

    print("Rekord A zaktualizowany!")
    print(f"Zwrócony status: {response['ChangeInfo']['Status']}")


if __name__ == "__main__":
    # Upewnienie się, że wymagane zmienne środowiskowe są załadowane
    if not all([INSTANCE_ID, HOSTED_ZONE_ID, DOMAIN_NAME]):
        raise ValueError(
            "Proszę upewnij się, że zmienne INSTANCE_ID, HOSTED_ZONE_ID i DOMAIN_NAME są ustawione w pliku .env")

    # Krok 1: Uruchomienie instancji EC2
    start_ec2_instance(INSTANCE_ID)

    # Krok 2: Pobranie publicznego adresu IP
    public_ip = get_instance_public_ip(INSTANCE_ID)

    # Krok 3: Aktualizacja rekordu Route 53
    update_route53_record(HOSTED_ZONE_ID, DOMAIN_NAME, public_ip)
