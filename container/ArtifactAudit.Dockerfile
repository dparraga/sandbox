# Candidate evaluation only. This image is not published or adopted by the application.
FROM python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 OMP_THREAD_LIMIT=1
RUN apt-get update && apt-get install --no-install-recommends -y tesseract-ocr=5.3.0-2 \
    && dpkg-query -W > /native-packages.txt && cat /native-packages.txt \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/check_interpretation_assets.py /checks/check_interpretation_assets.py
COPY tests/assets/interpretation-candidates.json /tests/assets/interpretation-candidates.json
COPY tests/assets/synthetic-white.heic /tests/assets/synthetic-white.heic
RUN python /checks/check_interpretation_assets.py --provision /audit
USER 10001:10001
WORKDIR /tmp
ENTRYPOINT ["python", "/checks/check_interpretation_assets.py", "--probe", "/audit", "--tesseract", "/usr/bin/tesseract", "--output", "/tmp/probe.json"]
