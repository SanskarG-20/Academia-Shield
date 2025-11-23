import mongoose from 'mongoose';
import dotenv from 'dotenv';
import Professor from '../models/Professor';
import Batch from '../models/Batch';
import { connectDB } from '../config/db';

dotenv.config();

const seedData = async () => {
  await connectDB();

  await Professor.deleteMany({});
  await Batch.deleteMany({});

  const professor = await Professor.create({
    name: 'Dr. Alan Turing',
    email: 'admin@university.edu',
    passwordHash: 'password123', // Will be hashed by pre-save hook
    department: 'CSE',
    designation: 'Professor'
  });

  await Batch.create({
    name: 'CS-A (Algorithms)',
    code: 'ALG9X2',
    department: 'CSE',
    year: '3',
    professorId: professor._id
  });

  console.log('Data Seeded!');
  (process as any).exit();
};

seedData();