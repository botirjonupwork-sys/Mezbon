Mezbon — Local run instructions
===============================

Quick start (macOS, dev)
-------------------------

1. Create and activate Python venv

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

2. Create `.env` (example values)

```env
SECRET_KEY=replace_with_generated_secret
DATABASE_URL=sqlite+aiosqlite:///./muhsina.db
API_URL=http://localhost:8000
DEBUG=True
ADMIN_PASSWORD=admin123
SUPER_ADMIN_PASSWORD=admin123
BOT_API_SECRET=changeme
BOT_TOKEN=your_telegram_bot_token
COURIER_BOT_TOKEN=your_courier_bot_token
```

3. Bootstrap DB and start backend + bots

```bash
# create tables (start.sh already runs this when using .venv python)
.venv/bin/python -c "from api.database import create_tables; import asyncio; asyncio.run(create_tables())"

# start backend + bots (start.sh uses .venv/python)
bash start.sh
```

4. Start frontend (dev)

```bash
cd admin
npm install
npm run dev
```

Verification
------------

- Backend health: `curl http://localhost:8000/health`
- Login via proxy (frontend):

```bash
curl -v -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

- Direct API auth check (using token from previous call):

```bash
TOKEN=$(curl -s http://localhost:3000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"admin123"}' | jq -r .token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/auth/me
```

Notes
-----
- Vite dev server proxies `/api` → `http://localhost:8000` in development. If you get ECONNREFUSED or 500 from the frontend, ensure the backend is running and `admin/vite.config.js` proxy `secure` is `false` for HTTP.
- Replace default passwords and secrets before exposing the app to networks.
