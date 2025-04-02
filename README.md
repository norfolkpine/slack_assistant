# 🤖 Slack Agent on Google Cloud Run

This project deploys a Python-based Slack Agent using the [Agno (Phidata)](https://docs.phidata.com/) framework. The agent is integrated with Slack via the **Events API (webhooks)** and securely deployed to **Google Cloud Run** with secrets managed via **Google Secret Manager**.

---

## 📦 Features

- Slack bot via Event Subscriptions (no Socket Mode)
- FastAPI-based webhook for Slack events
- Secure secret management via GCP Secret Manager
- Deployed with Docker to Google Cloud Run
- Uses Poetry for dependency management

---

## 🚀 Setup Guide

### ✅ Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/)
- [Google Cloud CLI](https://cloud.google.com/sdk/)
- [Docker](https://www.docker.com/)
- [Ngrok](https://ngrok.com/) (for local Slack testing)
- A Slack App with:
  - Bot Token (`xoxb-...`)
  - App Token (`xapp-...`, optional for other features)
  - Signing Secret
  - Event Subscriptions enabled

---

## 🧱 1. Local Development

If you don’t have a `pyproject.toml` file yet:

```bash
poetry init
```

Press Enter through the prompts, or manually enter dependencies later.

### Clone and Setup

```bash
git clone https://github.com/your-org/slack-agent.git
cd slack-agent
poetry install
poetry shell
```

### Local `.env`

For development, use a local `.env` file in the root directory:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
OPENAI_API_KEY=sk-...

JIRA_SERVER_URL=
JIRA_USERNAME=
JIRA_PASSWORD=
JIRA_TOKEN=
```

> This `.env` will not be included in production builds.

---

## 🔐 2. Google Secret Manager Integration

### Store `.env` as a Secret

```bash
gcloud secrets create SLACK_AGENT_ENV --data-file=.env
```

To update:

```bash
gcloud secrets versions add SLACK_AGENT_ENV --data-file=.env
```

### Load Secret in Code

Install dependencies:

```bash
poetry add python-dotenv google-cloud-secret-manager
```

Then in your code:

```python
from utils.load_env import load_env_from_secret

load_env_from_secret(secret_id="SLACK_AGENT_ENV", project_id="your-gcp-project-id")
```

---

## 📦 3. Add Core Dependencies

```bash
poetry add fastapi uvicorn slack-sdk agno python-dotenv google-cloud-secret-manager
```

---

## 🐳 4. Dockerfile

```Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"

RUN apt-get update && apt-get install -y curl build-essential && apt-get clean

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root --only main

COPY . .

EXPOSE 8080

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## ☁️ 5. Deploy to Cloud Run

### Build and Push

```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/slack-agent
```

### Deploy

```bash
gcloud run deploy slack-agent \
  --image gcr.io/YOUR_PROJECT_ID/slack-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=your-gcp-project-id
```

> Your app reads this env var to load secrets from GCP.

---

## 🔑 6. IAM Setup

Give Cloud Run permission to access your secrets:

```bash
gcloud run services add-iam-policy-binding slack-agent \
  --member="serviceAccount:YOUR_CLOUD_RUN_SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 🔗 7. Connect to Slack

In your Slack App settings:

- **Event Subscriptions**: Enable
- **Request URL**:  
  `https://<your-cloud-run-url>/slack/events`
- **Subscribe to bot events**:
  - `app_mention`
  - `message.im` (DMs)
- **OAuth & Scopes**:
  - `chat:write`
  - `app_mentions:read`
  - `im:history`

Then install the app to your workspace.

---

## ✅ Done!

Your Slack Agent is now:
- Deployed on Google Cloud Run
- Authenticated with Slack
- Receiving events via webhook
- Using secure secrets via Secret Manager
- Powered by OpenAI via Agno

---

## 🛠️ Local Testing (Optional)

```bash
ngrok http 8080
```

Set the Slack request URL to the HTTPS forwarding address from Ngrok.

---

## 🤝 Contributing

PRs welcome! Make sure to:
- Use Poetry for dependencies
- Keep `.env` out of version control
- Follow clean code and deployment practices

---

## 🧠 License

MIT or your custom license.

# Docker
docker build -t gcr.io/bh-crypto/my-slack-bot:latest .
