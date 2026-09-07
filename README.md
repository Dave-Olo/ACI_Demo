# Access Code Authentication Server

A Node.js (Express) HTTP server with a SQLite database for per-facility access code registration, authentication, and invalidation, plus facility registration.

All JSON payloads use camelCase field names. Access codes are scoped to a `facilityId` so the same code can exist independently across different facilities.

TLS is not handled by the app itself. On Render (and similar platforms), TLS is terminated at the edge/load balancer, which forwards plain HTTP to the app; see `Procfile`.

## Setup

1. Install dependencies:

```powershell
npm install
```

2. Configure the application's `.env` file:

```dotenv
PORT=8000
HOST=0.0.0.0
```

3. Start the server:

```powershell
# Listens on the PORT/HOST configured in .env
node server.js

# Custom port
node server.js --port 5000

# Custom host and port
node server.js --host 127.0.0.1 --port 5000
```

### Command-line arguments

| Argument | Values | Default | Description |
|----------|--------|---------|-------------|
| `--port` | any integer | `PORT` from `.env`, or `8443` | Port to listen on; overrides `PORT` |
| `--host` | any host/IP | `HOST` from `.env`, or `0.0.0.0` | Host/IP to bind to; overrides `HOST` |

Set `PORT` in `.env` to an integer from `1` through `65535`; it defaults to `8443` when omitted (see `.env` for the configured value). Set `HOST` to the address to bind to; it defaults to `0.0.0.0` (all interfaces) so the app is reachable regardless of the machine's LAN IP.

## API Endpoints

### Register a new access code

POST `/register`

Request JSON:

```json
{
  "accessCode": "1234",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

- `accessCode`: 4–16 digit numeric string
- `facilityId`: identifier of the facility this code belongs to
- `facilityName`: display name of the facility (stored with the code and validated on authenticate/invalidate)

Response:

- `201`: Access code registered successfully
- `400`: Missing or invalid fields
- `409`: Access code already exists for this facility

### Register facility details

POST `/facility/register`

Request JSON:

```json
{
  "accessCode": "123456",
  "facilityName": "Your Facility Name",
  "facilityId": "FAC001"
}
```

Response:

- `201`: Facility registration received successfully
- `400`: Missing or invalid fields
- `409`: Facility registration already exists

### Authenticate an access code

POST `/authenticate`

Request JSON:

```json
{
  "accessCode": "1234",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

Validates the access code for the given facility (including `facilityName` match) and immediately marks it as used (one-time use).

Response:

- `200`: Access code is valid and has been invalidated
- `400`: Missing or invalid fields
- `403`: Access code has already been used, or facility name does not match
- `404`: Access code not found

### Invalidate an access code

POST `/invalidate`

Request JSON:

```json
{
  "accessCode": "1234",
  "facilityId": "FAC001",
  "facilityName": "Your Facility Name"
}
```

Response:

- `200`: Access code invalidated successfully (or was already invalidated)
- `400`: Missing or invalid fields
- `403`: Facility name does not match
- `404`: Access code not found

### Health check

GET `/status`

Response:

- `200`: Server is running
