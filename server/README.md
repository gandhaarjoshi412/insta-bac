# NoInsta Backend Server

The **NoInsta Backend Server** is the central authority for the NoInsta personal productivity-control ecosystem. It manages user authentication, secure device pairing, phone-generated Instagram event ingestion, global 5-minute intervention cooldown logic, laptop presence tracking, and real-time intervention routing over authenticated WebSockets.

Production Server Host: `https://noinsta.platesight.in/`

---

## Architecture Overview

```text
                                 INTERNET
                                    │
                     ┌──────────────▼──────────────┐
                     │         NOINSTA VPS         │
                     │                             │
                     │ FastAPI                     │
                     │ PostgreSQL                  │
                     │ Authentication              │
                     │ Pairing                     │
                     │ Event processing            │
                     │ Laptop presence             │
                     │ WebSocket manager           │
                     └──────────┬───────────┬──────┘
                                │           │
                             HTTPS         WSS
                                │           │
                       ┌────────▼───┐   ┌───▼──────────┐
                       │   Android  │   │    Laptop    │
                       │    Phone   │   │ Python/PyQt  │
                       └────────────┘   └──────────────┘
```

### Multi-User & Multi-Device Hierarchy
* A single user account can own **one Android phone** and **multiple laptops**.
* When an Android phone reports an Instagram opening event:
  1. The server authenticates the device and user.
  2. The event is recorded in PostgreSQL.
  3. The global **5-minute cooldown** is evaluated against the user's last intervention timestamp with database row-level locking.
  4. If the cooldown has expired: all **active and online laptops** belonging to that user receive an `instagram_open` command over their authenticated WebSocket.
  5. Offline laptops are ignored and stale commands are never replayed upon reconnection.

---

## 1. Technology Stack

* **Python 3.11+**
* **FastAPI**: Modern, high-performance async web framework.
* **Uvicorn**: Lightning-fast ASGI web and WebSocket server.
* **PostgreSQL + asyncpg**: Production relational database with async I/O.
* **SQLAlchemy 2.x + Alembic**: Type-annotated ORM and database migrations.
* **Pydantic v2**: Strict schema validation.
* **PyJWT & bcrypt**: Cryptographic password hashing and signed JWT bearer tokens.

---

## 2. Repository Structure

