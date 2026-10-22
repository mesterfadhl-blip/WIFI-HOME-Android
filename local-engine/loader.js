"use strict";
(async function () {
  // Android content:// providers may omit randomUUID despite exposing secure
  // getRandomValues. These UUIDs identify requests/files, never credentials.
  if (!globalThis.crypto?.randomUUID && globalThis.crypto?.getRandomValues) {
    Object.defineProperty(globalThis.crypto, "randomUUID", {
      value: () => {
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        const hex = [...bytes]
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
      },
      configurable: true,
    });
  }
  const pack = JSON.parse(document.getElementById("erp-package").textContent);
  const root = document.getElementById("root");
  const status = document.getElementById("local-status");
  const assets = pack.assets;
  let py,
    queue = Promise.resolve(),
    dirty = false,
    storageOK = true,
    storageIssue = "";
  const key = pack.storageKey;
  function bytes(value) {
    const str = atob(value),
      result = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) result[i] = str.charCodeAt(i);
    return result;
  }
  function encoded(value) {
    let result = "";
    for (let i = 0; i < value.length; i += 32768)
      result += String.fromCharCode(...value.subarray(i, i + 32768));
    return btoa(result);
  }
  function serial(job) {
    const task = queue.then(job);
    queue = task.catch(() => {});
    return task;
  }
  function banner() {
    status.textContent = storageOK
      ? "النظام يعمل محلياً على هذا الجهاز. احتفظ بنسخة ملف خارج المتصفح."
      : "المتصفح يمنع الحفظ التلقائي: " +
        storageIssue +
        " احفظ نسخة النظام بعد العمل، وافتح الملف الجديد لاحقاً.";
    if (dirty)
      status.textContent += " توجد تغييرات منذ آخر تنزيل لنسخة النظام.";
  }
  async function exportSnapshot() {
    return await serial(() => py.runPythonAsync("_local_bridge.snapshot()"));
  }
  async function persist() {
    const db = await py.runPythonAsync("_local_bridge.snapshot()");
    try {
      window.localStorage.setItem(key, db);
      storageOK = true;
      storageIssue = "";
    } catch (e) {
      storageOK = false;
      storageIssue = "احفظ بياناتك بملف HTML أو قاعدة SQLite.";
    }
    dirty = true;
    banner();
  }
  function download(name, body, type) {
    const url = URL.createObjectURL(new Blob([body], { type })),
      a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  }
  const decoder = new TextDecoder();
  function source(name) {
    if (!assets[name]) throw Error("Missing bundled asset: " + name);
    return bytes(assets[name]);
  }
  window.fetch = async function (input, options = {}) {
    const path =
      typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : String(input);
    const url = new URL(path, "https://wifi-home.invalid/");
    if (
      url.pathname.startsWith("/runtime/") ||
      assets[url.pathname.split("/").pop()]
    ) {
      const name = url.pathname.split("/").pop();
      return new Response(source(name), {
        status: 200,
        headers: {
          "Content-Type": name.endsWith(".wasm")
            ? "application/wasm"
            : "application/octet-stream",
        },
      });
    }
    if (
      !url.pathname.startsWith("/api/") &&
      !url.pathname.startsWith("/print/") &&
      !url.pathname.startsWith("/export/")
    )
      throw Error(
        "External networking is disabled in this local file: " + url.pathname,
      );
    return serial(async () => {
      const headers = Object.fromEntries(
        new Headers(options.headers || {}).entries(),
      );
      py.globals.set(
        "_local_request",
        JSON.stringify({
          path: url.pathname + url.search,
          method: options.method || "GET",
          body: options.body || "",
          headers,
        }),
      );
      const result = JSON.parse(
        await py.runPythonAsync("_local_bridge.call(_local_request)"),
      );
      if ((options.method || "GET") !== "GET" && result.status < 400)
        await persist();
      return new Response(bytes(result.body), {
        status: result.status,
        headers: result.headers,
      });
    });
  };
  async function output(path) {
    const response = await window.fetch(path);
    if (!response.ok) {
      let message = await response.text();
      try {
        message = JSON.parse(message).error;
      } catch {}
      throw Error(message);
    }
    const type = response.headers.get("content-type") || "";
    if (!type.startsWith("text/html")) {
      const name =
        (response.headers.get("content-disposition") || "").match(
          /filename="([^"]+)"/,
        )?.[1] || "WIFI-HOME-export";
      download(name, await response.arrayBuffer(), type);
      return;
    }
    const html = (await response.text()).replace(
      /<script\s+src="\/document\.js"\s+defer><\/script>/g,
      "",
    );
    let d = document.getElementById("local-document");
    if (d) d.remove();
    d = document.createElement("dialog");
    d.id = "local-document";
    d.innerHTML =
      '<div class="local-tools"><button id="local-print">طباعة / حفظ PDF</button><button id="local-doc-save">حفظ المستند HTML</button><button id="local-doc-close">رجوع</button></div><iframe sandbox="allow-modals allow-same-origin" title="مستند مستقل"></iframe>';
    document.body.append(d);
    d.querySelector("iframe").srcdoc = html;
    d.showModal();
    const print = () => {
      const w = d.querySelector("iframe").contentWindow;
      w.focus();
      w.print();
    };
    d.querySelector("iframe").onload = () => {
      const b = d
        .querySelector("iframe")
        .contentDocument.querySelector("#print-document");
      if (b) b.onclick = print;
    };
    document.getElementById("local-print").onclick = print;
    document.getElementById("local-doc-save").onclick = () =>
      download("WIFI-HOME-document.html", html, "text/html");
    document.getElementById("local-doc-close").onclick = () => d.close();
  }
  document.addEventListener(
    "click",
    (event) => {
      const a = event.target.closest("a");
      if (!a) return;
      const href = a.getAttribute("href") || "";
      if (
        href.startsWith("/print/") ||
        href.startsWith("/export/") ||
        href === "/api/backup"
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        output(href).catch((e) => alert(e.message));
      }
    },
    true,
  );
  const realOpen = window.open.bind(window);
  window.open = function (url, ...args) {
    if (typeof url === "string" && url.startsWith("/print/")) {
      output(url).catch((e) => alert(e.message));
      return null;
    }
    return realOpen(url, ...args);
  };
  document.getElementById("save-system").onclick = async function () {
    this.disabled = true;
    try {
      const db = await exportSnapshot();
      const documentCopy = document.documentElement.cloneNode(true);
      const updated = {
        ...pack,
        database: db,
        storageKey: "wifi-home-full-" + crypto.randomUUID(),
      };
      documentCopy.querySelector("#erp-package").textContent = JSON.stringify(
        updated,
      ).replace(/</g, "\\u003c");
      documentCopy.querySelector("#root").innerHTML = "";
      documentCopy.querySelector("#local-document")?.remove();
      documentCopy.querySelector("#save-system").removeAttribute("disabled");
      download(
        "WIFI-HOME-FULL-" + Date.now() + ".html",
        "<!doctype html>\n" + documentCopy.outerHTML,
        "text/html",
      );
      dirty = false;
      banner();
      alert(
        "تم طلب تنزيل نسخة النظام ببياناتك. تحقق من وجود الملف في التنزيلات وافتح النسخة الجديدة في المرة القادمة.",
      );
    } catch (e) {
      alert(e.message);
    } finally {
      this.disabled = false;
    }
  };
  window.addEventListener("beforeunload", (event) => {
    if (dirty && !storageOK) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.getElementById("save-database").onclick = async () => {
    try {
      download(
        "WIFI-HOME-database-" + Date.now() + ".sqlite3",
        bytes(await exportSnapshot()),
        "application/vnd.sqlite3",
      );
    } catch (e) {
      alert(e.message);
    }
  };
  try {
    root.innerHTML =
      '<div class="loading">يجري تشغيل نفس محرك النظام وقاعدة البيانات محلياً… قد يستغرق أول فتح بعض الوقت.</div>';
    status.textContent =
      "تحميل المحرك المحلي المضمن في الملف؛ لا يحتاج اتصالاً بالإنترنت.";
    for (const name of ["pyodide.asm.js", "pyodide.js"]) {
      const tag = document.createElement("script");
      tag.textContent = decoder.decode(source(name));
      document.head.append(tag);
      tag.remove();
    }
    py = await loadPyodide({ indexURL: "https://wifi-home.invalid/runtime/" });
    await py.loadPackage(["sqlite3", "hashlib"]);
    py.FS.mkdirTree("/app");
    py.FS.mkdirTree("/data");
    py.FS.writeFile("/app/erp.zip", source("erp.zip"));
    py.FS.writeFile("/app/bridge.py", source("bridge.py"));
    let database = pack.database;
    try {
      database = window.localStorage.getItem(key) || database;
    } catch (e) {
      storageOK = false;
      storageIssue = "التخزين غير متاح لهذا الملف.";
    }
    if (database) py.FS.writeFile("/data/erp.sqlite3", bytes(database));
    await py.runPythonAsync(
      "import sys,zipfile,importlib.util\nzipfile.ZipFile('/app/erp.zip').extractall('/app')\nsys.path.insert(0,'/app')\nspec=importlib.util.spec_from_file_location('_local_bridge','/app/bridge.py')\n_local_bridge=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(_local_bridge)",
    );
    root.innerHTML = "";
    banner();
    // The original scripts run together in their original order and share scope.
    const app = document.createElement("script");
    app.textContent = pack.frontend;
    document.body.append(app);
    app.remove();
    document.getElementById("save-system").disabled = false;
    document.getElementById("save-database").disabled = false;
  } catch (error) {
    console.error(error);
    root.textContent = "تعذر تشغيل المحرك المحلي: " + error.message;
    status.textContent =
      "لم تُعدّل قاعدة البيانات الأصلية. احتفظ بالملف وأرسل صورة الخطأ.";
  }
})();
