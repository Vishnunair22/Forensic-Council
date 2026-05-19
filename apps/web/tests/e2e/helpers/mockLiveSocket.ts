import type { Page } from "@playwright/test";

const DEFAULT_AGENT_NAMES: Record<string, string> = {
  Agent1: "Image Forensics",
  Agent2: "Audio Forensics",
  Agent3: "Object Detection",
  Agent4: "Video Forensics",
  Agent5: "Metadata Expert",
};

export async function installMockLiveSocket(
  page: Page,
  sessionId: string,
  agentNames: Record<string, string> = DEFAULT_AGENT_NAMES,
) {
  await page.addInitScript(
    ({ sessionId: initSessionId, agentNames: initAgentNames }) => {
      type Listener = (event: Event) => void;
      const OriginalWebSocket = window.WebSocket;

      const makeMessage = (type: string, data: Record<string, unknown> = {}) =>
        JSON.stringify({
          type,
          session_id: initSessionId,
          agent_id: data.agent_id ?? null,
          agent_name: data.agent_id ? initAgentNames[String(data.agent_id)] : null,
          message: data.message ?? "Forensic update received",
          data: data.data ?? null,
        });

      const completedAgent = (agentId: string, phase: "initial" | "deep") =>
        makeMessage("AGENT_COMPLETE", {
          agent_id: agentId,
          message: `${initAgentNames[agentId]} ${phase} analysis complete`,
          data: {
            status: "complete",
            analysis_phase: phase,
            confidence: phase === "deep" ? 0.91 : 0.84,
            findings_count: phase === "deep" ? 2 : 1,
            tools_ran: phase === "deep" ? 5 : 3,
            tools_failed: 0,
            agent_verdict: "LIKELY_AUTHENTIC",
            findings_preview: [{
              tool: phase === "deep" ? "deep_consistency_model" : "initial_screen",
              summary: `${initAgentNames[agentId]} found no decisive manipulation markers during ${phase} analysis.`,
              confidence: phase === "deep" ? 0.91 : 0.84,
              flag: "PASS",
              severity: "LOW",
              verdict: "LIKELY_AUTHENTIC",
              key_signal: "No critical artifact cluster detected.",
              section: phase,
            }],
          },
        });

      class FakeWebSocket extends EventTarget {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;

        readonly url: string;
        readonly protocol = "forensic-v1";
        readyState = FakeWebSocket.CONNECTING;
        onopen: Listener | null = null;
        onmessage: Listener | null = null;
        onerror: Listener | null = null;
        onclose: Listener | null = null;

        constructor(url: string) {
          if (OriginalWebSocket && (url.includes("webpack-hmr") || !url.includes("sessions"))) {
            return new OriginalWebSocket(url) as any;
          }
          super();
          this.url = url;
          (window as typeof window & { __fcE2ESockets?: FakeWebSocket[] }).__fcE2ESockets ??= [];
          (window as typeof window & { __fcE2ESockets: FakeWebSocket[] }).__fcE2ESockets.push(this);
          window.setTimeout(() => {
            if (this.readyState !== FakeWebSocket.CONNECTING) return;
            this.readyState = FakeWebSocket.OPEN;
            this.dispatchTyped("open", new Event("open"));
            window.setTimeout(() => {
              const state = window as typeof window & {
                __fcE2ENextPhase?: "initial" | "deep";
                __fcE2EEmitInitial?: () => void;
                __fcE2EEmitDeep?: () => void;
              };
              if (state.__fcE2ENextPhase === "deep") {
                state.__fcE2ENextPhase = "initial";
                state.__fcE2EEmitDeep?.();
                return;
              }
              state.__fcE2EEmitInitial?.();
            }, 20);
          }, 0);
        }

        send(_data: string) {}

        close(code = 1000, reason = "") {
          if (this.readyState === FakeWebSocket.CLOSED) return;
          this.readyState = FakeWebSocket.CLOSED;
          this.dispatchTyped("close", new CloseEvent("close", { code, reason }));
        }

        private dispatchTyped(type: string, event: Event) {
          this.dispatchEvent(event);
          const handler =
            type === "open" ? this.onopen :
            type === "message" ? this.onmessage :
            type === "error" ? this.onerror :
            type === "close" ? this.onclose :
            null;
          if (typeof handler === "function") {
            handler.call(this, event);
          }
        }

        emit(payload: string) {
          if (this.readyState !== FakeWebSocket.OPEN) return;
          this.dispatchTyped("message", new MessageEvent("message", { data: payload }));
        }
      }

      const activeSocket = () => {
        const sockets = (window as typeof window & { __fcE2ESockets?: FakeWebSocket[] }).__fcE2ESockets ?? [];
        return [...sockets].reverse().find((socket) => socket.readyState === FakeWebSocket.OPEN) ?? null;
      };

      (window as typeof window & { __fcE2EEmitLive?: (type: string, data?: Record<string, unknown>) => void })
        .__fcE2EEmitLive = (type, data = {}) => activeSocket()?.emit(makeMessage(type, data));

      (window as typeof window & { __fcE2EEmitInitial?: () => void }).__fcE2EEmitInitial = () => {
        const socket = activeSocket();
        if (!socket) return;
        socket.emit(makeMessage("CONNECTED", { message: "Live stream connected" }));
        socket.emit(makeMessage("AGENT_UPDATE", {
          message: "Initial forensic screening started",
          data: { thinking: "Initial pass is dispatching across the council." },
        }));
        for (const agentId of Object.keys(initAgentNames)) {
          socket.emit(completedAgent(agentId, "initial"));
        }
        socket.emit(makeMessage("PIPELINE_PAUSED", {
          message: "Initial analysis complete. Awaiting analyst decision.",
        }));
      };

      (window as typeof window & { __fcE2EEmitDeep?: () => void }).__fcE2EEmitDeep = () => {
        const socket = activeSocket();
        if (!socket) return;
        socket.emit(makeMessage("CONNECTED", { message: "Live stream connected" }));
        socket.emit(makeMessage("AGENT_UPDATE", {
          message: "Deep analysis started",
          data: { thinking: "Deep detectors are running." },
        }));
        for (const agentId of Object.keys(initAgentNames)) {
          socket.emit(completedAgent(agentId, "deep"));
        }
        socket.emit(makeMessage("PIPELINE_PAUSED", {
          message: "Deep analysis complete. Awaiting report synthesis.",
        }));
      };

      (window as typeof window & { __fcE2EEmitComplete?: (message?: string) => void }).__fcE2EEmitComplete = (message) => {
        activeSocket()?.emit(makeMessage("PIPELINE_COMPLETE", {
          message: message ?? "Final report signed.",
        }));
      };

      Object.assign(FakeWebSocket, {
        CONNECTING: 0,
        OPEN: 1,
        CLOSING: 2,
        CLOSED: 3,
      });

      window.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    },
    { sessionId, agentNames },
  );
}

export async function emitMockLiveSocketDeep(page: Page) {
  await page.evaluate(() => {
    (window as typeof window & { __fcE2ENextPhase?: "initial" | "deep" }).__fcE2ENextPhase = "deep";
    (window as typeof window & { __fcE2EEmitDeep?: () => void }).__fcE2EEmitDeep?.();
  });
}

export async function emitMockLiveSocketComplete(page: Page, message = "Final report signed.") {
  await page.evaluate((msg) => {
    (window as typeof window & { __fcE2EEmitComplete?: (message?: string) => void }).__fcE2EEmitComplete?.(msg);
  }, message);
}
