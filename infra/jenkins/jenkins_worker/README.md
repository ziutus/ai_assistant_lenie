# Jenkins support for Lenie-AI

Jenkins is an open-source automation server designed to streamline software development processes. It enables continuous integration and continuous delivery (CI/CD) to efficiently build, test, and deploy code, ensuring faster and more reliable software delivery.
By incorporating Jenkins into the Lenie-AI project, we automate essential development workflows, such as code testing, building, and deployment pipelines. This improves development speed, reduces the chance of human error, and ensures our project adheres to a professional CI/CD pipeline, fostering team collaboration and high software quality.

## Github webooks

### testing

```bash
curl -X POST   -H "Content-Type: application/json"   -d '{"key1":"value1", "key2":"value2"}'   https://1bkc3kz7c9.execute-api.us-east-1.amazonaws.com/v1/infra/git-webhooks
```

## Jenkins installation

## Pluggins

## Jenkins updates

### update SSL certificate

```bash
letsencrypt renew
```

```bash
openssl pkcs12 -export   -in /etc/letsencrypt/live/jenkins.lenie-ai.eu/fullchain.pem   -inkey /etc/letsencrypt/live/jenkins.lenie-ai.eu/privkey.pem   -out jenkins.p12   -name jenkins   -CAfile /etc/letsencrypt/live/jenkins.lenie-ai.eu/chain.pem   -caname root
```

```bash
 keytool -importkeystore   -deststorepass <twoje_haslo>   -destkeypass <twoje_haslo>   -destkeystore /var/lib/jenkins/jenkins.jks   -srckeystore jenkins.p12   -srcstoretype PKCS12   -srcstorepass <twoje_hasło_z_p12>   -alias jenkins
```