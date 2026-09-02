FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY alter_model_runtime ./alter_model_runtime
RUN pip install --no-cache-dir .

RUN addgroup --system alter && adduser --system --ingroup alter alter
USER alter

EXPOSE 8422
CMD ["uvicorn", "alter_model_runtime.app:app", "--host", "0.0.0.0", "--port", "8422"]
