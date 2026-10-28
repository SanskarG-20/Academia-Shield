import mongoose, { Document, Schema } from 'mongoose';

export interface IDevice extends Document {
  studentId: mongoose.Types.ObjectId;
  credentialHash: string;
  createdAt: Date;
  lastSeenAt?: Date;
  revokedAt?: Date;
}

const schema = new Schema<IDevice>({
  studentId: { type: Schema.Types.ObjectId, ref: 'Student', required: true, index: true },
  credentialHash: { type: String, required: true, unique: true, select: false },
  lastSeenAt: Date,
  revokedAt: { type: Date, default: null },
}, { timestamps: true });

export default mongoose.model<IDevice>('Device', schema);
