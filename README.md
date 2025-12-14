# 🎙️ LeadFlow AI — Autonomous Voice Sales Agent (RAG + LangGraph + Vapi)

**GDG Kutaisi Hackathon 2025 — Productivity Track**

LeadFlow AI is a **voice-first sales agent**: it answers repetitive customer questions using the company’s own policy PDF (RAG), then **qualifies the caller** and **captures name + phone** into a database.

---

## 🚨 Problem

Small businesses waste hours daily on the same calls:
- “How much is it?”
- “What are your hours?”
- “Do you have discounts?”

If they don’t answer, they lose customers. If they do answer, they often spend time on people who aren’t serious buyers.

---

## 💡 What it does

1) Answers customer questions using the company’s real policy (RAG) — **it doesn’t guess**  
2) Switches from support to sales by asking simple qualifying questions  
3) If the caller shows intent, it collects **name + phone** and saves it as a **hot lead**

---

## 🛠️ How we built it

1) Website call UI (HTML/CSS/JS) triggers a WebRTC voice call via **Vapi.ai**  
2) **FastAPI backend** exposes `/vapi-config` and streams assistant responses from `/chat/completions`  
3) **ngrok (required for our demo)** tunnels local FastAPI to a public HTTPS URL so Vapi can reach it  
4) **LangGraph state machine** drives conversation flow and tool usage  
5) **RAG pipeline:** `company_policy.pdf → chunk → embed → store in ChromaDB`  
6) Tools:
   - `lookup_policy(query)` retrieves relevant policy chunks
   - `save_lead_mock(name, phone)` normalizes phone numbers and writes leads to Postgres

The agent is prompted to operate in Georgian context and gather lead details when appropriate.

---

## ✨ What’s special (demo-ready features)

### 1) “No hallucinated prices” via RAG from the real PDF
- We ingest `data/company_policy.pdf` into a local Chroma vector DB
- Before answering, the agent retrieves relevant policy chunks via `lookup_policy(query)`

### 2) Georgian number handling for voice (prices, hours, phone numbers)
Voice models can pronounce digits inconsistently in Georgian.  
We convert digit sequences into **Georgian digit-words** before sending responses to TTS.

Example: `599123456` → `ხუთი ცხრა ცხრა ერთი ორი სამი ოთხი ხუთი ექვსი`

### 3) Lead capture to Postgres
Once the user confirms name + phone, the agent calls `save_lead_mock(name, phone)` and inserts the lead into Postgres.

### 4) Voice-safe “end call” guardrail (tool forcing)
In voice, you can’t rely on “the user will hang up.”  
We enforce a fixed Georgian goodbye phrase and detect it on the backend.  
When detected, the backend emits an `endCall` tool call to Vapi to end the call cleanly.

---

## ⚠️ Challenges we ran into

1) Keeping voice interactions low-latency while still using RAG + tools  
2) Preventing hallucinated prices/hours (forcing policy lookup before answering)  
3) Clean call-ending logic (detecting the goodbye phrase reliably)  
4) Georgian voice quality: we switched to a model that handled Georgian better and added extra number-reading logic

---

## 🧠 Architecture (high level)

```mermaid
graph LR
  U((User)) -->|Voice/WebRTC| V[Vapi.ai]
  V -->|Calls backend via HTTPS| N[ngrok tunnel]
  N --> S[FastAPI Backend]
  S --> G[LangGraph Sales Agent]
  G -->|lookup_policy| C[(ChromaDB: company_policy.pdf)]
  G -->|save_lead_mock| P[(Postgres: leads table)]
  S -->|TTS-safe response| V
  S -->|endCall tool| V
```


🏆 Accomplishments we’re proud of

1)Built a real voice agent, not just a chatbot

2)RAG answers are grounded in a PDF knowledge base (trusted business info)

3)Captures real leads into a real database

4)End-to-end demo: Call → Answer → Qualify → Save lead → End call

5)Implemented a Georgian-speaking assistant fast while keeping it reliable

📚 What we learned

1)Voice agents need stricter guardrails than chat (forcing tool use + short answers)

2)LangGraph makes multi-step conversational workflows easier to control and debug

3)General workflow for AI agents: define states, define tools, enforce tool rules, iterate using real conversation logs

4)Small UX details matter a lot in voice (number formatting, confirmations, end-of-call behavior)

🚀 What’s next for LeadFlow

1)Phone number support (real inbound calls, not only website)

2)Better Georgian handling (more natural speech, better number pronunciation, clearer understanding)

3)Expand what businesses can automate (lead qualification, intake forms over the phone, routing, summarized leads to the team)

4)More business control (easy updates to company info so the assistant stays accurate)

📁 Project structure
LEADFLOW-AI/
├─ app/
│  ├─ graph.py        # LangGraph flow + tools + number-to-words helpers
│  ├─ rag.py          # Chroma retrieval
│  └─ server.py       # FastAPI server (vapi-config + streaming)
├─ client/
│  ├─ index.html      # Website UI (Vapi WebRTC)
│  └─ style.css
├─ data/
│  └─ company_policy.pdf
├─ chroma_db/         # generated after ingestion
├─ ingestion.py       # PDF → chunks → embeddings → Chroma
├─ requirements.txt
├─ README.md
└─ .env               # secrets (not committed)

## ▶️ Run the demo (local)

### 1) Install dependencies
```bash
pip install -r requirements.txt
```

2) Create .env

Create a file named .env in the project root:
```bash
OPENAI_API_KEY=...

VAPI_PUBLIC_KEY=...
VAPI_ASSISTANT_ID=...

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...

COMPANY_NAME=...
COMPANY_CITY=...
```
