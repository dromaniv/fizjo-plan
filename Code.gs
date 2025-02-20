function ColorEvents() {
  var calendars = CalendarApp.getAllOwnedCalendars();
  
  // Define date range: from 'now' to two months later
  var now = new Date();
  var twoMonthsFromNow = new Date();
  twoMonthsFromNow.setMonth(twoMonthsFromNow.getMonth() + 2);
  
  // Process each owned calendar
  calendars.forEach(function(calendar) {
    // Fetch all events in the date range
    var events = calendar.getEvents(now, twoMonthsFromNow);
    
    // This map will track "zajęcia" events by their start time
    var eventMap = {};
    
    // Go through each event
    events.forEach(function(e) {
      var description = e.getDescription();
      
      // Only process events that have "zajęcia" in the description
      if (!description.includes("zajęcia")) {
        return;  // Skip if it doesn't match
      }
      
      // Use the event's start time (string) as a key to detect duplicates
      var startTimeKey = e.getStartTime().toString();
      
      if (eventMap[startTimeKey]) {
        // If there's already an event at this start time,
        // keep the one that was created later.
        var existingEvent = eventMap[startTimeKey];
        if (e.getDateCreated() > existingEvent.getDateCreated()) {
          existingEvent.deleteEvent();
          eventMap[startTimeKey] = e;
        } else {
          e.deleteEvent();
          return; // Stop handling the current (older) event
        }
      } else {
        eventMap[startTimeKey] = e;
      }
      
      // Determine a color based on keywords
      var eventColor = CalendarApp.EventColor.MAUVE;  // Default
      if (description.includes("wyk")) {
        eventColor = CalendarApp.EventColor.GRAY;
      } else if (description.includes("ćw ")) {
        eventColor = CalendarApp.EventColor.GREEN;
      } else if (description.includes("klin")) {
        eventColor = CalendarApp.EventColor.YELLOW;
      }
      
      // Only set if needed
      if (e.getColor() !== eventColor) {
        e.setColor(eventColor);
      }
    });
    
    Logger.log("Processed " + events.length + " events in calendar: " + calendar.getName());
  });
}
