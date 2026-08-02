"use strict";

const $ = (id) => document.getElementById(id);
let latest = null;
let busy = false;

function bytes(value) {
  if (!value) return "unknown space";
  const gb = value / 1024 ** 3;
  return gb > 1024 ? `${(gb / 1024).toFixed(2)} TB free` : `${gb.toFixed(1)} GB free`;
}

function selectedModel() {
  return document.querySelector('input[name="model"]:checked').value;
}

function setProgress(id, job) {
  const box = $(id);
  const bar = box.querySelector("span");
  if (!job || job.status === "done" || job.status === "error") {
    box.hidden = true;
    box.classList.remove("indeterminate");
    return;
  }
  box.hidden = false;
  if (job.total) {
    box.classList.remove("indeterminate");
    bar.style.width = `${Math.min(100, job.done / job.total * 100)}%`;
  } else {
    box.classList.add("indeterminate");
    bar.style.width = "";
  }
}

function jobText(job) {
  if (!job) return "";
  if (job.total && job.status === "running") {
    const pct = Math.floor(job.done / job.total * 100);
    return `${job.detail} · ${pct}%`;
  }
  return job.detail || job.status;
}

async function refresh() {
  try {
    latest = await (await fetch("/api/setup")).json();
    $("drive-root").textContent = latest.drive_root;
    $("drive-space").textContent = bytes(latest.drive_free);

    const storage = $("storage-status");
    storage.textContent = latest.drive_writable ? "READY · ALL WRITES STAY HERE" : "DRIVE IS READ-ONLY";
    storage.className = `step-status ${latest.drive_writable ? "ok" : "error"}`;
    $("step-storage").classList.toggle("done", latest.drive_writable);

    const runtimeJob = latest.jobs["setup:ollama"];
    const runtimeReady = latest.ollama_installed && latest.ollama_online;
    $("runtime-status").textContent = runtimeReady ? "READY · RUNNING FROM THIS DRIVE"
      : jobText(runtimeJob) || (latest.ollama_installed ? "STARTING PORTABLE RUNTIME…" : "NOT INSTALLED");
    $("runtime-status").className = `step-status ${runtimeReady ? "ok" : runtimeJob?.status === "error" ? "error" : ""}`;
    $("install-runtime").disabled = busy || !latest.drive_writable || runtimeReady || runtimeJob?.status === "running";
    $("install-runtime").textContent = latest.ollama_installed ? "START PORTABLE OLLAMA" : "INSTALL PORTABLE OLLAMA";
    $("step-runtime").classList.toggle("done", runtimeReady);
    setProgress("runtime-progress", runtimeJob);

    const model = selectedModel();
    const modelJob = latest.jobs[`model:${model}`];
    const installed = latest.models.includes(model);
    $("model-status").textContent = installed ? "READY · MODEL STORED ON THIS DRIVE"
      : jobText(modelJob) || (runtimeReady ? "READY TO DOWNLOAD" : "INSTALL THE RUNTIME FIRST");
    $("model-status").className = `step-status ${installed ? "ok" : modelJob?.status === "error" ? "error" : ""}`;
    $("install-model").disabled = busy || !runtimeReady || installed || modelJob?.status === "running";
    $("step-model").classList.toggle("done", latest.models.length > 0);
    setProgress("model-progress", modelJob);

    $("finish").disabled = busy || !latest.drive_writable || !runtimeReady || !installed;
  } catch (error) {
    $("storage-status").textContent = `SETUP SERVICE ERROR · ${error}`;
    $("storage-status").className = "step-status error";
  }
}

$("install-runtime").addEventListener("click", async () => {
  busy = true;
  await fetch("/api/setup/ollama", { method: "POST" });
  busy = false;
  refresh();
});

$("install-model").addEventListener("click", async () => {
  busy = true;
  await fetch("/api/downloads/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "model", id: selectedModel() }),
  });
  busy = false;
  refresh();
});

document.querySelectorAll('input[name="model"]').forEach((input) => {
  input.addEventListener("change", refresh);
});

$("finish").addEventListener("click", async () => {
  busy = true;
  const response = await fetch("/api/setup/finish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_model: selectedModel() }),
  });
  const result = await response.json();
  window.location.href = result.redirect || "/index.html";
});

refresh();
setInterval(refresh, 1000);
