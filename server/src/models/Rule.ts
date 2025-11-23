import mongoose, { Document, Schema } from 'mongoose';

export interface IRule extends Document {
  name: string;
  mode: 'Whitelist' | 'Blocklist';
  websites: string[];
  applications: string[];
  professorId: mongoose.Types.ObjectId;
}

const RuleSchema = new Schema<IRule>({
  name: { type: String, required: true },
  mode: { type: String, enum: ['Whitelist', 'Blocklist'], default: 'Blocklist' },
  websites: [{ type: String }],
  applications: [{ type: String }],
  professorId: { type: Schema.Types.ObjectId, ref: 'Professor', required: true }
}, { timestamps: true });

export default mongoose.model<IRule>('Rule', RuleSchema);