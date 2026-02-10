import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import mimetypes

ses_client = boto3.client('ses', region_name='us-east-1')
s3_client = boto3.client('s3', region_name='us-east-1')

def lambda_handler(event, context):
    try:
        nadawca = event['nadawca']
        odbiorca = event['odbiorca']
        temat = event['temat']
        tresc_html = event['tresc_html']
        s3_bucket = event['s3_bucket']
        s3_object_key = event['s3_object_key']

        lokalna_sciezka_pliku = f"/tmp/{s3_object_key.split('/')[-1]}"
        s3_client.download_file(s3_bucket, s3_object_key, lokalna_sciezka_pliku)

        msg = MIMEMultipart()
        msg['From'] = nadawca
        msg['To'] = odbiorca
        msg['Subject'] = temat
        msg.attach(MIMEText(tresc_html, 'html'))

        typ_mime, _ = mimetypes.guess_type(lokalna_sciezka_pliku)
        typ_mime = typ_mime or 'application/octet-stream'
        typ, podtyp = typ_mime.split('/', 1)

        with open(lokalna_sciezka_pliku, 'rb') as zalacznik:
            mime_base = MIMEBase(typ, podtyp)
            mime_base.set_payload(zalacznik.read())
            encoders.encode_base64(mime_base)
            mime_base.add_header('Content-Disposition', f'attachment; filename="{s3_object_key.split("/")[-1]}"')
            msg.attach(mime_base)

        odpowiedz = ses_client.send_raw_email(
            Source=nadawca,
            Destinations=[odbiorca],
            RawMessage={'Data': msg.as_string()}
        )

        return {
            'statusCode': 200,
            'body': f"E-mail wysłany poprawnie! ID wiadomości SES: {odpowiedz['MessageId']}"
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f"Błąd: {str(e)}"
        }
