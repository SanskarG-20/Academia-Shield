import mongoose, { Document, Schema } from 'mongoose';

export interface IOtp extends Document {
  sapId: string;
  code: string;
  email?: string;
  expiresAt: Date;
}

const OtpSchema = new Schema<IOtp>({
  sapId: { type: String, required: true },
  code: { type: String, required: true },
  email: { type: String },
  expiresAt: { type: Date, required: true, index: { expires: '5m' } } // Auto-delete after 5 mins
}, { timestamps: true });

export default mongoose.model<IOtp>('Otp', OtpSchema);
