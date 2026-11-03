(() => {
  const form = document.getElementById("chat-form");
  if (!form) return;
  const input = document.getElementById("chat-input");
  const button = document.getElementById("send-button");
  const messages = document.getElementById("messages");
  const sessionId = form.dataset.sessionId;

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function renderText(text) {
    const escaped = String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/~~(.+?)~~/g, "<del>$1</del>")
      .replace(/\n/g, "<br>");
  }

  function appendMessage(role, text) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "assistant") {
      bubble.innerHTML = renderText(text);
    } else {
      bubble.textContent = text;
    }
    wrapper.appendChild(bubble);
    messages.appendChild(wrapper);
    scrollToBottom();
    return { wrapper, bubble };
  }

  function createTrace(wrapper) {
    const details = document.createElement("details");
    details.className = "trace";
    const summary = document.createElement("summary");
    summary.textContent = "View lookup";
    const body = document.createElement("div");
    body.className = "trace-body";
    details.appendChild(summary);
    details.appendChild(body);
    wrapper.appendChild(details);
    return body;
  }

  function addTraceItem(body, name, args, latency, output, error) {
    const item = document.createElement("div");
    item.className = "trace-item";
    const title = document.createElement("div");
    title.className = "name";
    title.textContent = name;
    item.appendChild(title);
    const argsLine = document.createElement("div");
    argsLine.className = "muted";
    argsLine.textContent = JSON.stringify(args);
    item.appendChild(argsLine);
    if (latency !== undefined) {
      const latencyLine = document.createElement("div");
      latencyLine.className = "muted";
      latencyLine.textContent = `${latency} ms`;
      item.appendChild(latencyLine);
    }
    if (output !== undefined) {
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(output, null, 2).slice(0, 2000);
      item.appendChild(pre);
    }
    if (error) {
      const errorLine = document.createElement("div");
      errorLine.className = "error small";
      errorLine.textContent = error;
      item.appendChild(errorLine);
    }
    body.appendChild(item);
  }

  async function sendMessage(text) {
    if (!text.trim()) return;
    const empty = document.getElementById("empty-chat");
    if (empty) empty.remove();

    appendMessage("user", text);
    input.value = "";
    input.style.height = "auto";
    input.disabled = true;
    button.disabled = true;
    button.textContent = "Please wait";

    const assistant = appendMessage("assistant", "");
    assistant.bubble.classList.add("streaming");
    const traceBody = createTrace(assistant.wrapper);
    let buffer = "";
    let finalText = "";

    try {
      const formData = new FormData();
      formData.append("message", text);
      formData.append("session_id", sessionId);
      const response = await fetch("/chat/stream", {
        method: "POST",
        body: formData,
        headers: { Accept: "text/event-stream" },
      });
      if (!response.ok || !response.body) {
        throw new Error(`Falha no servidor (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          let eventName = "message";
          let dataLine = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) eventName = line.slice(6).trim();
            if (line.startsWith("data:")) dataLine += line.slice(5).trim();
          }
          if (!dataLine) continue;
          let data;
          try {
            data = JSON.parse(dataLine);
          } catch {
            continue;
          }
          if (eventName === "token") {
            finalText += data.text || "";
            assistant.bubble.innerHTML = renderText(finalText);
            scrollToBottom();
          } else if (eventName === "tool_call") {
            addTraceItem(traceBody, data.name, data.arguments);
            scrollToBottom();
          } else if (eventName === "tool_result") {
            addTraceItem(traceBody, data.name, {}, data.latency_ms, data.output, data.error);
            scrollToBottom();
          } else if (eventName === "done") {
            if (data.text) {
              finalText = data.text;
              assistant.bubble.innerHTML = renderText(finalText);
            }
            assistant.bubble.classList.remove("streaming");
            if (data.warnings && data.warnings.length) {
              const warning = document.createElement("div");
              warning.className = "warning small";
              warning.textContent = data.warnings.join(" ");
              assistant.wrapper.appendChild(warning);
            }
          } else if (eventName === "error") {
            finalText = data.message || "Ocorreu um erro.";
            assistant.bubble.textContent = finalText;
            assistant.bubble.classList.remove("streaming");
          }
        }
      }
      if (assistant.bubble.classList.contains("streaming")) {
        assistant.bubble.classList.remove("streaming");
        if (!finalText) assistant.bubble.textContent = "I did not receive a complete response. Please try again.";
      }
    } catch (error) {
      assistant.bubble.classList.remove("streaming");
      assistant.bubble.textContent = `I could not reach the server: ${error.message}`;
    } finally {
      input.disabled = false;
      button.disabled = false;
      button.textContent = "Send";
      input.focus();
      scrollToBottom();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  });

  document.querySelectorAll(".suggestion").forEach((buttonEl) => {
    buttonEl.addEventListener("click", () => {
      input.value = buttonEl.dataset.prompt || buttonEl.textContent;
      form.requestSubmit();
    });
  });
})();
