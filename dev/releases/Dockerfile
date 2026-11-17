# Development releases of Prusa Connect, served the way GitHub serves releases
# and signed with a development key made at the first start. See serve.py.
#
# The binary is the full build, with the web app, as a release ships it. It is
# built in the builder stage of Prusa Connect's own docker/mockup/Dockerfile,
# which has the web app built and the source in /app.
FROM builder AS full
RUN CGO_ENABLED=0 go build -tags full -o /prusa_connect_full ./cmd/prusa-connect

FROM python:3.13-slim
RUN pip install --no-cache-dir cryptography==46.0.5
COPY --from=full /prusa_connect_full /prusa_connect
COPY serve.py /releases/
VOLUME /data
HEALTHCHECK --interval=2s --start-period=30s CMD test -s /data/public.key
ENTRYPOINT ["python3", "/releases/serve.py"]
