// services/resale-ticket-service/src/__tests__/resale-flow.test.ts
// Integration tests: Scenario 2A (seller lists) + 2B (buyer purchases)

import request from "supertest";
import app from "../index";

jest.mock("axios");
import axios from "axios";
const mockAxios = axios as jest.Mocked<typeof axios>;

jest.mock("../../../../shared/utils/amqp", () => ({
  publish: jest.fn().mockResolvedValue(undefined),
  subscribe: jest.fn().mockResolvedValue(undefined),
  TOPICS: { TICKET_RESOLD: "ticket.resold" },
}));
import { publish } from "../../../../shared/utils/amqp";

const mockTicket = {
  ticketID: 5, ownerID: 10, eventID: 3,
  ticketType: "Category 1", status: "SOLD", version: 2,
};

const mockPricing = { eventID: 3, basePrice: 188, resalePrice: 280, currency: "SGD" };

describe("Resale Ticket Service", () => {
  beforeEach(() => jest.clearAllMocks());

  // ── Scenario 2A ───────────────────────────────────────────
  describe("Scenario 2A — POST /resale/list", () => {
    it("lists a ticket for resale successfully", async () => {
      mockAxios.get
        .mockResolvedValueOnce({ data: { data: mockTicket } })       // GET ticket
        .mockResolvedValueOnce({ data: { data: mockPricing } });      // GET pricing
      mockAxios.put
        .mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "RESALE", version: 3 } } })
        .mockResolvedValueOnce({ data: { data: { ...mockTicket, status: "LISTED", version: 4 } } });

      const res = await request(app)
        .post("/resale/list")
        .send({ ticketID: 5, sellerID: 10 });

      expect(res.status).toBe(200);
      expect(res.body.data.status).toBe("LISTED");
      expect(res.body.data.resalePrice).toBe(280);
    });

    it("rejects listing if caller does not own the ticket", async () => {
      mockAxios.get.mockResolvedValueOnce({ data: { data: mockTicket } });

      const res = await request(app)
        .post("/resale/list")
        .send({ ticketID: 5, sellerID: 999 }); // wrong seller

      expect(res.status).toBe(422);
      expect(res.body.error.message).toMatch(/do not own/i);
    });
  });

  // ── Scenario 2B ───────────────────────────────────────────
  describe("Scenario 2B — GET /resale/tickets/:ticketId", () => {
    it("returns 404 for a non-listed ticket", async () => {
      const res = await request(app).get("/resale/tickets/9999");
      expect(res.status).toBe(404);
    });
  });

  describe("Scenario 2B — POST /resale/purchase", () => {
    beforeEach(async () => {
      // Setup: list the ticket first
      mockAxios.get
        .mockResolvedValueOnce({ data: { data: mockTicket } })
        .mockResolvedValueOnce({ data: { data: mockPricing } });
      mockAxios.put
        .mockResolvedValueOnce({ data: {} })
        .mockResolvedValueOnce({ data: {} });

      await request(app).post("/resale/list").send({ ticketID: 5, sellerID: 10 });
      jest.clearAllMocks();
    });

    it("completes full buyer purchase flow and publishes ticket.resold", async () => {
      // GET ticket for version
      mockAxios.get.mockResolvedValueOnce({ data: { data: { ...mockTicket, version: 4 } } });
      // POST payment charge
      mockAxios.post.mockResolvedValueOnce({
        data: { data: { transactionID: "txn_resale_001", status: "SUCCESS" } },
      });
      // PUT transfer ownership
      mockAxios.put.mockResolvedValueOnce({ data: { data: { ...mockTicket, ownerID: 77, status: "SOLD" } } });
      // POST seller payout
      mockAxios.post.mockResolvedValueOnce({ data: { data: { payoutStatus: "SUCCESS" } } });

      const res = await request(app)
        .post("/resale/purchase")
        .send({ ticketID: 5, buyerID: 77, resalePrice: 280 });

      expect(res.status).toBe(200);
      expect(res.body.data.status).toBe("SOLD");
      expect(publish).toHaveBeenCalledWith(
        expect.objectContaining({ topic: "ticket.resold" })
      );
    });

    it("reverts listing status if payment fails", async () => {
      mockAxios.get.mockResolvedValueOnce({ data: { data: { ...mockTicket, version: 4 } } });
      mockAxios.post.mockRejectedValueOnce({
        response: { data: { error: { message: "Insufficient funds" } } },
      });

      const res = await request(app)
        .post("/resale/purchase")
        .send({ ticketID: 5, buyerID: 77, resalePrice: 280 });

      expect(res.status).toBe(402);
      expect(publish).not.toHaveBeenCalled();
    });
  });
});
