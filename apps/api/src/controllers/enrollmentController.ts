import crypto from 'crypto';
import { Request, Response } from 'express';
import Device from '../models/Device';
import EnrollmentClaim from '../models/EnrollmentClaim';
import Student from '../models/Student';
import { authenticateDevice, hashCredential } from '../middleware/deviceAuth';
import { sendError, sendSuccess } from '../utils/apiResponse';

export const issueEnrollmentClaim = async (req: Request | any, res: Response) => {
  const student = await Student.findById(req.user.id).select('_id');
  if (!student) return sendError(res, 'Student not found', 404);
  const now = new Date();
  await EnrollmentClaim.updateMany({ studentId: student._id, consumedAt: null }, { $set: { consumedAt: now } });
  const claim = crypto.randomBytes(24).toString('base64url');
  const expiresAt = new Date(now.getTime() + 10 * 60_000);
  await EnrollmentClaim.create({ studentId: student._id, claimHash: hashCredential(claim), expiresAt });
  return sendSuccess(res, { claim, expiresAt }, 'Enrollment claim issued');
};

export const enrollDevice = async (req: Request, res: Response) => {
  // Enrollment is performed by the local CLI. Browser JavaScript receives the
  // claim but must never receive the long-lived device credential.
  if (req.headers.origin) return sendError(res, 'Enroll from the local agent', 403);
  const claim = typeof req.body?.claim === 'string' ? req.body.claim.trim() : '';
  if (!/^[A-Za-z0-9_-]{32}$/.test(claim)) return sendError(res, 'Invalid enrollment claim', 400);
  const previous = req.headers.authorization ? await authenticateDevice(req.headers.authorization) : null;
  if (req.headers.authorization && !previous) return sendError(res, 'Previous device credential is invalid', 401);

  const record = await EnrollmentClaim.findOneAndUpdate(
    { claimHash: hashCredential(claim), consumedAt: null, expiresAt: { $gt: new Date() } },
    { $set: { consumedAt: new Date() } },
    { new: true }
  );
  if (!record) return sendError(res, 'Enrollment claim expired or already used', 400);
  if (previous) {
    previous.revokedAt = new Date();
    await previous.save();
  }
  const secret = crypto.randomBytes(32).toString('base64url');
  const device = await Device.create({ studentId: record.studentId, credentialHash: hashCredential(secret) });
  return sendSuccess(res, { deviceId: String(device._id), credential: `${device._id}.${secret}` }, 'Device enrolled', 201);
};

export const listDevices = async (req: Request | any, res: Response) => {
  const devices = await Device.find({ studentId: req.user.id }).select('_id createdAt lastSeenAt revokedAt').sort({ createdAt: -1 });
  return sendSuccess(res, devices, 'Devices fetched');
};

export const revokeDevice = async (req: Request | any, res: Response) => {
  const device = await Device.findOneAndUpdate(
    { _id: req.params.id, studentId: req.user.id, revokedAt: null },
    { $set: { revokedAt: new Date() } },
    { new: true }
  );
  if (!device) return sendError(res, 'Device not found', 404);
  return sendSuccess(res, { deviceId: String(device._id), revoked: true }, 'Device revoked');
};
