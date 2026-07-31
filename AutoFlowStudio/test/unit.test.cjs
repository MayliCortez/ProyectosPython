/* unit.test.cjs — Pruebas unitarias sin framework (solo node + assert).
   Ejecuta: node test/unit.test.cjs  */
const assert = require("assert");
const path = require("path");

const prompts = require(path.join("..", "lib", "prompt-parser.js"));
const csv = require(path.join("..", "lib", "csv-parser.js"));
const { QueueEngine } = require(path.join("..", "lib", "queue-engine.js"));
const flow = require(path.join("..", "lib", "flow-adapter.js"));

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try {
    await fn();
    passed++;
    console.log("  \x1b[32m✓\x1b[0m " + name);
  } catch (e) {
    failed++;
    console.log("  \x1b[31m✗\x1b[0m " + name + "\n      " + e.message);
  }
}

(async () => {
  console.log("\nprompt-parser");
  await test("separa prompts por linea en blanco", () => {
    const r = prompts.parsePrompts("uno\n\ndos\n\ntres");
    assert.deepStrictEqual(r, ["uno", "dos", "tres"]);
  });
  await test("ignora lineas en blanco multiples y espacios", () => {
    const r = prompts.parsePrompts("  a \n\n\n\n b \n\n");
    assert.deepStrictEqual(r, ["a", "b"]);
  });
  await test("limpia numeracion inicial", () => {
    const r = prompts.parsePrompts("1. hola\n\n2) mundo\n\n- tres");
    assert.deepStrictEqual(r, ["hola", "mundo", "tres"]);
  });
  await test("mantiene multilinea dentro de un prompt", () => {
    const r = prompts.parsePrompts("linea A\nlinea B\n\notro");
    assert.deepStrictEqual(r, ["linea A\nlinea B", "otro"]);
  });
  await test("parseLines: una linea por prompt", () => {
    assert.deepStrictEqual(prompts.parseLines("a\nb\n\nc"), ["a", "b", "c"]);
  });
  await test("joinPrompts hace round-trip", () => {
    const list = ["x", "y", "z"];
    assert.deepStrictEqual(prompts.parsePrompts(prompts.joinPrompts(list)), list);
  });
  await test("vacio -> []", () => {
    assert.deepStrictEqual(prompts.parsePrompts(""), []);
    assert.deepStrictEqual(prompts.parsePrompts(null), []);
  });

  console.log("\ncsv-parser");
  await test("parsea CSV simple", () => {
    assert.deepStrictEqual(csv.parse("a,b\nc,d"), [["a", "b"], ["c", "d"]]);
  });
  await test("respeta comillas con comas internas", () => {
    assert.deepStrictEqual(csv.parse('"a,1",b'), [["a,1", "b"]]);
  });
  await test("escape de comillas dobles", () => {
    assert.deepStrictEqual(csv.parse('"di ""hola""",x'), [['di "hola"', "x"]]);
  });
  await test("detecta delimitador tab", () => {
    assert.strictEqual(csv.detectDelimiter("a\tb\tc"), "\t");
  });
  await test("columnToPrompts con cabecera y nombre", () => {
    const rows = csv.parse("titulo,prompt\nx,gato\ny,perro");
    assert.deepStrictEqual(
      csv.columnToPrompts(rows, { hasHeader: true, column: "prompt" }),
      ["gato", "perro"]
    );
  });
  await test("columnToPrompts por indice sin cabecera", () => {
    const rows = csv.parse("gato\nperro");
    assert.deepStrictEqual(csv.columnToPrompts(rows, { column: 0 }), ["gato", "perro"]);
  });

  console.log("\nqueue-engine");
  await test("procesa todos los jobs en orden (concurrencia 1)", async () => {
    const order = [];
    const eng = new QueueEngine({
      processJob: async (job) => { order.push(job.prompt); },
      concurrency: 1, delayMs: [0, 0], retries: 0,
    });
    eng.add(["a", "b", "c"]);
    const counts = await eng.start();
    assert.deepStrictEqual(order, ["a", "b", "c"]);
    assert.strictEqual(counts.completed, 3);
  });
  await test("reintenta y luego marca failed", async () => {
    let calls = 0;
    const eng = new QueueEngine({
      processJob: async () => { calls++; throw new Error("boom"); },
      concurrency: 1, delayMs: [0, 0], retries: 2,
    });
    eng.add(["x"]);
    const counts = await eng.start();
    assert.strictEqual(calls, 3, "3 intentos (1 + 2 retries)");
    assert.strictEqual(counts.failed, 1);
  });
  await test("reintento que luego pasa -> completed", async () => {
    let calls = 0;
    const eng = new QueueEngine({
      processJob: async () => { calls++; if (calls < 2) throw new Error("temp"); },
      concurrency: 1, delayMs: [0, 0], retries: 3,
    });
    eng.add(["x"]);
    const counts = await eng.start();
    assert.strictEqual(counts.completed, 1);
    assert.ok(calls >= 2);
  });
  await test("concurrencia procesa en paralelo", async () => {
    let active = 0, maxActive = 0;
    const eng = new QueueEngine({
      processJob: async () => {
        active++; maxActive = Math.max(maxActive, active);
        await new Promise((r) => setTimeout(r, 20));
        active--;
      },
      concurrency: 3, delayMs: [0, 0], retries: 0,
    });
    eng.add(["1", "2", "3", "4", "5", "6"]);
    await eng.start();
    assert.ok(maxActive >= 2, "deben correr al menos 2 a la vez, fue " + maxActive);
  });
  await test("stop detiene el procesamiento", async () => {
    let done = 0;
    const eng = new QueueEngine({
      processJob: async (job) => {
        await new Promise((r) => setTimeout(r, 15));
        done++;
        if (job.prompt === "2") eng.stop();
      },
      concurrency: 1, delayMs: [0, 0], retries: 0,
    });
    eng.add(["1", "2", "3", "4", "5"]);
    await eng.start();
    assert.ok(done < 5, "no debe completar todos, completo " + done);
  });
  await test("emite eventos de estado", async () => {
    const types = new Set();
    const eng = new QueueEngine({
      processJob: async () => {},
      concurrency: 1, delayMs: [0, 0], retries: 0,
      onEvent: (e) => types.add(e.type),
    });
    eng.add(["a"]);
    await eng.start();
    assert.ok(types.has("added"));
    assert.ok(types.has("status"));
    assert.ok(types.has("finished"));
  });
  await test("remove elimina job en espera", () => {
    const eng = new QueueEngine({ processJob: async () => {} });
    const [j] = eng.add(["solo"]);
    assert.strictEqual(eng.remove(j.id), true);
    assert.strictEqual(eng.counts.total, 0);
  });

  console.log("\nflow-adapter (helpers puros)");
  await test("norm colapsa espacios", () => {
    assert.strictEqual(flow.helpers.norm("  a   b \n c "), "a b c");
  });
  await test("anyMatch detecta patrones", () => {
    assert.ok(flow.helpers.anyMatch("Generar Video", [/generar/i]));
    assert.ok(!flow.helpers.anyMatch("Cancelar", [/generar/i]));
  });
  await test("SELECTORS.projectUrl matchea URL de proyecto", () => {
    assert.ok(flow.FlowAdapter.SELECTORS.projectUrl.test("https://labs.google/fx/es/tools/flow/project/abc123"));
    assert.ok(!flow.FlowAdapter.SELECTORS.projectUrl.test("https://labs.google/fx/tools/flow"));
  });

  console.log(`\n\x1b[1mResultado: ${passed} pasaron, ${failed} fallaron\x1b[0m\n`);
  process.exit(failed ? 1 : 0);
})();
