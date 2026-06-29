import 'dotenv/config';
import mongoose from 'mongoose';
import bcrypt from 'bcryptjs';
import Professor from '../models/Professor';
import Student from '../models/Student';
import Batch from '../models/Batch';
import Session from '../models/Session';
import Rule from '../models/Rule';
import Log from '../models/Log';
import Otp from '../models/Otp';
import { connectDB } from '../config/db';

const DEMO_EMAIL = 'demo@professor.com';
const DEMO_PASSWORD = 'password123';
const LEGACY_DEMO_EMAIL = 'dr.sharma@university.edu';
const DEMO_STUDENT_SAP_ID = '600000001234';

const run = async () => {
  try {
    await connectDB();
    console.log('🔗 Connected to MongoDB\n');

    // Remove current and legacy demo professor accounts before creating fresh demo data.
    await Professor.deleteMany({ email: { $in: [DEMO_EMAIL, LEGACY_DEMO_EMAIL] } });
    await Promise.all([
      Batch.deleteMany({ code: 'CE-SY-2024' }),
      Session.deleteMany({ title: 'Data Structures - Unit 3' }),
      Rule.deleteMany({ name: { $in: ['Social Media Block', 'Entertainment Block'] } }),
      Log.deleteMany({}),
      Otp.deleteMany({}),
      Student.deleteMany({ sapId: DEMO_STUDENT_SAP_ID }),
    ]);
    console.log('🧹 Cleared old demo records');

    // ─── STEP 1: Create Demo Professor ──────────────────────────────────────
    const hashed = await bcrypt.hash(DEMO_PASSWORD, 10);
    const professor = await Professor.create({
      name: 'Demo Professor',
      email: DEMO_EMAIL,
      passwordHash: hashed,
      department: 'Computer Engineering',
      designation: 'Professor',
    });
    console.log('✅ Demo professor created');

    // ─── STEP 2: Create Batch ────────────────────────────────────────────────
    const batch = await Batch.create({
      name: 'Computer Engineering - SY',
      code: 'CE-SY-2024',
      department: 'Computer Engineering',
      year: '2',
      professorId: professor._id,
      students: [],
    });
    console.log('✅ Batch created → CE-SY-2024');

    // ─── STEP 3: Create Rules ────────────────────────────────────────────────
    const [rule1] = await Rule.insertMany([
      {
        name: 'Social Media Block',
        mode: 'Blocklist',
        websites: ['youtube.com', 'instagram.com', 'reddit.com', 'twitter.com', 'facebook.com'],
        applications: ['Discord', 'Steam', 'Spotify'],
        professorId: professor._id,
      },
      {
        name: 'Entertainment Block',
        mode: 'Blocklist',
        websites: ['netflix.com', 'hotstar.com', 'primevideo.com', 'twitch.tv'],
        applications: ['VLC'],
        professorId: professor._id,
      },
    ]);
    console.log('✅ 2 Rules created');

    // ─── STEP 4: Create Session ──────────────────────────────────────────────
    const today = new Date();
    const startTime = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 10, 0, 0);
    const endTime   = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 11, 0, 0);

    await Session.create({
      title: 'Data Structures - Unit 3',
      course: 'Data Structures & Algorithms',
      type: 'Lecture',
      startTime,
      endTime,
      status: 'Upcoming',
      professorId: professor._id,
      ruleSetId: rule1._id,
      batchIds: [batch._id],
    });
    console.log('✅ Session created → Data Structures - Unit 3');

    // ─── STEP 5: Create Student ──────────────────────────────────────────────
    await Student.create({
      sapId: DEMO_STUDENT_SAP_ID,
      name: 'Demo Student',
      email: `${DEMO_STUDENT_SAP_ID}@student.university.edu`,
      department: 'Computer Engineering',
      rollNumber: 'A01',
      year: '2',
      joinedBatches: [batch._id],
    });
    console.log(`✅ Demo student created → SAP ID ${DEMO_STUDENT_SAP_ID}`);

    // ─── STEP 6: Summary ─────────────────────────────────────────────────────
    const pad = '━'.repeat(33);
    console.log(`\n${pad}`);
    console.log('🎓 ACADEMIA SHIELD — DEMO SEED COMPLETE');
    console.log(pad);
    console.log(`Login:    ${DEMO_EMAIL} / ${DEMO_PASSWORD}`);
    console.log('Batch:    CE-SY-2024');
    console.log('Rules:    Social Media Block, Entertainment Block');
    console.log(`Session:  Data Structures - Unit 3 (10:00–11:00, today)`);
    console.log(`${pad}\n`);

  } catch (err: any) {
    console.error('❌ Seed failed:', err.message);
    process.exitCode = 1;
  } finally {
    // ─── STEP 7: Close connection ─────────────────────────────────────────────
    if (mongoose.connection.readyState !== 0) {
      await mongoose.connection.close();
      console.log('🔌 DB connection closed.');
    }
  }
};

void run();
