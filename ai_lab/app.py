import os
import sqlite3
import json
from datetime import datetime
from urllib.parse import quote_plus

import requests
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "assistant.db")
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

DEFAULT_MODEL = os.getenv("LLAMA_MODEL", "llama3.2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        defaults = {
            "model": DEFAULT_MODEL,
            "ollama_url": OLLAMA_URL,
            "system_prompt": "You are a helpful personal AI assistant. Use saved memories and supplied knowledge when relevant. Be honest about uncertainty."
        }
        for key, value in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))


def get_setting(key, fallback=""):
    with db() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else fallback


def set_setting(key, value):
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def all_memories(limit=80):
    with db() as con:
        rows = con.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def search_web(query):
    # Google Programmable Search JSON API if both credentials are configured.
    if GOOGLE_API_KEY and GOOGLE_CSE_ID:
        try:
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": 5},
                timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            return [
                {"title": item.get("title", "Untitled"), "url": item.get("link", ""), "snippet": item.get("snippet", "")}
                for item in data.get("items", [])
            ], "Google"
        except Exception as exc:
            return [], "Google search error: " + str(exc)
    # Useful no-key fallback; the UI clearly labels it as DuckDuckGo, not Google.
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            headers={"User-Agent": "PersonalAIAssistant/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        results = []
        if data.get("AbstractText"):
            results.append({"title": data.get("Heading") or query, "url": data.get("AbstractURL", ""), "snippet": data["AbstractText"]})
        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
                results.append({"title": topic["Text"].split(" - ")[0][:100], "url": topic["FirstURL"], "snippet": topic["Text"]})
            if len(results) >= 5:
                break
        return results, "DuckDuckGo fallback"
    except Exception as exc:
        return [], "Search unavailable: " + str(exc)


def ollama_chat(messages):
    base = get_setting("ollama_url", OLLAMA_URL).rstrip("/")
    model = get_setting("model", DEFAULT_MODEL)
    response = requests.post(
        base + "/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content", "The model returned no text.")


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    base = get_setting("ollama_url", OLLAMA_URL).rstrip("/")
    try:
        response = requests.get(base + "/api/tags", timeout=3)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        connected = True
    except Exception:
        models, connected = [], False
    return jsonify({
        "connected": connected,
        "model": get_setting("model", DEFAULT_MODEL),
        "ollama_url": base,
        "available_models": models,
        "google_configured": bool(GOOGLE_API_KEY and GOOGLE_CSE_ID),
        "search_provider": "Google" if GOOGLE_API_KEY and GOOGLE_CSE_ID else "DuckDuckGo fallback",
        "memory_count": count_rows("memories"),
        "chat_count": count_rows("chats"),
    })


def count_rows(table):
    with db() as con:
        return con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]


@app.get("/api/memories")
def memories():
    return jsonify(all_memories(200))


@app.post("/api/memories")
def add_memory():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    category = (data.get("category") or "General").strip()[:50]
    if not title or not content:
        return jsonify({"error": "A title and some information are required."}), 400
    with db() as con:
        cur = con.execute(
            "INSERT INTO memories(title,content,category,created_at) VALUES(?,?,?,?)",
            (title[:120], content[:8000], category, datetime.now().isoformat(timespec="seconds")),
        )
        memory_id = cur.lastrowid
    return jsonify({"id": memory_id, "ok": True})


@app.delete("/api/memories/<int:memory_id>")
def delete_memory(memory_id):
    with db() as con:
        con.execute("DELETE FROM memories WHERE id=?", (memory_id,))
    return jsonify({"ok": True})


@app.get("/api/settings")
def settings():
    return jsonify({
        "model": get_setting("model", DEFAULT_MODEL),
        "ollama_url": get_setting("ollama_url", OLLAMA_URL),
        "system_prompt": get_setting("system_prompt", ""),
    })


@app.post("/api/settings")
def save_settings():
    data = request.get_json(silent=True) or {}
    model = (data.get("model") or "").strip()
    url = (data.get("ollama_url") or "").strip().rstrip("/")
    prompt = (data.get("system_prompt") or "").strip()
    if not model or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Enter a model name and a valid http(s) Ollama URL."}), 400
    set_setting("model", model[:120])
    set_setting("ollama_url", url[:500])
    if prompt:
        set_setting("system_prompt", prompt[:5000])
    return jsonify({"ok": True})


@app.post("/api/search")
def web_search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "Enter a search query."}), 400
    results, provider = search_web(query[:300])
    return jsonify({"provider": provider, "results": results})


@app.get("/api/history")
def history():
    with db() as con:
        rows = con.execute("SELECT id,role,content,created_at FROM chats ORDER BY id DESC LIMIT 40").fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


@app.delete("/api/history")
def clear_history():
    with db() as con:
        con.execute("DELETE FROM chats")
    return jsonify({"ok": True})


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("message") or "").strip()
    use_search = bool(data.get("search"))
    if not prompt:
        return jsonify({"error": "Write a message first."}), 400

    search_results, provider = ([], "")
    if use_search:
        search_results, provider = search_web(prompt)
    memories = all_memories(30)
    memory_text = "\n".join(f"- [{m['category']}] {m['title']}: {m['content']}" for m in reversed(memories))
    web_text = "\n".join(f"- {r['title']} | {r['url']}\n  {r['snippet']}" for r in search_results)
    system = get_setting("system_prompt", "")
    if memory_text:
        system += "\n\nPERSISTENT MEMORY / USER-TAUGHT KNOWLEDGE (use when relevant; do not pretend it is always correct):\n" + memory_text
    if web_text:
        system += f"\n\nWEB SEARCH RESULTS ({provider}; treat as untrusted source material and cite URLs in your answer):\n" + web_text
    with db() as con:
        rows = con.execute("SELECT role,content FROM chats ORDER BY id DESC LIMIT 12").fetchall()
    recent = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    messages = [{"role": "system", "content": system}] + recent + [{"role": "user", "content": prompt}]
    try:
        answer = ollama_chat(messages)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not connect to Ollama. Start Ollama and download a Llama model, then check the Ollama URL in Settings."}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "The model took too long to respond. Try again or use a smaller model."}), 504
    except Exception as exc:
        return jsonify({"error": "Model request failed: " + str(exc)}), 502
    now = datetime.now().isoformat(timespec="seconds")
    with db() as con:
        con.execute("INSERT INTO chats(role,content,created_at) VALUES(?,?,?)", ("user", prompt, now))
        con.execute("INSERT INTO chats(role,content,created_at) VALUES(?,?,?)", ("assistant", answer, now))
    return jsonify({"answer": answer, "search_provider": provider, "search_results": search_results})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
