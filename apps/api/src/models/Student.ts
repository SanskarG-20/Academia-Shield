import mongoose, { Document, Schema } from 'mongoose';

export interface IStudent extends Document {
  sapId: string;
  name: string;
  email: string;
  department: string;
  rollNumber: string;
  year: string;
  joinedBatches: mongoose.Types.ObjectId[];
}

const StudentSchema = new Schema<IStudent>({
  sapId: {
    type: String,
    required: true,
    unique: true,
    match: [/^\d{12}$/, 'sapId must be exactly 12 digits'],
  },
  name: { type: String, required: true },
  email: { type: String, required: true },
  department: { type: String, required: true },
  rollNumber: { type: String, required: true },
  year: { type: String, required: true },
  joinedBatches: [{ type: Schema.Types.ObjectId, ref: 'Batch' }]
}, { timestamps: true });

export default mongoose.model<IStudent>('Student', StudentSchema);