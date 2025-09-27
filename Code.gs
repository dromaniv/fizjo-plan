/**
 * ICS → Google Calendar sync + coloring (entire semester, quota-safe).
 * - Owned calendar: "Plan zajęć."
 * - Upsert by VEVENT UID, prune removed
 * - Colors by Polish keywords
 * - Processes the whole semester, but month-by-month with write budget, sleeps, and quota backoff
 */

const ICS_URL = "https://dromaniv.github.io/fizjo-plan/iwonka.ics";
const TARGET_CALENDAR_NAME = "Plan zajęć."; // must be an owned calendar

// Semester boundaries (inclusive)
const SEM_START = new Date(2025, 8, 30, 0, 0, 0); // 2025-09-30 00:00:00  (month 8 = Sep)
const SEM_END = new Date(2026, 1, 28, 23, 59, 59); // 2026-02-28 23:59:59

// Throttling / safety knobs (tuned for Calendar operational limits & Apps Script runtime)
const GLOBAL_WRITE_LIMIT = 400; // max create/update/delete per run (soft ceiling)
const SLEEP_EVERY_WRITES = 40; // pause every N writes
const SLEEP_MS = 100; // 100ms pause to smooth bursts
const MAX_ERRORS_BEFORE_STOP = 12;

// Entry point (set trigger daily at 06:00)
function ColorEvents() {
  const tz = Session.getScriptTimeZone() || "Europe/Warsaw";
  const cal = getOwnedCalendarByName_(TARGET_CALENDAR_NAME);
  if (!cal) {
    Logger.log("Calendar not found or not owned: " + TARGET_CALENDAR_NAME);
    return;
  }

  // Fetch + parse feed once
  let icsText;
  try {
    icsText = fetchIcs_(ICS_URL);
  } catch (e) {
    Logger.log("Fetch ICS failed: " + e);
    return;
  }

  // Read VCALENDAR-level metadata and VEVENTs
  const icsUpdated = readCalendarUpdated_(icsText);
  if (icsUpdated) Logger.log("Feed X-CALENDAR-UPDATED: " + icsUpdated);

  const vevents = parseICS_(icsText); // [{uid,summary,description,location,start,end}]

  // Pre-index all feed events in semester range by UID (to support deletes later per month)
  const allFeedByUid = Object.create(null);
  for (let i = 0; i < vevents.length; i++) {
    const ev = vevents[i];
    if (ev.start && ev.end && ev.end >= SEM_START && ev.start <= SEM_END) {
      allFeedByUid[ev.uid] = ev;
    }
  }

  // Build semester months; process in an order that spreads writes:
  // current month first, then months after, then months before.
  const months = listSemesterMonths_(SEM_START, SEM_END);
  const ordered = prioritizeMonths_(months, new Date());

  // Global counters / guardrails shared across months
  let totalCreated = 0,
    totalUpdated = 0,
    totalColored = 0,
    totalRemoved = 0,
    totalSkipped = 0,
    totalErrors = 0,
    totalWrites = 0;

  for (let k = 0; k < ordered.length; k++) {
    const win = ordered[k];
    if (totalWrites >= GLOBAL_WRITE_LIMIT) {
      Logger.log("Soft write budget reached; stop for this run.");
      break;
    }

    const res = syncWindow_(
      cal,
      vevents,
      allFeedByUid,
      win.start,
      win.end,
      tz,
      {
        writeBudgetLeft: GLOBAL_WRITE_LIMIT - totalWrites,
        sleepEvery: SLEEP_EVERY_WRITES,
        sleepMs: SLEEP_MS,
      },
      icsUpdated
    );

    totalCreated += res.created;
    totalUpdated += res.updated;
    totalColored += res.colored;
    totalRemoved += res.removed;
    totalSkipped += res.skipped;
    totalErrors += res.errors;
    totalWrites += res.writes;

    Logger.log(
      "Window: " +
        isoDate_(win.start) +
        " → " +
        isoDate_(win.end) +
        " | created: " +
        res.created +
        " | updated: " +
        res.updated +
        " | colored: " +
        res.colored +
        " | removed: " +
        res.removed +
        " | skipped: " +
        res.skipped +
        " | errors: " +
        res.errors +
        " | writes: " +
        res.writes
    );

    if (
      res.stoppedForQuota ||
      res.stoppedForWrites ||
      totalErrors >= MAX_ERRORS_BEFORE_STOP
    ) {
      Logger.log("Stopping early (quota/writes/errors guard).");
      break;
    }
  }

  Logger.log(
    "Calendar: " +
      TARGET_CALENDAR_NAME +
      " | semester: " +
      isoDate_(SEM_START) +
      " → " +
      isoDate_(SEM_END) +
      " | created: " +
      totalCreated +
      " | updated: " +
      totalUpdated +
      " | colored: " +
      totalColored +
      " | removed: " +
      totalRemoved +
      " | skipped: " +
      totalSkipped +
      " | errors: " +
      totalErrors +
      " | writes: " +
      totalWrites
  );
}

