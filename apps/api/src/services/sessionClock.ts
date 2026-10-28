import Session from '../models/Session';
import { getIO } from './socketService';

export async function reconcileSessions(now = new Date()): Promise<{ started: number; ended: number }> {
  let started = 0;
  let ended = 0;
  const due = await Session.find({ status: 'Upcoming', startTime: { $lte: now }, endTime: { $gt: now } }).select('_id');
  for (const session of due) {
    const result = await Session.updateOne({ _id: session._id, status: 'Upcoming', startTime: { $lte: now }, endTime: { $gt: now } }, { $set: { status: 'Active' } });
    if (result.modifiedCount) {
      started++;
      getIO()?.to(String(session._id)).emit('session_started', { sessionId: String(session._id) });
    }
  }
  const expired = await Session.find({ status: { $in: ['Upcoming', 'Active'] }, endTime: { $lte: now } }).select('_id');
  for (const session of expired) {
    const result = await Session.updateOne({ _id: session._id, status: { $in: ['Upcoming', 'Active'] }, endTime: { $lte: now } }, { $set: { status: 'Completed' } });
    if (result.modifiedCount) {
      ended++;
      getIO()?.to(String(session._id)).emit('session_ended', { sessionId: String(session._id) });
    }
  }
  return { started, ended };
}
