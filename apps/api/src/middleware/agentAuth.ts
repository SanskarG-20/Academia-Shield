import { Request, Response, NextFunction } from 'express';
import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import { sendError } from '../utils/apiResponse';

interface AgentRequest extends Request {
  user?: any;
}

const AGENT_SECRET = (process.env.AGENT_SHARED_SECRET || '').trim();

let warnedAboutOpenEndpoints = false;

const timingSafeEquals = (a: string, b: string) => {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return crypto.timingSafeEqual(bufA, bufB);
};

/**
 * Guards the /api/agent/* endpoints, which are hit by two very different callers:
 *
 *   1. The desktop agent, which presents a shared secret in `X-Agent-Secret`.
 *   2. The web app, where a signed-in student's browser polls config and posts
 *      heartbeats. Browsers can't hold a secret, so a valid JWT is accepted instead.
 *
 * Enforcement is opt-in: with AGENT_SHARED_SECRET unset the endpoints stay open so
 * that agents already installed in labs keep working. Set the variable once the
 * rebuilt .exe has been rolled out to turn the check on.
 */
export const agentAuth = (req: AgentRequest, res: Response, next: NextFunction) => {
  if (!AGENT_SECRET) {
    if (!warnedAboutOpenEndpoints) {
      warnedAboutOpenEndpoints = true;
      console.warn(
        '[agent-auth] AGENT_SHARED_SECRET is not set — /api/agent/* is unauthenticated. ' +
          'Set it (and rebuild the agent with a matching value) to enable enforcement.'
      );
    }
    return next();
  }

  const presentedSecret = String(req.headers['x-agent-secret'] || '').trim();
  if (presentedSecret && timingSafeEquals(presentedSecret, AGENT_SECRET)) {
    return next();
  }

  // Fall back to a normal user session so the web app's own polling still works.
  const authHeader = req.headers.authorization;
  if (authHeader?.startsWith('Bearer ')) {
    try {
      req.user = jwt.verify(authHeader.split(' ')[1], process.env.JWT_SECRET as string);
      return next();
    } catch {
      // Fall through to the shared 401 below.
    }
  }

  console.warn(`[agent-auth] denied ${req.method} ${req.originalUrl} from ${req.ip}`);
  return sendError(res, 'Not authorized to access agent endpoints', 401);
};
