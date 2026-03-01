# Smart Medirag

Flask + React (Vite) app with:
- JWT authentication (access + refresh tokens)
- RBAC (`admin`, `user`)
- OTP password reset (no SMTP, dev OTP returned by API)
- Chat threads/messages persistence
- Admin APIs for users and conversations

## Implemented API

Auth:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/forgot-password`
- `POST /auth/verify-otp`
- `POST /auth/reset-password`

Chat:
- `POST /chat/ask`
- `GET /chat/threads`
- `GET /chat/messages/<thread_id>`

Admin:
- `GET /admin/users`
- `GET /admin/conversations`

Legacy compatibility:
- `POST /answer`
- `POST /auth/forgot-password/request-otp`
- `POST /auth/forgot-password/reset`

## Backend setup

1. Create/activate venv and install dependencies:
```bash
pip install -r requirements.txt
```
2. Configure `.env`:
```env
JWT_SECRET=change_me
JWT_EXPIRATION_MINUTES=15
JWT_REFRESH_EXPIRATION_DAYS=7
PASSWORD_RESET_OTP_TTL_MINUTES=5
PASSWORD_RESET_OTP_RATE_LIMIT_PER_HOUR=3
DEV_SHOW_OTP=true
API_HOST=0.0.0.0
API_PORT=5000
API_DEBUG=true
CORS_ORIGINS=http://localhost:5173
```
3. Run backend:
```bash
python -m api.app
```

SQLite DB auto-creates at `data/app.db`.

## Frontend setup

1. Install dependencies:
```bash
cd frontend-app
npm install
```
2. Run frontend:
```bash
npm run dev
```

Vite proxies `/api/*` to `http://localhost:5000/*`.

## Admin panel access (step-by-step)

The admin flow now has a separate login page:
- Admin login page: `http://localhost:5173/#/admin/login`
- Admin ingestion console: `http://localhost:5173/#/admin/ingest`

### Admin login credentials

There is no hardcoded default admin user in code.  
Use the same credentials of the account you promote to `admin`.

- Username: `admin`
- Admin ID (email): `admin@smartmedirag.local`
- Password: `Admin@123`

### 1. Start backend and frontend

From project root:
```bash
pip install -r requirements.txt
python -m api.app
```

In a second terminal:
```bash
cd frontend-app
npm install
npm run dev
```

### 2. Create a user account (use admin credentials)

Open `http://localhost:5173`, register a user from the auth screen, then sign in once.

Use:
- Username: `admin`
- Email: `admin@smartmedirag.local`
- Password: `Admin@123`

Important: registration always creates users with `role = "user"` by default.

### 3. Promote the user to admin in SQLite

The app DB is `data/app.db`.

If you have `sqlite3` CLI:
```bash
sqlite3 data/app.db "UPDATE users SET role='admin' WHERE email='admin@smartmedirag.local';"
sqlite3 data/app.db "SELECT username,email,role FROM users;"
```

If `sqlite3` CLI is not installed, use Python:
```bash
python -c "import sqlite3; conn=sqlite3.connect('data/app.db'); conn.execute(\"UPDATE users SET role='admin' WHERE email='admin@smartmedirag.local'\"); conn.commit(); print(conn.execute(\"SELECT username,email,role FROM users\").fetchall()); conn.close()"
```

### 4. Re-login to refresh JWT role claims

Logout and login again in the frontend after changing the role, so the new access token contains `role: admin`.

### 5. Open the separate admin login page

Open:
- `http://localhost:5173/#/admin/login`

Only accounts with `role = "admin"` can sign in from this page and proceed to the ingestion console.

From chat, the admin button now routes to this dedicated admin login page first.

### 6. Verify backend admin APIs (optional)

After login as admin, these should work:
- `GET /admin/documents`
- `POST /admin/ingest/upload` (multipart form-data field: `files`)
- `GET /admin/users`
- `GET /admin/conversations`

If you see "Access Restricted", the logged-in token is still non-admin. Logout/login again and confirm the DB user role is `admin`.

## Security Notes

- Passwords and OTPs are bcrypt-hashed.
- OTP expiry + rate limiting are enforced server-side.
- Chat endpoints require JWT.
- Admin endpoints require `admin` role.
- User thread access is isolated by `user_id`.

## Docker

Run:
```bash
docker compose up --build
```

Services:
- Backend: `http://localhost:5000`
- Frontend: `http://localhost:5173`
