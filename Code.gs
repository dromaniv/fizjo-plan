function ColorEvents() {
  var calendars = CalendarApp.getAllOwnedCalendars();
  
  var now = new Date();
  var fiveMonthsFromNow = new Date();
  fiveMonthsFromNow.setMonth(fiveMonthsFromNow.getMonth() + 5);

  // Regex patterns
  var hashRegex = /Hash:\s*([a-f0-9]{8})/;
  var generatedAtRegex = /Generated at:\s*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})/;

  for (var ci = 0; ci < calendars.length; ci++) {
    var calendar = calendars[ci];
    var events = calendar.getEvents(now, fiveMonthsFromNow);
    var eventMap = {};
    var processedCount = 0;
    var deletedCount = 0;
    var errorCount = 0;

    for (var ei = 0; ei < events.length; ei++) {
      var e = events[ei];
      var description;

      try {
        description = e.getDescription();
      } catch (err) {
        // Event might already be gone
        errorCount++;
        continue;
      }

      // Only events from fizjo-plan
      if (!description || description.indexOf("fizjo-plan") === -1) {
        continue;
      }

      // Extract hash
      var hashMatch = hashRegex.exec(description);
      if (!hashMatch) {
        continue;
      }
      var eventHash = hashMatch[1];

      // Extract "Generated at" timestamp (fallback = creation date)
      var genMatch = generatedAtRegex.exec(description);
      var currentGenAt = genMatch ? new Date(genMatch[1]) : e.getDateCreated();

      if (eventMap[eventHash]) {
        var existing = eventMap[eventHash];
        if (currentGenAt > existing.generatedAt) {
          // Current is newer → delete old one
          deletedCount++;
          try {
            existing.event.deleteEvent();
          } catch (err) {
            errorCount++;
          }
          eventMap[eventHash] = { event: e, generatedAt: currentGenAt };
        } else {
          // Existing is newer → delete current
          deletedCount++;
          try {
            e.deleteEvent();
          } catch (err) {
            errorCount++;
          }
          continue;
        }
      } else {
        eventMap[eventHash] = { event: e, generatedAt: currentGenAt };
      }

      // Coloring logic
      var eventColor = CalendarApp.EventColor.MAUVE; // default
      if (description.indexOf("wyk") !== -1) {
        eventColor = CalendarApp.EventColor.GRAY;
      } else if (description.indexOf("ćw ") !== -1) {
        eventColor = CalendarApp.EventColor.GREEN;
      } else if (description.indexOf("klin") !== -1) {
        eventColor = CalendarApp.EventColor.YELLOW;
      }
      try {
        if (e.getColor() !== eventColor) {
          e.setColor(eventColor);
        }
      } catch (err) {
        errorCount++;
      }

      processedCount++;
    }

    Logger.log(
      "Calendar: " + calendar.getName() +
      " → Processed: " + processedCount +
      " | Deleted: " + deletedCount +
      " | Errors: " + errorCount
    );
  }
}