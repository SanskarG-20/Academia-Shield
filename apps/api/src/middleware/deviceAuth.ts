import crypto from 'crypto';
import { Request, Response, NextFunction } from 'express';
import Device, { IDevice } from '../models/Device';
import { sendError } from '../utils/apiResponse';

export const hashCredential = (value: string) => crypto.createHash('sha256').update(value).digest('hex');

export async function authenticateDevice(header: string | undefined): Promise<IDevice | null> {
  const match = /^Device ([a-f\d]{24})\.([A-Za-z0-9_-]{40,})$/.exec(header || '');
  if (!match) return null;
  const device = await Device.findById(match[1]).select('+credentialHash');
  if (!device || device.revokedAt) return null;
  const presented = Buffer.from(hashCredential(match[2]), 'hex');
  const stored = Buffer.from(device.credentialHash, 'hex');
  if (presented.length !== stored.length || !crypto.timingSafeEqual(presented, stored)) return null;
  return device;
}

export const deviceAuth = async (req: Request, res: Response, next: NextFunction) => {
  try {
    const device = await authenticateDevice(req.headers.authorization);
    if (!device) return sendError(res, 'Device authentication required', 401);
    (req as any).device = device;
    return next();
  } catch {
    return sendError(res, 'Device authentication failed', 401);
  }
};
