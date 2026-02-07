# Working with the API

Example API requests for the Lenie backend.

> **Parent document:** [../CLAUDE.md](../CLAUDE.md) — full architecture reference.

## Adding a URL (POST /url_add)

```shell
curl -X POST https://pir31ejsf2.execute-api.us-east-1.amazonaws.com/v1/url_add \
     -H "Content-Type: application/json" \
     -H "x-api-key: XXXX" \
     -d '{
           "url": "https://tech.wp.pl/ukrainski-system-delta-zintegrowany-z-polskim-topazem-zadaje-rosjanom-wielkie-straty,7066814570990208a",
           "type": "webpage",
           "note": "Interesting integration with the Polish battlefield imaging system",
           "text": "HTML of the page from the given URL"
         }'
```

## Listing Documents (GET /website_list)

If port forwarding is enabled, you can use this to validate your API request:

```
curl -H "x-api-key: XXX" -X GET "http://localhost:5000/website_list?type=ALL&
document_state=ALL&search_in_document="
```
