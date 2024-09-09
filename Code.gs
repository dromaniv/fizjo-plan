function ColorEvents() {
  var calendars = CalendarApp.getAllOwnedCalendars();

  var today = new Date();
  var two_weeks = new Date();

  today.setDate(today.getDate());
  two_weeks.setDate(two_weeks.getDate() + 14);

  for (var i = 0; i < calendars.length; i++) {
    var calendar = calendars[i];
    var events = calendar.getEvents(today, two_weeks);
    
    // Use a map to track duplicate events by title (with "(TP")
    var eventMap = {};

    for (var j = 0; j < events.length; j++) {
      var e = events[j];
      var description = e.getDescription();
      var title = e.getTitle();

      // Filter for events that contain "(TP" in their description
      if (description.includes("(TP")) {

        // If an event with the same title (with "(TP") already exists, compare creation times
        if (eventMap[title]) {
          var existingEvent = eventMap[title];

          // Compare the creation dates to keep the later one
          if (e.getDateCreated() > existingEvent.getDateCreated()) {
            // Keep the current event, delete the earlier one
            existingEvent.deleteEvent();
            eventMap[title] = e;  // Update map to keep the current event
          } else {
            // If the existing event is newer, delete the current one
            e.deleteEvent();
          }
        } else {
          // If no duplicate, add the event to the map
          eventMap[title] = e;
        }

        var eventColor;

        // Apply color based on description
        if (description.includes("Y2")) {
          eventColor = CalendarApp.EventColor.YELLOW;
        } else if (description.includes("Y3")) {
          eventColor = CalendarApp.EventColor.GREEN;
        } else if (description.includes("Y4")) {
          eventColor = CalendarApp.EventColor.RED;
        } else {
          eventColor = CalendarApp.EventColor.BLUE;  // Default color
        }

        // Only update color if it's different
        if (e.getColor() != eventColor) {
          e.setColor(eventColor);
        }
      }
    }
    Logger.log("Processed " + events.length + " events in calendar: " + calendar.getName());
  }
}
