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

const run = async () => {
  try {
    await mongoose.connect(
      process.env.MONGO_URI || 'mongodb://localhost:27017/academia-shield',
      { serverSelectionTimeoutMS: 5000 }
    );
    console.log('🔗 Connected to MongoDB\n');

    // ─── STEP 1: Clear existing data ────────────────────────────────────────
    await Promise.all([
      Professor.deleteMany({}),
      Student.deleteMany({}),
      Batch.deleteMany({}),
      Session.deleteMany({}),
      Rule.deleteMany({}),
      Log.deleteMany({}),
      Otp.deleteMany({}),
    ]);
    console.log('🗑️  Cleared existing data');

    // ─── STEP 2: Create Professor ────────────────────────────────────────────
    const passwordHash = await bcrypt.hash('demo1234', 10);
    const professor = await Professor.create({
      name: 'Dr. Sharma',
      email: 'dr.sharma@university.edu',
      passwordHash,
      department: 'Computer Engineering',
      designation: 'AP',
    });
    console.log('✅ Professor created → dr.sharma@university.edu / demo1234');

    // ─── STEP 3: Create Batch ────────────────────────────────────────────────
    const batch = await Batch.create({
      name: 'Computer Engineering - SY',
      code: 'CE-SY-2024',
      department: 'Computer Engineering',
      year: '2',
      professorId: professor._id,
      students: [],
    });
    console.log('✅ Batch created → CE-SY-2024');

    // ─── STEP 4: Create Rules ────────────────────────────────────────────────
    const [rule1, rule2] = await Rule.insertMany([
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

    // ─── STEP 5: Create Session ──────────────────────────────────────────────
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

    // ─── STEP 6: Summary ─────────────────────────────────────────────────────
    const pad = '━'.repeat(33);
    console.log(`\n${pad}`);
    console.log('🎓 ACADEMIA SHIELD — DEMO SEED COMPLETE');
    console.log(pad);
    console.log('Login:    dr.sharma@university.edu / demo1234');
    console.log('Batch:    CE-SY-2024');
    console.log('Rules:    Social Media Block, Entertainment Block');
    console.log(`Session:  Data Structures - Unit 3 (10:00–11:00, today)`);
    console.log(`${pad}\n`);

  } catch (err: any) {
    console.error('❌ Seed failed:', err.message);
    process.exit(1);
  } finally {
    // ─── STEP 7: Close connection ─────────────────────────────────────────────
    await mongoose.connection.close();
    console.log('🔌 DB connection closed.');
    process.exit(0);
  }
};

run();
