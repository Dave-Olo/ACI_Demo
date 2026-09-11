"use strict";

const crypto = require("crypto");
const http = require("http");
const path = require("path");
const { parseArgs } = require("util");

require("dotenv").config({ path: path.join(__dirname, ".env") });

const express = require("express");
const cors = require("cors");
const Database = require("better-sqlite3");

const DATABASE_PATH = path.join(__dirname, "pins.db");

function logLine(level, message) {
  const timestamp = new Date().toISOString().replace(/\.\d+Z$/, "");
  console.log(`${timestamp} [${level}] server - ${message}`);
}

const logger = {
  debug: (message) => logLine("DEBUG", message),
  info: (message) => logLine("INFO", message),
  warning: (message) => logLine("WARNING", message),
};

function getDb() {
  const db = new Database(DATABASE_PATH);
  db.pragma("journal_mode = WAL");
  return db;
}

function initDb() {
  const db = getDb();

  // Migrate pins table if facility_id or facility_name columns are missing
  const existingColumns = new Set(
    db.prepare("PRAGMA table_info(pins)").all().map((row) => row.name)
  );
  const targetColumns = ["pin_hash", "facility_id", "facility_name"];
  const needsMigration =
    existingColumns.size > 0 && !targetColumns.every((column) => existingColumns.has(column));

  if (needsMigration) {
    logger.info("Migrating pins table to add facility_id/facility_name columns...");
    const hasFacilityId = existingColumns.has("facility_id");
    db.exec("ALTER TABLE pins RENAME TO pins_old");
    db.exec(`
      CREATE TABLE pins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pin_hash TEXT NOT NULL,
        facility_id TEXT NOT NULL DEFAULT '',
        facility_name TEXT NOT NULL DEFAULT '',
        used INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(pin_hash, facility_id)
      )
    `);
    if (hasFacilityId) {
      db.exec(`
        INSERT INTO pins (id, pin_hash, facility_id, facility_name, used, created_at)
        SELECT id, pin_hash, facility_id, '', used, created_at FROM pins_old
      `);
    } else {
      db.exec(`
        INSERT INTO pins (id, pin_hash, facility_id, facility_name, used, created_at)
        SELECT id, pin_hash, '', '', used, created_at FROM pins_old
      `);
    }
    db.exec("DROP TABLE pins_old");
    logger.info("Migration complete.");
  } else {
    db.exec(`
      CREATE TABLE IF NOT EXISTS pins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pin_hash TEXT NOT NULL,
        facility_id TEXT NOT NULL DEFAULT '',
        facility_name TEXT NOT NULL DEFAULT '',
        used INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(pin_hash, facility_id)
      )
    `);
  }

  db.exec(`
    CREATE TABLE IF NOT EXISTS facility_registrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      access_code TEXT NOT NULL UNIQUE,
      facility_name TEXT NOT NULL,
      facility_id TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL
    )
  `);

  db.close();
  logger.info("Database initialized.");
}

function hashAccessCode(accessCode) {
  return crypto.createHash("sha256").update(accessCode, "utf-8").digest("hex");
}

function nowIso() {
  return new Date().toISOString().replace(/\.\d+Z$/, "") + "Z";
}

function getDefaultPort() {
  const portValue = process.env.PORT || "8443";
  const port = Number(portValue);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535.");
  }
  return port;
}


const app = express();
app.use(cors());
app.use(express.json());

function missingFields(fields) {
  return Object.entries(fields)
    .filter(([, value]) => !value)
    .map(([name]) => name);
}

