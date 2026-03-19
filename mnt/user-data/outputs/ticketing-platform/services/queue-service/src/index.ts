// ============================================================
// services/queue-service/src/index.ts
// Scenario 1 — Queue (Composite Microservice)
// Handles: join queue, track position, grant purchase windows
// Replicas: 3 | Protocol: HTTP + SSE + AMQP
// ============================================================
import express from "express";
import Redis from "ioredis";
import { v4 as uuidv4 } from "uuid";
import { publish, TOPICS } from "../../../shared/utils/amqp";
import { ok, created, asyncHandler, errorHandler, NotFoundError, ConflictError } from "../../../shared/utils/http";

const app = express();
app.use(express.json());

const redis = new Redis({
  host: process.env.REDIS_HOST ?? "redis",
  port: Number(process.env.REDIS_PORT ?? 6379),
});

const WINDOW_DURATION_SECONDS = 600; // 10 minutes to complete purchase

// ── Routes ──────────────────────────────────────────────────

/**
 * POST /queue/join
 * Body: { concertId: number }
 * Assigns a position in the virtual queue.
 * Returns: { sessionToken, position, estimatedWait }
 */
app.post(
  "/queue/join",
  asyncHandler(async (req, res) => {
    const { concertId } = req.body;
    const userID: number = (req as any).user?.id; // set by Kong JWT middleware

    if (!concertId) throw new Error("concertId is required");

    // Check if user already in queue
    const existingToken = await redis.get(`queue:user:${userID}:${concertId}`);
    if (existingToken) throw new ConflictError("User already in queue for this concert");

    // Atomically increment queue counter
    const position = await redis.incr(`queue:size:${concertId}`);
    const sessionToken = uuidv4();
    const expiresAt = new Date(Date.now() + WINDOW_DURATION_SECONDS * 1000).toISOString();

    // Store queue entry (TTL: 2 hours max wait)
    await redis.setex(
      `queue:entry:${sessionToken}`,
      7200,
      JSON.stringify({ userID, concertId, position, status: "WAITING", sessionToken, expiresAt })
    );
    // Reverse lookup: user → sessionToken
    await redis.setex(`queue:user:${userID}:${concertId}`, 7200, sessionToken);

    // Track position in sorted set (score = join timestamp)
    await redis.zadd(`queue:concert:${concertId}`, Date.now(), sessionToken);

    created(res, { sessionToken, position, expiresAt });
  })
);

/**
 * GET /queue/position/:sessionToken
 * Returns current queue position and status.
 * Used by frontend to poll or as SSE initial state.
 */
app.get(
  "/queue/position/:sessionToken",
  asyncHandler(async (req, res) => {
    const { sessionToken } = req.params;
    const raw = await redis.get(`queue:entry:${sessionToken}`);
    if (!raw) throw new NotFoundError("Queue entry");

    const entry = JSON.parse(raw);
    // Recalculate live position based on sorted set rank
    const rank = await redis.zrank(`queue:concert:${entry.concertId}`, sessionToken);
    entry.position = rank !== null ? rank + 1 : entry.position;

    ok(res, entry);
  })
);

/**
 * GET /queue/stream/:sessionToken
 * Server-Sent Events: pushes live position updates to the browser.
 */
app.get("/queue/stream/:sessionToken", async (req, res) => {
  const { sessionToken } = req.params;

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  const interval = setInterval(async () => {
    const raw = await redis.get(`queue:entry:${sessionToken}`);
    if (!raw) {
      res.write(`data: ${JSON.stringify({ error: "Queue entry not found" })}\n\n`);
      clearInterval(interval);
      return;
    }
    const entry = JSON.parse(raw);
    const rank = await redis.zrank(`queue:concert:${entry.concertId}`, sessionToken);
    const position = rank !== null ? rank + 1 : 0;

    res.write(`data: ${JSON.stringify({ position, status: entry.status, expiresAt: entry.expiresAt })}\n\n`);

    // Stop streaming once window is granted
    if (entry.status === "GRANTED") clearInterval(interval);
  }, 3000);

  req.on("close", () => clearInterval(interval));
});

/**
 * POST /queue/grant/:concertId
 * Internal/cron endpoint — advances the queue and grants windows.
 * Typically called by a scheduler or the Purchase Window service.
 */
app.post(
  "/queue/grant/:concertId",
  asyncHandler(async (req, res) => {
    const concertId = Number(req.params.concertId);
    const batchSize = Number(req.body.batchSize ?? 10);

    // Get the next N users in queue
    const tokens = await redis.zrange(`queue:concert:${concertId}`, 0, batchSize - 1);

    const granted = [];
    for (const sessionToken of tokens) {
      const raw = await redis.get(`queue:entry:${sessionToken}`);
      if (!raw) continue;

      const entry = JSON.parse(raw);
      entry.status = "GRANTED";
      const expiresAt = new Date(Date.now() + WINDOW_DURATION_SECONDS * 1000).toISOString();
      entry.expiresAt = expiresAt;

      await redis.setex(`queue:entry:${sessionToken}`, WINDOW_DURATION_SECONDS, JSON.stringify(entry));

      // Publish window.granted event for Notification service
      await publish({
        topic: "window.granted",
        data: { userID: entry.userID, concertID: concertId, sessionToken, expiresAt },
      });

      granted.push({ sessionToken, userID: entry.userID });
    }

    // Remove granted users from the sorted queue
    if (tokens.length > 0) {
      await redis.zrem(`queue:concert:${concertId}`, ...tokens);
    }

    ok(res, { granted: granted.length, tokens: granted });
  })
);

/**
 * DELETE /queue/leave/:sessionToken
 * User explicitly leaves queue or session expired.
 */
app.delete(
  "/queue/leave/:sessionToken",
  asyncHandler(async (req, res) => {
    const { sessionToken } = req.params;
    const raw = await redis.get(`queue:entry:${sessionToken}`);
    if (!raw) throw new NotFoundError("Queue entry");

    const entry = JSON.parse(raw);
    await redis.del(`queue:entry:${sessionToken}`);
    await redis.del(`queue:user:${entry.userID}:${entry.concertId}`);
    await redis.zrem(`queue:concert:${entry.concertId}`, sessionToken);

    ok(res, { message: "Left queue successfully" });
  })
);

// ── Error handler (must be last) ────────────────────────────
app.use(errorHandler);

const PORT = process.env.PORT ?? 3001;
app.listen(PORT, () => console.log(`[queue-service] Listening on :${PORT}`));

export default app;
