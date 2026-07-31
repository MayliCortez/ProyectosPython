/*
 * queue-engine.js — Motor de cola por lotes.
 *
 * Recibe una lista de "jobs" y los procesa con:
 *   - concurrencia configurable (1..6)
 *   - reintentos automaticos por job (con backoff)
 *   - delay aleatorio entre envios (anti rate-limit)
 *   - pausa / reanudar / detener
 *   - eventos de estado en vivo (queued -> generating -> downloading -> completed | failed)
 *
 * Es agnostico de Google Flow: la funcion `processJob(job, ctx)` la inyecta
 * quien lo use (en la extension = flow-adapter). Asi es 100% testeable.
 *
 * UMD (content + node tests).
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.AFS = Object.assign(root.AFS || {}, { QueueEngine: mod.QueueEngine });
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const STATUS = {
    QUEUED: "queued",
    GENERATING: "generating",
    DOWNLOADING: "downloading",
    COMPLETED: "completed",
    FAILED: "failed",
    SKIPPED: "skipped",
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function randBetween(min, max) {
    if (max <= min) return min;
    return Math.floor(min + Math.random() * (max - min));
  }

  let _seq = 0;
  function nextId() {
    _seq += 1;
    return "job_" + Date.now().toString(36) + "_" + _seq;
  }

  class QueueEngine {
    /**
     * @param {object} options
     * @param {(job, ctx) => Promise<any>} options.processJob
     * @param {number} [options.concurrency=1]
     * @param {number} [options.retries=3]
     * @param {[number,number]} [options.delayMs=[3000,7000]] rango de delay entre envios
     * @param {(evt) => void} [options.onEvent] callback de estado
     * @param {() => number} [options.now] inyectable para tests
     */
    constructor(options) {
      options = options || {};
      if (typeof options.processJob !== "function") {
        throw new Error("QueueEngine requiere processJob(job, ctx)");
      }
      this.processJob = options.processJob;
      this.concurrency = Math.max(1, Math.min(6, options.concurrency || 1));
      this.retries = options.retries == null ? 3 : options.retries;
      this.delayMs = options.delayMs || [3000, 7000];
      this.onEvent = options.onEvent || function () {};
      this._now = options.now || (() => Date.now());

      this.jobs = [];
      this._running = false;
      this._paused = false;
      this._stopped = false;
      this._active = 0;
      this._cursor = 0;
      this._donePromise = null;
      this._resolveDone = null;
    }

    /** Agrega jobs. Cada job puede traer { prompt, images, meta }. */
    add(items) {
      const list = Array.isArray(items) ? items : [items];
      const created = list.map((it) => {
        const base = typeof it === "string" ? { prompt: it } : Object.assign({}, it);
        return Object.assign(base, {
          id: base.id || nextId(),
          status: STATUS.QUEUED,
          attempts: 0,
          error: null,
          result: null,
          createdAt: this._now(),
        });
      });
      this.jobs.push(...created);
      created.forEach((j) => this._emit("added", j));
      return created;
    }

    /** Elimina un job pendiente por id (no afecta a los ya en curso). */
    remove(id) {
      const idx = this.jobs.findIndex((j) => j.id === id);
      if (idx >= 0 && this.jobs[idx].status === STATUS.QUEUED) {
        const [removed] = this.jobs.splice(idx, 1);
        if (idx < this._cursor) this._cursor--;
        this._emit("removed", removed);
        return true;
      }
      return false;
    }

    clear() {
      if (this._running) throw new Error("No se puede limpiar mientras corre");
      this.jobs = [];
      this._cursor = 0;
    }

    get counts() {
      const c = { total: this.jobs.length };
      for (const k of Object.values(STATUS)) c[k] = 0;
      for (const j of this.jobs) c[j.status] = (c[j.status] || 0) + 1;
      return c;
    }

    _emit(type, job) {
      try {
        this.onEvent({ type, job, counts: this.counts });
      } catch (e) {
        /* nunca dejar que un handler rompa el motor */
      }
    }

    _setStatus(job, status, extra) {
      job.status = status;
      if (extra) Object.assign(job, extra);
      this._emit("status", job);
    }

    /** Arranca el procesamiento. Devuelve una promesa que resuelve al terminar. */
    async start() {
      if (this._running) return this._donePromise;
      this._running = true;
      this._paused = false;
      this._stopped = false;
      this._donePromise = new Promise((res) => (this._resolveDone = res));

      const workers = [];
      for (let i = 0; i < this.concurrency; i++) workers.push(this._worker(i));
      await Promise.all(workers);

      this._running = false;
      this._emit("finished", null);
      if (this._resolveDone) this._resolveDone(this.counts);
      return this.counts;
    }

    async _worker(workerIndex) {
      while (true) {
        if (this._stopped) return;
        // Pausa cooperativa.
        while (this._paused && !this._stopped) await sleep(200);
        if (this._stopped) return;

        const job = this._takeNext();
        if (!job) return; // no quedan pendientes

        this._active++;
        await this._runJob(job, workerIndex);
        this._active--;

        // Delay aleatorio antes del siguiente envio (anti rate-limit).
        const [dmin, dmax] = this.delayMs;
        if (dmax > 0 && this._hasPending()) {
          const wait = randBetween(dmin, dmax);
          this._emit("delay", { id: job.id, waitMs: wait });
          await sleep(wait);
        }
      }
    }

    _takeNext() {
      while (this._cursor < this.jobs.length) {
        const job = this.jobs[this._cursor++];
        if (job.status === STATUS.QUEUED) return job;
      }
      return null;
    }

    _hasPending() {
      return this.jobs.some((j) => j.status === STATUS.QUEUED);
    }

    async _runJob(job, workerIndex) {
      const maxAttempts = this.retries + 1;
      while (job.attempts < maxAttempts) {
        job.attempts++;
        this._setStatus(job, STATUS.GENERATING);
        try {
          const ctx = {
            workerIndex,
            attempt: job.attempts,
            setDownloading: () => this._setStatus(job, STATUS.DOWNLOADING),
            isStopped: () => this._stopped,
          };
          const result = await this.processJob(job, ctx);
          this._setStatus(job, STATUS.COMPLETED, { result, error: null });
          return;
        } catch (err) {
          job.error = (err && err.message) || String(err);
          if (this._stopped) {
            this._setStatus(job, STATUS.SKIPPED);
            return;
          }
          if (job.attempts >= maxAttempts) {
            this._setStatus(job, STATUS.FAILED);
            return;
          }
          // Backoff exponencial suave antes de reintentar.
          this._emit("retry", job);
          await sleep(Math.min(15000, 1000 * Math.pow(2, job.attempts)));
        }
      }
    }

    pause() {
      this._paused = true;
      this._emit("paused", null);
    }

    resume() {
      this._paused = false;
      this._emit("resumed", null);
    }

    stop() {
      this._stopped = true;
      this._paused = false;
      this._emit("stopped", null);
    }
  }

  QueueEngine.STATUS = STATUS;
  QueueEngine.randBetween = randBetween;
  return { QueueEngine };
});
