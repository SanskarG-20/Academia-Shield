import mongoose, { Document, Schema } from 'mongoose';

export enum SessionStatus {
  UPCOMING = 'Upcoming',
  ACTIVE = 'Active',
  COMPLETED = 'Completed',
  CANCELLED = 'Cancelled'
}

export interface ISession extends Document {
  title: string;
  course: string;
  type: string;
  startTime: Date;
  endTime: Date;
  status: SessionStatus;
  professorId: mongoose.Types.ObjectId;
  ruleSetId: mongoose.Types.ObjectId;
  batchIds: mongoose.Types.ObjectId[];
  joinedStudentIds: mongoose.Types.ObjectId[];
}

const SessionSchema = new Schema<ISession>({
  title: { type: String, required: true },
  course: { type: String, required: true },
  type: { type: String, required: true },
  startTime: { type: Date, required: true },
  endTime: { type: Date, required: true },
  status: { type: String, enum: Object.values(SessionStatus), default: SessionStatus.UPCOMING },
  professorId: { type: Schema.Types.ObjectId, ref: 'Professor', required: true },
  ruleSetId: { type: Schema.Types.ObjectId, ref: 'Rule' },
  batchIds: [{ type: Schema.Types.ObjectId, ref: 'Batch' }],
  joinedStudentIds: [{ type: Schema.Types.ObjectId, ref: 'Student' }],
}, { timestamps: true });

export default mongoose.model<ISession>('Session', SessionSchema);