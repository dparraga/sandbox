ARG PYTHON_IMAGE=python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY requirements-build.txt ./
RUN python -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
COPY requirements-runtime.txt ./
RUN python -m pip download --require-hashes --only-binary=:all: --no-deps --dest /wheels -r requirements-runtime.txt
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
RUN python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir /wheels .

FROM ${PYTHON_IMAGE} AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Users build this image locally; no native image or wheelhouse is published.
RUN apt-get update && apt-get install --no-install-recommends -y tesseract-ocr=5.3.0-2 \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir /opt/flex-photo-models && python -c "import hashlib,pathlib,urllib.request; p=pathlib.Path('/opt/flex-photo-models/eng.traineddata'); data=urllib.request.urlopen('https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/65727574dfcd264acbb0c3e07860e4e9e9b22185/eng.traineddata',timeout=60).read(4113089); assert len(data)==4113088 and hashlib.sha256(data).hexdigest()=='7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'; p.write_bytes(data)"
COPY --from=builder /wheels/ /wheels/
RUN python -m pip install --no-deps --no-index /wheels/*.whl \
    && rm -rf /wheels
WORKDIR /app
USER 10001:10001
ENTRYPOINT ["flex-photo"]
