import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError

# Konfiguracja
AWS_REGION = "us-east-1"  # Podaj swoją docelową strefę Region AWS SES
SENDER = "notify-no-response@ses.dev.lenie-ai.eu"  # Adres e-mail nadawcy (musi być zweryfikowany w AWS SES, chyba że SES działa w trybie produkcyjnym)
RECIPIENT = "krzysztof@lenie-ai.eu"  # Adres e-mail odbiorcy
SUBJECT = "SES własna konfiguracja"
BODY_TEXT = "To jest testowy e-mail wysłany przy użyciu usługi AWS SES w Pythonie."
BODY_HTML = """<html>
<head></head>
<body>
  <h1>Testowy e-mail</h1>
  <p>To jest <b>testowy</b> e-mail wysłany przy pomocy <a href='https://aws.amazon.com/ses/'>AWS SES</a>.</p>
</body>
</html>
"""
CHARSET = "UTF-8"  # Kodowanie wiadomości


def send_email():
    try:
        # Utwórz klienta SES
        client = boto3.client('ses', region_name=AWS_REGION)

        # Skonfiguruj parametry wiadomości
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': CHARSET,
                        'Data': BODY_HTML,
                    },
                    'Text': {
                        'Charset': CHARSET,
                        'Data': BODY_TEXT,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
            ConfigurationSetName="lenie-ai-dev"
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
    send_email()