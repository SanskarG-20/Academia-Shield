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
  joinMode: 'auto' | 'opt-in';
  aiSummary?: string;
  summaryGeneratedAt?: Date;
  summaryVersion?: number;
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
  joinMode: { type: String, enum: ['auto', 'opt-in'], default: 'opt-in' },
  aiSummary: { type: String },
  summaryGeneratedAt: { type: Date },
  summaryVersion: { type: Number },
}, { timestamps: true });

SessionSchema.index({ status: 1, startTime: 1, endTime: 1 });
SessionSchema.index({ joinedStudentIds: 1, status: 1 });
SessionSchema.index({ batchIds: 1, status: 1 });

export default mongoose.model<ISession>('Session', SessionSchema);
