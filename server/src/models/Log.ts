import mongoose, { Document, Schema } from 'mongoose';

export interface ILog extends Document {
  sessionId: mongoose.Types.ObjectId;
  studentId: mongoose.Types.ObjectId;
  studentName: string;
  type: 'USAGE' | 'EVENT' | 'ANOMALY';
  resource?: string;
  details?: string;
  duration?: number;
  engagementScore?: number;
  timestamp: Date;
  isViolation: boolean;
}

const LogSchema = new Schema<ILog>({
  sessionId: { type: Schema.Types.ObjectId, ref: 'Session', required: true },
  studentId: { type: Schema.Types.ObjectId, ref: 'Student', required: true },
  studentName: { type: String, required: true },
  type: { type: String, enum: ['USAGE', 'EVENT', 'ANOMALY'], required: true },
  resource: { type: String }, // Website domain or App name
  details: { type: String },
  duration: { type: Number }, // Seconds
  engagementScore: { type: Number },
  isViolation: { type: Boolean, default: false },
  timestamp: { type: Date, default: Date.now }
});

export default mongoose.model<ILog>('Log', LogSchema);