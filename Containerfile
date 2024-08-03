FROM docker.io/library/python:3.12
ARG release
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.pip pip install -r requirements.txt
COPY . /app
ENV SENTRY_RELEASE=$release
CMD ["python", "-m", "bridge"]
