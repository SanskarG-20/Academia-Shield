import { Request, Response } from 'express';
import mongoose from 'mongoose';
import Batch from '../models/Batch';
import Student from '../models/Student';
import { sendError, sendSuccess } from '../utils/apiResponse';

const normalizeDepartment = (value: unknown) => String(value || '').trim().toUpperCase();

const addStudentToBatch = async (batch: any, studentId: string, res: Response) => {
  const alreadyJoined = batch.students.some(
    (memberId: any) => memberId.toString() === studentId
  );

  if (alreadyJoined) {
    return sendError(res, 'Already a member of this batch', 400);
  }

  batch.students.push(studentId);
  await batch.save();

  await Student.findByIdAndUpdate(studentId, {
    $addToSet: { joinedBatches: batch._id },
  });

  return sendSuccess(res, batch, `Successfully joined ${batch.name}`);
};

// @desc    Create a Batch
// @route   POST /api/batches
export const createBatch = async (req: Request | any, res: Response) => {
  try {
    const { name, code, department, year } = req.body;

    if (!name || !code || !department || !year) {
      return sendError(res, 'name, code, department and year are required', 400);
    }

    const normalizedCode = String(code).toUpperCase();
    const batchExists = await Batch.findOne({ code: normalizedCode });
    if (batchExists) {
      return sendError(res, 'Batch code already exists', 400);
    }

    const batch = await Batch.create({
      name,
      code: normalizedCode,
      department: normalizeDepartment(department),
      year,
      professorId: req.user.id,
    });

    return sendSuccess(res, batch, 'Batch created successfully', 201);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to create batch', 500);
  }
};

// @desc    Get Professor's Batches
// @route   GET /api/batches
export const getBatches = async (req: Request | any, res: Response) => {
  try {
    const batches = await Batch.find({ professorId: req.user.id })
      .populate('students', 'name sapId rollNumber email department year')
      .sort({ createdAt: -1 });

    return sendSuccess(res, batches, 'Batches fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch batches', 500);
  }
};

// @desc    Join Batch (Student)
// @route   POST /api/batches/join
export const joinBatch = async (req: Request | any, res: Response) => {
  try {
    const { code } = req.body;
    const studentId = req.user.id;

    if (!code) {
      return sendError(res, 'Batch code is required', 400);
    }

    const batch = await Batch.findOne({ code: String(code).toUpperCase() });
    if (!batch) {
      return sendError(res, 'Batch not found', 404);
    }

    return addStudentToBatch(batch, studentId, res);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to join batch', 500);
  }
};

// @desc    Get unjoined batches matching the authenticated student's department
// @route   GET /api/batches/student/available
export const getAvailableBatches = async (req: Request | any, res: Response) => {
  try {
    const student = await Student.findById(req.user.id).select('department');
    if (!student) {
      return sendError(res, 'Student not found', 404);
    }

    // The department is always derived from the authenticated student record.
    // Do not accept a client-supplied department as an authorization filter.
    const batches = await Batch.find({
      department: normalizeDepartment(student.department),
      students: { $ne: student._id },
    })
      .select('_id name department year')
      .sort({ createdAt: -1 })
      .lean();

    return sendSuccess(res, batches, 'Available department batches fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch available batches', 500);
  }
};

// @desc    Join a discovered batch from the authenticated student's department
// @route   POST /api/batches/student/available/:id/join
export const joinAvailableBatch = async (req: Request | any, res: Response) => {
  try {
    if (!mongoose.isValidObjectId(req.params.id)) {
      return sendError(res, 'Invalid batch ID', 400);
    }

    const student = await Student.findById(req.user.id).select('department');
    if (!student) {
      return sendError(res, 'Student not found', 404);
    }

    const batch = await Batch.findById(req.params.id);
    if (!batch) {
      return sendError(res, 'Batch not found', 404);
    }

    if (normalizeDepartment(batch.department) !== normalizeDepartment(student.department)) {
      return sendError(res, 'This batch is not available for your department', 403);
    }

    return addStudentToBatch(batch, req.user.id, res);
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to join available batch', 500);
  }
};

// @desc    Get joined batches for the student
// @route   GET /api/batches/student/my
export const getMyBatches = async (req: Request | any, res: Response) => {
  try {
    const batches = await Batch.find({ students: req.user.id })
      .populate('students', 'name sapId rollNumber email department year')
      .sort({ createdAt: -1 });

    return sendSuccess(res, batches, 'Joined batches fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch joined batches', 500);
  }
};

// @desc    Get batch details by ID
// @route   GET /api/batches/:id
export const getBatchById = async (req: Request | any, res: Response) => {
  try {
    const batch = await Batch.findById(req.params.id).populate(
      'students',
      'name sapId rollNumber email department year'
    );

    if (!batch) {
      return sendError(res, 'Batch not found', 404);
    }

    const isProfessorOwner =
      req.user.role === 'professor' && batch.professorId.toString() === req.user.id;
    const isStudentMember =
      req.user.role === 'student' &&
      batch.students.some((member: any) => member._id.toString() === req.user.id);

    if (!isProfessorOwner && !isStudentMember) {
      return sendError(res, 'Not authorised to view this batch', 403);
    }

    return sendSuccess(res, batch, 'Batch details fetched successfully');
  } catch (err: any) {
    return sendError(res, err.message || 'Unable to fetch batch details', 500);
  }
};
