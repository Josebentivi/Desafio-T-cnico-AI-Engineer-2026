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
    search_products: "Busca no catálogo",
    get_product: "Detalhes do instrumento",
    get_active_promotions: "Promoções ativas",
    get_order: "Consulta de pedido",
    search_policy: "Consulta às políticas",
    get_store_status: "Horário da loja",
    get_shipping_estimate: "Estimativa de frete",
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
    else avatar.textContent = "V";
    const content = document.createElement("div");
    content.className = "message-content";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("strong");
    name.textContent = role === "assistant" ? "Empório da Música" : "Você";
    const time = document.createElement("time");
    time.dateTime = new Date().toISOString();
    time.textContent = new Intl.DateTimeFormat("pt-BR", {
      timeZone: form.dataset.timezone || "America/Campo_Grande", dateStyle: "short", timeStyle: "short",
    }).format(new Date()).replace(", ", " às ");
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
    summary.textContent = "Ver fontes consultadas";
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
    title.textContent = toolNames[data.name] || "Consulta ao sistema";
    const progress = document.createElement("div");
    progress.className = "muted";
    progress.textContent = "Consultando…";
    const technical = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Dados técnicos";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify({ ferramenta: data.name, parametros: data.arguments }, null, 2);
    technical.append(summary, pre);
    item.append(title, progress, technical);
    body.appendChild(item);
    return { item, progress, pre };
  }

  async function sendMessage(text) {
    if (sending) return;
    if (!text.trim()) {
      input.setCustomValidity("Digite sua mensagem para começar.");
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
    sendLabel.textContent = "Aguarde";
    status.classList.add("busy");
    statusText.textContent = "Preparando sua resposta";
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
        statusText.textContent = "Escrevendo sua resposta";
      } else if (eventName === "tool_call") {
        if (!traceBody) traceBody = createTrace(assistant.content);
        pendingTrace = addTraceItem(traceBody, data);
        statusText.textContent = toolNames[data.name] || "Consultando informações";
      } else if (eventName === "tool_result") {
        if (!traceBody) traceBody = createTrace(assistant.content);
        const trace = pendingTrace || addTraceItem(traceBody, data);
        trace.progress.textContent = `${data.error ? "Consulta com erro" : "Consulta concluída"} · ${data.latency_ms || 0} ms`;
        trace.pre.textContent += "\n\n" + JSON.stringify({ resultado: data.output, erro: data.error || undefined }, null, 2).slice(0, 8000);
        pendingTrace = null;
      } else if (eventName === "done") {
        completed = true;
        if (data.text) finalText = data.text;
        assistant.bubble.innerHTML = renderText(finalText);
        assistant.bubble.classList.remove("streaming");
        const currentSession = document.querySelector(".session-link.active");
        const title = currentSession?.querySelector(".title");
        if (title?.textContent === "Nova conversa") {
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
        finalText = data.message || "Não foi possível concluir o atendimento. Tente novamente.";
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
      if (!response.ok || !response.body) throw new Error("Resposta indisponível");
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
          ? `${finalText}\n\nA resposta foi interrompida. Tente novamente.`
          : "Não recebemos uma resposta completa. Tente novamente.";
      }
    } catch {
      failed = true;
      assistant.bubble.textContent = "Não foi possível concluir a conexão com o atendimento. Tente novamente em instantes.";
    } finally {
      assistant.bubble.classList.remove("streaming");
      messages.setAttribute("aria-busy", "false");
      input.disabled = false;
      button.disabled = false;
      sendLabel.textContent = "Enviar";
      status.classList.remove("busy");
      statusText.textContent = failed ? "Tente enviar novamente" : "Pronto para ajudar";
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
    if (input.validity.valueMissing) input.setCustomValidity("Digite sua mensagem para começar.");
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
