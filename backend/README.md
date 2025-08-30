## Typical problems

### Co może być powodem odpowiedzi jeżeli w logach AWS API Gateway z lambdy widzę: Execution failed due to configuration error: Malformed Lambda proxy response?

Kiedy widzisz błąd "Execution failed due to configuration error: Malformed Lambda proxy response" w logach AWS API Gateway, najczęstszym powodem jest, że odpowiedź zwrócona przez funkcję Lambda nie jest prawidłowo sformatowana dla API Gateway.
API Gateway oczekuje, że odpowiedź Lambda będzie miała określony format, zgodny z modelem odpowiedzi AWS Lambda proxy. Główne pola, które powinny być zawarte w odpowiedzi, to:
statusCode: Kod statusu HTTP dla odpowiedzi - musi to być poprawny kod statusu HTTP jako liczba całkowita.
body: Ciało odpowiedzi; musi być zwrócone jako ciąg znaków. Jeśli zwracasz dane JSON, musisz je zamienić na ciąg znaków za pomocą metody JSON.stringify w JavaScript lub json.dumps w Pythonie.
headers: Nagłówki odpowiedzi - to musi być obiekt JSON z par klucz-wartość jako nagłówki HTTP.
Oto przykładowa prawidłowo sformatowana odpowiedź Lambda dla API Gateway w Pythonie:

``` python
{
    "statusCode": 200,
    "body": json.dumps({
        "message": "hello world",
    }),
    "headers": {
        "Content-Type": "application/json",
    }
}
```