/* ================= Core per-window sync ================= */

function syncWindow_(
  cal,
  vevents,
  allFeedByUid,
  RANGE_START,
  RANGE_END,
  tz,
  limits,
  icsUpdated
) {
  const EXIST_UID_RX = /ICS-UID:\s*(\S+)/;

  // Index feed in window
  const feedByUid = Object.create(null);
  for (let i = 0; i < vevents.length; i++) {
    const ev = vevents[i];
    if (ev.start && ev.end && ev.end >= RANGE_START && ev.start <= RANGE_END) {
      feedByUid[ev.uid] = ev;
    }
  }

  // Index existing events in window
  let existing = [];
  try {
    existing = cal.getEvents(RANGE_START, RANGE_END);
  } catch (e) {
    return {
      created: 0,
      updated: 0,
      colored: 0,
      removed: 0,
      skipped: 0,
      errors: 1,
      writes: 0,
      stoppedForQuota: false,
      stoppedForWrites: false,
    };
  }
  const calByUid = Object.create(null);
  for (let i = 0; i < existing.length; i++) {
    const ev = existing[i];
    try {
      if (!ev.isOwnedByMe()) continue;
      const m = EXIST_UID_RX.exec(ev.getDescription() || "");
      if (m) calByUid[m[1]] = ev;
    } catch (_) {}
  }

  // Upserts
  const nowStamp = Utilities.formatDate(new Date(), tz, "yyyy-MM-dd HH:mm:ss");
  let created = 0,
    updated = 0,
    colored = 0,
    skipped = 0,
    removed = 0,
    errors = 0,
    writes = 0;
  let stoppedForQuota = false,
    stoppedForWrites = false;

  const uids = Object.keys(feedByUid);
  // Sort by start time to make deletes less likely later
  uids.sort((a, b) => feedByUid[a].start - feedByUid[b].start);

  for (let i = 0; i < uids.length; i++) {
    const uid = uids[i];
    const src = feedByUid[uid];
    const color = chooseColor_(src);

    try {
      const existingEv = calByUid[uid];
      if (existingEv) {
        let changed = false;

        const oldTitle = safeGet_(existingEv, "getTitle", "");
        if ((src.summary || "") !== oldTitle) {
          existingEv.setTitle(src.summary || "");
          changed = true;
          writes++;
        }

        const oldLoc = safeGet_(existingEv, "getLocation", "");
        if ((src.location || "") !== oldLoc) {
          existingEv.setLocation(src.location || "");
          changed = true;
          writes++;
        }

        const oldStart = safeGet_(existingEv, "getStartTime", null);
        const oldEnd = safeGet_(existingEv, "getEndTime", null);
        const oldStartTs = oldStart ? oldStart.getTime() : null;
        const oldEndTs = oldEnd ? oldEnd.getTime() : null;
        if (
          oldStartTs !== src.start.getTime() ||
          oldEndTs !== src.end.getTime()
        ) {
          existingEv.setTime(src.start, src.end);
          changed = true;
          writes++;
        }

        const desiredDesc = buildDescWithMarkers_(
          src.description || "",
          uid,
          nowStamp,
          icsUpdated
        );
        const curDesc = safeGet_(existingEv, "getDescription", "");
        if (curDesc !== desiredDesc) {
          existingEv.setDescription(desiredDesc);
          changed = true;
          writes++;
        }

        const oldColor = safeTry_(() => existingEv.getColor(), null);
        if (oldColor !== color) {
          existingEv.setColor(color);
          colored++;
          changed = true;
          writes++;
        }

        if (changed) updated++;
        else skipped++;
      } else {
        const options = {
          description: buildDescWithMarkers_(
            src.description || "",
            uid,
            nowStamp,
            icsUpdated
          ),
          location: src.location || "",
        };
        const newEv = cal.createEvent(
          src.summary || "",
          src.start,
          src.end,
          options
        );
        safeTry_(() => newEv.setColor(color));
        created++;
        writes += 2; // create + color
      }
    } catch (e) {
      errors++;
      if (errors <= 10) Logger.log("Upsert error (" + uid + "): " + e);
      if (String(e).match(/creating or deleting too many|Quota|Rate/i)) {
        stoppedForQuota = true;
        break;
      }
    }

    // Throttle
    if (writes > 0 && writes % SLEEP_EVERY_WRITES === 0)
      Utilities.sleep(SLEEP_MS);
    if (writes >= limits.writeBudgetLeft) {
      stoppedForWrites = true;
      break;
    }
  }

  // Deletes (only within window)
  if (!stoppedForQuota && !stoppedForWrites) {
    const calUids = Object.keys(calByUid);
    for (let j = 0; j < calUids.length; j++) {
      const uid = calUids[j];
      if (!(uid in feedByUid)) {
        try {
          calByUid[uid].deleteEvent();
          writes++; // delete is a write
          removed++; // track actual deletions
        } catch (e) {
          errors++;
          if (errors <= 10) Logger.log("Delete error (" + uid + "): " + e);
          if (String(e).match(/creating or deleting too many|Quota|Rate/i)) {
            stoppedForQuota = true;
            break;
          }
        }
        if (writes > 0 && writes % SLEEP_EVERY_WRITES === 0)
          Utilities.sleep(SLEEP_MS);
        if (writes >= limits.writeBudgetLeft) {
          stoppedForWrites = true;
          break;
        }
      }
    }
  }

  return {
    created,
    updated,
    colored,
    removed,
    skipped,
    errors,
    writes,
    stoppedForQuota,
    stoppedForWrites,
  };
}

