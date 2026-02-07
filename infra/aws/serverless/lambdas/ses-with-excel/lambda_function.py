import os
import json
import boto3
import openpyxl
from io import BytesIO

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes

from library.aws_s3 import save_to_s3

S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

ses_client = boto3.client('ses', region_name='us-east-1')  # Region SES
s3_client = boto3.client('s3', region_name='us-east-1')  # Region S3


# Funkcja do pobrania pliku z S3
def pobierz_plik_z_s3(bucket_name, object_key, lokalna_sciezka):
    try:
        s3_client.download_file(bucket_name, object_key, lokalna_sciezka)
        print(f"Pobrano plik z S3: {object_key}")
        return lokalna_sciezka
    except Exception as e:
        print(f"Błąd podczas pobierania pliku z S3: {str(e)}")
        raise


def wyslij_email_html_z_zalacznikiem_z_s3(
        nadawca: str,
        odbiorca: str,
        temat: str,
        tresc_html: str,
        s3_bucket: str,
        s3_object_key: str
):
    # Pobierz plik z S3
    lokalna_sciezka_pliku = f"/tmp/{s3_object_key.split('/')[-1]}"  # Tymczasowa ścieżka
    pobierz_plik_z_s3(s3_bucket, s3_object_key, lokalna_sciezka_pliku)

    # Utwórz wiadomość MIME
    msg = MIMEMultipart()
    msg['From'] = nadawca
    msg['To'] = odbiorca
    msg['Subject'] = temat

    # Treść HTML wiadomości
    msg.attach(MIMEText(tresc_html, 'html'))

    # Dodanie załącznika
    typ_mime, _ = mimetypes.guess_type(lokalna_sciezka_pliku)
    typ_mime = typ_mime or 'application/octet-stream'
    typ, podtyp = typ_mime.split('/', 1)

    with open(lokalna_sciezka_pliku, 'rb') as zalacznik:
        mime_base = MIMEBase(typ, podtyp)
        mime_base.set_payload(zalacznik.read())
        encoders.encode_base64(mime_base)

        # Dodanie nagłówków załącznika (nazwa pliku)
        mime_base.add_header(
            'Content-Disposition',
            f'attachment; filename="{s3_object_key.split("/")[-1]}"'
        )
        msg.attach(mime_base)

    # Wysłanie wiadomości przez SES
    try:
        odpowiedz = ses_client.send_raw_email(
            Source=nadawca,
            Destinations=[odbiorca],
            RawMessage={
                'Data': msg.as_string()
            }
        )
        print(f"E-mail wysłany poprawnie! ID wiadomości SES: {odpowiedz['MessageId']}")
    except Exception as e:
        print(f"Wystąpił błąd podczas wysyłania e-maila: {str(e)}")


def lambda_handler(event, context):

    text = "Hello from Lambda!"
    save_to_s3(text, "hello.txt", S3_BUCKET_NAME)

    # Stwórz nowy plik Excela
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "TestSheet"
    sheet["A1"] = "Hello, AWS Lambda with openpyxl!"

    # Zapisz plik tymczasowo
    # temp_file = "/tmp/example.xlsx"
    # workbook.save(temp_file)

    # Zapisz plik do obiektu BytesIO (w pamięci zamiast na dysku)
    excel_data = BytesIO()
    workbook.save(excel_data)
    excel_data.seek(0)  # Ustaw pointer na początek pliku

    # Wyślij plik do S3
    s3_key = "example.xlsx"  # Klucz w bucket S3, folder/example_name

    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=excel_data,
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"We have problem {str(e)}")

    # Przykład użycia funkcji
    nadawca = "krzysztof@itsnap.eu"
    odbiorca = "krzysztof@itsnap.eu"
    temat = "Raport miesięczny - testowy 07/01/2025"
    tresc_html = """
    <html>
        <body>
            <h1>Raport miesięczny</h1>
            <p>Proszę znaleźć raport w załączniku.</p>
        </body>
    </html>
    """

    s3_object_key = "example.xlsx"  # Klucz pliku w S3

    # Wywołanie funkcji
    wyslij_email_html_z_zalacznikiem_z_s3(nadawca, odbiorca, temat, tresc_html, S3_BUCKET_NAME, s3_object_key)

    return {
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True,
            'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
        },
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
