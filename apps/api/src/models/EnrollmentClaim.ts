import mongoose, { Document, Schema } from 'mongoose';

export interface IEnrollmentClaim extends Document {
  studentId: mongoose.Types.ObjectId;
  claimHash: string;
  expiresAt: Date;
  consumedAt?: Date;
}

const schema = new Schema<IEnrollmentClaim>({
  studentId: { type: Schema.Types.ObjectId, ref: 'Student', required: true, index: true },
  claimHash: { type: String, required: true, unique: true },
  expiresAt: { type: Date, required: true, index: { expires: 0 } },
  consumedAt: { type: Date, default: null },
}, { timestamps: true });

export default mongoose.model<IEnrollmentClaim>('EnrollmentClaim', schema);
