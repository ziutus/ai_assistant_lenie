# Pobierz najnowszy obraz Node.js
FROM node:latest AS build

# Ustaw katalog roboczy
WORKDIR /app

# Skopiuj pliki z pakietem
COPY package*.json ./

# Zainstaluj wszystkie zależności
RUN npm install

# Skopiuj resztę plików źródłowych
COPY . .

# Zbuduj aplikację
RUN npm run build

# Deploy
FROM nginx:alpine

# Skopiuj pliki statyczne do serwera Nginx
COPY --from=build /app/build /usr/share/nginx/html

# Expose port
EXPOSE 80

# Run
CMD ["nginx", "-g", "daemon off;"]