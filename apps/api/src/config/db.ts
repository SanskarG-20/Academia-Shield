import mongoose from 'mongoose';

export const connectDB = async () => {
  try {
    const conn = await mongoose.connect(
      process.env.MONGO_URI || 'mongodb://localhost:27017/academia-shield',
      { serverSelectionTimeoutMS: 5000 }
    );
    console.log(`✅ MongoDB Atlas connected: ${conn.connection.host}`);
  } catch (error: any) {
    console.error(`❌ MongoDB connection failed: ${error.message}`);
    process.exit(1);
  }
};