/* ================= Semester/month planning ================= */

function listSemesterMonths_(semStart, semEnd) {
  const out = [];
  let cur = new Date(semStart.getFullYear(), semStart.getMonth(), 1, 0, 0, 0);
  while (cur <= semEnd) {
    const y = cur.getFullYear(),
      m = cur.getMonth();
    const start = new Date(y, m, 1, 0, 0, 0);
    const end = new Date(y, m + 1, 0, 23, 59, 59);
    out.push({
      start: start < semStart ? new Date(semStart) : start,
      end: end > semEnd ? new Date(semEnd) : end,
    });
    cur = new Date(y, m + 1, 1, 0, 0, 0);
  }
  return out;
}

function prioritizeMonths_(months, today) {
  if (!months.length) return months.slice();
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  // Find idx containing today; if not found, pick closest (start or end)
  let idx = -1;
  for (let i = 0; i < months.length; i++) {
    const ms = new Date(
      months[i].start.getFullYear(),
      months[i].start.getMonth(),
      months[i].start.getDate()
    );
    const me = new Date(
      months[i].end.getFullYear(),
      months[i].end.getMonth(),
      months[i].end.getDate()
    );
    if (d >= ms && d <= me) {
      idx = i;
      break;
    }
  }
  if (idx === -1) {
    idx = d < months[0].start ? 0 : months.length - 1;
  }

  // Order: current, then next months forward, then previous months backward
  const forward = months.slice(idx + 1);
  const backward = months.slice(0, idx).reverse();
  return [months[idx]].concat(forward).concat(backward);
}

/* ================= Utilities / parsing / coloring ================= */

function getOwnedCalendarByName_(name) {
  const list = CalendarApp.getCalendarsByName(name) || [];
  for (var i = 0; i < list.length; i++) {
    try {
      if (list[i].isOwnedByMe()) return list[i];
    } catch (_) {}
  }
  return null;
}

function fetchIcs_(url) {
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (res.getResponseCode() >= 400) {
    throw new Error(
      "Fetch failed: " + res.getResponseCode() + " " + res.getContentText()
    );
  }
  // ICS is UTF-8 (with BOM) from your generator; we read as UTF-8 text
  return res.getContentText("UTF-8");
}

/**
 * Reads the VCALENDAR-level "X-CALENDAR-UPDATED" header (added by your generator).
 * Returns empty string if absent.
 */
