"use client";

import { useEffect, useState } from "react";

type Msg = { role: "user" | "assistant"; text: string; citations?: string[]; sources?: string[] };
type RetrievedDoc = {
  doc_id: number;
  title: string;
  source: string;
  chunk_index: number;
  score: number;
  content_snippet: string;
  doc_type: string;
};

type DonePayload = {
  answer: string;
  citations: string[];
  sources: string[];
  retrieved_docs: RetrievedDoc[];
};

function stripInlineCitations(text: string): string {
  return (text || "")
    .replace(/\s*\[doc:\d+\]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function buildCitationLabels(citations: string[], retrievedDocs: RetrievedDoc[]): string[] {
  const byId = new Map<number, RetrievedDoc>();
  for (const doc of retrievedDocs || []) {
    byId.set(doc.doc_id, doc);
  }

  return (citations || []).map((citation) => {
    const docId = Number(citation.replace("doc:", ""));
    const match = byId.get(docId);
    if (!match) return citation;
    return `${match.title} (${match.source})`;
  });
}

export default function Page() {
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<(Msg & { citationLabels?: string[] })[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let sid = sessionStorage.getItem("session_id");
    if (!sid) {
      sid = `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem("session_id", sid);
    }
    setSessionId(sid);
  }, []);

  async function send() {
    if (!input.trim() || !sessionId || isLoading) return;
    const userMsg = input.trim();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8020";

    setHistory((h) => [...h, { role: "user", text: userMsg }, { role: "assistant", text: "", citations: [], sources: [] }]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch(`${apiUrl}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, session_id: sessionId }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      let renderedText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });

        const events = pending.split("\n\n");
        pending = events.pop() ?? "";

        for (const evt of events) {
          const lines = evt.split("\n");
          const eventType = lines.find((l) => l.startsWith("event:"))?.replace("event:", "").trim();
          const dataLine = lines.find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.replace("data:", "").trim());

          if (eventType === "token") {
            renderedText += payload.delta || "";
            setHistory((h) => {
              const copy = [...h];
              copy[copy.length - 1] = { role: "assistant", text: stripInlineCitations(renderedText) };
              return copy;
            });
          } else if (eventType === "done") {
            const finalPayload = payload as DonePayload;
            const citationLabels = buildCitationLabels(finalPayload.citations || [], finalPayload.retrieved_docs || []);
            setHistory((h) => {
              const copy = [...h];
              copy[copy.length - 1] = {
                role: "assistant",
                text: stripInlineCitations(finalPayload.answer),
                citations: finalPayload.citations || [],
                sources: finalPayload.sources || [],
                citationLabels,
              };
              return copy;
            });
          } else if (eventType === "error") {
            throw new Error(payload.error || "Stream error");
          }
        }
      }
    } catch (error) {
      setHistory((h) => {
        const copy = [...h];
        copy[copy.length - 1] = {
          role: "assistant",
          text: `Sorry, I hit an error: ${error instanceof Error ? error.message : "unknown error"}`,
        };
        return copy;
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontWeight: 600 }}>K-Food Helpdesk</h1>
      <div
        style={{
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: 12,
          height: 350,
          overflowY: "auto",
          background: "#fff",
        }}
      >
        {history.map((m, i) => (
          <div key={i} style={{ textAlign: m.role === "user" ? "right" : "left", marginBottom: 8 }}>
            <span
              style={{
                display: "inline-block",
                background: m.role === "user" ? "#dbeafe" : "#f3f4f6",
                padding: 8,
                borderRadius: 8,
                whiteSpace: "pre-wrap",
                maxWidth: "90%",
              }}
            >
              {m.text || (isLoading && i === history.length - 1 ? "..." : "")}
              {m.role === "assistant" && (m.citations?.length || m.sources?.length) ? (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #ddd", fontSize: 12, color: "#444" }}>
                  {m.citations?.length ? (
                    <div>
                      Citations: {(m.citationLabels || m.citations).map((label, idx) => (
                        <span key={idx} title={m.citations?.[idx] || ""}>
                          {idx > 0 ? ", " : ""}
                          {label}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {m.sources?.length ? <div>Sources: {m.sources.join(", ")}</div> : null}
                </div>
              ) : null}
            </span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about refunds, delivery, allergens..."
          style={{ flex: 1, border: "1px solid #ccc", borderRadius: 6, padding: 8 }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              send();
            }
          }}
        />
        <button
          onClick={send}
          disabled={isLoading}
          style={{ padding: "8px 16px", borderRadius: 6, background: "#111", color: "#fff", opacity: isLoading ? 0.7 : 1 }}
        >
          {isLoading ? "..." : "Send"}
        </button>
      </div>
    </main>
  );
}
