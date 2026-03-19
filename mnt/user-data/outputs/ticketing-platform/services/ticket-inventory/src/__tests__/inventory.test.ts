// services/ticket-inventory/src/__tests__/inventory.test.ts
import request from "supertest";
import app from "../index";

// ── Mock pg Pool ─────────────────────────────────────────────
const mockTicket = {
  ticketID: 1, ownerID: null, eventID: 10,
  ticketType: "General Admission", status: "AVAILABLE", version: 0,
  updatedAt: new Date().toISOString(),
};

jest.mock("pg", () => {
  const mPool = {
    query: jest.fn(),
  };
  return { Pool: jest.fn(() => mPool) };
});

import { Pool } from "pg";
const mockPool = new Pool() as jest.Mocked<Pool>;

describe("Ticket Inventory Service", () => {
  beforeEach(() => jest.clearAllMocks());

  describe("GET /inventory/ticket/:concertId", () => {
    it("returns available tickets for a concert", async () => {
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [mockTicket] });
      const res = await request(app).get("/inventory/ticket/10");
      expect(res.status).toBe(200);
      expect(res.body.data).toBeInstanceOf(Array);
    });
  });

  describe("GET /inventory/ticket/:concertId/:ticketId", () => {
    it("returns 404 when ticket not found", async () => {
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [] });
      const res = await request(app).get("/inventory/ticket/10/999");
      expect(res.status).toBe(404);
    });

    it("returns ticket details when found", async () => {
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [mockTicket] });
      const res = await request(app).get("/inventory/ticket/10/1");
      expect(res.status).toBe(200);
      expect(res.body.data.ticketID).toBe(1);
    });
  });

  describe("PUT /inventory/ticket/:concertId/:ticketId/status", () => {
    it("updates ticket status with correct version", async () => {
      const updated = { ...mockTicket, status: "PENDING", version: 1 };
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [updated] });

      const res = await request(app)
        .put("/inventory/ticket/10/1/status")
        .send({ status: "PENDING", version: 0 });

      expect(res.status).toBe(200);
      expect(res.body.data.status).toBe("PENDING");
    });

    it("returns 409 on optimistic lock conflict", async () => {
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [] });
      const res = await request(app)
        .put("/inventory/ticket/10/1/status")
        .send({ status: "PENDING", version: 999 });
      expect(res.status).toBe(409);
    });
  });

  describe("PUT /inventory/ticket/:ticketId/owner", () => {
    it("transfers ownership on successful payment", async () => {
      const owned = { ...mockTicket, ownerID: 42, status: "SOLD", version: 1 };
      (mockPool.query as jest.Mock).mockResolvedValueOnce({ rows: [owned] });

      const res = await request(app)
        .put("/inventory/ticket/1/owner")
        .send({ buyerID: 42, version: 0 });

      expect(res.status).toBe(200);
      expect(res.body.data.ownerID).toBe(42);
      expect(res.body.data.status).toBe("SOLD");
    });
  });
});
