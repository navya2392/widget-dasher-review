# Cloud Run / any container host. Build: gcloud run deploy widget-dasher-review --source . --region us-central1 \
#   --allow-unauthenticated --set-env-vars ANTHROPIC_API_KEY=...   (or set the secret in the Cloud Run console)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py pipeline.py ai.py ./
COPY prompts/ prompts/
COPY data/ data/
COPY demo/ demo/
ENV PORT=8080
EXPOSE 8080
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
