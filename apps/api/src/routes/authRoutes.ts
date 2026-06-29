import express from 'express';
import {
	loginProfessor,
	requestOtp,
	verifyOtp,
	createStudentProfile,
	getMe,
	updateMe,
} from '../controllers/authController';
import { protect } from '../middleware/auth';

const router = express.Router();

router.post('/professor/login', loginProfessor);
router.post('/student/request-otp', requestOtp);
router.post('/student/verify-otp', verifyOtp);
router.post('/student/profile', createStudentProfile);
router.get('/me', protect, getMe);
router.patch('/me', protect, updateMe);

export default router;