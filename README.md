# HTTPS Access Code Authentication Server

A Python HTTPS server with a SQLite database for per-facility access code registration, authentication, and invalidation, plus facility registration.

All JSON payloads use camelCase field names. Access codes are scoped to a `facilityId` so the same code can exist independently across different facilities.

## Setup

1. Create a Python virtual environment and install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Generate a self-signed certificate pair in the project folder:

```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout key.pem -out cert.pem -subj "/CN=localhost"
```

3. Start the server:

```powershell
# HTTPS on default port 8443 (requires cert.pem and key.pem)
python server.py

# HTTP on default port 8443 (no certificate needed)
python server.py --mode http

# HTTP on a custom port
python server.py --mode http --port 5000

# HTTPS on a custom port
python server.py --mode https --port 9443
```

### Command-line arguments

| Argument | Values | Default | Description |
|----------|--------|---------|-------------|
| `--mode` | `http`, `https` | `https` | Run the server in HTTP or HTTPS mode |
| `--port` | any integer | `8443` | Port to listen on |

By default the server listens on `https://0.0.0.0:8443`. When using `--mode https`, the certificate files (`cert.pem` and `key.pem`) must exist in the project folder.

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


Issues:

if you encounter this issue in powershell
```
.\venv\Scripts\Activate.ps1 .\venv\Scripts\Activate.ps1 : File C:\Users\USER\Documents\STM\ACI\Python Server\venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled on this system. For more information, see about_Execution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170. At line:1 char:1 + .\venv\Scripts\Activate.ps1 + ~~~~~~~~~~~~~~~~~~~~~~~~~~~ + CategoryInfo : SecurityError: (:) [], PSSecurityException + FullyQualifiedErrorId : UnauthorizedAccess
```

use this command:

```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```
