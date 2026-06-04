/**
 * Unit Tests — Investigation Storage Persistence
 * =================================================
 * Tests that clearInvestigationPersistence correctly:
 * - Removes active session state
 * - Removes agent snapshots
 * - Expires forensic_session_id cookie
 * - Preserves forensic_history
 * - Preserves auth tokens and investigator identity
 *
 * Run: cd apps/web && npm test -- tests/unit/lib/investigationStorage.test.ts
 */

jest.mock("@/lib/storage", () => {
  const store: Record<string, string> = {};
  const sessionStore: Record<string, string> = {};

  return {
    __mockStore: store,
    __mockSessionStore: sessionStore,
    storage: {
      getItem: jest.fn((key: string, parseJson?: boolean) => {
        const val = store[key];
        if (val === undefined) return null;
        if (parseJson) {
          try {
            return JSON.parse(val);
          } catch {
            return null;
          }
        }
        return val;
      }),
      setItem: jest.fn((key: string, value: unknown) => {
        store[key] = typeof value === "string" ? value : JSON.stringify(value);
      }),
      removeItem: jest.fn((key: string) => {
        delete store[key];
      }),
    },
    sessionOnlyStorage: {
      getItem: jest.fn((key: string, parseJson?: boolean) => {
        const val = sessionStore[key];
        if (val === undefined) return null;
        if (parseJson) {
          try {
            return JSON.parse(val);
          } catch {
            return null;
          }
        }
        return val;
      }),
      setItem: jest.fn((key: string, value: unknown) => {
        sessionStore[key] = typeof value === "string" ? value : JSON.stringify(value);
      }),
      removeItem: jest.fn((key: string) => {
        delete sessionStore[key];
      }),
    },
  };
});

const lsStore: Record<string, string> = {};

