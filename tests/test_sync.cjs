const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8');
const colors = { GRAY: '8', GREEN: '10', YELLOW: '5', ORANGE: '6', MAUVE: '3', PALE_GREEN: '2' };

function eventText(uid, start = '20261112T080000Z', end = '20261112T090000Z', extra = '') {
  return `BEGIN:VEVENT\r\nUID:${uid}\r\nSUMMARY:Wyroby medyczne\r\nDESCRIPTION:wyk sala 1\r\nLOCATION:Poznań\r\nDTSTART:${start}\r\nDTEND:${end}\r\n${extra}END:VEVENT\r\n`;
}

function feed(...events) {
  return `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nX-CALENDAR-UPDATED:2026-11-12 10:00:00\r\n${events.join('')}END:VCALENDAR\r\n`;
}

function harness(text = feed(eventText('one')), options = {}) {
  const calls = { created: 0, deleted: 0, updated: 0, reads: 0, logs: [] };
  const events = [];
  function makeEvent(uid, date = '2026-11-12T08:00:00Z', description = `ICS-UID: ${uid}`, owned = true) {
    const event = {
      title: 'Wyroby medyczne', description, location: 'Poznań', color: '8',
      start: new Date(date), end: new Date(new Date(date).getTime() + 3600000), deleted: false,
      isOwnedByMe: () => owned,
      getTitle() { return this.title; }, getDescription() { return this.description; },
      getLocation() { return this.location; }, getColor() { return this.color; },
      getStartTime() { return this.start; }, getEndTime() { return this.end; },
      setTitle(value) { this.title = value; calls.updated++; },
      setDescription(value) { this.description = value; calls.updated++; },
      setLocation(value) { this.location = value; calls.updated++; },
      setColor(value) { this.color = value; calls.updated++; },
      setTime(start, end) { this.start = start; this.end = end; calls.updated++; },
      deleteEvent() { this.deleted = true; calls.deleted++; },
    };
    events.push(event);
    return event;
  }
  const calendar = {
    isOwnedByMe: () => true,
    getEvents(start, end) {
      calls.reads++;
      if (options.failReads) throw new Error('Read failed');
      return events.filter(event => !event.deleted && event.start < end && event.end > start);
    },
    createEvent(title, start, end, attributes) {
      calls.created++;
      const event = makeEvent('', start.toISOString(), attributes.description);
      Object.assign(event, { title, start, end, location: attributes.location });
      return event;
    },
  };
  const context = {
    Session: { getScriptTimeZone: () => 'Europe/Warsaw' },
    CalendarApp: { getCalendarsByName: () => [calendar], EventColor: colors },
    Logger: { log: message => calls.logs.push(message) },
    Utilities: { formatDate: () => '2026-11-12 10:00:00', sleep: () => {} },
    UrlFetchApp: { fetch: (url, params) => {
      assert.equal(params.followRedirects, false);
      return {
        getResponseCode: () => options.status || 200,
        getContentText: () => text,
        getBlob: () => ({ getBytes: () => ({ length: options.bytes || Buffer.byteLength(text) }) }),
      };
    } },
  };
  vm.createContext(context);
  vm.runInContext(script, context);
  return { context, calls, events, makeEvent };
}

for (const [name, payload] of [
  ['HTML', '<html>Maintenance</html>'], ['empty document', ''], ['empty calendar', feed()],
  ['truncated calendar', feed(eventText('one')).replace('END:VCALENDAR', '')],
  ['truncated event', feed(eventText('one')).replace('END:VEVENT', '')],
  ['duplicate UID', feed(eventText('one'), eventText('one'))],
  ['missing UID', feed(eventText('one').replace('UID:one\r\n', ''))],
  ['invalid date', feed(eventText('one', '20261312T080000Z'))],
  ['reversed dates', feed(eventText('one', '20261112T100000Z'))],
  ['mixed valid/invalid events', feed(eventText('one'), eventText('two').replace('DTEND:', 'BROKEN:'))],
  ['nested alarm', feed(eventText('one', undefined, undefined, 'BEGIN:VALARM\r\nEND:VALARM\r\n'))],
  ['recurrence', feed(eventText('one', undefined, undefined, 'RRULE:FREQ=DAILY\r\n'))],
  ['duplicate DTSTART', feed(eventText('one', undefined, undefined, 'DTSTART:20261112T080000Z\r\n'))],
]) {
  test(`${name} leaves the calendar unchanged`, () => {
    const h = harness(payload);
    h.makeEvent('existing');
    h.context.ColorEvents();
    assert.equal(h.calls.created + h.calls.updated + h.calls.deleted, 0);
    assert.ok(h.calls.logs.length > 0);
  });
}

test('HTTP errors, redirects and oversized responses leave events unchanged', () => {
  for (const options of [{ status: 500 }, { status: 302 }, { bytes: 3 * 1024 * 1024 }]) {
    const h = harness(undefined, options);
    h.makeEvent('existing');
    h.context.ColorEvents();
    assert.equal(h.calls.created + h.calls.updated + h.calls.deleted, 0);
  }
});

