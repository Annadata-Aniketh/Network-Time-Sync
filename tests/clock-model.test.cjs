/* Run with: node --test tests/clock-model.test.cjs (no browser or packages needed). */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const ClockModel = require("../web/clock-model.js");
const close = (actual, expected, tolerance = 1e-6) =>
  assert.ok(
    Math.abs(actual - expected) < tolerance,
    `${actual} != ${expected}`,
  );

test("without synchronization the three clocks drift at their own rates", () => {
  const model = new ClockModel();
  model.advance(2);
  [140, 70, 160].forEach((error, i) => close(model.clients[i].offset, error));
  assert.equal(model.clients[0].replies, 0);
});
test("four timestamps correct the initial gap; clocks drift again between replies", () => {
  const model = new ClockModel();
  model.setSync(true);
  model.advance(0.022);
  assert.equal(model.clients[0].replies, 1);
  close(model.clients[0].offset, 0.22);
  close(model.clients[1].offset, -0.165);
  close(model.clients[0].rtt, 20.44);
  model.advance(0.5);
  close(model.clients[0].offset, 10.22);
});
test("unequal directional delays leave half their difference as offset bias", () => {
  const model = new ClockModel();
  model.setDrift(0);
  model.busy = true;
  model.send();
  model.advance(0.112);
  model.clients.forEach((client) => close(client.offset, 45));
});
test("optimized policy reroutes on a poll, then restores after three clear polls", () => {
  const model = new ClockModel();
  model.setDrift(0);
  model.setPolicy("optimized");
  model.busy = true;
  model.setSync(true);
  model.advance(1.99);
  assert.equal(model.route, "A");
  model.advance(0.01);
  assert.equal(model.route, "B");
  model.advance(0.022);
  model.clients.forEach((client) => close(client.offset, 0));
  model.busy = false;
  model.advance(3.978);
  assert.equal(model.lowPolls, 2);
  assert.equal(model.route, "B");
  model.advance(2);
  assert.equal(model.route, "A");
});
test("baseline never reroutes and changing back to baseline restores A", () => {
  const model = new ClockModel();
  model.busy = true;
  model.advance(6);
  assert.equal(model.route, "A");
  model.setPolicy("optimized");
  model.advance(2);
  assert.equal(model.route, "B");
  model.setPolicy("baseline");
  assert.equal(model.route, "A");
});
test("stop synchronization lets an in-flight reply finish but sends no further requests", () => {
  const model = new ClockModel();
  model.setSync(true);
  model.setSync(false);
  model.advance(3);
  model.clients.forEach((client) => assert.equal(client.replies, 1));
  assert.ok(model.clients[0].offset > 50);
});
test("zero drift plus symmetric delay stays aligned; short intervals send more requests", () => {
  const model = new ClockModel();
  model.setDrift(0);
  model.setInterval(0.5);
  model.setSync(true);
  model.advance(10);
  model.clients.forEach((client) => {
    close(client.offset, 0);
    assert.equal(client.replies, 20);
  });
});
test("reset restores all controls, history, and pending exchanges", () => {
  const model = new ClockModel();
  model.setSync(true);
  model.busy = true;
  model.setDrift(2);
  model.advance(4);
  model.reset();
  assert.equal(model.time, 0);
  assert.equal(model.sync, false);
  assert.equal(model.busy, false);
  assert.equal(model.interval, 1);
  assert.equal(model.drift, 1);
  assert.equal(model.history.length, 1);
  model.clients.forEach((c) => {
    assert.equal(c.offset, 100);
    assert.equal(c.pending, null);
  });
});
test("frame rate does not change simulation results and history stays bounded", () => {
  const a = new ClockModel(),
    b = new ClockModel();
  a.setSync(true);
  b.setSync(true);
  a.advance(30);
  for (let i = 0; i < 1800; i++) b.advance(1 / 60);
  a.clients.forEach((c, i) => {
    close(c.offset, b.clients[i].offset, 1e-4);
    assert.equal(c.replies, b.clients[i].replies);
  });
  for (let i = 0; i < 10; i++) a.advance(60);
  assert.ok(a.history.length < 1200);
  assert.ok(a.history[0].time >= a.time - 60.2);
});
test("invalid controls and deltas cannot poison the model or hang the event loop", () => {
  const model = new ClockModel();
  for (const invalid of [NaN, Infinity, -1, 61])
    assert.throws(() => model.advance(invalid), RangeError);
  for (const invalid of [NaN, Infinity, 0, 4])
    assert.throws(() => model.setInterval(invalid), RangeError);
  for (const invalid of [NaN, Infinity, -1, 3])
    assert.throws(() => model.setDrift(invalid), RangeError);
  assert.throws(() => model.setPolicy("typo"), RangeError);
  model.advance(0);
  assert.equal(model.time, 0);
});