Object.defineProperty(window, "localStorage", {
  value: {
    getItem: jest.fn((key: string) => lsStore[key] ?? null),
    setItem: jest.fn((key: string, value: string) => {
      lsStore[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete lsStore[key];
    }),
    clear: jest.fn(() => {
      Object.keys(lsStore).forEach((k) => delete lsStore[k]);
    }),
    get length() {
      return Object.keys(lsStore).length;
    },
    key: jest.fn((i: number) => Object.keys(lsStore)[i] ?? null),
  },
  writable: true,
});

import {
  clearInvestigationPersistence,
  clearAgentSnapshots,
  expireSessionCookie,
} from "@/lib/investigationStorage";

describe("investigationStorage", () => {
  let cookieString = "";

  beforeEach(() => {
    const storageModule = jest.requireMock("@/lib/storage");
    Object.keys(storageModule.__mockStore).forEach((k) => delete storageModule.__mockStore[k]);
    Object.keys(storageModule.__mockSessionStore).forEach((k) => delete storageModule.__mockSessionStore[k]);
    Object.keys(lsStore).forEach((k) => delete lsStore[k]);

    cookieString = "";

    Object.defineProperty(document, "cookie", {
      get: jest.fn(() => cookieString),
      set: jest.fn((cookie: string) => {
        cookieString = cookie;
      }),
      configurable: true,
    });
  });

  describe("clearInvestigationPersistence", () => {
    it("preserves forensic_history when clearing active investigation", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      const history = [
        { sessionId: "sess-old", fileName: "old.png", verdict: "LIKELY", timestamp: 1000, type: "Initial" },
      ];
      storageModule.__mockStore["forensic_history"] = JSON.stringify(history);
      storageModule.__mockStore["forensic_session_id"] = "sess-active";
      storageModule.__mockStore["forensic_investigation_ctx"] = '{"session_id":"sess-active"}';

      clearInvestigationPersistence();

      const preserved = JSON.parse(storageModule.__mockStore["forensic_history"] ?? "[]");
      expect(preserved).toEqual(history);
    });

    it("preserves forensic_investigator_id when clearing active investigation", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_investigator_id"] = "inv-12345";
      storageModule.__mockStore["forensic_session_id"] = "sess-active";

      clearInvestigationPersistence();

      expect(storageModule.__mockStore["forensic_investigator_id"]).toBe("inv-12345");
    });

    it("preserves forensic_auth_token when clearing active investigation", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_auth_token"] = "jwt-token-abc";
      storageModule.__mockStore["forensic_session_id"] = "sess-active";

      clearInvestigationPersistence();

      expect(storageModule.__mockStore["forensic_auth_token"]).toBe("jwt-token-abc");
    });

    it("preserves forensic_auth_token_expiry when clearing active investigation", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_auth_token_expiry"] = String(Date.now() + 3600000);
      storageModule.__mockStore["forensic_session_id"] = "sess-active";

      clearInvestigationPersistence();

      expect(storageModule.__mockStore["forensic_auth_token_expiry"]).toBeDefined();
    });

    it("removes forensic_session_id", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_session_id"] = "sess-active";

      clearInvestigationPersistence();

      expect(storageModule.__mockStore["forensic_session_id"]).toBeUndefined();
    });

    it("removes forensic_investigation_ctx", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_investigation_ctx"] = '{"session_id":"sess-active","file_name":"test.png"}';

      clearInvestigationPersistence();

      expect(storageModule.__mockStore["forensic_investigation_ctx"]).toBeUndefined();
    });

    it("removes forensic_initial_agents:{sid}", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_session_id"] = "sess-123";
      lsStore["forensic_initial_agents:sess-123"] = JSON.stringify([{ agent_id: "agent-1" }]);

      clearInvestigationPersistence();

      expect(lsStore["forensic_initial_agents:sess-123"]).toBeUndefined();
    });

    it("removes forensic_deep_agents:{sid}", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_session_id"] = "sess-123";
      lsStore["forensic_deep_agents:sess-123"] = JSON.stringify([{ agent_id: "agent-1" }]);

      clearInvestigationPersistence();

      expect(lsStore["forensic_deep_agents:sess-123"]).toBeUndefined();
    });

    it("expires forensic_session_id cookie", () => {
      cookieString = "forensic_session_id=sess-active; path=/";

      expireSessionCookie();

      expect(cookieString).toContain("max-age=0");
    });

    it("removes session-scoped forensic_investigation_ctx:{sid}", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_session_id"] = "sess-123";
      lsStore["forensic_investigation_ctx:sess-123"] = '{"session_id":"sess-123"}';

      clearInvestigationPersistence();

      expect(lsStore["forensic_investigation_ctx:sess-123"]).toBeUndefined();
    });

    it("preserves session-scoped CONTEXT for a session still in history, prunes orphans", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_history"] = JSON.stringify([
        { sessionId: "sess-keep", fileName: "keep.png", verdict: "AUTHENTIC", timestamp: 1, type: "Initial" },
      ]);
      storageModule.__mockStore["forensic_session_id"] = "sess-active";
      lsStore["forensic_investigation_ctx:sess-keep"] = '{"session_id":"sess-keep","file_name":"keep.png"}';
      lsStore["forensic_thumbnail:sess-keep"] = "data:image/jpeg;base64,xxx";
      lsStore["forensic_mime_type:sess-keep"] = "image/png";
      // Orphan (not in history, not active) — must be pruned.
      lsStore["forensic_investigation_ctx:sess-orphan"] = '{"session_id":"sess-orphan"}';
      lsStore["forensic_thumbnail:sess-orphan"] = "data:image/jpeg;base64,yyy";

      clearInvestigationPersistence();

      // History session keeps its context so a revisit renders correct metadata.
      expect(lsStore["forensic_investigation_ctx:sess-keep"]).toBeDefined();
      expect(lsStore["forensic_thumbnail:sess-keep"]).toBeDefined();
      expect(lsStore["forensic_mime_type:sess-keep"]).toBeDefined();
      // Orphaned session context is removed (bounded accumulation).
      expect(lsStore["forensic_investigation_ctx:sess-orphan"]).toBeUndefined();
      expect(lsStore["forensic_thumbnail:sess-orphan"]).toBeUndefined();
    });

    it("always sweeps streamed agent FINDINGS even for in-history sessions", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_history"] = JSON.stringify([
        { sessionId: "sess-keep", fileName: "keep.png", verdict: "AUTHENTIC", timestamp: 1, type: "Initial" },
      ]);
      lsStore["forensic_initial_agents:sess-keep"] = JSON.stringify([{ agent_id: "agent-1" }]);
      lsStore["forensic_deep_agents:sess-keep"] = JSON.stringify([{ agent_id: "agent-2" }]);

      clearInvestigationPersistence();

      // Findings are stale-prone — never retained, even for revisitable sessions
      // (the result page rebuilds the timeline from the authoritative report).
      expect(lsStore["forensic_initial_agents:sess-keep"]).toBeUndefined();
      expect(lsStore["forensic_deep_agents:sess-keep"]).toBeUndefined();
    });
  });

  describe("clearAgentSnapshots", () => {
    it("removes global forensic_initial_agents", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_initial_agents"] = JSON.stringify([{ agent_id: "agent-1" }]);

      clearAgentSnapshots();

      expect(storageModule.__mockStore["forensic_initial_agents"]).toBeUndefined();
    });

    it("removes global forensic_deep_agents", () => {
      const storageModule = jest.requireMock("@/lib/storage");
      storageModule.__mockStore["forensic_deep_agents"] = JSON.stringify([{ agent_id: "agent-1" }]);

      clearAgentSnapshots();

      expect(storageModule.__mockStore["forensic_deep_agents"]).toBeUndefined();
    });

    it("removes session-scoped agent keys", () => {
      lsStore["forensic_initial_agents:sess-123"] = JSON.stringify([{ agent_id: "agent-1" }]);
      lsStore["forensic_deep_agents:sess-456"] = JSON.stringify([{ agent_id: "agent-2" }]);

      clearAgentSnapshots();

      expect(lsStore["forensic_initial_agents:sess-123"]).toBeUndefined();
      expect(lsStore["forensic_deep_agents:sess-456"]).toBeUndefined();
    });
  });

  describe("expireSessionCookie", () => {
    it("sets cookie with max-age=0", () => {
      expireSessionCookie();

      expect(cookieString).toContain("max-age=0");
      expect(cookieString).toContain("forensic_session_id=");
    });
  });
});