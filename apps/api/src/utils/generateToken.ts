import jwt, { SignOptions } from 'jsonwebtoken';

// S2 FIX: Accept optional expiresIn so temp tokens can have a shorter lifespan.
export const generateToken = (id: string, role: string, expiresIn: SignOptions['expiresIn'] = '30d', claims: Record<string, string> = {}) => {
  return jwt.sign({ ...claims, id, role }, process.env.JWT_SECRET as string, {
    expiresIn,
  });
};