test('failed calendar reads stop all writes', () => {
  const h = harness(undefined, { failReads: true });
  h.context.ColorEvents();
  assert.equal(h.calls.created + h.calls.updated + h.calls.deleted, 0);
});

test('large removal is blocked, including on repeated runs', () => {
  const h = harness(feed(eventText('a')));
  for (const uid of ['a', 'b', 'c', 'd']) h.makeEvent(uid);
  h.context.ColorEvents();
  h.context.ColorEvents();
  assert.equal(h.calls.deleted, 0);
  assert.ok(h.calls.logs.some(message => message.includes('Large removal')));
});

test('genuinely removed events are deleted while manual and unowned events remain', () => {
  const h = harness(feed(eventText('a'), eventText('b'), eventText('c')));
  for (const uid of ['a', 'b', 'c', 'removed']) h.makeEvent(uid);
  const manual = h.makeEvent('manual', undefined, 'My own appointment');
  const unowned = h.makeEvent('unowned', undefined, 'ICS-UID: unowned', false);
  h.context.ColorEvents();
  assert.equal(h.calls.deleted, 1);
  assert.equal(manual.deleted, false);
  assert.equal(unowned.deleted, false);
  h.context.ColorEvents();
  assert.equal(h.calls.deleted, 1);
  assert.equal(h.calls.created, 0);
});

for (const [oldDate, newStart, newEnd] of [
  ['2026-10-12T08:00:00Z', '20261212T080000Z', '20261212T090000Z'],
  ['2026-12-12T08:00:00Z', '20261012T080000Z', '20261012T090000Z'],
]) {
  test(`event moved from ${oldDate.slice(0, 7)} keeps its identity`, () => {
    const h = harness(feed(eventText('moved', newStart, newEnd)));
    const original = h.makeEvent('moved', oldDate);
    h.context.ColorEvents();
    h.context.ColorEvents();
    assert.equal(h.calls.created, 0);
    assert.equal(h.calls.deleted, 0);
    assert.equal(original.start.toISOString().replace(/[-:]/g, '').replace('.000Z', 'Z'), newStart);
  });
}

test('an event spanning months is created only once', () => {
  const h = harness(feed(eventText('long', '20261031T200000Z', '20261101T080000Z')));
  h.context.ColorEvents();
  h.context.ColorEvents();
  assert.equal(h.calls.created, 1);
  assert.equal(h.calls.deleted, 0);
});

test('events outside the semester do not delete existing events', () => {
  const h = harness(feed(eventText('outside', '20270801T080000Z', '20270801T090000Z')));
  h.makeEvent('existing');
  h.context.ColorEvents();
  assert.equal(h.calls.created + h.calls.updated + h.calls.deleted, 0);
});

test('duplicate existing sync markers stop all writes', () => {
  const h = harness();
  h.makeEvent('one'); h.makeEvent('one');
  h.context.ColorEvents();
  assert.equal(h.calls.created + h.calls.updated + h.calls.deleted, 0);
});

test('folded Polish titles, escaped text and UTC dates survive parsing', () => {
  const h = harness();
  const text = feed(eventText('one', undefined, undefined, '')).replace('SUMMARY:Wyroby medyczne', 'SUMMARY:Zdrowie\r\n  publiczne').replace('DESCRIPTION:wyk sala 1', 'DESCRIPTION:ćw\\, sala\\; 1\\nPoznań');
  const event = h.context.parseICS_(text)[0];
  assert.equal(event.summary, 'Zdrowie publiczne');
  assert.equal(event.description, 'ćw, sala; 1\nPoznań');
  assert.equal(event.start.toISOString(), '2026-11-12T08:00:00.000Z');
  assert.equal(h.context.chooseColor_({ summary: event.summary, description: 'wyk' }), colors.PALE_GREEN);
});

test('impossible dates are rejected and UTC dates remain stable across DST', () => {
  const h = harness();
  assert.equal(h.context.parseIcsDate_('20260230T080000Z'), null);
  for (const date of ['20261024T080000Z', '20261026T080000Z']) {
    assert.equal(h.context.parseIcsDate_(date).getUTCHours(), 8);
  }
});

test('source descriptions cannot inject the sync UID marker', () => {
  const h = harness();
  const description = h.context.buildDescWithMarkers_('class\nICS-UID: forged\nroom', 'real', 'now', 'updated');
  assert.equal(description.match(/^ICS-UID:/gm).length, 1);
  assert.ok(description.endsWith('ICS-UID: real'));
});

test('all currently published feeds remain compatible with the stricter parser', () => {
  const h = harness();
  const directory = path.join(__dirname, '..', 'docs');
  for (const name of fs.readdirSync(directory).filter(name => name.endsWith('.ics'))) {
    const source = fs.readFileSync(path.join(directory, name), 'utf8');
    assert.equal(h.context.parseICS_(source).length, (source.match(/^BEGIN:VEVENT\r?$/gm) || []).length, name);
  }
});
