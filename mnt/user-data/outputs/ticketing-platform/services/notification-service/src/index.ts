// ============================================================
// services/notification-service/src/index.ts
// Atomic Microservice — sends email/SMS confirmations
// Consumes: ticket.confirmed, window.granted, hold.expired (AMQP)
// Integrates with: Twilio (SMS) + SendGrid/Nodemailer (Email)
// Replicas: 2
// ============================================================
import express from "express";
import nodemailer from "nodemailer";
import twilio from "twilio";
import { subscribe, TOPICS } from "../../../shared/utils/amqp";
import { ok, asyncHandler, errorHandler } from "../../../shared/utils/http";
import type {
  TicketConfirmedEvent,
  TicketResoldEvent,
  WindowGrantedEvent,
} from "../../../shared/types";

const app = express();
app.use(express.json());

// ── Email (SMTP via Nodemailer / SendGrid) ───────────────────
const mailer = nodemailer.createTransport({
  host: process.env.SMTP_HOST ?? "smtp.sendgrid.net",
  port: 587,
  auth: {
    user: process.env.SMTP_USER ?? "apikey",
    pass: process.env.SMTP_PASS ?? "SG.placeholder",
  },
});

// ── SMS (Twilio) ─────────────────────────────────────────────
const twilioClient = twilio(
  process.env.TWILIO_ACCOUNT_SID ?? "ACplaceholder",
  process.env.TWILIO_AUTH_TOKEN ?? "placeholder"
);

// ── Helpers ──────────────────────────────────────────────────

async function sendEmail(to: string, subject: string, html: string): Promise<void> {
  await mailer.sendMail({
    from: process.env.EMAIL_FROM ?? "tickets@platform.com",
    to,
    subject,
    html,
  });
}

async function sendSMS(to: string, body: string): Promise<void> {
  await twilioClient.messages.create({
    from: process.env.TWILIO_FROM ?? "+1234567890",
    to,
    body,
  });
}

// TODO: replace with real user lookup from a User service
async function getUserContact(userID: number): Promise<{ email: string; phone: string }> {
  return {
    email: `user${userID}@example.com`,
    phone: "+6500000000",
  };
}

// ── Routes ──────────────────────────────────────────────────

/**
 * POST /notification/send
 * Manual notification trigger (for admin / testing).
 */
app.post(
  "/notification/send",
  asyncHandler(async (req, res) => {
    const { to, subject, message, channel } = req.body;
    if (channel === "sms") {
      await sendSMS(to, message);
    } else {
      await sendEmail(to, subject, `<p>${message}</p>`);
    }
    ok(res, { sent: true });
  })
);

// ── AMQP consumers ──────────────────────────────────────────

async function startConsumers(): Promise<void> {
  // ticket.confirmed → send purchase confirmation email + SMS
  await subscribe(
    [TOPICS.TICKET_CONFIRMED],
    "notification-service-confirmed",
    async (_topic, data) => {
      const { ticketID, buyerID, eventID } = data as TicketConfirmedEvent;
      const contact = await getUserContact(buyerID);

      await sendEmail(
        contact.email,
        "Your Ticket is Confirmed! 🎉",
        `
          <h1>Booking Confirmed</h1>
          <p>Hi! Your ticket (ID: <strong>${ticketID}</strong>) for event ${eventID} is confirmed.</p>
          <p>Your QR code will be sent separately once generated.</p>
        `
      );

      await sendSMS(contact.phone, `Ticket confirmed! Ticket ID: ${ticketID}. Your QR code will arrive shortly.`);
      console.log(`[notification] Sent confirmation for ticket ${ticketID}`);
    }
  );

  // ticket.resold → send new QR to resale buyer
  await subscribe(
    [TOPICS.TICKET_RESOLD],
    "notification-service-resold",
    async (_topic, data) => {
      const { ticketID, buyerID, newQR, eventID } = data as TicketResoldEvent;
      const contact = await getUserContact(buyerID);

      await sendEmail(
        contact.email,
        "Your Resale Ticket & QR Code 🎟",
        `
          <h1>Resale Purchase Confirmed</h1>
          <p>Ticket ID: <strong>${ticketID}</strong> | Event: ${eventID}</p>
          <p>Your new QR code: <code>${newQR}</code></p>
          <p>Please screenshot this and present at the venue.</p>
        `
      );

      console.log(`[notification] Sent resale QR for ticket ${ticketID} to buyer ${buyerID}`);
    }
  );

  // window.granted → notify user it's their turn
  await subscribe(
    [TOPICS.WINDOW_GRANTED],
    "notification-service-window",
    async (_topic, data) => {
      const { userID, concertID, expiresAt } = data as WindowGrantedEvent;
      const contact = await getUserContact(userID);

      await sendSMS(
        contact.phone,
        `It's your turn! You have 10 minutes to complete your purchase for concert ${concertID}. Expires: ${expiresAt}`
      );

      console.log(`[notification] Notified user ${userID} of purchase window`);
    }
  );

  // hold.expired → notify user their hold expired
  await subscribe(
    ["hold.expired"],
    "notification-service-hold-expired",
    async (_topic, data: any) => {
      const contact = await getUserContact(data.userID);
      await sendEmail(
        contact.email,
        "Your ticket hold has expired",
        `<p>Your hold on ticket ${data.ticketID} has expired. Please rejoin the queue to try again.</p>`
      );
    }
  );
}

app.use(errorHandler);

const PORT = process.env.PORT ?? 3006;
app.listen(PORT, async () => {
  await startConsumers();
  console.log(`[notification-service] Listening on :${PORT}`);
});

export default app;
