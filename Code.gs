function ColorEvents() {
  // Hardcoded inclusive range: 30 Sep 2025 00:00:00 → 28 Feb 2026 23:59:59
  const rangeStart = new Date(2025, 8, 30, 0, 0, 0);   // month is 0-based (8 = Sep)
  const rangeEnd   = new Date(2026, 1, 28, 23, 59, 59); // 1 = Feb

  // Constants & precompiled regex (avoid creating per event)
  const TAG = "fizjo-plan";                  // exact ASCII hyphen
  const HASH_RX = /Hash:\s*([a-f0-9]{8})/;   // title+time hash already provided by your generator
  const GEN_RX  = /Generated at:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/;

  // Fast manual parser to avoid Date.parse quirks & locale costs
  function parseGeneratedAt(s) {
    const m = GEN_RX.exec(s);
    if (!m) return null;
    // m[1] is "YYYY-MM-DD HH:MM:SS"
    const t = m[1];
    // Split once without allocations from regex groups beyond exec above
    const y = +t.substring(0, 4);
    const mo = +t.substring(5, 7) - 1;
    const d = +t.substring(8, 10);
    const h = +t.substring(11, 13);
    const mi = +t.substring(14, 16);
    const s2 = +t.substring(17, 19);
    return new Date(y, mo, d, h, mi, s2);
  }

  const calendars = CalendarApp.getAllOwnedCalendars();

  for (let ci = 0; ci < calendars.length; ci++) {
    const calendar = calendars[ci];

    let events;
    try {
      events = calendar.getEvents(rangeStart, rangeEnd);
    } catch (err) {
      // Skip this calendar on fetch failure
      Logger.log("ERROR fetching events for calendar " + calendar.getName() + ": " + err);
      continue;
    }

    // Map: hash -> { event: CalendarEvent, genAt: Date }
    const byHash = Object.create(null);
    let processed = 0, deleted = 0, errors = 0;

    for (let i = 0, n = events.length; i < n; i++) {
      const ev = events[i];

      // Read description defensively (deleted/ghost events can throw)
      let desc;
      try {
        desc = ev.getDescription();
      } catch (e) {
        errors++;
        continue;
      }

      // Fast early filters (string checks before regex)
      if (!desc || desc.indexOf(TAG) === -1) continue;
      if (desc.indexOf("Hash:") === -1) continue;

      const hm = HASH_RX.exec(desc);
      if (!hm) continue;
      const hash = hm[1];

      // Prefer explicit "Generated at", otherwise fall back to creation time
      let genAt = parseGeneratedAt(desc);
      if (!genAt) {
        try {
          genAt = ev.getDateCreated();
        } catch (e) {
          errors++;
          continue;
        }
      }

      // De-dupe: keep later "Generated at" for same hash
      const existing = byHash[hash];
      if (existing) {
        if (genAt > existing.genAt) {
          // Current is newer → delete the existing
          deleted++;
          try { existing.event.deleteEvent(); } catch (e) { errors++; }
          byHash[hash] = { event: ev, genAt: genAt };
        } else if (genAt < existing.genAt) {
          // Existing is newer → delete current
          deleted++;
          try { ev.deleteEvent(); } catch (e) { errors++; }
          continue;
        } else {
          // genAt is exactly the same → delete the duplicate current
          deleted++;
          try { ev.deleteEvent(); } catch (e) { errors++; }
          continue;
        }
      } else {
        byHash[hash] = { event: ev, genAt: genAt };
      }

      // Read title once (case-important check for "Gr")
      let title = "";
      try {
        title = ev.getTitle() || "";
      } catch (e) {
        // If title read fails, keep it empty and continue with desc-based rules
        title = "";
      }

      // Lightweight color decision (no extra allocations)
      let color = CalendarApp.EventColor.MAUVE;
      // If title contains exact "Gr" (case-sensitive)
      if (title.indexOf("Gr") !== -1) {
        color = CalendarApp.EventColor.ORANGE;
      } else {
        // Order matters only if overlaps; keep simple substring checks
        if (desc.indexOf("wyk") !== -1) {
          color = CalendarApp.EventColor.GRAY;
        } else if (desc.indexOf("ćw ") !== -1) {
          color = CalendarApp.EventColor.GREEN;
        } else if (desc.indexOf("klin") !== -1) {
          color = CalendarApp.EventColor.YELLOW;
        }
      }

      // Minimize service calls: only set when different
      try {
        if (ev.getColor() !== color) ev.setColor(color);
      } catch (e) {
        errors++;
      }

      processed++;
    }

    // Single concise per-calendar log (no global summary)
    Logger.log(
      "Calendar: " + calendar.getName() +
      " | processed: " + processed +
      " | deleted: " + deleted +
      " | errors: " + errors
    );
  }
}