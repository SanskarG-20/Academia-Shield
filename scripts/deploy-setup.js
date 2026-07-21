#!/usr/bin/env node

/**
 * Academia Shield — Quick Deployment Setup
 * 
 * This script helps configure and prepare your project for deployment.
 * 
 * Usage:
 *   npm run deploy:setup
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

const question = (query) => new Promise(resolve => rl.question(query, resolve));

async function main() {
  console.log('\n🚀 Academia Shield — Deployment Configuration\n');

  // Prompt for values
  const vercelUrl = await question('Enter your Vercel frontend URL (e.g., https://myapp.vercel.app): ');
  const renderUrl = await question('Enter your Render API URL (e.g., https://academia-shield-api.onrender.com): ');
  const mongoUri = await question('Enter MongoDB Atlas connection string: ');
  const jwtSecret = await question('Enter JWT secret (min 32 chars): ');
  const emailUser = await question('Enter email for notifications (optional): ');
  const emailPass = await question('Enter email app password (optional): ');

  console.log('\n📝 Creating environment files...\n');

  // Create API .env.production
  const apiEnv = `NODE_ENV=production
PORT=5000
MONGODB_URI=${mongoUri}
JWT_SECRET=${jwtSecret}
EMAIL_USER=${emailUser}
EMAIL_PASS=${emailPass}
FRONTEND_URL=${vercelUrl}
`;

  fs.writeFileSync(path.join(__dirname, 'apps/api/.env.production'), apiEnv);
  console.log('✓ apps/api/.env.production');

  // Create web .env.production
  const webEnv = `VITE_API_URL=${renderUrl}
VITE_GEMINI_API_KEY=
`;

  fs.writeFileSync(path.join(__dirname, 'apps/web/.env.production'), webEnv);
  console.log('✓ apps/web/.env.production');

  // Create agent .env.production
  const agentEnv = `TEST_MODE=false
API_URL=${renderUrl}
POLL_INTERVAL=30
REQUEST_TIMEOUT=10
RETRY_ATTEMPTS=5
ENFORCEMENT_MODE=HOSTS
SOCKET_ENABLED=false
STUDENT_SAP_ID=
`;

  fs.writeFileSync(path.join(__dirname, 'services/agent/.env.production'), agentEnv);
  console.log('✓ services/agent/.env.production');

  console.log('\n✅ Environment files created!\n');
  console.log('📋 Next steps:\n');
  console.log('1. Build the project:');
  console.log('   npm run build\n');
  console.log('2. Deploy backend to Render:');
  console.log(`   URL: ${renderUrl}\n`);
  console.log('3. Deploy frontend to Vercel:');
  console.log(`   URL: ${vercelUrl}\n`);
  console.log('4. Bundle Python agent:');
  console.log('   cd services/agent && bash build_unix.sh  (macOS/Linux)\n');
  console.log('   cd services/agent && build_windows.bat   (Windows)\n');

  rl.close();
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
