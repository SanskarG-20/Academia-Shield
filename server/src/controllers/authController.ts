import { Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import Professor from '../models/Professor';
import Student from '../models/Student';
import Otp from '../models/Otp';
import { generateToken } from '../utils/generateToken';
import { sendEmail } from '../utils/email';

// @desc    Auth Professor & Get Token
// @route   POST /api/auth/professor/login
export const loginProfessor = async (req: Request, res: Response) => {
  const { email, password } = req.body;
  const professor = await Professor.findOne({ email });

  if (professor && (await professor.matchPassword(password))) {
    res.json({
      _id: professor._id,
      name: professor.name,
      email: professor.email,
      role: 'professor',
      token: generateToken(professor._id as string, 'professor'),
    });
  } else {
    res.status(401).json({ message: 'Invalid email or password' });
  }
};

// @desc    Request OTP for Student
// @route   POST /api/auth/student/request-otp
export const requestOtp = async (req: Request, res: Response) => {
  const { sapId } = req.body;
  
  // In a real scenario, you might check if student exists first, 
  // but for this flow we might allow OTP to register/verify.
  // For now, let's assume student record is created during profile setup or seeded.
  
  const otpCode = Math.floor(100000 + Math.random() * 900000).toString();
  
  // Hash OTP or store raw (hashed recommended, raw for demo simplicity)
  const hashedOtp = await bcrypt.hash(otpCode, 10);

  // Save to DB
  await Otp.create({
    sapId,
    code: hashedOtp,
    expiresAt: new Date(Date.now() + 5 * 60 * 1000) // 5 mins
  });

  // Mock finding email (in prod, lookup student email)
  const studentEmail = `${sapId}@student.university.edu`; 

  await sendEmail(studentEmail, 'Your Login OTP', `Your OTP is: ${otpCode}`);

  res.json({ message: 'OTP sent successfully' });
};

// @desc    Verify OTP & Student Login
// @route   POST /api/auth/student/verify-otp
export const verifyOtp = async (req: Request, res: Response) => {
  const { sapId, otp } = req.body;

  // Find latest OTP
  const validOtp = await Otp.findOne({ sapId }).sort({ createdAt: -1 });

  if (!validOtp) {
    return res.status(400).json({ message: 'Invalid or expired OTP' });
  }

  const isMatch = await bcrypt.compare(otp, validOtp.code);
  if (!isMatch) {
    return res.status(400).json({ message: 'Invalid OTP code' });
  }

  // Check if student exists, else create placeholder or return info to setup profile
  let student = await Student.findOne({ sapId });
  
  if (!student) {
    // Return a flag indicating profile needs setup
    return res.json({
      message: 'OTP Verified',
      requiresProfileSetup: true,
      sapId,
      token: generateToken(sapId, 'student_temp') // Temp token for profile setup
    });
  }

  // Clean up used OTPs
  await Otp.deleteMany({ sapId });

  res.json({
    _id: student._id,
    name: student.name,
    sapId: student.sapId,
    role: 'student',
    token: generateToken(student._id as string, 'student'),
  });
};

// @desc    Complete Student Profile
// @route   POST /api/auth/student/profile
export const createStudentProfile = async (req: Request, res: Response) => {
  const { sapId, name, email, department, rollNumber, year } = req.body;
  
  const studentExists = await Student.findOne({ sapId });
  if (studentExists) {
    return res.status(400).json({ message: 'Student already exists' });
  }

  const student = await Student.create({
    sapId, name, email, department, rollNumber, year
  });

  if (student) {
    res.status(201).json({
      _id: student._id,
      name: student.name,
      sapId: student.sapId,
      role: 'student',
      token: generateToken(student._id as string, 'student')
    });
  } else {
    res.status(400).json({ message: 'Invalid student data' });
  }
};