import express from 'express';
import { loginProfessor, requestOtp, verifyOtp, createStudentProfile } from '../controllers/authController';

const router = express.Router();

router.post('/professor/login', loginProfessor);
router.post('/student/request-otp', requestOtp);
router.post('/student/verify-otp', verifyOtp);
router.post('/student/profile', createStudentProfile);

export default router;