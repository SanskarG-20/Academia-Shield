import mongoose, { Document, Schema } from 'mongoose';

export interface IActivityEvent extends Document {
  sessionId: mongoose.Types.ObjectId;
  studentId: mongoose.Types.ObjectId;
  studentName: string;
  sapId: string;
  eventType: 'APP_FOCUS' | 'DOMAIN_VISIT' | 'DOMAIN_BLOCKED';
  application: string;
  domain?: string;
  title?: string;
  status: 'ALLOWED' | 'BLOCKED';
  startedAt: Date;
  endedAt: Date;
  durationMs: number;
  createdAt: Date;
}

const ActivityEventSchema = new Schema<IActivityEvent>(
  {
    sessionId: { type: Schema.Types.ObjectId, ref: 'Session', required: true },
    studentId: { type: Schema.Types.ObjectId, ref: 'Student', required: true },
    studentName: { type: String, required: true },
    sapId: { type: String, required: true },
    eventType: {
      type: String,
      enum: ['APP_FOCUS', 'DOMAIN_VISIT', 'DOMAIN_BLOCKED'],
      required: true,
    },
    application: { type: String, required: true },
    domain: { type: String },
    title: { type: String, maxlength: 200 },
    status: { type: String, enum: ['ALLOWED', 'BLOCKED'], default: 'ALLOWED' },
    startedAt: { type: Date, required: true },
    endedAt: { type: Date, required: true },
    durationMs: { type: Number, required: true },
  },
  { timestamps: true }
);

// Primary query index: fetch activity for a student in a session
ActivityEventSchema.index({ sessionId: 1, studentId: 1, startedAt: -1 });

// TTL index: auto-delete after 90 days
const RETENTION_DAYS = parseInt(process.env.ACTIVITY_RETENTION_DAYS || '90', 10);
ActivityEventSchema.index({ createdAt: 1 }, { expireAfterSeconds: RETENTION_DAYS * 86400 });

export default mongoose.model<IActivityEvent>('ActivityEvent', ActivityEventSchema);
