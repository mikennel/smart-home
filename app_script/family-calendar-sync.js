// --- CONFIG ---
// Put the calendar IDs (email addresses) of the calendars you want to copy FROM:
const SOURCE_CALENDAR_IDS = ['michaelkk42@gmail.com', 'brittanygk42@gmail.com'];

// ID of the shared calendar to sync INTO (e.g. the "Family" calendar ID).
// You can use the calendar's "calendar ID" from Calendar settings.
const TARGET_CALENDAR_ID = 'family01152826815456006742@group.calendar.google.com';

// How far forward to sync (days)
const LOOKAHEAD_DAYS = 365;

// Marker text used to tag events created by this script (used for safe delete/replace)
const SYNC_MARKER = 'SYNCED_BY_APPSCRIPT:calendar-sync-v1';

// --- MAIN ---
function syncCalendarsDaily() {
  const now = new Date();
  const end = new Date();
  end.setDate(now.getDate() + LOOKAHEAD_DAYS);

  const targetCal = CalendarApp.getCalendarById(TARGET_CALENDAR_ID);
  if (!targetCal) {
    throw new Error('Target calendar not found. Check TARGET_CALENDAR_ID.');
  }

  // 1) Remove earlier events previously created by this script in the target range
  const existing = targetCal.getEvents(now, end);
  for (let ev of existing) {
    const desc = ev.getDescription() || '';
    if (desc.indexOf(SYNC_MARKER) !== -1) {
      // delete only events previously created by this script
      ev.deleteEvent();
      Utilities.sleep(100); // Add 100ms delay between deletions
    }
  }

  // 2) Read each source calendar and copy events into target
  SOURCE_CALENDAR_IDS.forEach(function(sourceId) {
    const sourceCal = CalendarApp.getCalendarById(sourceId);
    if (!sourceCal) {
      Logger.log('Source calendar not found or not shared: ' + sourceId);
      return;
    }

    const events = sourceCal.getEvents(now, end);
    events.forEach(function(ev) {
      try {
        // gather metadata
        const title = ev.getTitle();
        const start = ev.getStartTime();
        const endTime = ev.getEndTime();
        const location = ev.getLocation();
        const guests = ev.getGuestList().map(g => g.getEmail()).filter(Boolean);
        const originalId = ev.getId(); // source event id
        const originalUrl = ev.getHtmlLink ? ev.getHtmlLink() : '';
        const isAllDay = typeof ev.isAllDayEvent === 'function' ? ev.isAllDayEvent() : false;

        // build description preserving existing description + marker
        let desc = ev.getDescription() || '';
        
        // Include guest list in description for reference, but don't invite them
        if (guests.length) {
          desc += '\n\nORIGINAL_GUESTS: ' + guests.join(', ');
        }
        
        desc += '\n\n' + SYNC_MARKER + '|' + sourceId + '|' + originalId;
        if (originalUrl) desc += '\nSOURCE_URL: ' + originalUrl;

        const options = {
          description: desc,
          location: location
        };

        // create event on target WITHOUT inviting guests to prevent duplicate invitations
        let newEvent;
        if (isAllDay) {
          // all-day events
          const allDayStart = new Date(start.getFullYear(), start.getMonth(), start.getDate());
          newEvent = targetCal.createAllDayEvent(title, allDayStart, {description: desc});
        } else {
          newEvent = targetCal.createEvent(title, start, endTime, options);
        }

        // Add small delay between event creations to avoid rate limiting
        Utilities.sleep(100);

        // NOTE: Guests are NOT invited to prevent duplicate invitations
        // Original guest list is preserved in the event description for reference
      } catch (err) {
        Logger.log('Failed copying event: ' + err);
      }
    });
  });

  Logger.log('Calendar sync complete.');
}
