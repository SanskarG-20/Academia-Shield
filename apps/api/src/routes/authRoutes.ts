import express from 'express';
import {
	loginProfessor,
	requestOtp,
	verifyOtp,
	createStudentProfile,
	getMe,
	updateMe,
} from '../controllers/authController';
import { protect, authorize } from '../middleware/auth';

const router = express.Router();

router.post('/professor/login', loginProfessor);
router.post('/student/request-otp', requestOtp);
router.post('/student/verify-otp', verifyOtp);
router.post('/student/profile', protect, authorize('student_temp'), createStudentProfile);
router.get('/me', protect, getMe);
router.patch('/me', protect, updateMe);

export default router;