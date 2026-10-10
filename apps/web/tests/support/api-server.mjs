import { createServer } from "node:http";

const port = 3107;
const requests = [];
const pending = new Map();
let scenarios = {};
let sequence = 0;
const categoryItems = [
  { slug: "air", name: "大気", display_order: 1 },
  { slug: "soil", name: "土壌", display_order: 2 },
];

function defaults(path, url) {
  if (path === "/fixed-categories") return { items: categoryItems };
  const page = Number(url.searchParams.get("page") ?? 1);
  return {
    items: [
      {
        title: "API由来の報道発表",
        source_url: "https://example.invalid/releases/1",
        published_at: "2026-01-05",
        source_categories: ["表示しない取得元カテゴリ"],
        fixed_categories: [
          { slug: "air", name: "大気" },
          { slug: "soil", name: "土壌" },
        ],
      },
    ],
    pagination: { page, page_size: 50, total_items: 62, total_pages: 2 },
  };
}

function json(res, value, status = 200) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(value));
}

async function body(req) {
  let data = "";
  for await (const chunk of req) {
    data += chunk;
    if (data.length > 262144) throw new Error("control body too large");
  }
  return JSON.parse(data);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${port}`);
  const path = url.pathname;
  try {
    if (path === "/__ready") return json(res, { ready: true });
    if (path === "/__requests") return json(res, requests);
    if (req.method === "POST" && path === "/__reset") {
      const operations = [...pending.values()];
      for (const operation of operations) operation.cleanup();
      await Promise.all(operations.map((operation) => operation.closed));
      pending.clear();
      requests.length = 0;
      scenarios = await body(req);
      return json(res, { ready: true });
    }
    if (req.method === "POST" && path === "/__release") {
      const { ids } = await body(req);
      for (const id of ids) pending.get(id)?.respond();
      return json(res, { released: ids });
    }
    if (req.method === "POST" && path === "/__configure") {
      scenarios = { ...scenarios, ...(await body(req)) };
      return json(res, { ready: true });
    }
    if (req.method !== "GET" || !["/press-releases", "/fixed-categories"].includes(path)) {
      requests.push({
        id: ++sequence,
        path,
        query: url.search,
        arrivedAt: Date.now(),
        unexpected: true,
      });
      return json(res, { detail: "Not found" }, 404);
    }
    const configured = scenarios[path] ?? {};
    const scenario = Array.isArray(configured)
      ? (configured[
          Math.min(requests.filter((entry) => entry.path === path).length, configured.length - 1)
        ] ?? {})
      : configured;
    const entry = {
      id: ++sequence,
      path,
      query: url.search,
      arrivedAt: Date.now(),
      finished: false,
      aborted: false,
      cleanup: false,
    };
    requests.push(entry);
    let timer;
    let closed;
    const closing = new Promise((resolve) => {
      closed = resolve;
    });
    function respond() {
      if (res.destroyed || res.writableEnded) return;
      const status = scenario.status ?? 200;
      res.writeHead(status, {
        "content-type": scenario.contentType ?? "application/json",
        ...scenario.headers,
      });
      res.end(scenario.raw ?? JSON.stringify(scenario.body ?? defaults(path, url)));
    }
    pending.set(entry.id, {
      respond,
      closed: closing,
      cleanup() {
        entry.cleanup = true;
        clearTimeout(timer);
        res.destroy();
      },
    });
    res.on("finish", () => {
      entry.finished = true;
      entry.finishedAt = Date.now();
    });
    res.on("close", () => {
      entry.closedAt = Date.now();
      entry.aborted = !res.writableFinished;
      clearTimeout(timer);
      pending.delete(entry.id);
      closed();
    });
    if (scenario.hold === "body") {
      res.writeHead(200, { "content-type": "application/json" });
      res.write('{"items":');
    } else if (scenario.hold === "headers" || scenario.hold === "gate") {
      return;
    } else if (scenario.delay) {
      timer = setTimeout(respond, scenario.delay);
    } else {
      respond();
    }
  } catch {
    if (!res.headersSent) json(res, { detail: "Control error" }, 400);
    else res.destroy();
  }
});

server.listen(port, "127.0.0.1");
function stop() {
  for (const operation of pending.values()) operation.cleanup();
  server.closeAllConnections();
  server.close(() => process.exit(0));
}
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