function readCalendarUpdated_(icsText) {
  if (!icsText) return "";
  // Unfold folded lines per RFC: CRLF + SP/HT
  const unfolded = icsText.replace(/\r\n[ \t]/g, "");
  const m = /^X-CALENDAR-UPDATED(?:;[^:\r\n]+)?:([^\r\n]*)/m.exec(unfolded);
  return m ? decodeText_(m[1].trim()) : "";
}

function parseICS_(text) {
  if (!text) return [];
  // Unfold folded lines: RFC allows CRLF + SP/HT to continue
  text = text.replace(/\r\n[ \t]/g, "");
  const out = [];
  const blocks = text.split(/BEGIN:VEVENT\r?\n/).slice(1);
  for (var i = 0; i < blocks.length; i++) {
    const raw = blocks[i].split(/END:VEVENT/)[0];

    function pick(prop) {
      // PROPNAME[:|;params:]value
      const rx = new RegExp(
        "^" + prop + "(?:;[^:\\r\\n]+)?:([\\s\\S]*?)$",
        "m"
      );
      const m = rx.exec(raw);
      return m ? m[1].trim() : "";
    }

    const uid = pick("UID");
    const sum = pick("SUMMARY");
    const desc = pick("DESCRIPTION");
    const loc = pick("LOCATION");
    const dtS = pick("DTSTART");
    const dtE = pick("DTEND");
    if (!uid || !dtS || !dtE) continue;

    const start = parseIcsDate_(dtS);
    const end = parseIcsDate_(dtE);
    if (!start || !end) continue;

    out.push({
      uid: uid,
      summary: decodeText_(sum),
      description: decodeText_(desc),
      location: decodeText_(loc),
      start: start,
      end: end,
    });
  }
  return out;
}

function parseIcsDate_(val) {
  if (!val) return null;
  if (/^\d{8}$/.test(val)) {
    const y = +val.slice(0, 4),
      m = +val.slice(4, 6) - 1,
      d = +val.slice(6, 8);
    return new Date(y, m, d, 0, 0, 0);
  }
  const m = /^(\d{8})T(\d{6})(Z)?$/.exec(val);
  if (!m) return null;
  const y = +m[1].slice(0, 4),
    mo = +m[1].slice(4, 6) - 1,
    d = +m[1].slice(6, 8);
  const hh = +m[2].slice(0, 2),
    mm = +m[2].slice(2, 4),
    ss = +m[2].slice(4, 6);
  return m[3] === "Z"
    ? new Date(Date.UTC(y, mo, d, hh, mm, ss))
    : new Date(y, mo, d, hh, mm, ss);
}

function decodeText_(s) {
  if (!s) return "";
  return s
    .replace(/\\n/gi, "\n")
    .replace(/\\,/g, ",")
    .replace(/\\;/g, ";")
    .replace(/\\\\/g, "\\");
}

/**
 * Build event description with stable markers.
 * Includes:
 *  - user (ICS) description
 *  - ICS Updated (from X-CALENDAR-UPDATED)
 *  - Synced at (this run's timestamp)
 *  - ICS-UID
 */
function buildDescWithMarkers_(userText, uid, stamp, icsUpdated) {
  // Remove any previous metadata block
  const clean = (userText || "").replace(
    /\n+--- Metadata ---[\s\S]*$/m,
    ""
  );
  const lines = [
    clean.trim(),
    "",
    "--- Metadata ---",
    "Plan generated: " + icsUpdated,
    "Synced at: " + stamp,
    "ICS-UID: " + uid,
  ];
  return lines.join("\n").trim();
}

function chooseColor_(ev) {
  const blob = (
    (ev.description || "") +
    " " +
    (ev.summary || "")
  ).toLowerCase();
  if (blob.indexOf("wyk") !== -1) return CalendarApp.EventColor.GRAY;
  if (blob.indexOf("ćw") !== -1) return CalendarApp.EventColor.GREEN;
  if (blob.indexOf("klin") !== -1) return CalendarApp.EventColor.YELLOW;
  if (/\b(gry|gim|pł|la)\b/.test(blob)) return CalendarApp.EventColor.ORANGE;
  return CalendarApp.EventColor.MAUVE;
}

function safeGet_(obj, method, fallback) {
  try {
    return obj[method]();
  } catch (_) {
    return fallback;
  }
}
function safeTry_(fn, val) {
  try {
    return fn();
  } catch (_) {
    return val;
  }
}
function isoDate_(d) {
  return d.toISOString().slice(0, 10);
}
