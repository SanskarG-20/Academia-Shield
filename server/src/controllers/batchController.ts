import { Request, Response } from 'express';
import Batch from '../models/Batch';
import Student from '../models/Student';

// @desc    Create a Batch
// @route   POST /api/batches
export const createBatch = async (req: Request | any, res: Response) => {
  const { name, code, department, year } = req.body;
  
  const batchExists = await Batch.findOne({ code });
  if (batchExists) {
    return res.status(400).json({ message: 'Batch code already exists' });
  }

  const batch = await Batch.create({
    name,
    code,
    department,
    year,
    professorId: req.user.id
  });

  res.status(201).json(batch);
};

// @desc    Get Professor's Batches
// @route   GET /api/batches
export const getBatches = async (req: Request | any, res: Response) => {
  const batches = await Batch.find({ professorId: req.user.id })
    .populate('students', 'name sapId rollNumber');
  res.json(batches);
};

// @desc    Join Batch (Student)
// @route   POST /api/batches/join
export const joinBatch = async (req: Request | any, res: Response) => {
  const { code } = req.body;
  const studentId = req.user.id;

  const batch = await Batch.findOne({ code });
  if (!batch) {
    return res.status(404).json({ message: 'Batch not found' });
  }

  // Check if already joined
  if (batch.students.includes(studentId)) {
    return res.status(400).json({ message: 'Already a member of this batch' });
  }

  batch.students.push(studentId);
  await batch.save();

  // Update student record
  await Student.findByIdAndUpdate(studentId, {
    $push: { joinedBatches: batch._id }
  });

  res.json({ message: `Successfully joined ${batch.name}` });
};