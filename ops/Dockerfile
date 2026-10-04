# Optional local research image. No broker, ports or credentials.
# Image download/build has not been run as part of repository setup.
FROM python:3.14-slim
WORKDIR /app
COPY quantlab ./quantlab
COPY examples ./examples
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["python3", "-m", "quantlab"]
CMD ["--help"]
