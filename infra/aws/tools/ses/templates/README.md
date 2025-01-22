
```bash
aws ses create-template --cli-input-json file://default_email_tempate.json
```

```bash
aws ses get-template --template-name MyTemplate
```

``` 
{
    "Template": {
        "TemplateName": "MyTemplate",
        "SubjectPart": "Witamy, {{name}}!",
        "TextPart": "Cześć {{name}}, Twój kod aktywacyjny to {{code}}.",
        "HtmlPart": "<html><body><h1>Witaj {{name}}!</h1><p>Twój kod aktywacyjny to <b>{{code}}</b>.</p></body></html>"
    }
}
```