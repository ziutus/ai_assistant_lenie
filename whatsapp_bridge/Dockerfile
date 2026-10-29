# Build context is the repository root (infra/docker/nas-deploy.sh), like the other services.
FROM golang:1.26-alpine AS build
WORKDIR /src
COPY whatsapp_bridge/go.mod whatsapp_bridge/go.sum ./
RUN go mod download
COPY whatsapp_bridge/*.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/whatsapp_bridge .

FROM alpine:3.20
RUN adduser -D -u 10001 bridge && mkdir /data && chown bridge /data
COPY --from=build /out/whatsapp_bridge /usr/local/bin/whatsapp_bridge
USER bridge
VOLUME /data
EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD wget -qO- http://127.0.0.1:8095/healthz >/dev/null || exit 1
ENTRYPOINT ["/usr/local/bin/whatsapp_bridge"]
