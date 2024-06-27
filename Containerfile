FROM docker.io/library/python:3.12
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.pip pip install -r requirements.txt
COPY . /app
CMD ["python", "-m", "bridge"]
