FROM node:24 AS build-stage
LABEL authors="ziutus"

WORKDIR /app

COPY web_interface_app2/package*.json ./
RUN npm ci

COPY shared/ ../shared/
COPY web_interface_app2/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build-stage /app/build /usr/share/nginx/html
COPY --from=build-stage /app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
