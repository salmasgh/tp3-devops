FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
# Pas de -ldflags "-s -w" : Beyla a besoin de la table des symboles
# pour poser ses uprobes sur net/http.
RUN CGO_ENABLED=0 go build -o /pricing-engine .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /pricing-engine /pricing-engine
EXPOSE 8080
ENTRYPOINT ["/pricing-engine"]
