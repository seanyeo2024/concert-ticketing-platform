// services/queue-service/src/__tests__/queue.test.ts
// Unit tests for Queue Service
// Run: npm test (from services/queue-service)

import request from "supertest";
import app from "../index";

// ── Mock Redis ───────────────────────────────────────────────
jest.mock("ioredis", () => {
  const store: Record<string, string> = {};
  const sortedSets: Record<string, { score: number; member: string }[]> = {};

  return jest.fn().mockImplementation(() => ({
    get: jest.fn(async (key: string) => store[key] ?? null),
    set: jest.fn(async (key: string, val: string) => { store[key] = val; }),
    setex: jest.fn(async (key: string, _ttl: number, val: string) => { store[key] = val; }),
    del: jest.fn(async (key: string) => { delete store[key]; }),
    incr: jest.fn(async (key: string) => {
      store[key] = String((parseInt(store[key] ?? "0") || 0) + 1);
      return parseInt(store[key]);
    }),
    zadd: jest.fn(async (key: string, score: number, member: string) => {
      if (!sortedSets[key]) sortedSets[key] = [];
      sortedSets[key].push({ score, member });
    }),
    zrank: jest.fn(async (key: string, member: string) => {
      const set = sortedSets[key] ?? [];
      const sorted = set.sort((a, b) => a.score - b.score);
      const idx = sorted.findIndex((x) => x.member === member);
      return idx === -1 ? null : idx;
    }),
    zrange: jest.fn(async (key: string, start: number, end: number) => {
      const set = (sortedSets[key] ?? []).sort((a, b) => a.score - b.score);
      return set.slice(start, end + 1).map((x) => x.member);
    }),
    zrem: jest.fn(async (key: string, ...members: string[]) => {
      if (sortedSets[key]) {
        sortedSets[key] = sortedSets[key].filter((x) => !members.includes(x.member));
      }
    }),
  }));
});

// ── Mock AMQP ────────────────────────────────────────────────
jest.mock("../../../../shared/utils/amqp", () => ({
  publish: jest.fn().mockResolvedValue(undefined),
  subscribe: jest.fn().mockResolvedValue(undefined),
  TOPICS: {
    TICKET_CONFIRMED: "ticket.confirmed",
    WINDOW_GRANTED: "window.granted",
    HOLD_EXPIRED: "hold.expired",
  },
}));

// ── Tests ─────────────────────────────────────────────────────
describe("Queue Service", () => {
  const mockUserMiddleware = (req: any, _res: any, next: any) => {
    req.user = { id: 42 };
    next();
  };

  beforeAll(() => {
    // Inject a mock user into all requests (Kong sets this in production)
    app.use(mockUserMiddleware);
  });

  describe("POST /queue/join", () => {
    it("should return 201 with sessionToken and position", async () => {
      const res = await request(app)
        .post("/queue/join")
        .send({ concertId: 1 });

      expect(res.status).toBe(201);
      expect(res.body.data).toHaveProperty("sessionToken");
      expect(res.body.data).toHaveProperty("position");
      expect(res.body.data).toHaveProperty("expiresAt");
    });

    it("should reject if concertId is missing", async () => {
      const res = await request(app).post("/queue/join").send({});
      expect(res.status).toBeGreaterThanOrEqual(400);
    });
  });

  describe("GET /queue/position/:sessionToken", () => {
    it("should return 404 for unknown token", async () => {
      const res = await request(app).get("/queue/position/nonexistent-token");
      expect(res.status).toBe(404);
    });

    it("should return position for a valid token", async () => {
      // First join the queue
      const joinRes = await request(app)
        .post("/queue/join")
        .send({ concertId: 99 });

      const { sessionToken } = joinRes.body.data;

      const posRes = await request(app).get(`/queue/position/${sessionToken}`);
      expect(posRes.status).toBe(200);
      expect(posRes.body.data).toHaveProperty("position");
      expect(posRes.body.data.status).toBe("WAITING");
    });
  });

  describe("DELETE /queue/leave/:sessionToken", () => {
    it("should allow a user to leave the queue", async () => {
      const joinRes = await request(app)
        .post("/queue/join")
        .send({ concertId: 55 });

      const { sessionToken } = joinRes.body.data;
      const leaveRes = await request(app).delete(`/queue/leave/${sessionToken}`);
      expect(leaveRes.status).toBe(200);
    });
  });

  describe("POST /queue/grant/:concertId", () => {
    it("should grant windows to waiting users", async () => {
      await request(app).post("/queue/join").send({ concertId: 77 });

      const grantRes = await request(app)
        .post("/queue/grant/77")
        .send({ batchSize: 5 });

      expect(grantRes.status).toBe(200);
      expect(grantRes.body.data).toHaveProperty("granted");
    });
  });
});
