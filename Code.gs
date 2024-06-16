function ColorEvents() {
  var calendars = CalendarApp.getAllOwnedCalendars();

  var today = new Date();
  var two_weeks = new Date();

  today.setDate(today.getDate());
  two_weeks.setDate(two_weeks.getDate() + 14);

  for (var i=0; i<calendars.length; i++) {
    var calendar = calendars[i];
    var events = calendar.getEvents(today, two_weeks);
    for (var j=0; j<events.length; j++) {
      var e = events[j];
      var description = e.getDescription();
     if (description.includes("wyk")) {
        e.setColor(CalendarApp.EventColor.GRAY);
      }
     else if (description.includes("ćw")) {
        e.setColor(CalendarApp.EventColor.RED);
      }
     else if (description.includes("klin")) {
        e.setColor(CalendarApp.EventColor.BLUE);
      }
     else {
        e.setColor(CalendarApp.EventColor.PALE_RED);
     }
    }
    Logger.log("Changed " + events.length + " events.");
  }
}
