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
