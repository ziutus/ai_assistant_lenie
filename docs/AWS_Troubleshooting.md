# AWS Troubleshooting

Common issues encountered when working with AWS services in this project.

## API Gateway + Lambda

### Malformed Lambda proxy response

**Error in API Gateway logs:**
```
Execution failed due to configuration error: Malformed Lambda proxy response
```

**Cause:** The response returned by the Lambda function is not properly formatted for API Gateway. API Gateway expects the Lambda response to follow the AWS Lambda proxy response model.

**Required fields:**
- `statusCode` — HTTP status code as an integer
- `body` — Response body as a **string** (use `json.dumps()` for JSON data)
- `headers` — JSON object with key-value pairs as HTTP headers

**Correct response example (Python):**

```python
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

> **Tip:** The most common mistake is returning `body` as a dict/object instead of a string. Always use `json.dumps()` in Python or `JSON.stringify()` in JavaScript.
