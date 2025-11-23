import mongoose, { Document, Schema } from 'mongoose';
import bcrypt from 'bcryptjs';

export interface IProfessor extends Document {
  name: string;
  email: string;
  passwordHash: string;
  department: string;
  designation: string;
  matchPassword: (enteredPassword: string) => Promise<boolean>;
}

const ProfessorSchema = new Schema<IProfessor>({
  name: { type: String, required: true },
  email: { type: String, required: true, unique: true },
  passwordHash: { type: String, required: true },
  department: { type: String, required: true },
  designation: { type: String, required: true }
}, { timestamps: true });

ProfessorSchema.methods.matchPassword = async function (enteredPassword: string) {
  return await bcrypt.compare(enteredPassword, this.passwordHash);
};

ProfessorSchema.pre('save', async function (next) {
  if (!this.isModified('passwordHash')) {
    next();
  }
  const salt = await bcrypt.genSalt(10);
  this.passwordHash = await bcrypt.hash(this.passwordHash, salt);
});

export default mongoose.model<IProfessor>('Professor', ProfessorSchema);