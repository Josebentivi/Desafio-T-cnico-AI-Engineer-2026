(() => {
  const form = document.getElementById("chat-form");
  if (!form) return;
  const input = document.getElementById("chat-input");
  const button = document.getElementById("send-button");
  const sendLabel = document.getElementById("send-label");
  const messages = document.getElementById("messages");
  const status = document.getElementById("assistant-status");
  const statusText = document.getElementById("status-text");
  const toolNames = {
    search_products: "Catalog search",
    get_product: "Instrument details",
    get_active_promotions: "Active promotions",
    get_order: "Order lookup",
    search_policy: "Policy lookup",
    get_store_status: "Store hours",
    get_shipping_estimate: "Shipping estimate",
  };
  let sending = false;
  let autoScroll = true;

  messages.addEventListener("scroll", () => {
    autoScroll = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
  });
  function scrollToBottom() {
    if (autoScroll) messages.scrollTop = messages.scrollHeight;
  }

  function renderText(text) {
    const escaped = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/~~(.+?)~~/g, "<del>$1</del>").replace(/\n/g, "<br>");
  }

  function appendMessage(role, text) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    if (role === "assistant") avatar.appendChild(document.querySelector(".assistant-mark .icon").cloneNode(true));
    else avatar.textContent = "Y";
    const content = document.createElement("div");
    content.className = "message-content";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("strong");
    name.textContent = role === "assistant" ? "Empório da Música" : "You";
    const time = document.createElement("time");
    time.dateTime = new Date().toISOString();
    time.textContent = new Intl.DateTimeFormat("pt-BR", {
      timeZone: form.dataset.timezone || "America/Campo_Grande", dateStyle: "short", timeStyle: "short",
    }).format(new Date()).replace(", ", " at ");
    meta.append(name, time);
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "assistant") bubble.innerHTML = renderText(text);
    else bubble.textContent = text;
    content.append(meta, bubble);
    wrapper.append(avatar, content);
    messages.appendChild(wrapper);
    scrollToBottom();
    return { wrapper, content, bubble };
  }

  function createTrace(content) {
    const details = document.createElement("details");
    details.className = "trace";
    const summary = document.createElement("summary");
    summary.textContent = "View sources consulted";
    const body = document.createElement("div");
    body.className = "trace-body";
    details.append(summary, body);
    content.appendChild(details);
    return body;
  }

  function addTraceItem(body, data) {
    const item = document.createElement("div");
    item.className = "trace-item";
    const title = document.createElement("div");
    title.className = "name";
    title.textContent = toolNames[data.name] || "System lookup";
    const progress = document.createElement("div");
    progress.className = "muted";
    progress.textContent = "Checking…";
    const technical = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Technical details";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify({ tool: data.name, parameters: data.arguments }, null, 2);
    technical.append(summary, pre);
    item.append(title, progress, technical);
    body.appendChild(item);
    return { item, progress, pre };
  }

  async function sendMessage(text) {
    if (sending) return;
    if (!text.trim()) {
      input.setCustomValidity("Type a message to get started.");
      input.reportValidity();
      return;
    }
    sending = true;
    autoScroll = true;
    document.getElementById("empty-chat")?.remove();
    appendMessage("user", text);
    input.value = "";
    input.style.height = "auto";
    input.disabled = true;
    button.disabled = true;
    sendLabel.textContent = "Please wait";
    status.classList.add("busy");
    statusText.textContent = "Preparing your response";
    messages.setAttribute("aria-busy", "true");
    const assistant = appendMessage("assistant", "");
    assistant.bubble.classList.add("streaming");
    let traceBody = null;
    let pendingTrace = null;
    let buffer = "";
    let finalText = "";
    let completed = false;
    let failed = false;

    function handleBlock(block) {
      let eventName = "message";
      let dataLine = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (!dataLine) return;
      const data = JSON.parse(dataLine);
      if (eventName === "token") {
        finalText += data.text || "";
        assistant.bubble.innerHTML = renderText(finalText);
        statusText.textContent = "Writing your response";
      } else if (eventName === "tool_call") {
        if (!traceBody) traceBody = createTrace(assistant.content);
        pendingTrace = addTraceItem(traceBody, data);
        statusText.textContent = toolNames[data.name] || "Checking information";
      } else if (eventName === "tool_result") {
        if (!traceBody) traceBody = createTrace(assistant.content);
        const trace = pendingTrace || addTraceItem(traceBody, data);
        trace.progress.textContent = `${data.error ? "Lookup failed" : "Lookup completed"} · ${data.latency_ms || 0} ms`;
        trace.pre.textContent += "\n\n" + JSON.stringify({ result: data.output, error: data.error || undefined }, null, 2).slice(0, 8000);
        pendingTrace = null;
      } else if (eventName === "done") {
        completed = true;
        if (data.text) finalText = data.text;
        assistant.bubble.innerHTML = renderText(finalText);
        assistant.bubble.classList.remove("streaming");
        const currentSession = document.querySelector(".session-link.active");
        const title = currentSession?.querySelector(".title");
        if (title?.textContent === "New conversation") {
          title.textContent = [...text.trim().replace(/\s+/g, " ")].slice(0, 60).join("");
        }
        const sessionTime = currentSession?.querySelector(".time");
        if (sessionTime) sessionTime.textContent = assistant.content.querySelector("time").textContent;
        if (data.warnings?.length) {
          const warning = document.createElement("div");
          warning.className = "warning small";
          warning.textContent = data.warnings.join(" ");
          assistant.content.appendChild(warning);
        }
      } else if (eventName === "error") {
        failed = true;
        finalText = data.message || "Could not complete the request. Please try again.";
        assistant.bubble.textContent = finalText;
        assistant.bubble.classList.remove("streaming");
      }
      scrollToBottom();
    }

    try {
      const formData = new FormData();
      formData.append("message", text);
      formData.append("session_id", form.dataset.sessionId);
      const response = await fetch("/chat/stream", {
        method: "POST", body: formData, headers: { Accept: "text/event-stream" },
      });
      if (!response.ok || !response.body) throw new Error("Response unavailable");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, "\n");
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) handleBlock(block);
        if (done) {
          if (buffer.trim()) handleBlock(buffer);
          break;
        }
      }
      if (!completed && !failed) {
        failed = true;
        assistant.bubble.textContent = finalText
          ? `${finalText}\n\nThe response was interrupted. Please try again.`
          : "We did not receive a complete response. Please try again.";
      }
    } catch {
      failed = true;
      assistant.bubble.textContent = "Could not connect to support. Please try again shortly.";
    } finally {
      assistant.bubble.classList.remove("streaming");
      messages.setAttribute("aria-busy", "false");
      input.disabled = false;
      button.disabled = false;
      sendLabel.textContent = "Send";
      status.classList.remove("busy");
      statusText.textContent = failed ? "Please try again" : "Ready to help";
      sending = false;
      input.focus({ preventScroll: true });
      scrollToBottom();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  input.addEventListener("input", () => {
    input.setCustomValidity("");
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  });
  input.addEventListener("invalid", () => {
    if (input.validity.valueMissing) input.setCustomValidity("Type a message to get started.");
  });
  document.querySelectorAll(".suggestion").forEach((suggestion) => {
    suggestion.addEventListener("click", () => {
      input.setCustomValidity("");
      input.value = suggestion.dataset.prompt;
      form.requestSubmit();
    });
  });
  scrollToBottom();
})();
