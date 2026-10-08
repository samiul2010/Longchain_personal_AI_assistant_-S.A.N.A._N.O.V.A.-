# Personal Assistant — LangGraph Edition

CrewAI থেকে **LangGraph + LangChain**-এ পুনর্নির্মিত পার্সোনাল এআই এসিস্ট্যান্ট।
মূল কাঠামো অপরিবর্তিত রাখা হয়েছে: একটি **main/supervisor agent** এবং চারটি
**sub agent** (GitHub, GitLab, Facebook, YouTube), প্রতিটির নিজস্ব MCP টুলসহ।

## কাঠামো

```
agents.py                 -> main supervisor agent (langgraph-supervisor দিয়ে তৈরি)
all_sub_agents.py          -> সব sub agent বিল্ড/একত্র করে
sub_agents/
  git_hub_agent/git_hub.py
  git_lab_agent/git_lab.py
  facebook_agent/facebook.py
  youtube_agent/youtube.py
app.py                     -> FastAPI backend + Manus-style streaming UI
static/                    -> index.html / style.css / app.js (frontend)
/agent/<agent_name>/       -> প্রতিটি এজেন্টের persistent memory (sqlite state.db)
```

## মেমরি / স্টেট — persistent `/agent` স্টোরেজ বাকেট

`/agent` কে একটি **persistent storage bucket** ধরে নেওয়া হয়েছে (HF Space-এ
আপনার Persistent Storage ভলিউম ঠিক এই পাথে মাউন্ট করা থাকতে হবে)। কোনো state,
sqlite ডাটাবেজ, thread index, বা আপলোড করা ফাইল — কোনোটাই ephemeral container
filesystem-এ লেখা হয় না; সবকিছু `storage_paths.py`-এর `agent_dir()` ফাংশনের
মাধ্যমে `/agent/...`-এর ভিতরে যায়। অ্যাপ চালু হওয়ার সময় এই ফাংশন `/agent`-এ
আসলেই write access আছে কিনা পরীক্ষা করে — না থাকলে স্পষ্ট এরর দিয়ে থেমে যায়
(silently ephemeral storage-এ fallback করে না), যাতে আপনি সাথে সাথে বুঝতে
পারেন bucket সঠিকভাবে মাউন্ট হয়নি।

প্রতিটি agent (main_agent সহ প্রতিটি sub agent) নিজস্ব `AsyncSqliteSaver`
checkpointer ব্যবহার করে, যার ফাইল থাকে:

```
/agent/main_agent/state.db
/agent/git_hub_agent/state.db
/agent/git_lab_agent/state.db
/agent/facebook_agent/state.db
/agent/youtube_agent/state.db
```

প্রতিটি কথোপকথনের `thread_id` অনুযায়ী পুরো মেসেজ-হিস্ট্রি এই ডাটাবেজে সেভ
থাকে — তাই **Space রিস্টার্ট/রিডিপ্লয় বা পেজ রিফ্রেশ দিলেও কথোপকথন মুছে
যায় না** (`/api/history` এই state থেকেই আগের কথোপকথন পুনর্গঠন করে)।

Thread তালিকা (সাইডবার) `/agent/main_agent/threads.json`-এ, আর আপলোড করা
ফাইল `/agent/main_agent/uploads/`-এ থাকে — এগুলোও একই bucket-এর ভিতরে, তাই
সবকিছু persist করে।

> **HF Spaces সেটআপ:** Space settings-এ গিয়ে Persistent Storage যোগ করুন এবং
> mount path হিসেবে ঠিক `/agent` লিখুন। এটা না করলে অ্যাপ চালুই হবে না —
> ইচ্ছাকৃতভাবে স্পষ্ট এরর দেখাবে, যাতে ডেটা নীরবে হারিয়ে না যায়।

## UI (Manus-style)

`app.py` একটি streaming (NDJSON) endpoint `/api/chat` দেয়, যা main agent এর
`astream_events` থেকে রিয়েল-টাইমে ধাপগুলো পাঠায়:

- `agent_start` — কখন main agent কোনো sub agent-কে কাজ দিচ্ছে
- `tool_start` / `tool_end` — কোন টুল চালানো হচ্ছে, ইনপুট/আউটপুট সহ
- `token` — চূড়ান্ত উত্তরের টেক্সট স্ট্রিম

Frontend (`static/app.js`) এই ইভেন্টগুলো দিয়ে Manus AI-এর মতো একটি
"action timeline" কার্ড দেখায় (প্রতিটি ধাপ expand করে বিস্তারিত দেখা যায়),
এবং প্রতিটি চ্যাট থ্রেড সাইডবারে সংরক্ষিত থাকে।

## চালানো

```bash
cp .env.example .env   # আপনার API key / token বসান
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 7860
```

অথবা Docker দিয়ে:

```bash
docker build -t personal-assistant .
docker run -p 7860:7860 --env-file .env -v $(pwd)/agent:/agent personal-assistant
```

> `-v $(pwd)/agent:/agent` দিলে কনটেইনার রিস্টার্ট হলেও সব agent-এর memory/state
> ধরে থাকবে।

## গুরুত্বপূর্ণ নোট

- সাব এজেন্টগুলো এখন LangGraph v1-এর নির্দেশনা অনুযায়ী deprecated
  `langgraph.prebuilt.create_react_agent`-এর বদলে **`langchain.agents.create_agent`**
  দিয়ে তৈরি (প্যারামিটার নাম `prompt` থেকে `system_prompt` হয়েছে) —
  মূল সুপারভাইজার এখনও `langgraph-supervisor`-এর `create_supervisor` ব্যবহার
  করছে, যেটা ঠিকভাবেই `create_agent`-নির্মিত সাব এজেন্টদের সাথে কাজ করে।
- `LLM_MODEL` / `SUB_LLM_MODEL` অবশ্যই LangChain-এর `init_chat_model` ফরম্যাটে
  দিতে হবে, যেমন `openai:gpt-4.1`, `anthropic:claude-sonnet-4-5`, বা
  `google_genai:gemini-2.0-flash`। যে provider ব্যবহার করবেন তার প্যাকেজ
  `requirements.txt`-এ আছে কিনা নিশ্চিত করুন।
- প্রতিটি sub agent-এর MCP সার্ভার (github-mcp-server, @zereight/mcp-gitlab,
  maagpi-youtube-mcp, just_facebook_mcp) সিস্টেমে ইনস্টল থাকা লাগবে —
  `Dockerfile`-এ প্রথম তিনটি ইনস্টল করা আছে; `just_facebook_mcp` আপনার নিজের
  ইনস্টল পদ্ধতি অনুযায়ী যোগ করুন যদি সেটি pip/npm প্যাকেজ না হয়।
- `langgraph==1.2.11` ও `langchain==1.3.15` আপনার অনুরোধ অনুযায়ী পিন করা
  হয়েছে — ইনস্টলের সময় আপনার প্যাকেজ ইনডেক্সে এই ভার্সনগুলো উপলব্ধ কিনা
  যাচাই করে নেবেন।
