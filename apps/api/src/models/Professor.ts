import mongoose, { Document, Schema } from 'mongoose';
import bcrypt from 'bcryptjs';

const BCRYPT_HASH_REGEX = /^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$/;

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

ProfessorSchema.pre('save', async function () {
  if (!this.isModified('passwordHash')) {
    return;
  }

  // Seed scripts may provide pre-hashed passwords. Avoid hashing those again.
  if (BCRYPT_HASH_REGEX.test(this.passwordHash)) {
    return;
  }

  const salt = await bcrypt.genSalt(10);
  this.passwordHash = await bcrypt.hash(this.passwordHash, salt);
});

export default mongoose.model<IProfessor>('Professor', ProfessorSchema);