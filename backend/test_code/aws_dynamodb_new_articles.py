import boto3
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('lenie_dev_documents')

# Wszystkie artykuły z dzisiaj
today = datetime.now().strftime('%Y-%m-%d')
response = table.query(
    IndexName='DateIndex',
    KeyConditionExpression=Key('created_date').eq(today)
)
print(f"Dzisiaj: {len(response['Items'])} artykułów")

# Artykuły z ostatnich 7 dni (wymaga sprawdzenia każdego dnia)
dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
all_items = []
for date in dates:
    response = table.query(
        IndexName='DateIndex',
        KeyConditionExpression=Key('created_date').eq(date)
    )
    all_items.extend(response['Items'])

print(f"Ostatnie 7 dni: {len(all_items)} artykułów")

# Wszystkie artykuły chronologicznie (od najnowszych)
response = table.query(
    KeyConditionExpression=Key('pk').eq('DOCUMENT'),
    ScanIndexForward=False,  # Od najnowszych
    Limit=50  # Ostatnie 50
)
