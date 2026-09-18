# ⚡ Planner Agent - Quick Start (5 Minutes)

## 🎯 Goal
Get the Planner Agent running and test it in under 5 minutes.

## 📝 Prerequisites
- Python 3.10+
- Supabase account with tables created
- Gemini API key

## 🚀 Quick Setup

### 1️⃣ Install (30 seconds)
```bash
cd agent/planner
pip install -r requirements.txt
```

### 2️⃣ Configure (1 minute)
```bash
cp .env.example .env
```

Edit `.env`:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-key-here
GEMINI_API_KEY=your-gemini-key
```

### 3️⃣ Run (10 seconds)
```bash
python main.py
```

### 4️⃣ Test (30 seconds)
Open new terminal:
```bash
curl http://localhost:8001/health
```

Or run the test script:
```bash
python test_manual.py
```

## ✅ Success!
If you see:
- Server running on port 8001
- Health check returns `{"status": "healthy"}`
- Test creates projects in Supabase

You're done! 🎉

## 🔗 Next Steps
- Read `README.md` for detailed API docs
- Check `SETUP.md` for troubleshooting
- Review `architecture.md` for design details

## 💡 Quick Test Command
```bash
curl -X POST http://localhost:8001/agents/planner/handle_message \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","session_id":"test","message_text":"Train a plant disease model"}'
```

## 🆘 Problems?
1. **Port in use?** Change port: `uvicorn main:app --port 8002`
2. **Module errors?** Run: `pip install -r requirements.txt`
3. **Connection errors?** Check `.env` credentials
4. **Table errors?** Run SQL schema from `SETUP.md`