function registerFacility(payload, res) {
  const accessCode = String(payload.accessCode ?? "").trim();
  const facilityName = String(payload.facilityName ?? "").trim();
  const facilityId = String(payload.facilityId ?? "").trim();

  const missing = missingFields({ accessCode, facilityName, facilityId });
  if (missing.length > 0) {
    logger.warning(`Facility registration missing fields: ${JSON.stringify(missing)}`);
    return res.status(400).json({
      success: false,
      error: `Missing required field(s): ${missing.join(", ")}`,
    });
  }

  const createdAt = nowIso();
  const db = getDb();
  try {
    db.prepare(
      "INSERT INTO facility_registrations (access_code, facility_name, facility_id, created_at) VALUES (?, ?, ?, ?)"
    ).run(accessCode, facilityName, facilityId, createdAt);
    logger.info(`Facility registered: facilityId=${facilityId}`);
  } catch (error) {
    logger.warning(
      `Facility registration conflict: facilityId=${facilityId} or accessCode already exists`
    );
    return res.status(409).json({ success: false, error: "Facility registration already exists." });
  } finally {
    db.close();
  }

  return res.status(201).json({
    success: true,
    message: "Facility registration received successfully.",
    facilityId,
  });
}

app.post("/register", (req, res) => {
  const data = req.body;
  if (!data || Object.keys(data).length === 0) {
    logger.warning(`POST /register - invalid JSON body from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Request body must be valid JSON." });
  }

  logger.debug(`POST /register payload keys: ${JSON.stringify(Object.keys(data))} from ${req.ip}`);

  const accessCode = String(data.accessCode ?? "").trim();
  const facilityId = String(data.facilityId ?? "").trim();
  const facilityName = String(data.facilityName ?? "").trim();

  const missing = missingFields({ accessCode, facilityId, facilityName });
  if (missing.length > 0) {
    logger.warning(`POST /register - missing fields: ${JSON.stringify(missing)} from ${req.ip}`);
    return res.status(400).json({
      success: false,
      error: `Missing required field(s): ${missing.join(", ")}`,
    });
  }

  if (!/^\d+$/.test(accessCode) || accessCode.length < 4 || accessCode.length > 16) {
    logger.warning(`POST /register - invalid accessCode format from ${req.ip}`);
    return res.status(400).json({ success: false, error: "accessCode must be 4-16 digits." });
  }

  const pinHash = hashAccessCode(accessCode);
  const createdAt = nowIso();

  const db = getDb();
  try {
    db.prepare(
      "INSERT INTO pins (pin_hash, facility_id, facility_name, used, created_at) VALUES (?, ?, ?, 0, ?)"
    ).run(pinHash, facilityId, facilityName, createdAt);
    logger.info(
      `POST /register - access code registered for facilityId=${facilityId} facilityName=${facilityName}`
    );
  } catch (error) {
    logger.warning(`POST /register - access code already exists for facilityId=${facilityId}`);
    return res.status(409).json({ success: false, error: "Access code already exists for this facility." });
  } finally {
    db.close();
  }

  return res.status(201).json({
    success: true,
    message: "Access code registered successfully.",
    facilityId,
    facilityName,
  });
});

app.post("/facility/register", (req, res) => {
  const data = req.body;
  if (!data || Object.keys(data).length === 0) {
    logger.warning(`POST /facility/register - invalid JSON body from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Request body must be valid JSON." });
  }

  logger.info(`POST /facility/register attempt from ${req.ip}`);
  return registerFacility(data, res);
});

app.post("/authenticate", (req, res) => {
  const data = req.body;
  if (!data || Object.keys(data).length === 0) {
    logger.warning(`POST /authenticate - invalid JSON body from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Request body must be valid JSON." });
  }

  const accessCode = String(data.accessCode ?? "").trim();
  const facilityId = String(data.facilityId ?? "").trim();
  const facilityName = String(data.facilityName ?? "").trim();

  const missing = missingFields({ accessCode, facilityId, facilityName });
  if (missing.length > 0) {
    logger.warning(`POST /authenticate - missing fields: ${JSON.stringify(missing)} from ${req.ip}`);
    return res.status(400).json({
      success: false,
      error: `Missing required field(s): ${missing.join(", ")}`,
    });
  }

  if (!/^\d+$/.test(accessCode)) {
    logger.warning(`POST /authenticate - invalid accessCode format from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Invalid accessCode format." });
  }

  const pinHash = hashAccessCode(accessCode);
  const db = getDb();
  const row = db
    .prepare("SELECT id, used, facility_name FROM pins WHERE pin_hash = ? AND facility_id = ?")
    .get(pinHash, facilityId);

  if (!row) {
    db.close();
    logger.warning(
      `POST /authenticate - access code not found for facilityId=${facilityId} facilityName=${facilityName} from ${req.ip}`
    );
    return res.status(404).json({ success: false, authenticated: false, error: "Access code not found." });
  }

  if (row.facility_name && row.facility_name !== facilityName) {
    db.close();
    logger.warning(`POST /authenticate - facilityName mismatch for facilityId=${facilityId} from ${req.ip}`);
    return res.status(403).json({ success: false, authenticated: false, error: "Facility name does not match." });
  }

  if (row.used) {
    db.close();
    logger.warning(
      `POST /authenticate - access code already used for facilityId=${facilityId} facilityName=${facilityName} from ${req.ip}`
    );
    return res
      .status(403)
      .json({ success: false, authenticated: false, error: "Access code has already been used." });
  }

  db.close();
  logger.info(
    `POST /authenticate - authenticated for facilityId=${facilityId} facilityName=${facilityName}`
  );

  return res.status(200).json({
    success: true,
    authenticated: true,
    message: "Access code is valid.",
    facilityName,
  });
});

app.post("/invalidate", (req, res) => {
  const data = req.body;
  if (!data || Object.keys(data).length === 0) {
    logger.warning(`POST /invalidate - invalid JSON body from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Request body must be valid JSON." });
  }

  const accessCode = String(data.accessCode ?? "").trim();
  const facilityId = String(data.facilityId ?? "").trim();
  const facilityName = String(data.facilityName ?? "").trim();

  const missing = missingFields({ accessCode, facilityId, facilityName });
  if (missing.length > 0) {
    logger.warning(`POST /invalidate - missing fields: ${JSON.stringify(missing)} from ${req.ip}`);
    return res.status(400).json({
      success: false,
      error: `Missing required field(s): ${missing.join(", ")}`,
    });
  }

  if (!/^\d+$/.test(accessCode)) {
    logger.warning(`POST /invalidate - invalid accessCode format from ${req.ip}`);
    return res.status(400).json({ success: false, error: "Invalid accessCode format." });
  }

  const pinHash = hashAccessCode(accessCode);
  const db = getDb();
  const row = db
    .prepare("SELECT id, used, facility_name FROM pins WHERE pin_hash = ? AND facility_id = ?")
    .get(pinHash, facilityId);

  if (!row) {
    db.close();
    logger.warning(
      `POST /invalidate - access code not found for facilityId=${facilityId} facilityName=${facilityName} from ${req.ip}`
    );
    return res.status(404).json({ success: false, error: "Access code not found." });
  }

  if (row.facility_name && row.facility_name !== facilityName) {
    db.close();
    logger.warning(`POST /invalidate - facilityName mismatch for facilityId=${facilityId} from ${req.ip}`);
    return res.status(403).json({ success: false, error: "Facility name does not match." });
  }

  if (row.used) {
    db.close();
    logger.info(
      `POST /invalidate - access code already invalidated for facilityId=${facilityId} facilityName=${facilityName}`
    );
    return res.status(200).json({ success: false, message: "Access code is already invalidated." });
  }

  db.prepare("UPDATE pins SET used = 1 WHERE id = ?").run(row.id);
  db.close();
  logger.info(
    `POST /invalidate - access code invalidated for facilityId=${facilityId} facilityName=${facilityName}`
  );

  return res.status(200).json({
    success: true,
    message: "Access code invalidated successfully.",
    facilityName,
  });
});

app.get("/status", (req, res) => {
  logger.debug(`GET /status from ${req.ip}`);
  return res.status(200).json({ success: true, message: "PIN auth server is running." });
});

initDb();

if (require.main === module) {
  const { values } = parseArgs({
    options: {
      port: { type: "string", default: String(getDefaultPort()) },
    },
  });

  const port = Number(values.port);

  http.createServer(app).listen(port, () => {
    logger.info(`Starting HTTP server on port ${port}.`);
  });
}

module.exports = app;
