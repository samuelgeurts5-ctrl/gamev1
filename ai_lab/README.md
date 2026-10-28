# Mindgarden AI

A browser dashboard for a personal Llama assistant, with persistent chat history, editable knowledge/memory, configurable model settings, and web search.

## Features

- **Llama via Ollama API:** select the installed model and configure the Ollama endpoint in Settings.
- **Persistent memory:** add, review, categorize, and delete notes in the Memory & Teaching dashboard.
- **Persistent chat history:** conversation turns are stored in SQLite.
- **Web search:** uses Google Programmable Search when both `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` are configured. Otherwise, it uses a clearly labeled DuckDuckGo instant-answer fallback.
- **Custom instructions:** set a system prompt from the visual dashboard.
- **Single-user prototype:** designed for a trusted local environment / private Codespace, not for public deployment.

## Run it in GitHub Codespaces

Open the Codespace for this repository, then open a terminal and run:

```bash
cd ai_lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open the **Ports** tab, forward port **8000**, and open its browser link.

The Python backend and the Ollama model endpoint must both be reachable from the Codespace. For the default setting, Ollama is expected at `http://127.0.0.1:11434` inside the same environment. Install and start Ollama in the Codespace (or point the dashboard to a reachable Ollama-compatible service), and download a model there. The selected model name must match the installed model.

## Google search setup

The app uses the official Google Custom Search JSON API when both environment variables are configured:

- `GOOGLE_API_KEY`
- `GOOGLE_CSE_ID`

Set them as environment variables in the backend terminal before launching the app. Do not commit API keys into this repository. If either is missing, the app uses its DuckDuckGo fallback and labels it honestly.

## Memory vs. training

The visual knowledge vault is persistent retrieval-style memory: saved notes are added to the model's context when it responds. This does **not** update Llama's neural-network weights. Fine-tuning (such as LoRA) is a separate training workflow and can be added as a later milestone.

## Important safety / deployment notes

- Do not commit API keys or other secrets.
- Do not expose this app to the public internet as-is. It currently has no login, access control, CSRF protection, or per-user data separation.
- Use only a trusted private Codespace or local machine until authentication and security controls are implemented.
- Search results are untrusted source material; verify claims and sources independently.
