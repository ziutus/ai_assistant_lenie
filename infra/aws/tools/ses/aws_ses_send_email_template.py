import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

# Konfiguracja
AWS_REGION = "us-east-1"  # Region SES
SENDER = "notify-no-response@ses.dev.lenie-ai.eu"  # Adres e-mail nadawcy (musi być zweryfikowany w AWS SES, chyba że SES działa w trybie produkcyjnym)
RECIPIENT = "krzysztof@lenie-ai.eu"  # Adres e-mail odbiorcy
TEMPLATE_NAME = "MyTemplate"  # Nazwa szablonu zdefiniowanego w AWS SES

template_data = """
{
    "name": "Krzysztof",
    "code": "123456"
}
"""

def send_email_with_template():
    try:
        # Utwórz klienta SES
        client = boto3.client('ses', region_name=AWS_REGION)

        # Skonfiguruj parametry wiadomości oparte o szablon
        response = client.send_templated_email(
            Source=SENDER,
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Template=TEMPLATE_NAME,
            TemplateData=template_data
        )

        # Wyświetl ID wiadomości
        print(f"E-mail wysłany! Message ID: {response['MessageId']}")

    except NoCredentialsError:
        print("Błąd: Nie znaleziono danych uwierzytelniających AWS.")
    except PartialCredentialsError:
        print("Błąd: Niekompletne dane uwierzytelniające AWS.")
    except Exception as e:
        print(f"Wystąpił błąd: {str(e)}")


if __name__ == "__main__":
    send_email_with_template()