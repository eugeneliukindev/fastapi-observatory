// Faro: browser logs, errors, Web Vitals and traces.
const { initializeFaro, getWebInstrumentations } = window.GrafanaFaroWebSdk;
const { TracingInstrumentation } = window.GrafanaFaroWebTracing;

const faro = initializeFaro({
  url: window.FARO_URL,
  app: { name: "web", version: "0.1.0", environment: window.ENVIRONMENT },
  instrumentations: [
    ...getWebInstrumentations({ captureConsole: true }),
    // Same-origin fetch carries a traceparent header, so the API span becomes a child of the browser span.
    new TracingInstrumentation(),
  ],
});

const tracer = faro.api.getOTEL().trace.getTracer("web");
const output = document.getElementById("output");
const draft = { user_id: 1, title: "post from the page", body: "written by a click" };

// A span per click names the trace after what the user did; the fetch span and the whole API side
// become its children. Without it every trace from the page would be called just `GET`.
async function call(action, path, method) {
  await tracer.startActiveSpan(action, async (span) => {
    const started = performance.now();
    try {
      const response = await fetch(path, method === "POST"
        ? { method, headers: { "content-type": "application/json" }, body: JSON.stringify(draft) }
        : { method });
      const text = await response.text();
      const elapsed = Math.round(performance.now() - started);
      output.textContent = `${method} ${path} → ${response.status} in ${elapsed} ms\n\n${text}`;
      if (!response.ok) {
        console.warn("API request failed", method, path, response.status);
      }
    } finally {
      span.end();
    }
  });
}

for (const button of document.querySelectorAll("button[data-path]")) {
  button.addEventListener("click", () =>
    call(button.dataset.action, button.dataset.path, button.dataset.method ?? "GET"));
}

document.getElementById("throw").addEventListener("click", () => {
  throw new Error("error thrown in the browser on purpose");
});
