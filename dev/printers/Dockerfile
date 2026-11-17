# Simulated printers that dial a running Prusa Connect: tools/printersim, built
# in the builder stage of Prusa Connect's own docker/mockup/Dockerfile.
FROM builder AS build
RUN CGO_ENABLED=0 go build -o /printersim ./tools/printersim

FROM debian:trixie-slim
COPY --from=build /printersim /printersim
ENTRYPOINT ["/printersim"]
