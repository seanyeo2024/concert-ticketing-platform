// services/purchase-window/src/__tests__/purchase-flow.test.ts
// Integration test: full Scenario 1 orchestration
// Tests the happy path: session valid → hold → pay → sell → publish

import request from "supertest";
import app from "../index";

// ── Mock axios (internal service calls) ─────────────────────
jest.mock("axios");
import axios from "axios";
const mockAxios = axios as jest.Mocked<typeof axios>;

// ── Mock AMQP ────────────────────────────────────────────────
jest.mock("../../../../shared/utils/amqp", () => ({
  publish: jest.fn().mockResolvedValue(undefined),
  TOPICS: { TICKET_CONFIRMED: "ticket.confirmed" },
}));

import { publish } from "../../../../shared/utils/amqp";

describe("Purchase Window — Scenario 1 Flow", () => {
  const futureExpiry = new Date(Date.now() + 600_000).toISOString();

  const mockTicket = {
    ticketID: 7, eventID: 1, ownerID: null,
    status: "AVAILABLE", version: 0, price: 128,
  };

  const mockPaymentSuccess = {
    transactionID: "txn_abc123",
    status: "SUCCESS",
    buyerID: 42,
    amount: 128,
  };

  beforeEach(() => jest.clearAllMocks());

  describe("POST /purchase/details — happy path", () => {
    it("orchestrates hold → payment → sell → publish", async () => {
      // 1. GET ticket details
      mockAxios.get.mockResolvedValueOnce({ data: { data: mockTicket } });
      // 2. PUT hold (PENDING)
      mockAxios.put.mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "PENDING", version: 1 } } });
      // 3. POST payment charge
      mockAxios.post.mockResolvedValueOnce({ data: { data: mockPaymentSuccess } });
      // 4. PUT status SOLD
      mockAxios.put.mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "SOLD", version: 2 } } });

      const res = await request(app)
        .post("/purchase/details")
        .send({
          concertID: 1,
          sessionToken: "qt-VALIDTOKEN",
          expiresAt: futureExpiry,
          ticketID: 7,
          buyerID: 42,
        });

      expect(res.status).toBe(200);
      expect(res.body.data.status).toBe("SOLD");
      expect(res.body.data.transactionID).toBe("txn_abc123");

      // Verify AMQP event was published
      expect(publish).toHaveBeenCalledWith({
        topic: "ticket.confirmed",
        data: expect.objectContaining({ ticketID: 7, buyerID: 42 }),
      });
    });
  });

  describe("POST /purchase/details — expired session", () => {
    it("rejects purchases with expired window", async () => {
      const expiredTime = new Date(Date.now() - 1000).toISOString();

      const res = await request(app)
        .post("/purchase/details")
        .send({
          concertID: 1,
          sessionToken: "qt-EXPIRED",
          expiresAt: expiredTime,
          ticketID: 7,
          buyerID: 42,
        });

      expect(res.status).toBe(422);
      expect(res.body.error.message).toMatch(/expired/i);
      expect(publish).not.toHaveBeenCalled();
    });
  });

  describe("POST /purchase/details — payment failure with rollback", () => {
    it("reverts ticket to AVAILABLE when payment fails", async () => {
      // 1. GET ticket
      mockAxios.get.mockResolvedValueOnce({ data: { data: mockTicket } });
      // 2. PUT PENDING (hold)
      mockAxios.put.mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "PENDING" } } });
      // 3. POST payment — fails
      mockAxios.post.mockRejectedValueOnce({
        response: { data: { error: { message: "Card declined" } } },
      });
      // 4. PUT rollback to AVAILABLE
      mockAxios.put.mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "AVAILABLE" } } });

      const res = await request(app)
        .post("/purchase/details")
        .send({
          concertID: 1,
          sessionToken: "qt-VALIDTOKEN2",
          expiresAt: futureExpiry,
          ticketID: 7,
          buyerID: 99,
        });

      expect(res.status).toBe(402);
      expect(res.body.error.message).toMatch(/Card declined/i);

      // Rollback PUT should have been called with AVAILABLE
      expect(mockAxios.put).toHaveBeenLastCalledWith(
        expect.stringContaining("/status"),
        expect.objectContaining({ status: "AVAILABLE" })
      );
    });
  });

  describe("POST /purchase/details — ticket already taken", () => {
    it("rejects when ticket is not AVAILABLE", async () => {
      mockAxios.get.mockResolvedValueOnce({
        data: { data: { ...mockTicket, status: "SOLD" } },
      });

      const res = await request(app)
        .post("/purchase/details")
        .send({
          concertID: 1,
          sessionToken: "qt-VALIDTOKEN3",
          expiresAt: futureExpiry,
          ticketID: 7,
          buyerID: 55,
        });

      expect(res.status).toBe(422);
      expect(res.body.error.message).toMatch(/no longer available/i);
    });
  });
});
