FROM node:24 AS build-stage
LABEL authors="ziutus"

WORKDIR /app

COPY web_interface_react/package*.json ./
# This project intentionally does not commit package-lock.json. `npm ci`
# requires one, while `npm install` resolves the declared package versions and
# lets the NAS image build from the tracked package.json alone.
RUN npm install

COPY shared/ ../shared/
COPY web_interface_react/ .
RUN npm run build

FROM nginx:stable-bookworm
COPY --from=build-stage /app/build /usr/share/nginx/html
COPY --from=build-stage /app/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
