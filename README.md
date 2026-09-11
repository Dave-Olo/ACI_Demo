# Access Code Authentication Server

A Node.js (Express) HTTP server with a SQLite database for per-facility access code registration, authentication, and invalidation, plus facility registration.

All JSON payloads use **camelCase** field names. Access codes are scoped to a `facilityId`, so the same code can exist independently across different facilities.

TLS is **not** handled by the application. On platforms like Render, TLS is terminated at the edge/load balancer and plain HTTP is forwarded to the app.

---

## Setup

### 1. Install dependencies

```powershell
npm install
```

> **Note for Windows users**  
> `better-sqlite3` is a native module. If you see a warning about install scripts, run:
> ```powershell
> npm approve-scripts better-sqlite3
> npm rebuild better-sqlite3
> ```

### 2. Configure `.env`

```dotenv
PORT=8000
HOST=0.0.0.0
```

### 3. Start the server

```powershell
# Uses values from .env
node server.js

# Custom port
node server.js --port 5000

# Custom host and port
node server.js --host 127.0.0.1 --port 5000
```

#### Command-line arguments

| Argument | Values      | Default                          | Description                          |
|----------|-------------|----------------------------------|--------------------------------------|
| `--port` | any integer | `PORT` from `.env`, or `8443`    | Port to listen on                    |
| `--host` | any host/IP | `HOST` from `.env`, or `0.0.0.0` | Host/IP to bind to                   |

---

## API Endpoints

### Register a new access code

**POST** `/register`

```json
{
  "accessCode": "123456",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

- `accessCode`: 4–16 digit numeric string  
- `facilityId`: facility identifier  
- `facilityName`: display name (stored and later validated)

**Responses**
- `201` – Access code registered successfully  
- `400` – Missing or invalid fields  
- `409` – Access code already exists for this facility  

---

### Register facility details

**POST** `/facility/register`

```json
{
  "accessCode": "123456",
  "facilityName": "Your Facility Name",
  "facilityId": "FAC001"
}
```

**Responses**
- `201` – Facility registration received successfully  
- `400` – Missing or invalid fields  
- `409` – Facility registration already exists  

---

### Authenticate an access code

**POST** `/authenticate`

```json
{
  "accessCode": "123456",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

Validates the code without marking it as used. Call `/invalidate` separately to mark it used.

**Responses**
- `200` – Access code is valid  
- `400` – Missing or invalid fields  
- `403` – Already used **or** facility name mismatch  
- `404` – Access code not found  

---

### Invalidate an access code

**POST** `/invalidate`

```json
{
  "accessCode": "123456",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

**Responses**
- `200` – Access code invalidated successfully (or was already invalidated)  
- `400` – Missing or invalid fields  
- `403` – Facility name does not match  
- `404` – Access code not found  

---

### Register a guest visit

**POST** `/guest/register`

```json
{
  "guestName": "Jane Doe",
  "guestEmail": "jane@example.com",
  "guestPhone": "+1 555 0100"
}
```

The response contains a unique six-digit `pin`. Store or send this PIN to the guest; it is only returned during registration.

**Responses**
- `201` - Guest visit registered and PIN issued
- `400` - Missing fields or invalid email

### Validate a guest visit

**POST** `/guest/validate`

```json
{
  "pin": "123456"
}
```

Validation marks the PIN as used and returns the registered guest details. A PIN can only be validated once.

**Responses**
- `200` - Guest PIN validated successfully
- `400` - Missing or invalid PIN
- `404` - Guest PIN not found
- `409` - Guest PIN has already been used

---

### Health check

**GET** `/status`

- `200` – Server is running

---

## Testing the API (Windows PowerShell)

1. Start the server in one terminal:
   ```powershell
   node server.js --port 5000
   ```

2. Open a **second** PowerShell window for testing (do **not** use the same window).

### Recommended way to send requests

```powershell
$body = @{
    accessCode   = "123456"
    facilityId   = "FAC001"
    facilityName = "Your Facility Name"
} | ConvertTo-Json
```

#### Register
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/register" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

#### Authenticate
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/authenticate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

#### Invalidate
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/invalidate" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

#### Health check
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/status"
```

> **Tip**: On Windows PowerShell, prefer `Invoke-RestMethod` or `curl.exe`.  
> Plain `curl` is an alias for `Invoke-WebRequest` and will usually fail with the examples above.

---

## Troubleshooting

### Port already in use (`EADDRINUSE`)
```powershell
# Option A – use another port
node server.js --port 5000

# Option B – free the port
netstat -ano | findstr :8000
taskkill /PID <PID_NUMBER> /F
```

### better-sqlite3 / native module issues
```powershell
npm approve-scripts better-sqlite3
npm rebuild better-sqlite3
```

### JSON parse errors from the server
Make sure you are sending a proper JSON body. The safest pattern is the `$body = @{ ... } | ConvertTo-Json` method shown above.

---

## Typical test flow

1. Register a new access code → expect success  
2. Authenticate the same code → expect success (code is now used)  
3. Authenticate the same code again → expect `403` (already used)  
4. Register another code and then Invalidate it → expect success  
```

The file has been created at:

**`/home/workdir/artifacts/README.md`**

You can download it and replace your existing `README.md` with this improved version.  

Would you like any further changes (for example, adding Linux/macOS `curl` examples as well)?