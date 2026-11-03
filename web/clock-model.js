/* Deterministic teaching model. All times are simulated; no VM telemetry is read. */
(function (root) {
  "use strict";

  class ClockModel {
    constructor() {
      this.reset();
    }

    reset() {
      this.time = 0;
      this.interval = 1;
      this.drift = 1;
      this.sync = false;
      this.busy = false;
      this.policy = "baseline";
      this.route = "A";
      this.lowPolls = 0;
      this.nextPoll = 2;
      this.nextSync = 1;
      this.nextHistory = 0.1;
      this.clients = [100, 100, 100].map((offset, index) => ({
        offset,
        rate: [20, -15, 30][index],
        pending: null,
        replies: 0,
        correction: null,
        rtt: null,
        residual: null,
      }));
      this.history = [];
      this.record();
    }

    setInterval(value) {
      if (!Number.isFinite(value) || value < 0.5 || value > 3)
        throw new RangeError(
          "Sync interval must be between 0.5 and 3 seconds.",
        );
      this.interval = value;
      this.nextSync = this.time + value;
    }

    setDrift(value) {
      if (!Number.isFinite(value) || value < 0 || value > 2)
        throw new RangeError("Drift multiplier must be between 0 and 2.");
      this.drift = value;
    }

    setSync(enabled) {
      this.sync = Boolean(enabled);
      this.nextSync = this.time + this.interval;
      if (this.sync) this.send();
      // An exchange already in flight can still complete after sending stops.
    }

    setPolicy(policy) {
      if (!["baseline", "optimized"].includes(policy))
        throw new RangeError("Unknown network policy.");
      this.policy = policy;
      if (policy === "baseline") this.route = "A";
      this.lowPolls = 0;
    }

    send() {
      const forward = this.busy && this.route === "A" ? 100 : 10;
      const reverse = 10;
      const processing = 2;
      for (const client of this.clients) {
        if (client.pending) continue;
        client.pending = {
          sent: this.time,
          arrival: this.time + (forward + reverse + processing) / 1000,
          forward,
          reverse,
          processing,
          t0: this.time + client.offset / 1000,
        };
      }
    }

    record() {
      this.history.push({
        time: this.time,
        errors: this.clients.map((c) => c.offset),
      });
      // Keep a sliding minute, with a bounded number of correction vertices.
      while (this.history.length > 1 && this.history[1].time < this.time - 60)
        this.history.shift();
    }

    advance(seconds) {
      if (!Number.isFinite(seconds) || seconds < 0 || seconds > 60)
        throw new RangeError("Advance must be between 0 and 60 seconds.");
      const target = this.time + seconds;
      const epsilon = 1e-8;
      while (this.time < target - epsilon) {
        const arrival = Math.min(
          ...this.clients.map((c) => c.pending?.arrival ?? Infinity),
        );
        const next = Math.min(
          target,
          arrival,
          this.nextPoll,
          this.nextHistory,
          this.sync ? this.nextSync : Infinity,
        );
        const elapsed = Math.max(0, next - this.time);
        for (const client of this.clients)
          client.offset += client.rate * this.drift * elapsed;
        this.time = next;

        if (arrival <= this.time + epsilon) {
          this.record(); // Preserve the jump at correction, not a smoothed line.
          for (const client of this.clients) {
            const packet = client.pending;
            if (!packet || packet.arrival > this.time + epsilon) continue;
            const t1 = packet.sent + packet.forward / 1000;
            const t2 = t1 + packet.processing / 1000;
            const t3 = this.time + client.offset / 1000;
            client.correction = (t1 - packet.t0 + (t2 - t3)) * 500;
            client.rtt = (t3 - packet.t0 - (t2 - t1)) * 1000;
            client.offset += client.correction;
            client.residual = client.offset;
            client.replies += 1;
            client.pending = null;
          }
          this.record();
        }
        if (this.nextPoll <= this.time + epsilon) {
          if (this.policy === "optimized") {
            if (this.busy) {
              this.route = "B";
              this.lowPolls = 0;
            } else if (this.route === "B" && ++this.lowPolls >= 3)
              this.route = "A";
          }
          this.nextPoll += 2;
        }
        if (this.sync && this.nextSync <= this.time + epsilon) {
          this.send();
          this.nextSync += this.interval;
        }
        if (this.nextHistory <= this.time + epsilon) {
          this.record();
          this.nextHistory += 0.1;
        }
      }
    }
  }

  if (typeof module !== "undefined" && module.exports)
    module.exports = ClockModel;
  else root.ClockModel = ClockModel;
})(typeof window !== "undefined" ? window : this);
