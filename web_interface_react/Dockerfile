FROM node:24.0 AS build-stage
LABEL authors="ziutus"

# Ustawiamy katalog roboczy w kontenerze
WORKDIR /app

# Kopiujemy package.json oraz yarn.lock do katalogu roboczego kontenera
COPY package*.json  ./

# Instalujemy zależności
RUN yarn install

# Kopiujemy resztę kodu aplikacji do katalogu roboczego kontenera
COPY . .

FROM node:24.0-slim
WORKDIR /app
COPY --from=build-stage /app .

# Create a non-root user with specific UID and GID, and change ownership of the app directory
RUN groupadd -g 1001 lenie-ai-group && \
    useradd -u 1001 -g lenie-ai-group -m lenie-ai-client && \
    chown -R 1001:1001 /app

# Switch to the lenie-ai-client user
USER 1001

# Otwieramy port 3000
EXPOSE 3000

ENV NODE_ENV=production
# Uruchamiamy aplikację
CMD ["yarn", "start"]
