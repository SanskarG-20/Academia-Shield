import mongoose, { Document, Schema } from 'mongoose';

export interface IBatch extends Document {
  name: string;
  code: string;
  department: string;
  year: string;
  professorId: mongoose.Types.ObjectId;
  students: mongoose.Types.ObjectId[];
}

const BatchSchema = new Schema<IBatch>({
  name: { type: String, required: true },
  code: { type: String, required: true, unique: true, uppercase: true },
  department: { type: String, required: true },
  year: { type: String, required: true },
  professorId: { type: Schema.Types.ObjectId, ref: 'Professor', required: true },
  students: [{ type: Schema.Types.ObjectId, ref: 'Student' }]
}, { timestamps: true });

export default mongoose.model<IBatch>('Batch', BatchSchema);