```text
server/
├── app/
│   ├── main.py                  # FastAPI application, CORS, routers, lifespan
│   ├── core/
│   │   ├── config.py            # Pydantic settings & environment variables
│   │   ├── database.py          # SQLAlchemy async engine, session factory & Base
│   │   ├── security.py          # Bcrypt hashing, JWT generation/decoding, pairing code utils
│   │   └── rate_limit.py        # Sliding-window rate limiter for public endpoints
│   ├── models/
│   │   ├── user.py              # User entity with last_intervention_at cooldown tracker
│   │   ├── device.py            # Device entity (ANDROID / LAPTOP) with last_seen_at
│   │   ├── refresh_token.py     # Revocable hashed refresh tokens
│   │   ├── pairing.py           # Single-use hashed pairing codes with attempt limits
│   │   ├── session.py           # Continuous Instagram usage sessions
│   │   ├── event.py             # Instagram open/close events with idempotency constraint
│   │   └── intervention.py      # Laptop delivery and acknowledgment records
│   ├── schemas/
│   │   ├── auth.py              # User registration, login, token refresh models
│   │   ├── devices.py           # Device details and revocation models
│   │   ├── events.py            # Event submission, idempotency, and history models
│   │   ├── pairing.py           # Pairing code creation and claim models
│   │   └── websocket.py         # Centralized protocol schemas and message types
│   ├── api/
│   │   ├── deps.py              # User and Device JWT dependency extractors
│   │   ├── auth.py              # /api/v1/auth routes
│   │   ├── pairing.py           # /api/v1/pairing routes
│   │   ├── devices.py           # /api/v1/devices routes (including /devices/pair alias)
│   │   ├── events.py            # /api/v1/events routes
│   │   └── health.py            # /health and /api/v1/health probes
│   ├── services/
│   │   ├── auth_service.py      # Registration, verification, token rotation logic
│   │   ├── pairing_service.py   # Cryptographic pairing code lifecycle
│   │   ├── event_service.py     # Event processing, row locking cooldown & dispatch
│   │   ├── presence_service.py  # Laptop online status & 15-minute timeout evaluation
│   │   └── websocket_manager.py # Active WebSocket connection index & broadcast manager
│   └── websocket/
│       └── laptop.py            # /ws/laptop and /ws/device/{device_id} endpoints
├── migrations/
│   ├── env.py                   # Async Alembic environment
│   ├── script.py.mako           # Revision template
│   └── versions/
│       └── 0001_initial_schema.py # Complete 7-table initial migration
├── tests/
│   ├── conftest.py              # In-memory async database fixtures
│   ├── test_auth.py             # User registration, login, refresh, logout tests
│   ├── test_pairing.py          # Code creation, claiming, single-use, alias tests
│   ├── test_devices.py          # Device ownership and revocation tests
│   ├── test_events.py           # Event recording and idempotency deduplication tests
│   ├── test_cooldown.py         # 5-minute global cooldown & suppression tests
│   ├── test_presence.py         # Heartbeat tracking and 15-minute offline threshold tests
│   └── test_websocket.py        # WebSocket handshake, authentication, heartbeats & acks
├── .env.example
├── requirements.txt
├── alembic.ini
├── README.md
└── run.py                       # CLI runner for Uvicorn
```

---

## 3. Environment Configuration

Copy `.env.example` to `.env` and configure your database and security keys:

```bash
cp .env.example .env
```

### Configurable Parameters
| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async PostgreSQL connection string |
| `JWT_SECRET` | *Must be changed* | High-entropy secret for HMAC-SHA256 JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Short-lived access token lifespan |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Long-lived refresh token lifespan |
| `PAIRING_CODE_EXPIRE_MINUTES` | `10` | Lifespan of generated pairing code |
| `PAIRING_CODE_MAX_ATTEMPTS` | `5` | Maximum failed claim attempts per code |
| `INSTAGRAM_COOLDOWN_SECONDS` | `300` | Global user intervention cooldown (5 minutes) |
| `LAPTOP_HEARTBEAT_SECONDS` | `120` | Recommended client heartbeat interval (2 minutes) |
| `LAPTOP_OFFLINE_SECONDS` | `900` | Offline threshold timeout (15 minutes) |
| `ALLOWED_ORIGINS` | `https://noinsta.platesight.in` | Restrictive CORS origin whitelist |
| `RATE_LIMIT_PER_MINUTE` | `60` | Public endpoint rate limit per IP |

---

## 4. Database Setup & Migrations

Run database migrations to initialize the schema:

```bash
# Apply migrations to latest revision
alembic upgrade head
```

---

## 5. Running the Server

### Development Mode
```bash
python run.py --reload --port 8000
```
Interactive OpenAPI documentation will be available at:
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`

### Production Mode
```bash
python run.py --host 127.0.0.1 --port 8000
```
Or via Uvicorn directly:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips='*'
```

---

## 6. Authentication & Device Tokens

Authentication operates on two layers:
1. **User Accounts**: Owns devices, generates pairing codes, views event history.
   - `POST /api/v1/auth/register`
   - `POST /api/v1/auth/login`
2. **Device Identity**: Canonical identity assigned to laptops and Android phones.
   - Device tokens contain:
     ```json
     {
       "sub": "user_uuid",
       "device_id": "device_uuid",
       "device_type": "LAPTOP",
       "token_type": "access",
       "exp": 1789056000
     }
     ```
   - Hashed refresh tokens stored in `refresh_tokens` table for secure rotation:
     - `POST /api/v1/auth/refresh`
     - `POST /api/v1/auth/logout`

