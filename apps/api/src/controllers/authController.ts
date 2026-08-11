import { Request, Response } from 'express';
import bcrypt from 'bcryptjs';
import Professor from '../models/Professor';
import Student from '../models/Student';
import Otp from '../models/Otp';
import { generateToken } from '../utils/generateToken';
import { sendEmail } from '../utils/email';
import { sendError, sendSuccess } from '../utils/apiResponse';

const SAP_ID_REGEX = /^\d{12}$/;
const OTP_REGEX = /^\d{6}$/;

const normalizeSapId = (value: unknown) =>
  typeof value === 'string' ? value.trim() : '';

const resolveMockOtp = () => {
  const configuredOtp = (process.env.MOCK_STUDENT_OTP || '123456').trim();
  return OTP_REGEX.test(configuredOtp) ? configuredOtp : '123456';
};

const createOtpRecord = async (sapId: string, plainOtp: string) => {
  const hashedOtp = await bcrypt.hash(plainOtp, 10);
  await Otp.deleteMany({ sapId });

  await Otp.create({
    sapId,
    code: hashedOtp,
    expiresAt: new Date(Date.now() + 5 * 60 * 1000),
  });
};

// @desc    Auth Professor & Get Token
// @route   POST /api/auth/professor/login
export const loginProfessor = async (req: Request, res: Response) => {
  try {
    const { email, password } = req.body;
    const normalizedEmail = typeof email === 'string' ? email.trim().toLowerCase() : '';

    if (!normalizedEmail || typeof password !== 'string') {
      return sendError(res, 'Email and password are required', 400);
    }

    let professor = await Professor.findOne({ email: normalizedEmail });

    if (!professor) {
      // Auto-register new professor
      professor = await Professor.create({
        email: normalizedEmail,
        passwordHash: password, // Model's pre-save hook will hash this
        name: 'New Faculty',
        department: 'Pending',
        designation: 'Pending'
      });

      return sendSuccess(
        res,
        {
          requiresProfileSetup: true,
          user: {
            _id: professor._id,
            name: professor.name,
            email: professor.email,
            department: professor.department,
            designation: professor.designation,
            role: 'professor',
          },
          token: generateToken(professor._id as unknown as string, 'professor'),
        },
        'Professor registered successfully'
      );
    }

    const storedHash = professor.passwordHash || '';

    if (process.env.NODE_ENV !== 'production') {
      console.log('Input:', password);
      console.log('Stored:', storedHash);
    }

    const isPasswordValid = await bcrypt.compare(password, storedHash);

    if (!isPasswordValid) {
      return sendError(res, 'Invalid email or password', 401);
    }

    return sendSuccess(
      res,
      {
        user: {
          _id: professor._id,
          name: professor.name,
          email: professor.email,
          department: professor.department,
          designation: professor.designation,
          role: 'professor',
        },
        token: generateToken(professor._id as unknown as string, 'professor'),
      },
      'Professor login successful'
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to login professor', 500);
  }
};

// @desc    Request OTP for Student
// @route   POST /api/auth/student/request-otp
export const requestOtp = async (req: Request, res: Response) => {
  try {
    const sapId = normalizeSapId(req.body?.sapId);

    if (!sapId) {
      return sendError(res, 'sapId is required', 400);
    }

    if (!SAP_ID_REGEX.test(sapId)) {
      return sendError(res, 'sapId must be exactly 12 digits', 400);
    }

    // 60-second rate limit
    const lastOtp = await Otp.findOne({ sapId }).sort({ createdAt: -1 });
    if (lastOtp && (lastOtp as any).createdAt && (lastOtp as any).createdAt.getTime() > Date.now() - 60000) {
      return sendError(res, 'Please wait 60 seconds before requesting another OTP', 429);
    }

    const otpMode = (process.env.STUDENT_OTP_MODE || 'mock').toLowerCase();
    const mockOtp = resolveMockOtp();
    const randomOtp = Math.floor(100000 + Math.random() * 900000).toString();
    const otpCode = otpMode === 'email' ? randomOtp : mockOtp;

    await createOtpRecord(sapId, otpCode);

    if (otpMode !== 'email') {
      console.log(`[MOCK OTP] sapId=${sapId} otp=${otpCode}`);
      return sendSuccess(
        res,
        { sapId, mockOtp: otpCode, otpMode: 'mock' },
        'Mock OTP generated successfully'
      );
    }

    const studentEmail = `${sapId}@student.university.edu`;
    try {
      await sendEmail(studentEmail, 'Your Login OTP', `Your OTP is: ${otpCode}`);

      return sendSuccess(res, { sapId, otpMode: 'email' }, 'OTP sent successfully');
    } catch (emailError: any) {
      // Fallback to mock OTP in case SMTP is unavailable during local demo/testing.
      await createOtpRecord(sapId, mockOtp);
      console.warn(`[OTP EMAIL FALLBACK] sapId=${sapId}: ${emailError.message}`);
      console.log(`[MOCK OTP] sapId=${sapId} otp=${mockOtp}`);

      return sendSuccess(
        res,
        { sapId, mockOtp, otpMode: 'mock' },
        'Email delivery failed. Mock OTP generated for demo login.'
      );
    }
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to send OTP', 500);
  }
};

// @desc    Verify OTP & Student Login
// @route   POST /api/auth/student/verify-otp
export const verifyOtp = async (req: Request, res: Response) => {
  try {
    const sapId = normalizeSapId(req.body?.sapId);
    const otp = typeof req.body?.otp === 'string' ? req.body.otp.trim() : '';

    if (!sapId || !otp) {
      return sendError(res, 'sapId and otp are required', 400);
    }

    if (!SAP_ID_REGEX.test(sapId)) {
      return sendError(res, 'sapId must be exactly 12 digits', 400);
    }

    if (!OTP_REGEX.test(otp)) {
      return sendError(res, 'otp must be exactly 6 digits', 400);
    }

    const validOtp = await Otp.findOne({ sapId }).sort({ createdAt: -1 });

    if (!validOtp || validOtp.expiresAt.getTime() < Date.now()) {
      return sendError(res, 'Invalid or expired OTP', 400);
    }

    const isMatch = await bcrypt.compare(otp, validOtp.code);
    if (!isMatch) {
      return sendError(res, 'Invalid OTP code', 400);
    }

    const student = await Student.findOne({ sapId });

    if (!student) {
      return sendSuccess(
        res,
        {
          requiresProfileSetup: true,
          sapId,
          token: generateToken(sapId, 'student_temp'),
        },
        'OTP verified'
      );
    }

    await Otp.deleteMany({ sapId });

    return sendSuccess(
      res,
      {
        user: {
          _id: student._id,
          name: student.name,
          sapId: student.sapId,
          email: student.email,
          department: student.department,
          rollNumber: student.rollNumber,
          year: student.year,
          role: 'student',
        },
        token: generateToken(student._id as unknown as string, 'student'),
      },
      'Student login successful'
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to verify OTP', 500);
  }
};

// @desc    Complete Student Profile
// @route   POST /api/auth/student/profile
export const createStudentProfile = async (req: Request, res: Response) => {
  try {
    const { name, email, department, rollNumber, year } = req.body;
    const sapId = normalizeSapId(req.body?.sapId);

    if (!sapId || !name || !email || !department || !rollNumber || !year) {
      return sendError(res, 'All student profile fields are required', 400);
    }

    if (!SAP_ID_REGEX.test(sapId)) {
      return sendError(res, 'sapId must be exactly 12 digits', 400);
    }

    const studentExists = await Student.findOne({ sapId });
    if (studentExists) {
      return sendError(res, 'Student already exists', 400);
    }

    const student = await Student.create({
      sapId,
      name,
      email,
      department,
      rollNumber,
      year,
    });

    return sendSuccess(
      res,
      {
        user: {
          _id: student._id,
          name: student.name,
          sapId: student.sapId,
          email: student.email,
          department: student.department,
          rollNumber: student.rollNumber,
          year: student.year,
          role: 'student',
        },
        token: generateToken(student._id as unknown as string, 'student'),
      },
      'Student profile created successfully',
      201
    );
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to create student profile', 500);
  }
};

// @desc    Get current authenticated user profile
// @route   GET /api/auth/me
export const getMe = async (req: Request | any, res: Response) => {
  try {
    if (req.user.role === 'professor') {
      const professor = await Professor.findById(req.user.id).select('-passwordHash');
      if (!professor) {
        return sendError(res, 'Professor not found', 404);
      }

      return sendSuccess(
        res,
        {
          _id: professor._id,
          name: professor.name,
          email: professor.email,
          department: professor.department,
          designation: professor.designation,
          role: 'professor',
        },
        'Profile fetched successfully'
      );
    }

    if (req.user.role === 'student') {
      const student = await Student.findById(req.user.id).populate(
        'joinedBatches',
        'name code department year students'
      );
      if (!student) {
        return sendError(res, 'Student not found', 404);
      }

      return sendSuccess(
        res,
        {
          _id: student._id,
          sapId: student.sapId,
          name: student.name,
          email: student.email,
          department: student.department,
          rollNumber: student.rollNumber,
          year: student.year,
          joinedBatches: student.joinedBatches,
          role: 'student',
        },
        'Profile fetched successfully'
      );
    }

    return sendError(res, 'Profile is not available for this role', 403);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch profile', 500);
  }
};

// @desc    Update current authenticated user profile
// @route   PATCH /api/auth/me
export const updateMe = async (req: Request | any, res: Response) => {
  try {
    if (req.user.role === 'professor') {
      const professor = await Professor.findById(req.user.id);
      if (!professor) {
        return sendError(res, 'Professor not found', 404);
      }

      const { name, department, designation } = req.body;
      if (name) professor.name = name;
      if (department) professor.department = department;
      if (designation) professor.designation = designation;

      await professor.save();

      return sendSuccess(
        res,
        {
          _id: professor._id,
          name: professor.name,
          email: professor.email,
          department: professor.department,
          designation: professor.designation,
          role: 'professor',
        },
        'Professor profile updated successfully'
      );
    }

    if (req.user.role === 'student') {
      const student = await Student.findById(req.user.id);
      if (!student) {
        return sendError(res, 'Student not found', 404);
      }

      const { name, email, department, rollNumber, year } = req.body;
      if (name) student.name = name;
      if (email) student.email = email;
      if (department) student.department = department;
      if (rollNumber) student.rollNumber = rollNumber;
      if (year) student.year = year;

      await student.save();

      return sendSuccess(
        res,
        {
          _id: student._id,
          sapId: student.sapId,
          name: student.name,
          email: student.email,
          department: student.department,
          rollNumber: student.rollNumber,
          year: student.year,
          role: 'student',
        },
        'Student profile updated successfully'
      );
    }

    return sendError(res, 'Profile update is not available for this role', 403);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to update profile', 500);
  }
};