---

## 7. Pairing System

1. The user logs in via the Android app or web client and requests a pairing code:
   ```http
   POST /api/v1/pairing/create
   Authorization: Bearer <user_access_token>
   ```
   **Response:**
   ```json
   {
     "pairing_code": "A7K9Q2",
     "expires_at": "2026-09-10T12:10:00Z",
     "expires_in_seconds": 600
   }
   ```
2. The user enters `A7K9Q2` into the laptop client.
3. The laptop claims the pairing code:
   ```http
   POST /api/v1/pairing/claim  (or /api/v1/devices/pair)
   Content-Type: application/json

   {
     "pairing_code": "A7K9Q2",
     "device_name": "Gandhaar Fedora Laptop",
     "device_type": "LAPTOP"
   }
   ```
   **Response:**
   ```json
   {
     "device_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
     "access_token": "...",
     "refresh_token": "...",
     "user_id": "...",
     "message": "Device paired successfully."
   }
   ```
4. The pairing code is marked as `used_at = now()` and can never be reused.

---

## 8. Instagram Events & Cooldown Logic

Android phones post detected Instagram events:

```http
POST /api/v1/events
Authorization: Bearer <android_device_access_token>
Content-Type: application/json

{
  "event_type": "instagram_open",
  "client_event_id": "phone_evt_1001",
  "session_id": "sess_987",
  "timestamp": "2026-09-10T12:00:00Z"
}
```

### Idempotency
- If `client_event_id` was already processed for this device, the server returns the existing event without duplication.

### Cooldown Enforcement
- Evaluates `user.last_intervention_at`.
- Protected by PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) to prevent race conditions from concurrent events.
- Events are **always recorded** in the database.
- If `>= 300 seconds` (5 minutes) have elapsed since the user's last intervention:
  - `user.last_intervention_at` is updated and committed.
  - The server queries all online laptops for that user.
  - An `instagram_open` command is pushed through the active WebSocket to each online laptop.
  - An `interventions` record is created with status `SENT`.

---

## 9. Laptop WebSocket Protocol

Laptops connect to:
```text
wss://noinsta.platesight.in/ws/laptop
or
wss://noinsta.platesight.in/ws/device/{device_id}
```

### Protocol Flow
1. **Authentication Handshake**:
   Client sends:
   ```json
   {
     "type": "authenticate",
     "access_token": "...",
     "device_id": "..."
   }
   ```
   Server validates and responds:
   ```json
   {
     "type": "authenticated",
     "device_id": "...",
     "user_id": "..."
   }
   ```
2. **Heartbeat Beacon**:
   Client sends every 120s:
   ```json
   {
     "type": "heartbeat",
     "device_id": "..."
   }
   ```
   Server updates `device.last_seen_at` and responds:
   ```json
   {
     "type": "heartbeat_ack"
   }
   ```
3. **Intervention Dispatch (Server -> Laptop)**:
   ```json
   {
     "type": "instagram_open",
     "event_id": "evt_uuid",
     "timestamp": "2026-09-10T12:00:00Z"
   }
   ```
4. **Intervention Acknowledged (Laptop -> Server)**:
   When user dismisses the intervention:
   ```json
   {
     "type": "intervention_closed",
     "event_id": "evt_uuid",
     "device_id": "..."
   }
   ```
   Server updates `interventions.acknowledged_at = now()`, status to `ACKNOWLEDGED`.

---

## 10. Reverse Proxy Setup (Nginx)

When deploying behind Nginx at `noinsta.platesight.in`:

```nginx
server {
    server_name noinsta.platesight.in;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket upgrade headers
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket timeout adjustments
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

---

## 11. Running Tests

The test suite runs against an in-memory database and tests authentication, pairing, devices, events, cooldown, presence, and WebSocket communication:

```bash
pytest -v server/tests
```
